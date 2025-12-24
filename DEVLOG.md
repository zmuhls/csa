# Development Log

Chronological record of changes, decisions, and progress on the OCR pipeline enhancement.

---

## 2024-12-24: Project Planning Session

### Context
Assessed current OCR pipeline state. Found:
- 635 OCR outputs (PDFs: 98.8% confidence, Images: 23% success rate)
- Hallucination patterns in some outputs (repetitive lines)
- Session-based artifact grouping defaults to time proximity (90-second threshold)
- Single model (qwen/qwen-vl-plus) with no fallback

### Decisions Made
1. **Priority**: Artifact collation first, then human-in-the-loop, then multi-model ensemble
2. **Curation approach**: Human-in-the-loop (review flagged items, correct errors)
3. **Model stack**: Multi-model ensemble using Qwen models via OpenRouter
   - Primary: `qwen/qwen-vl-plus` (current)
   - Secondary: `qwen/qwen-vl-max` (higher quality for challenging docs)
4. **Todo tracking**: Kanban sections in CLAUDE.md (In Progress / Backlog / Done)

### Artifacts Created
- Added Kanban todo section to CLAUDE.md
- Created plan at `~/.claude/plans/delightful-scribbling-mccarthy.md`

### Next Steps
- Stage 1: Add artifact collation columns to inventory schema
- Create `scripts/refine_artifact_groups.py`

---

## 2024-12-24: Stage 1 Complete - Artifact Collation System

### Context
Implementing artifact collation as the first priority from the planning session.

### Changes Made
- `scripts/build_images_inventory.py`: Added 4 new fields to ImageRow dataclass
  - artifact_link_type (session_default, visual_match, content_overlap, manual_curation)
  - artifact_confidence (0.0-1.0)
  - needs_review (boolean)
  - parent_artifact_id (for hierarchical groupings)
- `scripts/merge_image_labels.py`: Updated to preserve new columns with defaults
- `scripts/migrate_inventory_schema.py`: Created to migrate existing CSV (384 rows)
- `scripts/refine_artifact_groups.py`: Created for text-similarity-based grouping
  - Found 12 content-based groups
  - Flagged 14 items for human review
- `scripts/consolidate_artifacts.py`: Added link type handling
  - New flags: --skip-review, --confident-only
  - Tracks confident_link_ratio and link_types per artifact
- `AGENTS.md`: Added DEVLOG update instructions
- `DEVLOG.md`: Created for development history

### Results
- Inventory schema now has 32 columns (was 28)
- 25 images updated with content_overlap link type
- Review queue generated at csv/artifact_review_queue.csv
- S0026 session test: revealed fragmented artifact IDs from LLM labeling

### Next Steps
- Stage 2: Human-in-the-loop review workflow
  - scripts/generate_review_queues.py for OCR hallucination detection
  - scripts/apply_corrections.py for ingesting curated corrections

---

## Log Template

```markdown
## YYYY-MM-DD: [Brief Title]

### Context
[What prompted this work]

### Changes Made
- [File]: [Description of change]

### Decisions
- [Key decision and rationale]

### Next Steps
- [What comes next]
```
