# Rule registry + source precedence (versioned documents that disagree)

For any problem where documents, circulars, notices or FAQs set **thresholds that tools use**
(windows, fees, limits, rates) and can conflict or change over time. Tools never hard-code a threshold:
they call `get_rule(parameter, as_of, category, tier)` and cite what it returns.

Contents: 1 Tables · 2 Resolver · 3 Registry access · 4 Rules on live ingest · 5 Tests · 6 Explaining it

## 1. Tables (SQLite)

`source_register` mirrors the statement's Source Register (one row per document; the same fields are the
`/ingest` metadata). `rule_registry` mirrors its rule table, plus four optional columns that make live
changes safe (`supersedes`, `status`, `origin`, `evidence_quote`). Adding columns is allowed; never
rename or drop the statement's columns.

**`app/data/registry_schema.py`** — source_register + rule_registry DDL (30 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/app/data/registry_schema.py`. Read it only when you need to edit it.

## 2. Resolver

Implements the five-step order typical of these briefs: **applicability** (effective on `as_of`, scope covers
the request) → **explicit supersession** (only by authority level 1–2) → **authority** (lower number wins,
regardless of date) → **recency** (same authority: later `effective_from` wins) → **unresolved** (report,
cite both, don't choose). Level-5 content is informational only and can never win. Not-yet-effective
candidates are returned as `upcoming` so the answer can mention them without applying them.

One disclosed interpretation: within **one document**, a narrower scope (e.g. a GOLD-tier clause) is an
exception to that document's general clause, not a conflict. Put this sentence in README assumptions.

**`app/data/registry.py`** — precedence resolver (5 steps) + get_rule(): the only way tools read thresholds (172 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/app/data/registry.py`. Read it only when you need to edit it.

Using it inside a tool (skill 05): call `get_rule`, compute with `res.value`, and return
`**res.to_state()` in the tool output so the trace and response carry `applied_rules`, `conflicts`,
`precedence_decisions` and upcoming-change notes. If `res.status == "unresolved"`, the tool returns
`{"unresolved": True, ...}` and the policy maps it to `conflict_flagged` (cite both, advise support).

## 3. Upserting sources and rules (curated seed, `/ingest` metadata, extraction)

**`app/data/registry_io.py`** — upsert_source / upsert_rules (46 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/app/data/registry_io.py`. Read it only when you need to edit it.

## 4. A circular that changes a rule arrives live (judges will do this)

Order of preference when `/ingest` receives a document:

1. **Metadata includes rules** → `upsert_rules(..., origin="ingest-metadata")`. Done; next request uses them.
2. **No rules in metadata** → extract with the LLM, then **verify before activating**:
   - parameter must be one already in the registry (`SELECT DISTINCT parameter`); unknown parameters go in with
     `status='review'` and are reported in the ingest response, never used by tools;
   - `evidence_quote` must occur verbatim (whitespace-normalised) in the document text;
   - the value must appear inside that quote (as written: "7 days" → 7, "10%" → 0.10 only if the
     registry stores fractions — check how existing rules store it).
   Verified rules are inserted with `origin='llm-verified'`; the ingest response lists them so a
   judge sees exactly what changed.
3. **MOCK_LLM or extraction failed** → the document is still indexed for retrieval; the response says
   `rules_extracted: 0` and why. Never invent a rule.

**`app/data/rule_extract.py`** — LLM rule extraction with verbatim-quote verification (47 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/app/data/rule_extract.py`. Read it only when you need to edit it.

## 5. Tests (the statement's worked example becomes the first test)

**`tests/test_precedence.py`** — import sqlite3 (63 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/tests/test_precedence.py`. Read it only when you need to edit it.

## 6. Explaining it (README + Q&A)

- "Thresholds live in `rule_registry`, each linked to a document clause. Tools call `get_rule()`; the
  response cites the winning rule and lists conflicts with the step that resolved them."
- "A new circular changes behaviour with no restart: `/ingest` registers the source, upserts its rules
  (from metadata, or LLM-extracted and verified against a verbatim quote), and the next `get_rule()`
  call resolves precedence again."
- "Not-yet-effective documents are reported as upcoming changes; level-5 content is informational only."
- "Ties after the policy steps are never silently broken: the answer is `conflict_flagged` with both cited."
