"""Smoke test the Streamlit entry point without a browser or ResPlan archive."""

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest


def test_streamlit_app_starts_with_current_solver():
    app = Path(__file__).resolve().parents[2] / "cable_planner" / "demo" / "app.py"
    page = AppTest.from_file(str(app), default_timeout=30).run()

    assert not page.exception
    assert page.button[0].label == "Run planner"
    assert "grid_router.py" in page.caption[1].value
