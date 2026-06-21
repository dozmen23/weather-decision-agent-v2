"""Google Places-backed venue provider for live nearby candidates."""

import json
import math
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.models.activity import CostLevel, TransportEase
from app.models.venue import Venue, VenueAttribution
from app.services.venue_providers.json_provider import VenueCatalogError


GOOGLE_PLACES_NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"
GOOGLE_PLACES_FIELD_MASK = (
    "places.id,"
    "places.displayName,"
    "places.location,"
    "places.types,"
    "places.primaryType,"
    "places.priceLevel,"
    "places.businessStatus,"
    "places.googleMapsUri,"
    "places.attributions"
)

OUTDOOR_PLACE_TYPES = {
    "beach",
    "botanical_garden",
    "city_park",
    "cycling_park",
    "dog_park",
    "garden",
    "hiking_area",
    "national_park",
    "park",
    "picnic_ground",
    "plaza",
    "scenic_spot",
    "state_park",
    "tourist_attraction",
}

INDOOR_PLACE_TYPES = {
    "art_gallery",
    "art_museum",
    "book_store",
    "bowling_alley",
    "cafe",
    "coffee_shop",
    "community_center",
    "coworking_space",
    "fitness_center",
    "gym",
    "history_museum",
    "library",
    "museum",
    "shopping_mall",
    "spa",
    "sports_complex",
    "swimming_pool",
    "yoga_studio",
}

DEFAULT_OUTDOOR_PLACE_TYPES = (
    "park",
    "tourist_attraction",
    "plaza",
    "garden",
    "scenic_spot",
)

DEFAULT_INDOOR_PLACE_TYPES = (
    "museum",
    "shopping_mall",
    "library",
    "cafe",
    "community_center",
)

PLACE_TYPES_BY_ACTIVITY = {
    "walking": {
        True: ("park", "city_park", "tourist_attraction", "plaza"),
        False: ("shopping_mall", "museum", "community_center"),
    },
    "running": {
        True: ("park", "city_park", "athletic_field", "stadium"),
        False: ("gym", "fitness_center", "sports_complex"),
    },
    "cycling": {
        True: ("cycling_park", "park", "city_park"),
        False: ("gym", "fitness_center"),
    },
    "sports": {
        True: ("athletic_field", "stadium", "sports_complex"),
        False: ("gym", "fitness_center", "sports_complex"),
    },
    "culture": {
        True: ("tourist_attraction", "historical_landmark", "plaza"),
        False: ("museum", "art_gallery", "cultural_center"),
    },
    "study": {
        True: ("park", "city_park", "garden"),
        False: ("library", "coworking_space", "cafe"),
    },
    "social": {
        True: ("park", "plaza", "tourist_attraction"),
        False: ("cafe", "coffee_shop", "shopping_mall"),
    },
    "photography": {
        True: ("scenic_spot", "tourist_attraction", "park"),
        False: ("museum", "art_gallery", "shopping_mall"),
    },
    "relaxation": {
        True: ("park", "garden", "botanical_garden"),
        False: ("spa", "wellness_center", "library"),
    },
}

PLACE_TYPES_BY_ACTIVITY_NAME = {
    "indoor swimming": ("swimming_pool",),
    "indoor climbing": (
        "adventure_sports_center",
        "sports_activity_location",
        "gym",
    ),
    "indoor court training": (
        "sports_complex",
        "sports_activity_location",
        "arena",
    ),
    "outdoor basketball": (
        "athletic_field",
        "sports_activity_location",
        "playground",
    ),
    "outdoor tennis practice": (
        "athletic_field",
        "sports_club",
        "sports_complex",
    ),
    "indoor cycling session": (
        "fitness_center",
        "sports_club",
        "gym",
    ),
    "stationary bike workout": (
        "fitness_center",
        "gym",
    ),
}


class GooglePlacesNearbyClient(Protocol):
    """Client boundary for Google Places Nearby Search."""

    def fetch_nearby_places(
        self,
        *,
        included_types: tuple[str, ...],
        latitude: float,
        longitude: float,
        radius_meters: int,
        max_result_count: int,
    ) -> list[dict[str, Any]]:
        """Return raw Google Places objects near a coordinate."""


