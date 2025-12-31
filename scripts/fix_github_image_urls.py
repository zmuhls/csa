#!/usr/bin/env python3
"""
Convert relative image paths in collection markdown files to GitHub media CDN URLs.

GitHub LFS files need to use media.githubusercontent.com URLs to display in markdown previews.
"""

import re
from pathlib import Path

COLLECTIONS_DIR = Path('output/collections')
GITHUB_REPO = "zmuhls/csa"
BRANCH = "main"

def convert_relative_to_media_url(relative_path: str) -> str:
    """
    Convert relative path to GitHub media CDN URL.

    Example:
        ../../raw/scans/img/IMG_0625.jpeg
        → https://media.githubusercontent.com/media/zmuhls/csa/main/raw/scans/img/IMG_0625.jpeg
    """
    # Remove leading ../../ or similar
    clean_path = relative_path.replace('../', '')

    return f"https://media.githubusercontent.com/media/{GITHUB_REPO}/{BRANCH}/{clean_path}"


def extract_filename_from_url(url: str) -> str:
    """Extract filename from Dropbox URL or relative path."""
    # Handle Dropbox URLs
    if 'dropbox.com' in url:
        # Extract path between domain and query string
        match = re.search(r'/scans/img/([^?]+)', url)
        if match:
            return f"raw/scans/img/{match.group(1)}"

    # Handle derived/thumbs paths
    if 'derived/thumbs' in url:
        match = re.search(r'derived/thumbs/([^?]+)', url)
        if match:
            return f"derived/thumbs/{match.group(1)}"

    # Handle relative paths
    return url.replace('../', '')


def update_markdown_file(md_file: Path) -> int:
    """
    Update image links in a markdown file.

    Returns number of replacements made.
    """
    content = md_file.read_text(encoding='utf-8')
    original_content = content

    # Pattern for markdown image links: [![alt](path)](path)
    # Handles both Dropbox URLs and relative paths

    def replace_link(match):
        alt_text = match.group(1)
        thumb_path = match.group(2)
        full_path = match.group(3)

        # Extract filenames and convert to GitHub media URLs
        thumb_clean = extract_filename_from_url(thumb_path)
        full_clean = extract_filename_from_url(full_path)

        thumb_url = f"https://media.githubusercontent.com/media/{GITHUB_REPO}/{BRANCH}/{thumb_clean}"
        full_url = f"https://media.githubusercontent.com/media/{GITHUB_REPO}/{BRANCH}/{full_clean}"

        return f"[![{alt_text}]({thumb_url})]({full_url})"

    # Pattern matches: [![alt](any_url)](any_url)
    pattern = r'\[!\[([^\]]*)\]\(([^)]+)\)\]\(([^)]+)\)'
    content = re.sub(pattern, replace_link, content)

    # Also fix standalone relative path links: [text](../../raw/scans/img/...)
    def replace_standalone_link(match):
        link_text = match.group(1)
        link_path = match.group(2)

        # Only process if it's a local image path
        if link_path.startswith('../../raw/') or link_path.startswith('../../derived/'):
            clean_path = extract_filename_from_url(link_path)
            new_url = f"https://media.githubusercontent.com/media/{GITHUB_REPO}/{BRANCH}/{clean_path}"
            return f"[{link_text}]({new_url})"

        return match.group(0)

    # Match standalone links (not already part of image markdown)
    # Negative lookbehind to avoid matching image links we already processed
    content = re.sub(r'(?<!\!)\[([^\]]+)\]\(([^)]+)\)', replace_standalone_link, content)

    # Count total changes
    num_changes = len(re.findall(pattern, original_content))

    if content != original_content:
        md_file.write_text(content, encoding='utf-8')

    return num_changes


def main():
    print("Fixing GitHub image URLs in collection markdown files...")
    print("-" * 70)

    if not COLLECTIONS_DIR.exists():
        print(f"Error: {COLLECTIONS_DIR} not found")
        return

    md_files = list(COLLECTIONS_DIR.glob('*.md'))

    if not md_files:
        print(f"No markdown files found in {COLLECTIONS_DIR}")
        return

    print(f"Found {len(md_files)} collection files\n")

    total_changes = 0
    for md_file in md_files:
        num_changes = update_markdown_file(md_file)
        if num_changes > 0:
            print(f"✓ {md_file.name}: updated {num_changes} image links")
            total_changes += num_changes
        else:
            print(f"  {md_file.name}: no changes needed")

    print("\n" + "=" * 70)
    print(f"Total: {total_changes} image links updated")
    print("\nImages will now display properly on GitHub!")
    print("Commit and push these changes:")
    print("  git add output/collections/")
    print("  git commit -m \"fix image urls for github lfs display\"")
    print("  git push origin main")


if __name__ == '__main__':
    main()
