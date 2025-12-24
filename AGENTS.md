# Repository Guidelines

## Project Structure & Module Organization
- `raw/` source artifacts; do not edit. Thumbnails live in `derived/thumbs/`.
- `csv/` inventories and labeled metadata (e.g., `images_inventory_labeled.csv`).
- `scripts/` one-off utilities (inventory, thumbnails, labeling prep/merge).
- `process_archive.py` batch orchestrator; `ocr.py` OCR engine; `ocr_config.yaml` prompts/config.
- `output/` generated OCR text, metadata, reports, and curated collections.
- `prompts/` prompt payloads and labeling requests/responses.

## Build, Test, and Development Commands
- Install deps: `pip install -r requirements.txt`
- Inventory photos: `python scripts/build_images_inventory.py`
- Generate thumbnails: `python scripts/generate_thumbnails.py`
- Run OCR (all): `python process_archive.py --collection all`
- Run OCR (images only): `python process_archive.py --collection images`
- Quick smoke check: inspect `output/ocr/` and console summary for counts/success rate.

## Coding Style & Naming Conventions
- Python 3.10+; PEP 8; 4-space indent; type hints where practical.
- snake_case for files/functions; PascalCase for classes; CONSTANTS in caps.
- Prefer `pathlib.Path`, `loguru` for logging, and small, single-purpose functions.
- Keep config in `ocr_config.yaml`; avoid hard-coding credentials (use `.env`).

## Testing Guidelines
- No formal test suite yet. Add lightweight “smoke” steps for changes:
  - Run `--collection images` on a small subset and verify new outputs in `output/ocr/`.
  - Re-run `scripts/generate_thumbnails.py` and spot-check links in curated markdown.
- Place any ad-hoc validators under `scripts/` and keep them idempotent.

## Commit & Pull Request Guidelines
- Commits: imperative mood, concise, scoped prefix when helpful (e.g., `scripts:`, `ocr:`).
- PRs: include purpose, sample commands used, before/after notes or links to generated files, and reference issues.
- Do not commit large binaries or secrets; `.env` must stay local.

## Agent-Specific Instructions
- Do not move or edit files under `raw/`; regenerate derived assets via scripts.
- Keep changes minimal and focused; update related docs when altering behavior.
- Use repository paths in markdown links (e.g., `../../raw/scans/img/IMG_xxxx.jpeg`).
- When adding outputs, prefer `output/` and document how to regenerate them.

## After Any Changes

**Always update these files:**

1. **DEVLOG.md** - Append a dated entry describing:
   - What changed and why
   - Key decisions made
   - Next steps

2. **CLAUDE.md** - Update the Kanban section:
   - Move completed items to "Done" with date
   - Move active items to "In Progress"
   - Add new items to "Backlog" as discovered

## File Update Frequency

| File | Purpose | When to Update |
|------|---------|----------------|
| `CLAUDE.md` | Project overview, commands, current work | After completing tasks |
| `DEVLOG.md` | Chronological dev history and decisions | After every session |
| `AGENTS.md` | Agent instructions (this file) | When workflow changes |

## Workflow Reminders

- **Before starting**: Read CLAUDE.md Kanban to understand current state
- **During work**: Track progress with TodoWrite
- **After completing**: Update DEVLOG.md and CLAUDE.md Kanban
- **When blocked**: Document blocker in DEVLOG.md
