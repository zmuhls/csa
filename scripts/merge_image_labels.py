#!/usr/bin/env python3
import csv
import json
from pathlib import Path

IN_CSV = Path('csv/images_inventory.csv')
IN_RESP = Path('prompts/images_label_responses.jsonl')
OUT_CSV = Path('csv/images_inventory_labeled.csv')


def load_responses(path: Path):
    out = {}
    if not path.exists():
        return out
    with path.open() as f:
        for line in f:
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
                rid = obj.get('id')
                if rid:
                    out[rid] = obj
            except Exception:
                continue
    return out


def main():
    resp = load_responses(IN_RESP)
    with IN_CSV.open() as f_in, OUT_CSV.open('w', newline='') as f_out:
        reader = csv.DictReader(f_in)
        fieldnames = reader.fieldnames or []
        # Ensure curation fields exist
        for extra in [
            'artifact_group_id', 'artifact_link_type', 'artifact_confidence',
            'needs_review', 'parent_artifact_id', 'item_type', 'subject',
            'location_guess', 'notes'
        ]:
            if extra not in fieldnames:
                fieldnames.append(extra)
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()
        for row in reader:
            # Set defaults for new artifact collation fields
            if not row.get('artifact_link_type'):
                row['artifact_link_type'] = 'session_default'
            if not row.get('artifact_confidence'):
                row['artifact_confidence'] = ''
            if not row.get('needs_review'):
                row['needs_review'] = 'False'
            if not row.get('parent_artifact_id'):
                row['parent_artifact_id'] = ''

            r = resp.get(row['id'])
            if r:
                for k in ['item_type', 'subject', 'location_guess', 'artifact_group_id', 'notes']:
                    v = r.get(k)
                    if v is not None:
                        row[k] = v
            writer.writerow(row)
    print(f"Merged labels into {OUT_CSV}")


if __name__ == '__main__':
    main()

