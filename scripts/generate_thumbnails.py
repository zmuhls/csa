#!/usr/bin/env python3
import os
import subprocess
from pathlib import Path

IMG_ROOT = Path('raw/imgs')
OUT_ROOT = Path('derived/thumbs')
MAX_DIM = 512  # pixels on the longest side


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def is_image(path: Path) -> bool:
    return path.suffix.lower() in {'.jpg', '.jpeg', '.png', '.tif', '.tiff'}


def gather_images(root: Path):
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            p = Path(dirpath) / fn
            if is_image(p):
                yield p


def main():
    ensure_dir(OUT_ROOT)
    count = 0
    for img in gather_images(IMG_ROOT):
        rel = img.relative_to(IMG_ROOT)
        out = OUT_ROOT / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists():
            # Skip existing thumbnails
            continue
        # Use sips to resize with max dimension
        cmd = [
            'sips',
            '-Z', str(MAX_DIM),
            str(img),
            '--out', str(out),
        ]
        subprocess.run(cmd, check=False)
        count += 1
    print(f"Generated/verified thumbnails in {OUT_ROOT}. New: {count}")


if __name__ == '__main__':
    main()

