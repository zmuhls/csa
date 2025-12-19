#!/usr/bin/env python3
import csv
from pathlib import Path

IN_CSV = Path('csv/images_inventory_labeled.csv')
OUT_TMP = Path('csv/.images_inventory_labeled.tmp.csv')


def prefer(a: dict, b: dict) -> dict:
    # Prefer the row that looks more curated
    def score(r: dict) -> int:
        s = 0
        if r.get('duplicate_of') in (None, ''):
            s += 2
        if r.get('item_type'):
            s += 2
        if r.get('subject'):
            s += 1
        if r.get('location_guess'):
            s += 1
        return s
    return a if score(a) >= score(b) else b


def main():
    with IN_CSV.open() as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        keep_by_digest = {}
        count_in = 0
        for row in reader:
            count_in += 1
            digest = row.get('sha256') or ''
            if not digest:
                # Fallback to relative path if no digest (should not happen)
                digest = row.get('relative_path')
            if digest in keep_by_digest:
                keep_by_digest[digest] = prefer(keep_by_digest[digest], row)
            else:
                keep_by_digest[digest] = row

    rows = list(keep_by_digest.values())
    rows.sort(key=lambda r: r.get('id'))

    with OUT_TMP.open('w', newline='') as f_out:
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    # Replace original
    OUT_TMP.replace(IN_CSV)
    print(f"Deduped {count_in} -> {len(rows)} rows in {IN_CSV}")


if __name__ == '__main__':
    main()

