#!/usr/bin/env python3
import csv
import hashlib
import os
import re
import subprocess
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

IMG_ROOT = Path('raw/imgs')
OUT_CSV = Path('csv/images_inventory.csv')


def run_sips_all(path: Path) -> Dict[str, str]:
    """Run `sips -g all` and return a dict of reported keys."""
    try:
        proc = subprocess.run(
            ["sips", "-g", "all", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        out = proc.stdout.splitlines()
        meta: Dict[str, str] = {}
        for line in out[1:]:  # first line is the file path
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        return meta
    except Exception:
        return {}


def sha256_of_file(path: Path, bufsize: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            chunk = f.read(bufsize)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def parse_creation_dt(meta: Dict[str, str], path: Path) -> Tuple[Optional[datetime], str]:
    # sips uses EXIF-like format: YYYY:MM:DD HH:MM:SS
    raw = meta.get('creation', '')
    if raw:
        try:
            return datetime.strptime(raw, "%Y:%m:%d %H:%M:%S"), raw
        except Exception:
            pass
    # Fallback to filesystem times
    try:
        st = path.stat()
        # macOS provides st_birthtime
        birth = getattr(st, 'st_birthtime', None)
        if birth:
            dt = datetime.fromtimestamp(birth)
            return dt, dt.isoformat(sep=' ', timespec='seconds')
        # fallback to mtime
        dt = datetime.fromtimestamp(st.st_mtime)
        return dt, dt.isoformat(sep=' ', timespec='seconds')
    except Exception:
        return None, ''


def filename_duplicate_hint(name: str) -> bool:
    # Matches patterns like "IMG_3323 2.jpeg" (space + small integer before extension)
    return bool(re.search(r" \d+(?=\.[^.]+$)", name))


def extract_img_number(stem: str) -> Optional[int]:
    # Try common iPhone naming: IMG_1234
    m = re.search(r"IMG[_-](\d{3,6})", stem, flags=re.IGNORECASE)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            return None
    return None


@dataclass
class ImageRow:
    id: str
    relative_path: str
    filename: str
    extension: str
    size_bytes: int
    sha256: str
    width_px: Optional[int]
    height_px: Optional[int]
    camera_make: str
    camera_model: str
    exif_creation: str
    file_birthtime: str
    file_mtime: str
    gps_latitude: str
    gps_longitude: str
    duplicate_hint_from_name: bool
    duplicate_group_id: str
    duplicate_of: str
    session_group_id: str
    session_index: int
    seconds_since_prev: Optional[float]
    img_number: Optional[int]
    # Curation/LLM fields (placeholders)
    artifact_group_id: str
    item_title: str
    item_type: str
    subject: str
    location_guess: str
    notes: str


def gather_images(root: Path) -> List[Path]:
    if not root.exists():
        return []
    img_exts = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
    paths: List[Path] = []
    for p in root.iterdir():
        if p.is_file() and p.suffix.lower() in img_exts:
            paths.append(p)
    # Also walk subdirectories, just in case
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext in img_exts:
                paths.append(Path(dirpath) / fn)
    # De-duplicate
    uniq = []
    seen = set()
    for p in paths:
        rp = str(p)
        if rp not in seen:
            seen.add(rp)
            uniq.append(p)
    return sorted(uniq)


def main() -> None:
    images = gather_images(IMG_ROOT)
    rows_tmp: List[Tuple[Optional[datetime], ImageRow]] = []

    for idx, path in enumerate(images, start=1):
        meta = run_sips_all(path)
        width = meta.get('pixelWidth')
        height = meta.get('pixelHeight')
        make = meta.get('make', '')
        model = meta.get('model', '')
        created_dt, exif_creation_raw = parse_creation_dt(meta, path)
        st = path.stat()
        birth = getattr(st, 'st_birthtime', None)
        birth_str = datetime.fromtimestamp(birth).isoformat(sep=' ', timespec='seconds') if birth else ''
        mtime_str = datetime.fromtimestamp(st.st_mtime).isoformat(sep=' ', timespec='seconds')

        digest = sha256_of_file(path)
        duplicate_hint = filename_duplicate_hint(path.name)
        img_num = extract_img_number(path.stem)

        row = ImageRow(
            id=f"img_{idx:04d}",
            relative_path=str(path.as_posix()),
            filename=path.name,
            extension=path.suffix.lower(),
            size_bytes=st.st_size,
            sha256=digest,
            width_px=int(width) if width and width.isdigit() else None,
            height_px=int(height) if height and height.isdigit() else None,
            camera_make=make,
            camera_model=model,
            exif_creation=exif_creation_raw,
            file_birthtime=birth_str,
            file_mtime=mtime_str,
            gps_latitude='',
            gps_longitude='',
            duplicate_hint_from_name=duplicate_hint,
            duplicate_group_id='',
            duplicate_of='',
            session_group_id='',
            session_index=0,
            seconds_since_prev=None,
            img_number=img_num,
            artifact_group_id='',
            item_title='',
            item_type='',
            subject='',
            location_guess='',
            notes='',
        )
        rows_tmp.append((created_dt, row))

    # Sort by creation time (fallback to mtime if missing)
    def sort_key(t: Tuple[Optional[datetime], ImageRow]):
        dt, row = t
        return dt or datetime.fromisoformat(row.file_mtime)

    rows_tmp.sort(key=sort_key)

    # Duplicate groups by checksum
    digest_to_group: Dict[str, str] = {}
    digest_first_path: Dict[str, str] = {}
    group_counter = 0

    # Session grouping by time delta
    session_id = 0
    last_dt: Optional[datetime] = None
    last_session_start: Optional[datetime] = None
    session_threshold_sec = 90.0
    session_indices: Dict[int, int] = {}

    finalized_rows: List[ImageRow] = []
    for dt, row in rows_tmp:
        # Duplicate grouping
        if row.sha256 in digest_to_group:
            row.duplicate_group_id = digest_to_group[row.sha256]
            row.duplicate_of = digest_first_path[row.sha256]
        else:
            group_counter += 1
            group_id = f"D{group_counter:04d}"
            digest_to_group[row.sha256] = group_id
            digest_first_path[row.sha256] = row.relative_path
            row.duplicate_group_id = group_id

        # Session grouping by time proximity
        current_dt = dt or datetime.fromisoformat(row.file_mtime)
        if last_dt is None or (current_dt - last_dt).total_seconds() > session_threshold_sec:
            session_id += 1
            last_session_start = current_dt
            session_indices[session_id] = 0
        session_indices[session_id] += 1
        row.session_group_id = f"S{session_id:04d}"
        row.session_index = session_indices[session_id]
        row.seconds_since_prev = None if last_dt is None else (current_dt - last_dt).total_seconds()
        last_dt = current_dt

        # Initial artifact grouping guess: align to session group; refinements can come later.
        row.artifact_group_id = row.session_group_id

        finalized_rows.append(row)

    # Write CSV
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(asdict(finalized_rows[0]).keys()) if finalized_rows else []
    with OUT_CSV.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in finalized_rows:
            writer.writerow(asdict(r))

    print(f"Wrote {len(finalized_rows)} rows to {OUT_CSV}")


if __name__ == '__main__':
    main()

