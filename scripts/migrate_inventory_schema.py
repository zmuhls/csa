#!/usr/bin/env python3
"""
Migrate existing inventory CSV to include new artifact collation columns.

New columns added:
- artifact_link_type: session_default, visual_match, content_overlap, manual_curation
- artifact_confidence: 0.0-1.0 confidence score for grouping
- needs_review: boolean flag for human review queue
- parent_artifact_id: for hierarchical groupings (e.g., volume -> pages)
"""
import csv
from pathlib import Path

IN_CSV = Path('csv/images_inventory_labeled.csv')
OUT_CSV = Path('csv/images_inventory_labeled.csv')  # overwrite in place
BACKUP_CSV = Path('csv/images_inventory_labeled.backup.csv')

NEW_COLUMNS = [
    ('artifact_link_type', 'session_default'),
    ('artifact_confidence', ''),
    ('needs_review', 'False'),
    ('parent_artifact_id', ''),
]


def main():
    if not IN_CSV.exists():
        print(f"Input file not found: {IN_CSV}")
        return

    # Read existing data
    with IN_CSV.open() as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    # Check if migration is needed
    new_cols_to_add = [(col, default) for col, default in NEW_COLUMNS if col not in fieldnames]
    if not new_cols_to_add:
        print("All new columns already exist. No migration needed.")
        return

    # Create backup
    BACKUP_CSV.write_text(IN_CSV.read_text())
    print(f"Created backup at {BACKUP_CSV}")

    # Find insertion point (after artifact_group_id)
    try:
        insert_idx = fieldnames.index('artifact_group_id') + 1
    except ValueError:
        insert_idx = len(fieldnames)

    # Insert new columns
    for col, default in reversed(new_cols_to_add):
        fieldnames.insert(insert_idx, col)
        print(f"Adding column: {col} (default: '{default}')")

    # Update rows with defaults
    for row in rows:
        for col, default in new_cols_to_add:
            if col not in row or not row[col]:
                row[col] = default

    # Write updated CSV
    with OUT_CSV.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Migrated {len(rows)} rows to {OUT_CSV}")
    print(f"New schema has {len(fieldnames)} columns")


if __name__ == '__main__':
    main()
