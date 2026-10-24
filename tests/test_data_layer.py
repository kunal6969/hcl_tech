# file: tests/test_data_layer.py
import pandas as pd
import pytest

from app.data import db
from app.data.ingest import ingest_table
from app.data.validate import TableSpec, register_table, validate_frame


@pytest.fixture(autouse=True)
def stores(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "t.sqlite"))
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "t.duckdb"))
    db.reset_duck()
    yield
    db.reset_duck()


ITEMS = TableSpec("order_items", {"order_id": "str", "sku": "str", "qty": "int", "net_unit_price": "float",
                                  "delivered_on": "date"}, primary_key=["order_id", "sku"], nullable={"delivered_on"},
                  row_rules=[("qty_at_least_1", lambda d: d["qty"] < 1, "error")])
METER = TableSpec("meter_15min", {"meter_id": "str", "ts": "datetime", "kwh": "float"},
                  primary_key=["meter_id", "ts"], store="duckdb", aliases=("meter",))


def test_validation_rejects_with_reasons_and_keeps_extra_columns():
    df = pd.DataFrame({"order_id": ["O-1", "O-2", "O-3", "O-3"], "sku": ["A", "B", "C", "C"],
                       "qty": ["1", "0", "x", "2"], "net_unit_price": ["10", "5", "5", "6"],
                       "delivered_on": ["2026-10-01", "", "2026-10-01", "2026-10-02"], "note": ["a", "b", "c", "d"]})
    clean, rejected, rep = validate_frame(df, ITEMS, "items.csv")
    assert list(clean["order_id"]) == ["O-1", "O-3"] and "note" in clean.columns
    assert set(rejected["_reason"]) == {"qty_at_least_1", "qty is not a valid int"}
    assert rep.rows_rejected == 2 and rep.ok


def test_missing_required_column_rejects_whole_file():
    _, rejected, rep = validate_frame(pd.DataFrame({"order_id": ["O-1"]}), ITEMS, "bad.csv")
    assert not rep.ok and len(rejected) == 1


def test_sqlite_upsert_is_idempotent_and_accepts_schema_change():
    register_table(ITEMS)
    df = pd.DataFrame({"order_id": ["O-1"], "sku": ["A"], "qty": ["1"], "net_unit_price": ["10"], "delivered_on": [""]})
    assert ingest_table(df, "order_items", source_name="a.csv")["rows_loaded"] == 1
    res = ingest_table(df.assign(qty=["3"], gift_wrap=["Y"]), "order_items", source_name="b.csv")
    rows = db.connect().execute("SELECT qty, gift_wrap FROM order_items").fetchall()
    assert rows == [(3, "Y")] and res["data_version"] == 2


def test_duckdb_upsert_by_key_for_corrected_late_file():
    register_table(METER)
    first = pd.DataFrame({"meter_id": ["main", "main"], "ts": ["2026-07-01T00:00Z", "2026-07-01T00:15Z"],
                          "kwh": ["1", "2"]})
    ingest_table(first, "meter_15min", source_name="meter.csv")
    res = ingest_table(pd.DataFrame({"meter_id": ["main"], "ts": ["2026-07-01T00:15Z"], "kwh": ["5"]}),
                       "meter_15min", source_name="meter_fix.csv")
    assert db.duck().execute('SELECT SUM(kwh), COUNT(*) FROM "meter_15min"').fetchone() == (6.0, 2)
    assert res["status"] == "loaded"
