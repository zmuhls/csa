#!/usr/bin/env python3
import base64
import csv
import json
from pathlib import Path

IN_CSV = Path('csv/images_inventory.csv')
THUMBS = Path('derived/thumbs')
OUT_JSONL = Path('prompts/images_label_requests.jsonl')

INSTRUCTIONS = (
    "You are labeling photos of archival artifacts. Return strict JSON only. "
    "Infer item_type (controlled values), subject (short phrase), location_guess (if signage/labels visible), "
    "and optionally refine artifact_group_id if this image likely belongs with nearby sequence images of the same artifact. "
    "Use only visible content; if uncertain, set fields to null and add a note."
)

CONTROLLED_ITEM_TYPES = [
    "document_page",
    "notecard",
    "ledger_or_register",
    "form",
    "letter",
    "pamphlet_or_brochure",
    "report",
    "meeting_minutes",
    "map_or_diagram",
    "photograph_of_display",
    "envelope_or_folder",
    "cover_or_title_page",
    "blank_or_unreadable",
]


def b64_of_image(path: Path) -> str:
    with open(path, 'rb') as f:
        return base64.b64encode(f.read()).decode('ascii')


def main():
    OUT_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with IN_CSV.open() as f_in, OUT_JSONL.open('w') as f_out:
        reader = csv.DictReader(f_in)
        for row in reader:
            thumb = THUMBS / Path(row['filename'])
            if not thumb.exists():
                # If thumbnail missing, point to original but skip embedding
                image_b64 = None
                image_path = row['relative_path']
            else:
                image_b64 = b64_of_image(thumb)
                image_path = str(thumb)

            payload = {
                "id": row['id'],
                "image_path": image_path,
                "image_b64": image_b64,  # Include for API calls that accept base64
                "metadata_hint": {
                    "session_group_id": row.get('session_group_id'),
                    "session_index": row.get('session_index'),
                    "exif_creation": row.get('exif_creation'),
                    "camera_model": row.get('camera_model'),
                },
                "instructions": INSTRUCTIONS,
                "schema": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "item_type": {"type": ["string", "null"], "enum": CONTROLLED_ITEM_TYPES + [None]},
                        "subject": {"type": ["string", "null"]},
                        "location_guess": {"type": ["string", "null"]},
                        "artifact_group_id": {"type": ["string", "null"]},
                        "notes": {"type": ["string", "null"]},
                        "confidence": {"type": ["number", "null"]}
                    },
                    "required": ["id", "item_type", "subject"],
                    "additionalProperties": False
                },
                "response_template": {
                    "id": row['id'],
                    "item_type": None,
                    "subject": None,
                    "location_guess": None,
                    "artifact_group_id": row.get('artifact_group_id') or None,
                    "notes": None,
                    "confidence": None
                }
            }
            f_out.write(json.dumps(payload) + "\n")
    print(f"Wrote requests to {OUT_JSONL}")


if __name__ == '__main__':
    main()