@dataclass(frozen=True)
class GooglePlacesClient:
    """Small HTTP client for Places API (New) Nearby Search."""

    api_key: str
    language_code: str = "tr"
    timeout_seconds: float = 8.0

    def fetch_nearby_places(
        self,
        *,
        included_types: tuple[str, ...],
        latitude: float,
        longitude: float,
        radius_meters: int,
        max_result_count: int,
    ) -> list[dict[str, Any]]:
        """Call Google Places Nearby Search and return raw place payloads."""
        payload = {
            "includedTypes": list(included_types),
            "maxResultCount": max(1, min(max_result_count, 20)),
            "rankPreference": "DISTANCE",
            "languageCode": self.language_code,
            "locationRestriction": {
                "circle": {
                    "center": {
                        "latitude": latitude,
                        "longitude": longitude,
                    },
                    "radius": float(radius_meters),
                }
            },
        }
        request = Request(
            GOOGLE_PLACES_NEARBY_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": self.api_key,
                "X-Goog-FieldMask": GOOGLE_PLACES_FIELD_MASK,
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                response_payload = json.loads(
                    response.read().decode("utf-8")
                )
        except HTTPError as exc:
            message = _google_error_message(exc)
            raise VenueCatalogError(
                f"Google Places request failed: {message}"
            ) from exc
        except (URLError, TimeoutError) as exc:
            raise VenueCatalogError(
                "Google Places request could not be completed."
            ) from exc
        except json.JSONDecodeError as exc:
            raise VenueCatalogError(
                "Google Places response contained invalid JSON."
            ) from exc

        places = response_payload.get("places", [])
        if not isinstance(places, list):
            raise VenueCatalogError("Google Places response is invalid.")
        return [place for place in places if isinstance(place, dict)]


class GooglePlacesVenueProvider:
    """Fetch and normalize live Google Places venue candidates."""

    def __init__(
        self,
        client: GooglePlacesNearbyClient,
        *,
        radius_meters: int = 2500,
        max_result_count: int = 10,
    ) -> None:
        self.client = client
        self.radius_meters = radius_meters
        self.max_result_count = max_result_count

    def get_all(self) -> list[Venue]:
        """Nearby providers need a selected origin, so no global catalog exists."""
        return []

    def find_nearby(
        self,
        *,
        activity_type: str,
        activity_name: str | None = None,
        is_outdoor: bool,
        origin_latitude: float,
        origin_longitude: float,
        limit: int,
    ) -> list[Venue]:
        """Return normalized Google Places candidates near the selected origin."""
        included_types = google_place_types_for_activity(
            activity_type,
            is_outdoor,
            activity_name=activity_name,
        )
        raw_places = self.client.fetch_nearby_places(
            included_types=included_types,
            latitude=origin_latitude,
            longitude=origin_longitude,
            radius_meters=self.radius_meters,
            max_result_count=max(limit, self.max_result_count),
        )
        venues = []
        for raw_place in raw_places:
            if not _is_usable_google_place(raw_place):
                continue
            try:
                venue = _venue_from_google_place(
                    raw_place,
                    activity_type=activity_type,
                    is_outdoor=is_outdoor,
                    origin_latitude=origin_latitude,
                    origin_longitude=origin_longitude,
                )
            except VenueCatalogError:
                continue
            venues.append(venue)
        return _deduplicate_by_name(venues)


def google_place_types_for_activity(
    activity_type: str,
    is_outdoor: bool,
    activity_name: str | None = None,
) -> tuple[str, ...]:
    """Return Google place types for a local activity type."""
    normalized_name = (activity_name or "").strip().casefold()
    if normalized_name in PLACE_TYPES_BY_ACTIVITY_NAME:
        return PLACE_TYPES_BY_ACTIVITY_NAME[normalized_name]

    normalized_type = activity_type.casefold()
    if normalized_type in PLACE_TYPES_BY_ACTIVITY:
        return PLACE_TYPES_BY_ACTIVITY[normalized_type][is_outdoor]
    return (
        DEFAULT_OUTDOOR_PLACE_TYPES
        if is_outdoor
        else DEFAULT_INDOOR_PLACE_TYPES
    )


def _venue_from_google_place(
    raw_place: dict[str, Any],
    *,
    activity_type: str,
    is_outdoor: bool,
    origin_latitude: float,
    origin_longitude: float,
) -> Venue:
    name = _place_name(raw_place)
    latitude, longitude = _place_location(raw_place)
    distance_km = _distance_km_between(
        origin_latitude,
        origin_longitude,
        latitude,
        longitude,
    )
    types = _place_types(raw_place)

    return Venue(
        name=name,
        activity_types=(activity_type.casefold(),),
        is_outdoor=is_outdoor,
        city="",
        latitude=latitude,
        longitude=longitude,
        distance_km=distance_km,
        transport_ease=_transport_ease_from_distance(distance_km),
        cost_level=_cost_level_from_google_price(raw_place, types),
        requires_reservation=False,
        source="google_places",
        tags=types,
        provider_venue_id=str(raw_place.get("id", "")).strip(),
        google_maps_uri=str(raw_place.get("googleMapsUri", "")).strip(),
        attributions=_place_attributions(raw_place),
    )


def _place_name(raw_place: dict[str, Any]) -> str:
    display_name = raw_place.get("displayName", {})
    if not isinstance(display_name, dict):
        raise VenueCatalogError("Google Places result is missing a display name.")
    name = str(display_name.get("text", "")).strip()
    if not name:
        raise VenueCatalogError("Google Places result is missing a display name.")
    return name


def _place_location(raw_place: dict[str, Any]) -> tuple[float, float]:
    location = raw_place.get("location", {})
    if not isinstance(location, dict):
        raise VenueCatalogError("Google Places result is missing a location.")
    try:
        latitude = float(location["latitude"])
        longitude = float(location["longitude"])
    except (KeyError, TypeError, ValueError) as exc:
        raise VenueCatalogError("Google Places result is missing a location.") from exc

    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise VenueCatalogError("Google Places result has invalid coordinates.")
    return latitude, longitude


def _place_types(raw_place: dict[str, Any]) -> tuple[str, ...]:
    raw_types = raw_place.get("types", [])
    if not isinstance(raw_types, list):
        return ()
    return tuple(
        str(place_type).strip().casefold()
        for place_type in raw_types
        if str(place_type).strip()
    )


def _place_attributions(
    raw_place: dict[str, Any],
) -> tuple[VenueAttribution, ...]:
    raw_attributions = raw_place.get("attributions", [])
    if not isinstance(raw_attributions, list):
        return ()

    attributions = []
    for raw_attribution in raw_attributions:
        if not isinstance(raw_attribution, dict):
            continue
        provider = str(raw_attribution.get("provider", "")).strip()
        if not provider:
            continue
        attributions.append(
            VenueAttribution(
                provider=provider,
                provider_uri=str(
                    raw_attribution.get("providerUri", "")
                ).strip(),
            )
        )
    return tuple(attributions)


def _is_usable_google_place(raw_place: dict[str, Any]) -> bool:
    return raw_place.get("businessStatus") != "CLOSED_PERMANENTLY"


def _cost_level_from_google_price(
    raw_place: dict[str, Any],
    place_types: tuple[str, ...],
) -> CostLevel:
    price_level = str(raw_place.get("priceLevel", "")).strip().upper()
    if price_level == "PRICE_LEVEL_FREE" or _looks_free(place_types):
        return CostLevel.FREE
    if price_level == "PRICE_LEVEL_INEXPENSIVE":
        return CostLevel.LOW
    if price_level == "PRICE_LEVEL_MODERATE":
        return CostLevel.MEDIUM
    if price_level in {"PRICE_LEVEL_EXPENSIVE", "PRICE_LEVEL_VERY_EXPENSIVE"}:
        return CostLevel.HIGH
    return CostLevel.MEDIUM


def _looks_free(place_types: tuple[str, ...]) -> bool:
    return any(
        place_type in OUTDOOR_PLACE_TYPES
        for place_type in place_types
    )


def _transport_ease_from_distance(distance_km: float) -> TransportEase:
    if distance_km <= 2:
        return TransportEase.EASY
    if distance_km <= 6:
        return TransportEase.MODERATE
    return TransportEase.HARD


def _deduplicate_by_name(venues: list[Venue]) -> list[Venue]:
    unique_venues: dict[str, Venue] = {}
    for venue in venues:
        key = venue.name.casefold()
        if key not in unique_venues:
            unique_venues[key] = venue
    return list(unique_venues.values())


def _distance_km_between(
    origin_latitude: float,
    origin_longitude: float,
    venue_latitude: float,
    venue_longitude: float,
) -> float:
    earth_radius_km = 6371.0
    origin_latitude_rad = math.radians(origin_latitude)
    venue_latitude_rad = math.radians(venue_latitude)
    latitude_delta = math.radians(venue_latitude - origin_latitude)
    longitude_delta = math.radians(venue_longitude - origin_longitude)
    haversine = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(origin_latitude_rad)
        * math.cos(venue_latitude_rad)
        * math.sin(longitude_delta / 2) ** 2
    )
    central_angle = 2 * math.atan2(
        math.sqrt(haversine),
        math.sqrt(1 - haversine),
    )
    return round(earth_radius_km * central_angle, 1)


def _google_error_message(exc: HTTPError) -> str:
    try:
        payload = json.loads(exc.read().decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return exc.reason
    error = payload.get("error", {})
    if isinstance(error, dict) and error.get("message"):
        return str(error["message"])
    return exc.reason
