---
name: 04-universal-data-db-and-live-ingest
description: Builds the data layer for any hackathon dataset - store choice (SQLite for entities, registry, traces and ingest log; DuckDB or Parquet for time series; ChromaDB for documents), schema-first table specs transcribed from the statement, a validation CLI whose report is shown in the demo, an idempotent CSV/XLSX loader for judge test data, live /ingest for both tables and documents with data versioning, document parsing (PDF, DOCX, HTML, OCR) with section-aware chunking, source register, rule registry with precedence, and disciplined LLM-generated synthetic data. Use this whenever the task mentions data packs, CSV schemas, loading or validating data, test customers, late data drops, schema changes, ingesting documents or circulars, the source register, rule thresholds, conflicting or versioned documents, or generating synthetic data with an LLM.
---

# Universal data layer + live ingest

Judges load **their own** files through your loader and `/ingest` during judging, including a schema
change, bad rows, or a circular that changes a rule. So: schema-first specs, validation before every
load, idempotent upserts, a data version that bumps on every ingest, and nothing hard-coded to your files.

- Precedence, rule registry, live rule changes: `references/precedence-and-rule-registry-patterns.md`
- Retrieval index used by document ingest: skill 05 (`app/rag/index.py`)
- Time-series cleaning and analytics recipes: skill 05 reference

## 1. Choose stores by data shape

| Data | Store | Why |
|---|---|---|
| Entities (customers, orders, assets), rule registry, source register, traces, ingest log, LLM cache | SQLite `data/app.sqlite` (WAL) | transactional upserts, FK checks, zero setup, mandated in many briefs |
| Interval/time-series (≥100k rows: 15-min meters, sensor logs, transactions) | DuckDB `data/analytics.duckdb` (+ Parquet snapshots per data version) | columnar SQL, range/ASOF joins, fast group-bys from pandas |
| Documents for grounded answers | ChromaDB `data/chroma/` persisted + BM25 sidecar | mandated vector store; hybrid retrieval beats either alone |

Stores live under `data/` (gitignored). Never re-ingest on restart: document ingest is keyed by sha256.

## 2. Connections + ingest log

**`app/data/db.py`** — SQLite + DuckDB connections, ingest_log, data_version (54 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/app/data/db.py`. Read it only when you need to edit it.

## 3. Table specs (schema-first) + validation

Transcribe every table in the statement's schema annex into `app/data/tables.py` (problem-specific).
Required columns are checked; **extra columns are kept** (briefs allow them); types are coerced; bad rows
are rejected with a reason, never silently dropped; duplicates keep the last row and are reported.

**`app/data/validate.py`** — TableSpec, validate_frame, read_any, infer_table, report_markdown + the validation CLI (160 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/app/data/validate.py`. Read it only when you need to edit it.

Problem-specific specs (fill at S2; examples show both shapes):

**`app/data/tables.py`** — PROBLEM-SPECIFIC: transcribe the statement's schema annex into TableSpecs here (14 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/app/data/tables.py`. Read it only when you need to edit it.

Cross-table rules (FK, "delivered_on only when DELIVERED and never before order_date", "net price ≤ list
price", reserved judge ID ranges) run in the loader after all files are read (`fk_violations` + joins) and
go into the same report. Reserved judge IDs must be **rejected in your own generated data** but **accepted
from judge files** — check by source, never globally.

## 4. Loading: SQLite or DuckDB, idempotent upsert, data version

**`app/data/ingest.py`** — ingest_table: validate -> upsert (SQLite/DuckDB) -> log a new data version (76 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/app/data/ingest.py`. Read it only when you need to edit it.

Judge-facing loader (the statement usually names it; keep the exact command in README):

**`scripts/load_data.py`** — judge-facing loader CLI (24 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/scripts/load_data.py`. Read it only when you need to edit it.

Order matters for FKs: name files so parents load first, or call `ingest_table` in an explicit order
(customers → products → orders → items → returns). For DuckDB tables, `ingest_table` upserts by key, so
a "corrected" late file overwrites only its rows.

## 5. Documents: parse → section-aware chunks → index → source register → rules

**`app/rag/ingest_docs.py`** — document ingest: parse (pdf/docx/html/ocr), section-aware chunking, index, register, rules (147 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/app/rag/ingest_docs.py`. Read it only when you need to edit it.

Seed your own corpus with the same function (`scripts/seed_documents.py` reading `source_register.csv`
and calling `ingest_document` per row) so judges' documents and yours take the same path.

## 6. Synthetic data with an LLM (when the statement asks you to generate it)

Judges assess prompt design, schema enforcement, validation and edge-case coverage. Discipline:

1. **Generate structure with code, content with the LLM.** IDs, dates, foreign keys and the edge cases
   are created deterministically (seeded `random.Random(42)`); the LLM fills names, product names,
   descriptions and free-text notes in JSON batches (≤ 25 rows) validated by Pydantic.
2. **Plant every edge case on purpose** with a named ID (e.g. `O-100013 = delivered exactly on the last
   day of the window as of the demo date`) and list them in the data card. Compute edge-case dates
   relative to the demo `as_of_date`, not "today".
3. **Prompt template** (save verbatim in `data_gen/prompts/`): role, the exact schema with types and
   allowed enums, 2 example rows, constraints (synthetic names only, no real people/companies, prices in
   range), batch size, "return a JSON object with key rows".
4. **Validate** with the same `TableSpec`s + cross-table rules; regenerate failed batches; keep the
   validation output (`docs/validation_report.md`) as a deliverable.
5. **Never use reserved judge ID ranges**; assert it in the validator for your generated files.
6. Record model, prompts, seeds, rounds, manual edits in the data card (skill 07 template).

## 6b. Tests for the data layer

**`tests/test_data_layer.py`** — import pandas as pd (45 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/tests/test_data_layer.py`. Read it only when you need to edit it.

## 7. Live ingest checklist (rehearse before the freeze)

- [ ] `/ingest` accepts the metadata however judges send it (form field or JSON file part) — skill 06.
- [ ] A CSV with an extra column loads; a CSV missing a required column is rejected with a clear message.
- [ ] Bad rows are rejected with reasons and counted in `rows_rejected`; good rows still load.
- [ ] Re-ingesting the same file is idempotent (same row counts, no duplicates).
- [ ] A corrected file (late drop) overwrites by key, bumps `data_version`, and analytics re-run on it.
- [ ] A new circular changes a rule used by a tool; the next request cites it without a restart.
- [ ] A scanned PDF either OCRs or reports `indexed_empty_text`; never a silent empty index.

## 8. Gotchas

- Read CSVs with `dtype=str` + explicit coercion: IDs keep leading zeros, `"NA"` stays a string.
- `encoding="utf-8-sig"` strips Excel's BOM, which otherwise renames the first column.
- Parse timestamps with `utc=True`; mixed offsets become one zone, as the validation checks require.
- SQLite in FastAPI threads: one connection per call (`connect()`), WAL mode, `timeout=30`.
- DuckDB allows one writer process: the API owns the file; CLI loaders should call the API's admin
  loader or run while the API is stopped.
- Chroma metadata must be scalar; `$and` needs ≥ 2 conditions; `$lte/$gte` only on numbers.
- pandas 3: copy-on-write means `df[col][mask] = x` silently does nothing — use `df.loc[mask, col] = x`.
