"""Reverse geocoding: turn picked coordinates into a readable place label.

Uses the free, key-less BigDataCloud reverse-geocode endpoint. Every failure
mode degrades gracefully to ``None`` so the caller can fall back to showing
raw coordinates without breaking the flow.
"""

import json
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


REVERSE_GEOCODE_URL = "https://api.bigdatacloud.net/data/reverse-geocode-client"

JsonFetcher = Callable[[str], dict[str, Any]]


def reverse_geocode_label(
    latitude: float,
    longitude: float,
    json_fetcher: JsonFetcher | None = None,
    language_code: str = "tr",
) -> str | None:
    """Return a short place label (e.g. "Kadıköy, İstanbul") or None.

    Never raises: any network, parsing, or data problem yields ``None``.
    """
    try:
        normalized_latitude = float(latitude)
        normalized_longitude = float(longitude)
    except (TypeError, ValueError):
        return None

    if not -90 <= normalized_latitude <= 90:
        return None
    if not -180 <= normalized_longitude <= 180:
        return None

    query = urlencode(
        {
            "latitude": normalized_latitude,
            "longitude": normalized_longitude,
            "localityLanguage": language_code,
        }
    )
    fetcher = json_fetcher or _fetch_json
    try:
        payload = fetcher(f"{REVERSE_GEOCODE_URL}?{query}")
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None
    return _build_place_label(payload)


def _build_place_label(payload: dict[str, Any]) -> str | None:
    """Compose a concise label from a reverse-geocode payload."""
    locality = _clean(payload.get("locality"))
    city = _clean(payload.get("city"))
    subdivision = _clean(payload.get("principalSubdivision"))

    # Prefer the most specific area (district/neighbourhood) for the first part
    # and a broader region (city/province) for context, avoiding duplicates.
    primary = locality or city or subdivision
    if primary is None:
        return None

    context = None
    for candidate in (city, subdivision):
        if candidate and candidate.casefold() != primary.casefold():
            context = candidate
            break

    if context is None:
        return primary
    return f"{primary}, {context}"


def _clean(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _fetch_json(url: str) -> dict[str, Any]:
    request = Request(
        url,
        headers={"User-Agent": "weather-decision-agent/0.1"},
    )
    with urlopen(request, timeout=8) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError("Reverse geocoder returned an invalid response.")
    return payload


# Keep imported error types referenced so linters don't flag them as unused;
# they document the exception surface handled by the broad guard above.
_HANDLED_NETWORK_ERRORS = (HTTPError, URLError, json.JSONDecodeError)
