# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview
This is a digital humanities archive containing historical materials documenting the Common School system of New York State (1800s-1900s), including handwritten documents, typed records, statistical charts, and administrative correspondence.

## Development Commands

### OCR Processing
```bash
# Install dependencies
pip install -r requirements.txt

# Process all materials (Kheel + NYS + Images)
python process_archive.py --collection all

# Process Loose Images only (reads from csv/images_inventory.csv)
python process_archive.py --collection images

# Process specific PDF collections
python process_archive.py --collection kheel
python process_archive.py --collection nys
```

### Inventory Management
```bash
# Build/Update the master inventory of loose images
python scripts/build_images_inventory.py

# Generate thumbnails for inventory items
python scripts/generate_thumbnails.py

# Prepare batch labeling requests for LLM
python scripts/prepare_image_label_requests.py
```

## Architecture Overview

### OCR Processing System
The codebase implements an async OCR pipeline using Qwen VL Plus via OpenRouter:

1. **`ocr.py`** - Core QwenVLOCR class
   - Async processing with retry logic and exponential backoff
   - Automatic PDF-to-image conversion at 300 DPI
   - Specialized prompt selection for different document types
   - Confidence scoring based on uncertainty markers ([?], [illegible])
   - SHA256 checksum tracking for all processed files

2. **`process_archive.py`** - Batch processing orchestrator
   - **PDF Mode**: Handles Kheel Center and NYS Archives collections by path.
   - **Image Mode**: Processes loose images by reading `csv/images_inventory.csv`.
   - **Type Mapping**: Maps inventory `item_type` to OCR prompts (e.g., `letter` -> `handwritten`).
   - Generates comprehensive JSON reports and tracks extraction metrics.

3. **`scripts/build_images_inventory.py`** - Ingestion engine
   - Scans `raw/imgs` for new assets.
   - Calculates SHA256 for deduplication.
   - Groups photos into "sessions" based on EXIF time deltas.
   - Maintains `csv/images_inventory.csv` as the source of truth for loose images.

### Data Model & Processing Flow

1. **Ingestion**: 
   - PDF scans are placed in `raw/scans/`.
   - Loose images are placed in `raw/imgs/` and cataloged via `build_images_inventory.py`.
2. **Classification**: 
   - PDFs are classified by filename patterns.
   - Images are classified via `item_type` field in the inventory (often populated via LLM labeling).
3. **OCR Execution**: `process_archive.py` sends images to Qwen VL Plus with context-aware prompts.
4. **Output**: Text transcriptions (.txt) and structural metadata (.json) are stored in `output/ocr/`.

### Output Structure
```
output/ocr/
├── text/           # OCR transcriptions (.txt)
├── metadata/       # Processing metadata (.json)
├── logs/           # Processing logs
├── reports/        # Batch processing reports
└── temp/           # Temporary PDF page images
```

### Historical Document Considerations

The OCR prompts are specifically tuned for 19th century documents:
- Preserves period spelling and abbreviations ("inst." for instant, "&c" for etc.)
- Handles archaic terminology (selectmen, freeholders, trustees)
- Marks uncertainty with [?] and illegible sections with [illegible]
- Notes stamps, seals, and marginal annotations
- Distinguishes between typed and handwritten sections in mixed documents
- Preserves original formatting and line breaks

## Material Inventory

### Raw Archives (`/raw`)
- **Images** (`/raw/imgs`): 210 JPEG images of historical documents
- **PDF Scans** (`/raw/scans`):
  - Kheel Center: `Toward-Better-Schools.pdf`
  - NYS Archives series: A4456, A4645, B0494, B0594
  
### Reference Data (`/csv`)
- `LIST_common-schools.xlsx`: Master list for validation
- `Selected Items (Albany).xlsx`: Albany district subset

### Key Processing Challenges
- Mixed handwritten and typed content
- 19th century script and abbreviations
- Faded ink and document damage
- Tables and structured forms
- Multiple document types requiring different OCR approaches

## API Configuration

### Qwen VL Plus via OpenRouter
- **Model**: `qwen/qwen-vl-plus`
- **Endpoint**: `https://openrouter.ai/api/v1/chat/completions`
- **Max tokens**: 4000 per request
- **Temperature**: 0.1 for consistent OCR
- **Retry strategy**: 3 attempts with exponential backoff

### Processing Metrics
- Batch size: 5 documents concurrent
- Image max size: 4000x4000px
- PDF extraction: 300 DPI
- Confidence calculation: Based on [?] and [illegible] marker frequency