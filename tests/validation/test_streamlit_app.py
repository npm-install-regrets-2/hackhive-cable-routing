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
    assert page.radio[0].options == [
        "Bundled examples (cloud-ready)",
        "Trusted local ResPlan archive",
    ]
    assert page.selectbox[0].options == ["12014", "8063", "4944", "8061", "13033", "14433"]


@pytest.mark.parametrize("plan_id", ["12014", "8063", "4944", "8061"])
def test_fast_bundled_examples_pass_independent_validation(plan_id):
    app = Path(__file__).resolve().parents[2] / "cable_planner" / "demo" / "app.py"
    page = AppTest.from_file(str(app), default_timeout=35).run()
    page.selectbox[0].set_value(plan_id).run()
    page.button[0].click().run()

    assert not page.exception
    assert any(item.value == "Independent validation passed" for item in page.success)


def test_4944_shows_side_by_side_checked_comparison():
    app = Path(__file__).resolve().parents[2] / "cable_planner" / "demo" / "app.py"
    page = AppTest.from_file(str(app), default_timeout=35).run()
    page.selectbox[0].set_value("4944").run()
    page.button[0].click().run()

    assert not page.exception
    captions = [item.value for item in page.caption]
    assert any("2 of 9 generated complete candidates had zero crossings" in value for value in captions)
    assert any("Selected best found route" in item.value for item in page.markdown)
    assert any("Best found zero crossings route" in item.value for item in page.markdown)
    assert [button.label for button in page.get("download_button")] == [
        "Download selected checked JSON", "Download alternative checked JSON",
    ]


def test_8061_reports_no_qualifying_candidate_found():
    app = Path(__file__).resolve().parents[2] / "cable_planner" / "demo" / "app.py"
    page = AppTest.from_file(str(app), default_timeout=35).run()
    page.selectbox[0].set_value("8061").run()
    page.button[0].click().run()

    assert not page.exception
    assert any(item.value == "No qualifying candidate found in this search" for item in page.info)
