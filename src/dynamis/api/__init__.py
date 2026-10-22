"""HTTP API (FastAPI) exposing the pipeline to the web app. Requires the `ml` + `web` extras."""

from .app import Settings, create_app

__all__ = ["Settings", "create_app"]
