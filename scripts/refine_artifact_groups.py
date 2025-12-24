#!/usr/bin/env python3
"""
Refine artifact groupings using text similarity analysis.

This script analyzes OCR outputs to detect content overlap between images,
suggesting grouping refinements beyond the default session-based assignments.

Outputs:
- Updated csv/images_inventory_labeled.csv with refined groupings
- csv/artifact_review_queue.csv for ambiguous groupings needing human review
"""

import csv
import json
import re
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Tuple

INVENTORY_CSV = Path('csv/images_inventory_labeled.csv')
OCR_TEXT_DIR = Path('output/ocr/text')
REVIEW_QUEUE_CSV = Path('csv/artifact_review_queue.csv')

# Thresholds for content analysis
HIGH_SIMILARITY = 0.85  # Likely same document (duplicate or same page)
MEDIUM_SIMILARITY = 0.40  # Related content (same artifact, different pages)
LOW_SIMILARITY = 0.15  # Possibly related (review recommended)


def load_inventory() -> List[Dict]:
    """Load labeled inventory as list of rows."""
    with INVENTORY_CSV.open() as f:
        reader = csv.DictReader(f)
        return list(reader)


def save_inventory(rows: List[Dict], fieldnames: List[str]) -> None:
    """Save updated inventory."""
    with INVENTORY_CSV.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def get_ocr_text(img_id: str, inventory_row: Dict) -> str:
    """Load OCR text for an image, trying multiple filename patterns."""
    # Try inventory filename first
    filename = inventory_row.get('filename', '')
    stem = Path(filename).stem if filename else ''

    patterns = [
        f"{stem}.txt",
        f"{img_id}.txt",
        f"{img_id.upper().replace('IMG_', 'IMG_')}.txt",
    ]

    for pattern in patterns:
        text_path = OCR_TEXT_DIR / pattern
        if text_path.exists():
            return text_path.read_text(encoding='utf-8')

    return ""


def text_similarity(text1: str, text2: str) -> float:
    """Calculate similarity ratio between two texts."""
    if not text1 or not text2:
        return 0.0
    # Normalize whitespace
    t1 = ' '.join(text1.split())
    t2 = ' '.join(text2.split())
    if not t1 or not t2:
        return 0.0
    return SequenceMatcher(None, t1, t2).ratio()


def analyze_session_content(
    session_rows: List[Dict],
    all_texts: Dict[str, str]
) -> List[Tuple[str, str, float]]:
    """
    Analyze text similarity within a session.
    Returns list of (img_id1, img_id2, similarity) tuples.
    """
    similarities = []
    ids = [r['id'] for r in session_rows]

    for i, id1 in enumerate(ids):
        for id2 in ids[i+1:]:
            t1 = all_texts.get(id1, '')
            t2 = all_texts.get(id2, '')
            if t1 and t2:
                sim = text_similarity(t1, t2)
                if sim > LOW_SIMILARITY:
                    similarities.append((id1, id2, sim))

    return similarities


def find_content_groups(
    similarities: List[Tuple[str, str, float]],
    threshold: float = MEDIUM_SIMILARITY
) -> Dict[str, List[str]]:
    """
    Cluster images into content groups based on similarity.
    Uses union-find to build connected components.
    """
    # Build graph of related images
    parent = {}

    def find(x):
        if x not in parent:
            parent[x] = x
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    # Connect images with similarity above threshold
    for id1, id2, sim in similarities:
        if sim >= threshold:
            union(id1, id2)

    # Collect groups
    groups = defaultdict(list)
    for img_id in parent:
        root = find(img_id)
        groups[root].append(img_id)

    return dict(groups)


def calculate_group_confidence(
    group_ids: List[str],
    all_texts: Dict[str, str],
    similarities: List[Tuple[str, str, float]]
) -> float:
    """
    Calculate confidence score for a grouping.
    Higher = more confident the grouping is correct.
    """
    if len(group_ids) <= 1:
        return 1.0

    # Get all similarities within this group
    group_sims = [
        sim for id1, id2, sim in similarities
        if id1 in group_ids and id2 in group_ids
    ]

    if not group_sims:
        return 0.5  # No similarity data, uncertain

    avg_sim = sum(group_sims) / len(group_sims)
    min_sim = min(group_sims)

    # High avg + high min = confident
    # Low min = some outliers, less confident
    confidence = (avg_sim * 0.7 + min_sim * 0.3)

    return round(confidence, 3)


