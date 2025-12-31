#!/usr/bin/env python3
"""
Date extraction utilities for historical documents.

Extracts dates from OCR text and metadata while distinguishing between:
- Document dates (when created)
- Subject dates (what it discusses)
- Reference dates (dates mentioned in content)
"""

import re
from typing import Optional, Tuple
from pathlib import Path


def extract_year_from_text(text: str, prefer_early: bool = False) -> Optional[int]:
    """
    Extract a single year from text.

    Args:
        text: Text to search
        prefer_early: If True, prefer earlier years when multiple found

    Returns:
        Year as integer, or None if no valid year found
    """
    if not text:
        return None

    # Match 4-digit years (1800-2099)
    year_pattern = r'\b(1[89]\d{2}|20\d{2})\b'
    matches = re.findall(year_pattern, text)

    if not matches:
        return None

    years = [int(y) for y in matches]

    # Prefer earliest or latest year
    return min(years) if prefer_early else max(years)


def extract_date_range(text: str) -> Tuple[Optional[int], Optional[int]]:
    """
    Extract year range from text like "1900-03" or "1894-1898".

    Returns:
        (start_year, end_year) tuple, or (None, None) if no range found
    """
    if not text:
        return (None, None)

    # Pattern for ranges like "1900-03" or "1900-1903"
    range_pattern = r'\b(1[89]\d{2})[-–](\d{2,4})\b'
    match = re.search(range_pattern, text)

    if not match:
        return (None, None)

    start_year = int(match.group(1))
    end_part = match.group(2)

    # Handle abbreviated end year (e.g., "03" in "1900-03")
    if len(end_part) == 2:
        # Assume same century
        century = (start_year // 100) * 100
        end_year = century + int(end_part)
    else:
        end_year = int(end_part)

    return (start_year, end_year)


def parse_letter_date(ocr_text: str) -> Optional[int]:
    """Extract date from letter dateline (e.g., 'September 19, 1941')."""
    if not ocr_text:
        return None

    # Pattern: Month Day, Year or Month Year
    # Common in letter headers
    dateline_pattern = r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+(1[89]\d{2}|20\d{2})\b'
    match = re.search(dateline_pattern, ocr_text, re.IGNORECASE)

    if match:
        return int(match.group(1))

    return None


def parse_meeting_date(ocr_text: str) -> Optional[int]:
    """Extract date from meeting proceedings header."""
    if not ocr_text:
        return None

    # Pattern: "ANNUAL MEETING... 1889" or "HELD AT... JULY... 1881"
    # Look for phrases near "annual meeting" or "held at"
    lines = ocr_text.split('\n')[:20]  # Check first 20 lines

    for line in lines:
        line_upper = line.upper()
        if 'ANNUAL MEETING' in line_upper or 'HELD AT' in line_upper:
            # Extract year from this line or next few lines
            year = extract_year_from_text(line, prefer_early=False)
            if year:
                return year

    return None


def parse_publication_imprint(ocr_text: str) -> Optional[int]:
    """Extract publication date from imprint (e.g., 'SYRACUSE, N. Y:... 1881')."""
    if not ocr_text:
        return None

    # Publication imprints usually appear near the end or in specific format
    # Pattern: City, State: Publisher, Year
    lines = ocr_text.split('\n')

    # Check last 30 lines for publication info
    for line in lines[-30:]:
        # Look for lines with city/state followed by year
        if re.search(r'(?:PRINTED|PUBLISHED|SYRACUSE|ALBANY|NEW YORK)', line, re.IGNORECASE):
            year = extract_year_from_text(line, prefer_early=False)
            if year:
                return year

    return None


def parse_title_page_date(ocr_text: str, item_type: str) -> Optional[int]:
    """
    Extract date from title page or cover.

    Looks for prominent year mentions near document title or
    publication information.
    """
    if not ocr_text or item_type not in ['cover_or_title_page', 'pamphlet_or_brochure']:
        return None

    # First try publication imprint
    year = parse_publication_imprint(ocr_text)
    if year:
        return year

    # Try meeting date for proceedings
    if 'PROCEEDINGS' in ocr_text.upper() or 'MEETING' in ocr_text.upper():
        year = parse_meeting_date(ocr_text)
        if year:
            return year

    # Fallback: extract most prominent year from first 15 lines
    lines = ocr_text.split('\n')[:15]
    return extract_year_from_text('\n'.join(lines), prefer_early=False)


def is_modern_item_type(item_type: str) -> bool:
    """Check if item type indicates modern documentation (not primary source)."""
    modern_types = {
        'photograph_of_display',
        'notecard',  # Usually archival metadata
    }
    return item_type in modern_types


def parse_ocr_for_document_date(ocr_text: str, item_type: str, item_title: str) -> Tuple[Optional[int], float]:
    """
    Parse OCR text for document creation date based on document type.

    Args:
        ocr_text: OCR transcription text
        item_type: Document classification
        item_title: Document title from inventory

    Returns:
        (year, confidence) tuple where confidence is 0.0-1.0
    """
    if not ocr_text:
        return (None, 0.0)

    # Modern items should not be dated from OCR (they're photos of old things)
    if is_modern_item_type(item_type):
        return (None, 0.0)

    year = None
    confidence = 0.0

    # Type-specific parsing with confidence scores
    if item_type == 'letter':
        year = parse_letter_date(ocr_text)
        confidence = 0.9 if year else 0.0

    elif item_type in ['meeting_minutes', 'report']:
        year = parse_meeting_date(ocr_text)
        confidence = 0.85 if year else 0.0

    elif item_type in ['cover_or_title_page', 'pamphlet_or_brochure']:
        year = parse_title_page_date(ocr_text, item_type)
        confidence = 0.8 if year else 0.0

    elif item_type in ['document_page', 'form', 'ledger_or_register']:
        # Try multiple strategies
        year = parse_meeting_date(ocr_text)
        if year:
            confidence = 0.7
        else:
            year = parse_publication_imprint(ocr_text)
            confidence = 0.6 if year else 0.0

    # Sanity check: year should be in reasonable range for this archive
    if year and (year < 1800 or year > 2025):
        return (None, 0.0)

    return (year, confidence)


def extract_year_from_title(title: str, notes: str = '') -> Tuple[Optional[int], float]:
    """
    Extract year from item title or notes, distinguishing subject vs. document dates.

    Returns:
        (year, confidence) where confidence reflects certainty it's a document date
    """
    combined = f"{title} {notes}"

    # High confidence patterns (explicit document dates)
    # E.g., "1881" standalone, "dated 1941", "published 1855"
    high_conf_patterns = [
        r'\bdated\s+(1[89]\d{2}|20\d{2})\b',
        r'\bpublished\s+(1[89]\d{2}|20\d{2})\b',
        r'\bprinted\s+(1[89]\d{2}|20\d{2})\b',
        r'\b(1[89]\d{2}|20\d{2})\b(?=\s*$)',  # Year at end
    ]

    for pattern in high_conf_patterns:
        match = re.search(pattern, combined, re.IGNORECASE)
        if match:
            year = int(match.group(1))
            return (year, 0.8)

    # Medium confidence: year ranges (use first year)
    start_year, end_year = extract_date_range(combined)
    if start_year:
        return (start_year, 0.7)

    # Low confidence: phrases that might be subject dates
    # E.g., "discussing 1845", "about 1845", "commemorating 1845"
    subject_patterns = [
        r'\b(?:discussing|about|commemorating|founded|established)\s+(1[89]\d{2}|20\d{2})\b',
    ]

    for pattern in subject_patterns:
        match = re.search(pattern, combined, re.IGNORECASE)
        if match:
            # This is a subject date, not document date
            return (None, 0.0)

    # Fallback: extract any year, but low confidence
    year = extract_year_from_text(combined, prefer_early=False)
    return (year, 0.4) if year else (None, 0.0)


def get_best_date(
    inventory_row: dict,
    ocr_text: Optional[str] = None,
    ocr_confidence: float = 0.0
) -> Tuple[Optional[int], str, float]:
    """
    Determine best date for an item from all available sources.

    Priority:
    1. OCR text document date (if high confidence and primary source)
    2. Item title/notes date (if explicit document date)
    3. OCR text (if medium confidence)
    4. Title/notes (if any year found)
    5. None (undated)

    Args:
        inventory_row: Row from inventory CSV (as dict)
        ocr_text: OCR transcription text
        ocr_confidence: Metadata confidence score from OCR processing

    Returns:
        (year, source_description, confidence) tuple
    """
    item_type = inventory_row.get('item_type', '')
    item_title = inventory_row.get('item_title', '')
    notes = inventory_row.get('notes', '')

    # Skip modern documentation
    if is_modern_item_type(item_type):
        return (None, 'undated_modern_documentation', 0.0)

    # Try OCR first
    ocr_year, ocr_conf = parse_ocr_for_document_date(ocr_text or '', item_type, item_title)

    # Try title/notes
    title_year, title_conf = extract_year_from_title(item_title, notes)

    # Decision logic
    if ocr_year and ocr_conf >= 0.7 and ocr_confidence >= 0.7:
        # High confidence OCR date
        return (ocr_year, 'ocr_text', ocr_conf)

    elif title_year and title_conf >= 0.7:
        # Explicit date in title/notes
        return (title_year, 'title_explicit', title_conf)

    elif ocr_year and ocr_conf >= 0.5:
        # Medium confidence OCR date
        uncertain = ocr_conf < 0.7 or ocr_confidence < 0.7
        source = 'ocr_text_uncertain' if uncertain else 'ocr_text'
        return (ocr_year, source, ocr_conf)

    elif title_year and title_conf >= 0.4:
        # Any year from title (low confidence)
        return (title_year, 'title_inferred', title_conf)

    else:
        # No date found
        return (None, 'undated', 0.0)


if __name__ == '__main__':
    # Quick test
    test_cases = [
        ("September 19, 1941", "letter", "Test letter", "Letter from 1941"),
        ("FORTY-FOURTH ANNUAL MEETING Brooklyn, N.Y., July 2d and 3d, 1889", "meeting_minutes", "", ""),
        ("SYRACUSE, N. Y: PRINTED AT THE OFFICE OF THE SCHOOL BULLETIN, C. W. BARDEEN, PUBLISHER, 1881.", "cover_or_title_page", "", ""),
    ]

    print("Testing date extraction:")
    for ocr, item_type, title, notes in test_cases:
        row = {'item_type': item_type, 'item_title': title, 'notes': notes}
        year, source, conf = get_best_date(row, ocr, 0.9)
        year_str = str(year) if year else 'None'
        print(f"  Type: {item_type:20s} → Year: {year_str:>4s}  Source: {source:20s}  Conf: {conf:.2f}")
