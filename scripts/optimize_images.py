#!/usr/bin/env python3
"""
Optimize images to reduce file size while maintaining OCR quality.

Reduces JPEG quality to 85% and resizes to max 2400px on longest edge.
This should cut file sizes by ~60-70% with minimal visual impact.

Usage:
    python scripts/optimize_images.py --dry-run  # Preview changes
    python scripts/optimize_images.py            # Apply optimizations
"""

import argparse
from pathlib import Path
from PIL import Image
import shutil

RAW_IMG_DIR = Path('raw/scans/img')
BACKUP_DIR = Path('raw/scans/img_original_backup')

# Optimization settings
MAX_DIMENSION = 2400  # Max width or height
JPEG_QUALITY = 85     # Quality (1-100, 85 is good balance)

def get_image_size_mb(path: Path) -> float:
    """Get file size in MB."""
    return path.stat().st_size / (1024 * 1024)


def optimize_image(img_path: Path, dry_run: bool = False) -> dict:
    """
    Optimize a single image.

    Returns dict with before/after sizes and status.
    """
    try:
        original_size = get_image_size_mb(img_path)

        if dry_run:
            # Estimate compression (typical 60-70% reduction)
            estimated_size = original_size * 0.35
            return {
                'path': str(img_path.name),
                'original_mb': original_size,
                'new_mb': estimated_size,
                'saved_mb': original_size - estimated_size,
                'status': 'would optimize'
            }

        # Open image
        img = Image.open(img_path)

        # Check if resize needed
        width, height = img.size
        max_dim = max(width, height)

        if max_dim > MAX_DIMENSION:
            # Calculate new dimensions maintaining aspect ratio
            if width > height:
                new_width = MAX_DIMENSION
                new_height = int(height * (MAX_DIMENSION / width))
            else:
                new_height = MAX_DIMENSION
                new_width = int(width * (MAX_DIMENSION / height))

            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # Save optimized version to temp file
        temp_path = img_path.with_suffix('.tmp.jpg')
        img.save(
            temp_path,
            'JPEG',
            quality=JPEG_QUALITY,
            optimize=True,
            progressive=True
        )

        new_size = get_image_size_mb(temp_path)

        # Replace original with optimized
        shutil.move(str(temp_path), str(img_path))

        return {
            'path': str(img_path.name),
            'original_mb': original_size,
            'new_mb': new_size,
            'saved_mb': original_size - new_size,
            'status': 'optimized'
        }

    except Exception as e:
        return {
            'path': str(img_path.name),
            'status': f'error: {str(e)}'
        }


def main():
    parser = argparse.ArgumentParser(description='Optimize images to reduce file size')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview changes without modifying files')
    parser.add_argument('--backup', action='store_true',
                        help='Create backup of originals before optimizing')
    args = parser.parse_args()

    if not RAW_IMG_DIR.exists():
        print(f"Error: {RAW_IMG_DIR} not found")
        return

    # Find all JPEG images
    images = list(RAW_IMG_DIR.glob('*.jpg')) + list(RAW_IMG_DIR.glob('*.jpeg'))

    if not images:
        print(f"No images found in {RAW_IMG_DIR}")
        return

    print(f"Found {len(images)} images to optimize")
    print(f"Settings: max dimension={MAX_DIMENSION}px, quality={JPEG_QUALITY}%")

    if args.dry_run:
        print("\n*** DRY RUN MODE - No files will be modified ***\n")
    elif args.backup:
        print(f"\nCreating backup at {BACKUP_DIR}...")
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        for img in images:
            shutil.copy2(img, BACKUP_DIR / img.name)
        print(f"Backed up {len(images)} files")

    # Process images
    results = []
    for i, img_path in enumerate(images, 1):
        if i % 50 == 0:
            print(f"Processing {i}/{len(images)}...")

        result = optimize_image(img_path, dry_run=args.dry_run)
        results.append(result)

    # Summary
    print("\n" + "="*70)
    print("OPTIMIZATION SUMMARY")
    print("="*70)

    total_original = sum(r.get('original_mb', 0) for r in results)
    total_new = sum(r.get('new_mb', 0) for r in results)
    total_saved = total_original - total_new

    print(f"\nTotal images: {len(results)}")
    print(f"Original size: {total_original:.1f} MB")
    print(f"New size: {total_new:.1f} MB")
    print(f"Space saved: {total_saved:.1f} MB ({total_saved/total_original*100:.1f}%)")

    # Show sample of changes
    print("\nSample results (first 5):")
    for r in results[:5]:
        if 'error' in r.get('status', ''):
            print(f"  {r['path']}: {r['status']}")
        else:
            print(f"  {r['path']}: {r['original_mb']:.2f}MB → {r['new_mb']:.2f}MB "
                  f"(saved {r['saved_mb']:.2f}MB)")

    if args.dry_run:
        print("\nTo apply these changes, run without --dry-run flag")
        print("To backup originals first, use --backup flag")
    else:
        print("\n✓ Optimization complete!")


if __name__ == '__main__':
    main()
