"""Local Streamlit component for Google Maps selection and venue markers."""

from pathlib import Path
from typing import Any, Mapping

import streamlit.components.v1 as components

from app.config import GoogleMapsSettings


_FRONTEND_PATH = Path(__file__).with_name("google_maps_frontend")
_google_maps_component = components.declare_component(
    "weather_google_maps_v2",
    path=_FRONTEND_PATH,
)


def load_google_maps_settings(
    environment: Mapping[str, str] | None = None,
) -> GoogleMapsSettings:
    """Load the browser map key without exposing the server Places key."""
    if environment is None:
        try:
            from dotenv import load_dotenv
        except ImportError:
            pass
        else:
            load_dotenv(override=False)
    return GoogleMapsSettings.from_environment(environment)


def google_map(
    *,
    api_key: str,
    center: tuple[float, float],
    zoom: int,
    markers: list[dict[str, Any]] | None = None,
    origin: tuple[float, float] | None = None,
    interactive: bool = False,
    height: int = 320,
    key: str,
) -> dict[str, float] | None:
    """Render Google Maps and optionally return a clicked coordinate."""
    return _google_maps_component(
        api_key=api_key,
        center={"latitude": center[0], "longitude": center[1]},
        zoom=zoom,
        markers=markers or [],
        origin=(
            {"latitude": origin[0], "longitude": origin[1]}
            if origin is not None
            else None
        ),
        interactive=interactive,
        height=height,
        key=key,
        default=None,
    )
