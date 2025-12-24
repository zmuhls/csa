#!/usr/bin/env python3
"""
Consolidate OCR outputs by artifact_group_id.
- Merges sequential pages within artifact groups
- Culls duplicate transcriptions via text similarity
- Routes research sources to separate folder
"""

import csv
import json
import re
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Tuple

INVENTORY_CSV = Path('csv/images_inventory_labeled.csv')
OCR_TEXT_DIR = Path('output/ocr/text')
OCR_META_DIR = Path('output/ocr/metadata')
ARCHIVE_DIR = Path('output/archive')
DOCUMENTS_DIR = ARCHIVE_DIR / 'documents'
RESEARCH_DIR = ARCHIVE_DIR / 'research'

# Keywords indicating research notes (not primary documents)
RESEARCH_KEYWORDS = [
    'research', 'notes', 'reference', 'handwritten notes',
    'biographical', 'preparatory', 'list of names'
]

SIMILARITY_THRESHOLD = 0.85  # Above this = duplicate content

# Link types that indicate confident groupings
CONFIDENT_LINK_TYPES = {'content_overlap', 'visual_match', 'manual_curation'}


def load_inventory(skip_needs_review: bool = False) -> Dict[str, Dict]:
    """Load labeled inventory, keyed by image ID.

    Args:
        skip_needs_review: If True, exclude items flagged for human review.
    """
    inventory = {}
    with INVENTORY_CSV.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Optionally skip items needing review
            if skip_needs_review and row.get('needs_review', '').lower() == 'true':
                continue
            inventory[row['id']] = row
    return inventory


def load_ocr_result(img_id: str) -> Tuple[str, Dict]:
    """Load OCR text and metadata for an image."""
    # Try different filename patterns
    patterns = [
        f"{img_id}.txt",
        f"{img_id.replace('img_', 'IMG_')}.txt",
    ]

    text = ""
    meta = {}

    for pattern in patterns:
        text_path = OCR_TEXT_DIR / pattern
        if text_path.exists():
            text = text_path.read_text(encoding='utf-8')
            break

    # Also check for files matching the original image filename
    # The OCR might use the original filename stem

    meta_patterns = [p.replace('.txt', '.json') for p in patterns]
    for pattern in meta_patterns:
        meta_path = OCR_META_DIR / pattern
        if meta_path.exists():
            with meta_path.open() as f:
                meta = json.load(f)
            break

    return text, meta


def text_similarity(text1: str, text2: str) -> float:
    """Calculate similarity ratio between two texts."""
    if not text1 or not text2:
        return 0.0
    # Normalize whitespace
    t1 = ' '.join(text1.split())
    t2 = ' '.join(text2.split())
    return SequenceMatcher(None, t1, t2).ratio()


def is_research_source(row: Dict) -> bool:
    """Check if an image is a research source based on subject/notes."""
    subject = (row.get('subject') or '').lower()
    notes = (row.get('notes') or '').lower()
    combined = subject + ' ' + notes

    return any(kw in combined for kw in RESEARCH_KEYWORDS)


def group_by_artifact(inventory: Dict[str, Dict]) -> Dict[str, List[str]]:
    """Group image IDs by artifact_group_id."""
    groups = defaultdict(list)
    for img_id, row in inventory.items():
        ag_id = row.get('artifact_group_id') or img_id  # Fallback to image ID
        groups[ag_id].append(img_id)

    # Sort images within each group by session_index or ID
    for ag_id in groups:
        groups[ag_id].sort(key=lambda x: (
            int(inventory[x].get('session_index') or 0),
            x
        ))

    return dict(groups)


