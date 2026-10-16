from cable_planner.demo.environment import available_plan_sources


def test_streamlit_cloud_does_not_offer_local_archive_path():
    assert available_plan_sources("https://hackhive-cable-planner.streamlit.app/") == (
        "Bundled examples (cloud-ready)",
    )


def test_local_streamlit_keeps_trusted_archive_option():
    assert available_plan_sources("http://localhost:8501/") == (
        "Bundled examples (cloud-ready)",
        "Trusted local ResPlan archive",
    )
