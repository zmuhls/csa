# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Digital humanities archive for the Common School system of New York State (1800s-1900s). Contains handwritten documents, typed records, statistical charts, and administrative correspondence. Uses multimodal AI (Qwen VL Plus via OpenRouter) to transcribe, classify, and extract metadata.

## Development Commands

### Full Pipeline (in order)
```bash
# 1. Ingest images and build inventory
python scripts/build_images_inventory.py

# 2. Generate thumbnails for LLM labeling
python scripts/generate_thumbnails.py

# 3. Prepare LLM labeling requests
python scripts/prepare_image_label_requests.py

# 4. Run automated LLM labeling (uses OPENROUTER_KEY)
python scripts/batch_label_images.py

# 5. Merge labels into inventory
python scripts/merge_image_labels.py

# 6. Deduplicate inventory entries
python scripts/dedupe_images_inventory.py

# 7. Run OCR (resumes from where it left off)
python process_archive.py --collection images

# 8. Consolidate artifacts and generate manifest
python scripts/consolidate_artifacts.py
python scripts/generate_archive_manifest.py
```

### OCR Processing
```bash
python process_archive.py --collection all      # All collections
python process_archive.py --collection images   # Loose images only
python process_archive.py --collection kheel    # Kheel Center PDFs
python process_archive.py --collection nys      # NYS Archives PDFs
```

## Architecture Overview

### Processing Pipeline
```
raw/scans/img/     →  build_images_inventory.py  →  csv/images_inventory.csv
                   →  generate_thumbnails.py     →  derived/thumbs/
                   →  prepare_image_label_requests.py → prompts/images_label_requests.jsonl
                   →  batch_label_images.py      →  prompts/images_label_responses.jsonl
                   →  merge_image_labels.py      →  csv/images_inventory_labeled.csv
                   →  process_archive.py         →  output/ocr/text/, output/ocr/metadata/
                   →  consolidate_artifacts.py   →  output/archive/documents/, output/archive/research/
                   →  generate_archive_manifest.py → output/archive/manifest.json
```

### Core Components

1. **`ocr.py`** - QwenVLOCR class
   - Async API calls with retry logic
   - PDF-to-image at 300 DPI
   - Document-type-specific prompts
   - Confidence scoring via [?] and [illegible] markers

2. **`process_archive.py`** - Batch orchestrator
   - Reads from `csv/images_inventory_labeled.csv`
   - Maps `item_type` to OCR prompts (letter→handwritten, form→table_form, etc.)
   - Resume capability: skips already-processed images

3. **`scripts/consolidate_artifacts.py`** - Post-OCR processing
   - Groups outputs by `artifact_group_id`
   - Merges sequential pages, culls duplicates (>85% text similarity)
   - Routes research notes to `output/archive/research/`

### Key Data Files

| File | Purpose |
|------|---------|
| `csv/images_inventory.csv` | Raw inventory from ingestion |
| `csv/images_inventory_labeled.csv` | Inventory with LLM classifications |
| `prompts/images_label_requests.jsonl` | LLM labeling requests |
| `prompts/images_label_responses.jsonl` | LLM labeling responses |
| `output/archive/manifest.json` | Final artifact catalog |
| `DEVLOG.md` | Chronological development history |
| `AGENTS.md` | Instructions for AI agents |

### Item Type Vocabulary
12 controlled types: `document_page`, `notecard`, `ledger_or_register`, `form`, `letter`, `pamphlet_or_brochure`, `report`, `meeting_minutes`, `map_or_diagram`, `photograph_of_display`, `envelope_or_folder`, `cover_or_title_page`, `blank_or_unreadable`

## API Configuration

- **Model**: `qwen/qwen-vl-plus` via OpenRouter
- **Auth**: `OPENROUTER_KEY` in `.env`
- **Settings**: 4000 max tokens, 0.1 temperature, 3 retries with exponential backoff
- **Batch size**: 5 concurrent requests

## Historical Document Handling

OCR prompts preserve 19th century characteristics:
- Period spelling and abbreviations ("inst." for instant, "&c" for etc.)
- Archaic terms (selectmen, freeholders, trustees)
- Uncertainty markers: [?] for unclear, [illegible] for unreadable
- Annotations: [stamp: ...], [handwritten: ...], [different hand: ...]

---

## Current Work: OCR Pipeline Enhancement

### In Progress
<!-- Move items here when actively working on them -->

### Backlog

**Stage 2: Human-in-the-Loop**
- Create `scripts/generate_review_queues.py` (hallucination detection, low-confidence flagging)
- Create `csv/ocr_review_queue.csv` template
- Create `scripts/apply_corrections.py` for correction ingestion
- Document review workflow in CLAUDE.md

**Stage 3: Multi-Model Ensemble**
- Abstract OCR class for multiple backends in `ocr.py`
- Add `qwen/qwen-vl-max` as secondary model via OpenRouter
- Add Mistral OCR as tertiary model via OpenRouter
- Create `scripts/ensemble_ocr.py` for comparative runs
- Add consensus scoring to metadata schema
- Test ensemble on 10 challenging documents

### Done

**Stage 1: Artifact Collation** (2024-12-24)
- Added new columns to inventory CSV schema (artifact_link_type, artifact_confidence, needs_review, parent_artifact_id)
- Created `scripts/refine_artifact_groups.py` for text-similarity-based grouping
- Created `scripts/migrate_inventory_schema.py` for existing data migration
- Updated `consolidate_artifacts.py` to handle different link types
- Tested on sample session S0026 (19 items)
- Generated `csv/artifact_review_queue.csv` with 14 items for review