def main():
    print("Loading inventory...")
    rows = load_inventory()
    fieldnames = list(rows[0].keys()) if rows else []

    # Build lookup by ID
    rows_by_id = {r['id']: r for r in rows}

    # Group by session
    sessions = defaultdict(list)
    for row in rows:
        session_id = row.get('session_group_id', '')
        if session_id:
            sessions[session_id].append(row)

    print(f"Found {len(sessions)} sessions across {len(rows)} images")

    # Load all OCR texts
    print("Loading OCR texts...")
    all_texts = {}
    for row in rows:
        text = get_ocr_text(row['id'], row)
        if text:
            all_texts[row['id']] = text

    print(f"Loaded {len(all_texts)} OCR texts")

    # Analyze each session
    all_similarities = []
    for session_id, session_rows in sessions.items():
        sims = analyze_session_content(session_rows, all_texts)
        all_similarities.extend(sims)

    print(f"Computed {len(all_similarities)} similarity pairs above threshold")

    # Find content groups
    content_groups = find_content_groups(all_similarities, MEDIUM_SIMILARITY)
    print(f"Identified {len(content_groups)} content-based groups")

    # Prepare review queue
    review_items = []

    # Update inventory with refined groupings
    group_counter = 0
    assigned_groups = {}  # img_id -> new artifact_group_id

    for root_id, member_ids in content_groups.items():
        if len(member_ids) > 1:
            # Multi-image group detected via content
            group_counter += 1
            new_group_id = f"CG{group_counter:04d}"

            confidence = calculate_group_confidence(
                member_ids, all_texts, all_similarities
            )

            # Determine if needs review
            needs_review = confidence < 0.6 or len(member_ids) > 5

            for img_id in member_ids:
                assigned_groups[img_id] = (new_group_id, confidence, needs_review)

                if needs_review:
                    row = rows_by_id.get(img_id, {})
                    review_items.append({
                        'id': img_id,
                        'proposed_group': new_group_id,
                        'current_group': row.get('artifact_group_id', ''),
                        'session_group': row.get('session_group_id', ''),
                        'confidence': confidence,
                        'reason': 'low_confidence' if confidence < 0.6 else 'large_group',
                        'group_size': len(member_ids),
                        'subject': row.get('subject', ''),
                    })

    # Update rows
    updates = 0
    for row in rows:
        img_id = row['id']
        if img_id in assigned_groups:
            new_group, confidence, needs_review = assigned_groups[img_id]

            # Only update if different from current
            if row.get('artifact_group_id') != new_group:
                row['artifact_group_id'] = new_group
                row['artifact_link_type'] = 'content_overlap'
                row['artifact_confidence'] = str(confidence)
                row['needs_review'] = str(needs_review)
                updates += 1
        else:
            # Keep existing, but update link type if still default
            if row.get('artifact_link_type') == 'session_default':
                row['artifact_confidence'] = '0.5'  # Uncertain, no content match

    # Save updated inventory
    save_inventory(rows, fieldnames)
    print(f"\nUpdated {updates} rows in inventory")

    # Write review queue
    if review_items:
        REVIEW_QUEUE_CSV.parent.mkdir(parents=True, exist_ok=True)
        review_fields = [
            'id', 'proposed_group', 'current_group', 'session_group',
            'confidence', 'reason', 'group_size', 'subject'
        ]
        with REVIEW_QUEUE_CSV.open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=review_fields)
            writer.writeheader()
            writer.writerows(review_items)
        print(f"Wrote {len(review_items)} items to review queue: {REVIEW_QUEUE_CSV}")
    else:
        print("No items flagged for review")

    # Summary stats
    print("\n--- Summary ---")
    print(f"Content-based groups created: {group_counter}")
    print(f"Images with content overlap: {len(assigned_groups)}")
    print(f"Items needing review: {len(review_items)}")


if __name__ == '__main__':
    main()
