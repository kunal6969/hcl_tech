# file: tests/test_api_contract.py
import json

import pytest
from fastapi.testclient import TestClient

from app.api.schemas import AskResponse


@pytest.fixture()
def client(tmp_path, monkeypatch):
    for k, v in {"DATA_DIR": str(tmp_path), "SQLITE_PATH": str(tmp_path / "app.sqlite"),
                 "DUCKDB_PATH": str(tmp_path / "a.duckdb"), "CHROMA_DIR": str(tmp_path / "chroma"),
                 "EMBEDDINGS": "hash", "MOCK_LLM": "true", "LLM_CACHE": "false", "ADMIN_TOKEN": "secret"}.items():
        monkeypatch.setenv(k, v)
    from app.data import db
    from app.data.validate import TableSpec, register_table
    from app.graph import policy
    from app.llm import gateway
    from app.rag import index
    gateway.reset_gateway()
    index.reset_index()
    db.reset_duck()
    monkeypatch.setattr(policy, "fallback_plan", lambda q: [{"tool": "search_documents", "args": {"query": q}}])
    register_table(TableSpec("tariff", {"valid_from": "datetime", "valid_to": "datetime", "period": "str",
                                        "price_per_kwh": "float"}, primary_key=["valid_from", "period"]))
    from app.api.main import app
    with TestClient(app) as c:
        yield c


DOC = "1 Return window\nElectronics can be returned within 7 days of delivery.\n"
META = {"doc_id": "CIRC-T1", "title": "Electronics window", "authority_level": 2, "version": "1.0",
        "effective_from": "2026-08-01", "doc_type": "circular"}


def test_health_reports_components(client):
    body = client.get("/health").json()
    assert {"api", "sqlite", "vector_store", "llm", "status"} <= set(body)


def test_ingest_metadata_as_form_field_then_cited_answer(client):
    r = client.post("/ingest", files={"file": ("circ.md", DOC)}, data={"metadata": json.dumps(META)})
    assert r.status_code == 200 and r.json()["chunks_indexed"] >= 1 and r.json()["doc_id"] == "CIRC-T1"
    ans = client.post("/ask", json={"question": "How many days to return electronics?", "as_of_date": "2026-10-06"})
    body = ans.json()
    AskResponse.model_validate(body)
    assert body["answer_type"] == "retrieved_fact" and body["citations"][0]["doc_id"] == "CIRC-T1"
    assert [s["doc_id"] for s in client.get("/sources").json()] == ["CIRC-T1"]


def test_ingest_metadata_as_json_file_part(client):
    r = client.post("/ingest", files={"file": ("circ.md", DOC),
                                      "metadata": ("meta.json", json.dumps(META), "application/json")})
    assert r.status_code == 200 and r.json()["doc_id"] == "CIRC-T1"


def test_unanswerable_returns_verbatim_not_found(client):
    body = client.post("/ask", json={"question": "Do you deliver to Antarctica?"}).json()
    assert body["answer_type"] == "not_found"
    assert body["answer"] == "I could not find this information in the authorised sources."
    assert body["citations"] == [] and body["tools_invoked"] == []


def test_audit_visible_to_owner_only(client):
    body = client.post("/ask", json={"question": "hello"}, headers={"X-Customer-Id": "C1001"}).json()
    tid = body["trace_id"]
    assert client.get(f"/audit/{tid}", headers={"X-Customer-Id": "C1001"}).status_code == 200
    assert client.get(f"/audit/{tid}", headers={"X-Customer-Id": "C1002"}).status_code == 404
    assert client.get(f"/audit/{tid}", headers={"X-Admin-Token": "secret"}).json()["trace_id"] == tid
    assert client.get("/audit/nope").status_code == 404


def test_table_ingest_with_loose_table_field_and_bad_row(client):
    csv = ("valid_from,valid_to,period,price_per_kwh,extra\n2026-07-01,2026-08-15,flat,8.0,x\n"
           "2026-08-15,2026-10-01,flat,nine,y\n")
    r = client.post("/ingest", files={"file": ("tariff_corrected.csv", csv)}, data={"table": "tariff"}).json()
    assert (r["table"], r["rows_loaded"], r["rows_rejected"]) == ("tariff", 1, 1)


def test_stream_emits_nodes_then_final(client):
    with client.stream("POST", "/ask/stream", json={"question": "anything"}) as resp:
        events = [json.loads(line[6:]) for line in resp.iter_lines() if line.startswith("data: ")]
    assert events[0]["event"] == "node" and events[-1]["event"] == "final"
    AskResponse.model_validate(events[-1]["response"])
