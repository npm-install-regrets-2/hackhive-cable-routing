"""Deployment-environment checks for the Streamlit demo."""

from urllib.parse import urlsplit


def available_plan_sources(url: str | None) -> tuple[str, ...]:
    """Return sources the app can actually read from the current deployment."""
    host = (urlsplit(url or "").hostname or "").lower()
    bundled = "Bundled examples (cloud-ready)"
    if host == "share.streamlit.io" or host.endswith(".streamlit.app"):
        return (bundled,)
    return (bundled, "Trusted local ResPlan archive")
