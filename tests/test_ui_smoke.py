# file: tests/test_ui_smoke.py
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(Path(__file__).resolve().parents[1] / "ui" / "streamlit_app.py")


def test_app_renders_without_api(monkeypatch):
    monkeypatch.setenv("API_BASE_URL", "http://127.0.0.1:9")      # nothing listens: UI must degrade gracefully
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    messages = [str(e.value) for e in [*at.error, *at.warning, *at.info]]
    assert any("API unreachable" in m for m in messages)


def test_charts_build_from_contract_rows():
    import sys
    sys.path.insert(0, str(Path(APP).parent))
    from charts import bridge_waterfall, ranges_bar
    rows = [{"cause": "tariff", "pct_points": 8.1, "range": [7.6, 8.6]},
            {"cause": "waste", "pct_points": 1.4, "range": [0.9, 1.9]}]
    assert bridge_waterfall(rows).data[0].type == "waterfall"
    assert ranges_bar(rows).data[0].error_x.array is not None
