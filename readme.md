# Common School Archive of New York State

A multimodal digital archive pipeline for preserving and analyzing 19th-century New York State educational records.

**Project Status:** Active Development
**Last Updated:** January 2025

---

## Table of Contents

- [Overview](#overview)
- [Browse the Archive](#browse-the-archive)
  - [District Consolidation Tables](#district-consolidation-tables)
  - [NYS Teachers' Association Collection](#nys-teachers-association-collection)
- [Repository Structure](#repository-structure)
- [Pipeline Architecture](#pipeline-architecture)
- [Usage Guide](#usage-guide)
- [Data Model](#data-model)

---

## Overview

This repository contains the processing pipeline, raw assets, and derived outputs for the **Common School Archive**, a digital humanities initiative to preserve and analyze historical New York State educational records.

The system employs a **multimodal AI pipeline** (Qwen VL Plus via OpenRouter) to transcribe, classify, and extract metadata from complex historical artifacts—handwritten ledgers, typed reports, mixed-media cards—preparing them for publication in an **Omeka Classic** digital exhibit.

---

## Browse the Archive

### District Consolidation Tables

Extracted tabular data from NYS Archives Series A4456: District Consolidation Records (1888-1940s). Each page includes the source document image and structured table extraction.

**[Browse by County](output/collections/district-consolidation-by-county.md)** — 30 NY counties with 115 pages of consolidated district, union free school, and central rural school records.

**Full index:** [Browse all 115 table extractions](output/ocr/tables/markdown/)

**Bulk downloads:**
- [CSV format](output/ocr/tables/csv/) — Structured data for analysis
- [JSON format](output/ocr/tables/json/) — Machine-readable with metadata

### NYS Teachers' Association Collection

A curated exhibition-styled collection of materials referencing the New York State Teachers' Association (NYSTA), spanning 1845-1920s.

**[View the full collection](output/collections/nys-teachers-association.md)** — Organized chronologically by decade and thematically by document type.

Includes:
- Annual meeting programs and proceedings
- Membership materials and advocacy documents
- Historical photographs and ephemera

---

## Repository Structure

```
cs-archive/
├── raw/                        # Primary archival materials
│   ├── scans/img/              # 210+ loose artifact photos (JPEG)
│   └── scans/                  # High-resolution PDF scans
│       ├── kheel/              # Kheel Center published reports
│       └── nysed/              # NYS Archives series (A4456, B0494, etc.)
│
├── scripts/                    # Processing pipeline scripts
│   ├── build_images_inventory.py
│   ├── batch_label_images.py
│   ├── extract_all_tables.py
│   ├── generate_nys_teachers_collection.py
│   ├── generate_county_collection.py
│   └── dev/                    # Experimental/test scripts
│
├── output/                     # Generated outputs
│   ├── ocr/
│   │   ├── text/               # Raw transcriptions
│   │   ├── metadata/           # JSON sidecars with confidence scores
│   │   └── tables/             # Structured table extractions
│   │       ├── markdown/       # Human-readable with images
│   │       ├── csv/            # Tabular data
│   │       ├── json/           # Machine-readable
│   │       └── thumbs/         # Display thumbnails (600px)
│   ├── collections/            # Curated thematic collections
│   └── archive/                # Consolidated artifacts
│       ├── documents/
│       ├── research/
│       └── manifest.json
│
├── csv/                        # Inventory and metadata
│   ├── images_inventory.csv    # Master image registry
│   └── images_inventory_labeled.csv
│
├── derived/                    # Generated assets
│   └── thumbs/                 # Image thumbnails for display
│
├── ocr.py                      # Core OCR engine (Qwen VL Plus)
├── process_archive.py          # Batch orchestrator
└── ocr_config.yaml             # Processing configuration
```

---

## Pipeline Architecture

```
raw/scans/img/  →  build_images_inventory.py  →  csv/images_inventory.csv
                →  generate_thumbnails.py     →  derived/thumbs/
                →  batch_label_images.py      →  csv/images_inventory_labeled.csv
                →  process_archive.py         →  output/ocr/text/, output/ocr/metadata/
                →  extract_all_tables.py      →  output/ocr/tables/
                →  consolidate_artifacts.py   →  output/archive/
```

### Core Components

| Component | Purpose |
|-----------|---------|
| `ocr.py` | Async API calls to Qwen VL Plus with retry logic, PDF-to-image conversion, document-type-specific prompts |
| `process_archive.py` | Batch orchestrator with resume capability, maps item types to OCR prompts |
| `extract_all_tables.py` | Structured table extraction from ledger pages to CSV/JSON/Markdown |
| `consolidate_artifacts.py` | Groups outputs by artifact, merges pages, culls duplicates (>85% text similarity) |

---

## Usage Guide

### Environment Setup

```bash
# Ensure .env contains OPENROUTER_KEY
pip install -r requirements.txt
```

### Processing Commands

```bash
# Full OCR pipeline
python process_archive.py --collection all      # All collections
python process_archive.py --collection images   # Loose images only
python process_archive.py --collection kheel    # Kheel Center PDFs
python process_archive.py --collection nys      # NYS Archives PDFs

# Table extraction
python scripts/extract_all_tables.py            # Extract structured tables

# Inventory management
python scripts/build_images_inventory.py        # Rebuild image inventory
python scripts/generate_thumbnails.py           # Generate display thumbnails
```

---

## Data Model

Target schema for Omeka ingestion:

| Field | Description | Source |
|-------|-------------|--------|
| **Title** | Derived from content or filename | LLM / Inventory |
| **Identifier** | UUID or Archival Call Number | `source_series` + `id` |
| **Date** | ISO 8601 (YYYY-MM-DD) | Extracted from text |
| **Description** | Summary of contents | LLM |
| **Transcription** | Full text content | OCR (Qwen VL Plus) |
| **Format** | Document type (Ledger, Letter, Report) | Classifier |
| **Creator** | School district / Official name | Entity linking |
| **Source** | Physical location/collection | Provenance metadata |

---

## Documentation

- [CLAUDE.md](CLAUDE.md) — Technical documentation for AI-assisted development
- [AGENTS.md](AGENTS.md) — Instructions for AI agents working on this codebase
- [DEVLOG.md](DEVLOG.md) — Chronological development history
