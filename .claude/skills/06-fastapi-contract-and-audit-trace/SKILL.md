---
name: 06-fastapi-contract-and-audit-trace
description: Implements the mandatory API contract exactly - FastAPI + Uvicorn + Pydantic v2 models transcribed verbatim from the statement (endpoint paths, headers, request bodies, response keys, answer_type enums), a service layer that runs the graph and never returns a bare 500, identity from headers only, a robust multipart /ingest that accepts metadata however judges send it, health checks per component, an audit/trace store with PII redaction and owner-only access, an optional SSE stream for live UI steps, Dockerfile and docker compose with Ollama on the host, and contract tests per answer type. Use this whenever the work touches endpoints, request or response JSON, headers such as X-Customer-Id, /ask or /analyze, /ingest, /health, /audit or /trace, /sources, loaders exposed over HTTP, curl examples, Docker, or "the judges' tests fail against our API".
---

# FastAPI contract + audit trace

Judges run the **same live tests against every team**. A field renamed, a header ignored or an enum
value misspelt fails them all, however good the agent is. So: transcribe the contract verbatim, keep
inputs lenient and outputs strict, and test every answer type through HTTP.

## 1. Transcribe the contract (S1, first 20 minutes)

1. Copy the statement's endpoint table into `docs/REQUIREMENTS.md` §3 and its response JSON example
   verbatim. Every key in that example becomes a field; the answer-type table becomes a `Literal`.
2. Requests: `extra="ignore"` (judges may send more). Responses: `extra="forbid"` (no drift).
3. Headers: identity only from the header the statement names (e.g. `X-Customer-Id`); never from the body.
4. Dates: accept `YYYY-MM-DD`; default `as_of_date` as the statement says (usually today) and echo it.
5. Rename the example models below to the statement's names; keep the service/trace code unchanged.

**`app/api/schemas.py`** — the contract: transcribe the statement's fields and answer types verbatim here (52 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/app/api/schemas.py`. Read it only when you need to edit it.

Analytics-style contracts look different but use the same machinery. Example shape (rename/extend to match):

```python
class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    question: str
    period: str | None = None        # e.g. "2026-Q3"
    compare_to: str | None = None    # e.g. "2026-Q2"

class BridgeItem(BaseModel):
    cause: str
    pct_points: float
    range: list[float]

class Recommendation(BaseModel):
    action: str
    saving_kwh_per_year: list[float]
    saving_money_per_year: list[float]
    saving_co2e_t_per_year: list[float]
    payback_months: list[float]
    ease: str
    rationale: str
    evidence_refs: list[str]
    confidence: Literal["low", "medium", "high"]
    requires_approval: bool = True

class AnalyzeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str
    answer_type: Literal["decomposition", "recommendation", "calculated", "not_in_data", "clarification_needed", "refused"]
    summary: str
    bridge: list[BridgeItem] = []
    recommendations: list[Recommendation] = []
    assumptions: list[str] = []
    limitations: list[str] = []
```

## 2. Trace store (audit records)

**`app/trace/store.py`** — trace persistence with PII redaction (39 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/app/trace/store.py`. Read it only when you need to edit it.

## 3. Service layer: graph → contract response + audit record

`answer()` is shared by the endpoint, the SSE stream and the in-process eval runner, so all three
produce identical responses and traces.

**`app/api/service.py`** — answer()/stream_answer(): graph -> contract response + audit record, never a bare 500 (117 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/app/api/service.py`. Read it only when you need to edit it.

## 4. App: endpoints, identity, robust `/ingest`

`/ingest` is where live judging breaks most often: judges may send metadata as a form field, as a JSON
file part, under `metadata`, `meta`, `json` or as loose fields like `table=tariff`. Accept all of them,
route tables vs documents by metadata or file extension, and return the statement's keys.

**`app/api/main.py`** — endpoints: ask, stream, robust multipart ingest, health, audit, sources, documents, admin load (139 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/app/api/main.py`. Read it only when you need to edit it.

**`app/tools/catalog.py`** — imports every tool module so it registers (add problem tools here) (4 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/app/tools/catalog.py`. Read it only when you need to edit it.

`def` endpoints run in FastAPI's threadpool, which is what `graph.invoke` (synchronous) needs. Never
call the graph from an `async def` endpoint without `run_in_threadpool`.

## 5. Contract tests (MOCK_LLM, hash embeddings, temp stores)

**`tests/test_api_contract.py`** — import json (65 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/tests/test_api_contract.py`. Read it only when you need to edit it.

## 6. Docker + compose (Ollama stays on the host)

**`Dockerfile`** — API image (CPU torch, tesseract) (11 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/Dockerfile`. Read it only when you need to edit it.

**`docker-compose.yml`** — api + ui, Ollama on the host via host-gateway (29 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/docker-compose.yml`. Read it only when you need to edit it.

**`requirements.txt`** — verified dependency set (27 lines). Installed by `python .claude/bootstrap.py`; source: `.claude/templates/requirements.txt`. Read it only when you need to edit it.

Build the image **before** the event (torch + model download take minutes). Pre-download the embedding
model once with `python -c "from sentence_transformers import SentenceTransformer as S; S('all-MiniLM-L6-v2')"`
and keep `data/hf` mounted so judges' machines don't need the network for it.

## 7. curl samples for README (fill the real paths/headers)

```bash
curl -s localhost:8000/health | jq
curl -s -X POST localhost:8000/ask -H 'Content-Type: application/json' -H 'X-Customer-Id: C1001' \
     -d '{"question":"Can I return the headphones from order O-100001?","as_of_date":"2026-10-06"}' | jq
curl -s -X POST localhost:8000/ingest -F 'file=@docs/CIRC-JDG.pdf' -F 'metadata=@meta.json;type=application/json' | jq
curl -s -X POST localhost:8000/ingest -F 'file=@tariff_corrected.csv' -F 'table=tariff' | jq
curl -s localhost:8000/audit/<trace_id> -H 'X-Customer-Id: C1001' | jq
curl -s localhost:8000/sources | jq
```

## 8. Checklist

- [ ] Every endpoint, header, body field and response key matches the statement character for character.
- [ ] One contract test per answer type passes through HTTP with MOCK_LLM.
- [ ] Missing/invalid identity on a personal question → `refused`, not 500. Unknown errors → contract-shaped
      abstain + trace, never a bare 500.
- [ ] `/ingest` works with metadata as form field, JSON file part, and loose fields; returns statement keys.
- [ ] `/audit/{id}` returns the full record to the owner/admin and 404 to everyone else.
- [ ] `docker compose up` from a clean clone serves `/health` = ok (Ollama reachable via host-gateway).