def consolidate_group(
    ag_id: str,
    img_ids: List[str],
    inventory: Dict[str, Dict]
) -> Dict:
    """
    Consolidate a single artifact group.
    Returns metadata about the consolidated artifact.
    """
    texts = []
    metas = []
    confidences = []

    for img_id in img_ids:
        text, meta = load_ocr_result(img_id)
        texts.append(text)
        metas.append(meta)
        if meta.get('confidence'):
            confidences.append(meta['confidence'])

    # Detect and remove duplicates
    unique_texts = []
    unique_indices = []

    for i, text in enumerate(texts):
        is_dup = False
        for j in unique_indices:
            if text_similarity(text, texts[j]) > SIMILARITY_THRESHOLD:
                is_dup = True
                # Keep the one with higher confidence
                if metas[i].get('confidence', 0) > metas[j].get('confidence', 0):
                    # Replace with better version
                    idx = unique_indices.index(j)
                    unique_indices[idx] = i
                    unique_texts[idx] = text
                break

        if not is_dup and text.strip():
            unique_texts.append(text)
            unique_indices.append(i)

    # Merge unique texts
    merged_text = '\n\n---\n\n'.join(unique_texts) if len(unique_texts) > 1 else (unique_texts[0] if unique_texts else '')

    # Get representative metadata from first image
    first_row = inventory.get(img_ids[0], {})

    # Get link type info for group quality assessment
    link_types = [inventory[img_id].get('artifact_link_type', 'session_default') for img_id in img_ids]
    confident_links = sum(1 for lt in link_types if lt in CONFIDENT_LINK_TYPES)
    group_confidence = float(first_row.get('artifact_confidence') or 0.5)

    return {
        'artifact_group_id': ag_id,
        'source_images': img_ids,
        'unique_pages': len(unique_texts),
        'duplicate_pages_culled': len(texts) - len(unique_texts),
        'merged_text': merged_text,
        'item_type': first_row.get('item_type'),
        'subject': first_row.get('subject'),
        'location_guess': first_row.get('location_guess'),
        'notes': first_row.get('notes'),
        'average_confidence': sum(confidences) / len(confidences) if confidences else 0.0,
        'group_confidence': group_confidence,
        'link_types': list(set(link_types)),
        'confident_link_ratio': confident_links / len(img_ids) if img_ids else 0.0,
        'is_research': is_research_source(first_row)
    }


def write_artifact(artifact: Dict, output_dir: Path) -> None:
    """Write consolidated artifact to disk."""
    ag_dir = output_dir / artifact['artifact_group_id']
    ag_dir.mkdir(parents=True, exist_ok=True)

    # Write transcription
    (ag_dir / 'transcription.txt').write_text(
        artifact['merged_text'],
        encoding='utf-8'
    )

    # Write source images list
    with (ag_dir / 'source_images.json').open('w') as f:
        json.dump(artifact['source_images'], f, indent=2)

    # Write metadata
    meta = {k: v for k, v in artifact.items() if k != 'merged_text'}
    with (ag_dir / 'metadata.json').open('w') as f:
        json.dump(meta, f, indent=2)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Consolidate OCR outputs by artifact group')
    parser.add_argument('--skip-review', action='store_true',
                        help='Skip items flagged for human review')
    parser.add_argument('--confident-only', action='store_true',
                        help='Only consolidate groups with confident link types')
    args = parser.parse_args()

    # Setup directories
    DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
    RESEARCH_DIR.mkdir(parents=True, exist_ok=True)

    # Load data
    inventory = load_inventory(skip_needs_review=args.skip_review)
    groups = group_by_artifact(inventory)

    print(f"Found {len(groups)} artifact groups from {len(inventory)} images")
    if args.skip_review:
        print("  (skipping items flagged for review)")

    stats = {
        'total_groups': len(groups),
        'documents': 0,
        'research': 0,
        'total_pages_culled': 0,
        'confident_groups': 0,
        'session_default_groups': 0,
    }

    for ag_id, img_ids in groups.items():
        artifact = consolidate_group(ag_id, img_ids, inventory)

        # Track link type stats
        if artifact['confident_link_ratio'] > 0.5:
            stats['confident_groups'] += 1
        if 'session_default' in artifact['link_types'] and len(artifact['link_types']) == 1:
            stats['session_default_groups'] += 1

        # Optionally skip non-confident groups
        if args.confident_only and artifact['confident_link_ratio'] < 0.5:
            continue

        # Route to appropriate directory
        if artifact['is_research']:
            write_artifact(artifact, RESEARCH_DIR)
            stats['research'] += 1
        else:
            write_artifact(artifact, DOCUMENTS_DIR)
            stats['documents'] += 1

        stats['total_pages_culled'] += artifact['duplicate_pages_culled']

    print(f"\nConsolidation complete:")
    print(f"  Documents: {stats['documents']}")
    print(f"  Research sources: {stats['research']}")
    print(f"  Duplicate pages culled: {stats['total_pages_culled']}")
    print(f"  Groups with confident links: {stats['confident_groups']}")
    print(f"  Session-default only groups: {stats['session_default_groups']}")
    print(f"\nOutput: {ARCHIVE_DIR}")


if __name__ == '__main__':
    main()
