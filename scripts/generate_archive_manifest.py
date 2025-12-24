#!/usr/bin/env python3
"""
Generate a comprehensive archive manifest from consolidated artifacts.
Creates a JSON catalog with metadata for all artifacts.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List

ARCHIVE_DIR = Path('output/archive')
DOCUMENTS_DIR = ARCHIVE_DIR / 'documents'
RESEARCH_DIR = ARCHIVE_DIR / 'research'
MANIFEST_PATH = ARCHIVE_DIR / 'manifest.json'


def load_artifact_metadata(artifact_dir: Path) -> Dict:
    """Load metadata for a single artifact."""
    meta_path = artifact_dir / 'metadata.json'
    if not meta_path.exists():
        return {}

    with meta_path.open() as f:
        meta = json.load(f)

    # Add transcription stats
    text_path = artifact_dir / 'transcription.txt'
    if text_path.exists():
        text = text_path.read_text(encoding='utf-8')
        meta['transcription_length'] = len(text)
        meta['word_count'] = len(text.split())
    else:
        meta['transcription_length'] = 0
        meta['word_count'] = 0

    return meta


def scan_collection(base_dir: Path, collection_type: str) -> List[Dict]:
    """Scan a collection directory for artifacts."""
    artifacts = []

    if not base_dir.exists():
        return artifacts

    for artifact_dir in sorted(base_dir.iterdir()):
        if artifact_dir.is_dir():
            meta = load_artifact_metadata(artifact_dir)
            if meta:
                meta['collection'] = collection_type
                meta['path'] = str(artifact_dir.relative_to(ARCHIVE_DIR))
                artifacts.append(meta)

    return artifacts


def generate_summary(artifacts: List[Dict]) -> Dict:
    """Generate summary statistics."""
    documents = [a for a in artifacts if a.get('collection') == 'documents']
    research = [a for a in artifacts if a.get('collection') == 'research']

    total_words = sum(a.get('word_count', 0) for a in artifacts)
    total_pages = sum(a.get('unique_pages', 1) for a in artifacts)
    total_images = sum(len(a.get('source_images', [])) for a in artifacts)
    culled = sum(a.get('duplicate_pages_culled', 0) for a in artifacts)

    # Item type distribution
    item_types = {}
    for a in artifacts:
        it = a.get('item_type') or 'unknown'
        item_types[it] = item_types.get(it, 0) + 1

    # Location distribution
    locations = {}
    for a in artifacts:
        loc = a.get('location_guess')
        if loc:
            # Extract primary location
            primary = loc.split('(')[0].strip().split(',')[0].strip()
            if primary:
                locations[primary] = locations.get(primary, 0) + 1

    return {
        'total_artifacts': len(artifacts),
        'documents': len(documents),
        'research_sources': len(research),
        'total_source_images': total_images,
        'unique_pages': total_pages,
        'duplicate_pages_culled': culled,
        'total_words': total_words,
        'item_type_distribution': item_types,
        'location_distribution': locations
    }


def main():
    print("Scanning archive for artifacts...")

    # Collect all artifacts
    documents = scan_collection(DOCUMENTS_DIR, 'documents')
    research = scan_collection(RESEARCH_DIR, 'research')
    all_artifacts = documents + research

    if not all_artifacts:
        print("No artifacts found. Run consolidate_artifacts.py first.")
        return

    # Generate summary
    summary = generate_summary(all_artifacts)

    # Build manifest
    manifest = {
        'generated_at': datetime.now().isoformat(),
        'archive_version': '1.0',
        'summary': summary,
        'artifacts': all_artifacts
    }

    # Write manifest
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    with MANIFEST_PATH.open('w') as f:
        json.dump(manifest, f, indent=2)

    print(f"\nManifest generated: {MANIFEST_PATH}")
    print(f"\nArchive Summary:")
    print(f"  Total artifacts: {summary['total_artifacts']}")
    print(f"  Documents: {summary['documents']}")
    print(f"  Research sources: {summary['research_sources']}")
    print(f"  Source images: {summary['total_source_images']}")
    print(f"  Unique pages: {summary['unique_pages']}")
    print(f"  Duplicates culled: {summary['duplicate_pages_culled']}")
    print(f"  Total words: {summary['total_words']:,}")

    print(f"\nItem Types:")
    for it, count in sorted(summary['item_type_distribution'].items(), key=lambda x: -x[1]):
        print(f"  {it}: {count}")

    if summary['location_distribution']:
        print(f"\nLocations:")
        for loc, count in sorted(summary['location_distribution'].items(), key=lambda x: -x[1])[:10]:
            print(f"  {loc}: {count}")


if __name__ == '__main__':
    main()
