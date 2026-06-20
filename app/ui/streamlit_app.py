"""Streamlit interface for the Weather Decision Agent."""

from collections.abc import Iterable
from dataclasses import replace
from datetime import date, timedelta
from typing import Any

import streamlit as st

try:
    import folium
    from streamlit_folium import st_folium
except ImportError:  # pragma: no cover - exercised by environments only.
    folium = None
    st_folium = None

from app.agent.decision_agent import WeatherTool
from app.agent.decision_agent import DecisionAgent
from app.agent.planner import AgentAction
from app.config import ConfigurationError
from app.llm.client import LLMServiceError
from app.llm.factory import (
    create_llm_client,
    load_llm_settings,
)
from app.models.activity import ActivityIntensity, CostLevel, TransportEase
from app.models.recommendation_history import (
    FeedbackValue,
    RecommendationHistoryItem,
)
from app.models.user_preferences import UserPreferences
from app.services.activity_service import ActivityCatalogError, ActivityService
from app.services.history_service import (
    RecommendationHistoryError,
    RecommendationHistoryRepository,
)
from app.services.recommendation_service import (
    RecommendationService,
    RecommendationWorkflowResult,
)
from app.services.venue_provider_factory import inspect_venue_provider
from app.services.weather_service import WeatherService, WeatherServiceError
from app.ui.google_maps_component import (
    google_map,
    load_google_maps_settings,
)
from evaluation.evaluation_runner import EvaluationDataError, EvaluationRunner


ACTION_LABELS = {
    AgentAction.FETCH_WEATHER: "Hava verisi alındı",
    AgentAction.LOAD_PREFERRED_CANDIDATES: "Tercihe uygun aktiviteler arandı",
    AgentAction.LOAD_RELATED_ALTERNATIVES: "Yakın kapalı alternatifler arandı",
    AgentAction.LOAD_BROADER_CANDIDATES: "Aktivite araması genişletildi",
    AgentAction.LOAD_SAFE_ALTERNATIVES: "Güvenli kapalı alan alternatifleri arandı",
    AgentAction.LOAD_GENERATED_CANDIDATES: "LLM aday aktiviteleri üretildi",
    AgentAction.SCORE_CANDIDATES: "Adaylar kurallardan geçirilip puanlandı",
    AgentAction.FINALIZE: "Son öneriler hazırlandı",
    AgentAction.STOP_NO_RESULT: "Güvenli öneri bulunamadığı için duruldu",
}

TURKISH_DAY_NAMES = (
    "Pazartesi",
    "Salı",
    "Çarşamba",
    "Perşembe",
    "Cuma",
    "Cumartesi",
    "Pazar",
)

TURKISH_MONTH_NAMES = (
    "Ocak",
    "Şubat",
    "Mart",
    "Nisan",
    "Mayıs",
    "Haziran",
    "Temmuz",
    "Ağustos",
    "Eylül",
    "Ekim",
    "Kasım",
    "Aralık",
)

USER_MODE = "user"
DEVELOPER_MODE = "developer"
LOCATION_MODE_CITY = "Şehir"
LOCATION_MODE_COORDINATES = "Harita"
DEFAULT_MAP_LATITUDE = 41.0138
DEFAULT_MAP_LONGITUDE = 28.9497
DEFAULT_MAP_ZOOM = 11

ACTIVITY_NAME_LABELS = {
    "Park Walk": "Park yürüyüşü",
    "Riverside Walk": "Sahil yürüyüşü",
    "Mall Walk": "AVM yürüyüşü",
    "Indoor Track Walk": "Kapalı pist yürüyüşü",
    "Treadmill Walk": "Koşu bandında yürüyüş",
    "Coastal Cycling": "Sahil bisikleti",
    "Park Cycling": "Parkta bisiklet",
    "Outdoor Running": "Açık havada koşu",
    "Trail Running": "Patika koşusu",
    "Indoor Track Running": "Kapalı pist koşusu",
    "Treadmill Running": "Koşu bandı",
    "Indoor Cycling Session": "Kapalı bisiklet dersi",
    "Stationary Bike Workout": "Sabit bisiklet antrenmanı",
    "Outdoor Basketball": "Açık saha basketbolu",
    "Outdoor Tennis Practice": "Açık kort tenis antrenmanı",
    "Indoor Swimming": "Kapalı havuz",
    "Indoor Climbing": "Kapalı tırmanış",
    "Indoor Court Training": "Kapalı saha antrenmanı",
    "Museum Visit": "Müze ziyareti",
    "Historical District Tour": "Tarihi semt turu",
    "Theatre Performance": "Tiyatro gösterisi",
    "Traditional Arts Exhibition": "Geleneksel sanatlar sergisi",
    "Art Workshop": "Sanat atölyesi",
    "Pottery Workshop": "Seramik atölyesi",
    "Outdoor Picnic": "Açık hava pikniği",
    "Cafe Meetup": "Kafe buluşması",
    "Public Garden Meetup": "Bahçe buluşması",
    "Board Game Meetup": "Kutu oyunu buluşması",
    "Covered Market Visit": "Kapalı pazar gezisi",
    "Community Center Meetup": "Topluluk merkezi buluşması",
    "Library Study Session": "Kütüphane çalışma seansı",
    "Outdoor Reading Garden": "Açık havada okuma molası",
    "Quiet Cafe Study": "Sessiz kafede çalışma",
    "Coworking Focus Session": "Ortak çalışma odak seansı",
    "City Photography Walk": "Şehir fotoğraf yürüyüşü",
    "Nature Photography": "Doğa fotoğrafçılığı",
    "Indoor Architecture Photography": "Kapalı mimari fotoğrafçılık",
    "Museum Photography Practice": "Müze fotoğraf pratiği",
    "Park Reading Break": "Parkta okuma molası",
    "Seaside Relaxation": "Sahil rahatlama molası",
    "Indoor Meditation Session": "Kapalı meditasyon seansı",
    "Wellness Session": "Wellness seansı",
    "Tea House Reading": "Çay evinde okuma",
}

ACTIVITY_TYPE_LABELS = {
    "walking": "Yürüyüş",
    "running": "Koşu",
    "cycling": "Bisiklet",
    "sports": "Spor",
    "culture": "Kültür",
    "social": "Sosyal",
    "study": "Çalışma",
    "photography": "Fotoğraf",
    "relaxation": "Rahatlama",
    "creative": "Yaratıcı",
}

WARNING_LABELS = {
    "Activity type does not match the user's first preference.": (
        "Bu öneri ilk seçtiğin aktivite türünden biraz farklı."
    ),
    "Indoor/outdoor setting does not match the user's preference.": (
        "Hava nedeniyle açık alan yerine kapalı alan öneriyorum."
    ),
    "Weather risk is high; a safer indoor alternative may be better.": (
        "Hava riskli görünüyor; kapalı alan daha rahat olur."
    ),
    "Weather risk is moderate; check conditions before going outside.": (
        "Hava biraz değişken; dışarı çıkmadan önce tekrar kontrol etmek "
        "iyi olur."
    ),
}

CONDITION_LABELS = {
    "Clear sky": "Açık",
    "Partly cloudy": "Parçalı bulutlu",
    "Foggy": "Sisli",
    "Drizzle": "Çiseleyen yağmur",
    "Rainy": "Yağmurlu",
    "Snowy": "Karlı",
    "Thunderstorm": "Gök gürültülü",
    "Unknown": "Bilinmiyor",
}

SEVERITY_LABELS = {
    "LOW": "rahat",
    "MODERATE": "temkinli",
    "HIGH": "riskli",
    "SEVERE": "çok riskli",
}

COST_LEVEL_LABELS = {
    CostLevel.FREE: "Ücretsiz",
    CostLevel.LOW: "Düşük",
    CostLevel.MEDIUM: "Orta",
    CostLevel.HIGH: "Yüksek",
}

INTENSITY_LABELS = {
    None: "Fark etmez",
    ActivityIntensity.LOW: "Hafif",
    ActivityIntensity.MODERATE: "Orta",
    ActivityIntensity.HIGH: "Yüksek",
}

TEMPERATURE_LEVEL_RANGES = {
    "Serin": (5, 20),
    "Ilık": (12, 30),
    "Sıcak": (18, 35),
    "Fark etmez": (-10, 45),
}

PRECIPITATION_LEVEL_LIMITS = {
    "Az": 25,
    "Orta": 45,
    "Çok": 70,
    "Fark etmez": 100,
}

WIND_LEVEL_LIMITS = {
    "Az": 18,
    "Orta": 30,
    "Çok": 45,
    "Fark etmez": 100,
}

DURATION_LEVEL_LIMITS = {
    "Kısa": 60,
    "Orta": 120,
    "Uzun": 180,
    "Fark etmez": 240,
}

PARTICIPANT_LABELS = {
    None: "Fark etmez",
    "solo": "Tek başıma",
    "friends": "Arkadaşla",
    "families": "Aileyle",
}

TRANSPORT_EASE_LABELS = {
    TransportEase.EASY: "Kolay olsun",
    TransportEase.MODERATE: "Orta olabilir",
    TransportEase.HARD: "Fark etmez",
}

VENUE_TRANSPORT_LABELS = {
    TransportEase.EASY: "kolay ulaşım",
    TransportEase.MODERATE: "orta ulaşım",
    TransportEase.HARD: "daha zahmetli ulaşım",
}


def main() -> None:
    """Render the complete Streamlit application."""
    st.set_page_config(
        page_title="Weather Decision Agent",
        page_icon="W",
        layout="wide",
    )
    _render_styles()

    history_repository = RecommendationHistoryRepository()
    view_mode = _render_view_mode()
    developer_mode = view_mode == DEVELOPER_MODE
    _render_header(developer_mode)

    activity_types = get_activity_types()
    form_values = _render_preference_form(activity_types)
    if form_values is None:
        last_result = st.session_state.get("last_workflow_result")
        if isinstance(last_result, RecommendationWorkflowResult):
            _render_workflow_result(
                last_result,
                history_repository,
                developer_mode=developer_mode,
            )
            _render_recent_history(
                history_repository,
                developer_mode=developer_mode,
            )
            if developer_mode:
                _render_evaluation_dashboard()
        else:
            _render_empty_state(developer_mode)
            if developer_mode:
                _render_evaluation_dashboard()
        return

    try:
        preferences = build_preferences(**form_values["preferences"])
        service = build_recommendation_service(
            form_values["use_llm"],
            history_repository=history_repository,
            weather_tool=form_values["weather_tool"],
        )

        with st.spinner(
            "Hava verisi alınıyor ve agent karar planını çalıştırıyor..."
        ):
            result = service.recommend(
                city=form_values["city"],
                preferences=preferences,
                recommendation_limit=form_values["recommendation_limit"],
                target_date=form_values["target_date"],
                venue_origin=form_values["venue_origin"],
            )
    except (
        ActivityCatalogError,
        ConfigurationError,
        RecommendationHistoryError,
        LLMServiceError,
        WeatherServiceError,
        ValueError,
    ) as exc:
        st.error(f"İşlem tamamlanamadı: {exc}")
        return

    st.session_state["last_workflow_result"] = result
    _render_workflow_result(
        result,
        history_repository,
        developer_mode=developer_mode,
    )
    _render_recent_history(
        history_repository,
        developer_mode=developer_mode,
    )
    if developer_mode:
        _render_evaluation_dashboard()


def get_activity_types() -> list[str]:
    """Return sorted unique activity types exposed by the catalog."""
    activity_types = {
        activity.activity_type
        for activity in ActivityService().get_all()
    }
    return sorted(activity_types)


def build_preferences(
    *,
    preferred_activity_type: str,
    prefers_outdoor: bool,
    temperature_range: tuple[int, int],
    max_precipitation_probability_percent: int,
    max_wind_speed_kmh: int,
    max_cost_level: CostLevel = CostLevel.HIGH,
    max_duration_minutes: int = 240,
    preferred_intensity: ActivityIntensity | None = None,
    avoid_reservations: bool = False,
    suitable_for: str | None = None,
    max_transport_ease: TransportEase = TransportEase.HARD,
) -> UserPreferences:
    """Convert validated UI values into the domain preference model."""
    minimum_temperature, maximum_temperature = temperature_range
    if minimum_temperature >= maximum_temperature:
        raise ValueError(
            "Minimum sıcaklık, maksimum sıcaklıktan düşük olmalıdır."
        )

    return UserPreferences(
        preferred_activity_type=preferred_activity_type,
        prefers_outdoor=prefers_outdoor,
        min_temperature_celsius=float(minimum_temperature),
        max_temperature_celsius=float(maximum_temperature),
        max_precipitation_probability_percent=(
            max_precipitation_probability_percent
        ),
        max_wind_speed_kmh=float(max_wind_speed_kmh),
        max_cost_level=max_cost_level,
        max_duration_minutes=max_duration_minutes,
        preferred_intensity=preferred_intensity,
        avoid_reservations=avoid_reservations,
        suitable_for=suitable_for,
        max_transport_ease=max_transport_ease,
    )


def build_recommendation_service(
    use_llm: bool,
    history_repository: RecommendationHistoryRepository | None = None,
    weather_tool: WeatherTool | None = None,
) -> RecommendationService:
    """Create a workflow service with optional configured LLM enrichment."""
    agent = DecisionAgent(weather_tool=weather_tool) if weather_tool else None

    if not use_llm:
        return RecommendationService(
            agent=agent,
            history_repository=history_repository,
        )

    settings = load_llm_settings()
    return RecommendationService(
        agent=agent,
        llm_client=create_llm_client(settings),
        history_repository=history_repository,
    )


def format_trace_action(action: AgentAction) -> str:
    """Return a readable Turkish label for an agent action."""
    return ACTION_LABELS.get(action, action.value)


def get_forecast_date_bounds(
    today: date | None = None,
) -> tuple[date, date]:
    """Return the inclusive seven-day selection window."""
    first_day = today or date.today()
    return first_day, first_day + timedelta(days=6)


@st.cache_data(ttl=600, show_spinner=False)
def get_sidebar_forecast(city: str):
    """Return a cached seven-day forecast for sidebar day selection."""
    return WeatherService().get_daily_forecast(city, forecast_days=7)


@st.cache_data(ttl=600, show_spinner=False)
def get_sidebar_forecast_for_coordinates(
    latitude: float,
    longitude: float,
    label: str,
):
    """Return a cached forecast for direct coordinate day selection."""
    return WeatherService().get_daily_forecast_for_coordinates(
        latitude,
        longitude,
        label=label,
        forecast_days=7,
    )


class CoordinateWeatherTool:
    """Weather tool adapter for map/coordinate-selected locations."""

    def __init__(
        self,
        latitude: float,
        longitude: float,
        label: str,
        weather_service: WeatherService | None = None,
    ) -> None:
        self.latitude = latitude
        self.longitude = longitude
        self.label = label
        self.weather_service = weather_service or WeatherService()

    def get_current_weather(self, _: str):
        """Return current weather for the selected coordinates."""
        return self.weather_service.get_current_weather_for_coordinates(
            self.latitude,
            self.longitude,
            label=self.label,
        )

    def get_weather_for_date(self, _: str, target_date: date):
        """Return forecast weather for the selected coordinates."""
        return self.weather_service.get_weather_for_coordinates_and_date(
            self.latitude,
            self.longitude,
            target_date,
            label=self.label,
        )


def format_forecast_date(forecast_date: date) -> str:
    """Return a locale-independent Turkish date label."""
    return (
        f"{forecast_date.day} "
        f"{TURKISH_MONTH_NAMES[forecast_date.month - 1]} "
        f"{forecast_date.year}, "
        f"{TURKISH_DAY_NAMES[forecast_date.weekday()]}"
    )


def format_forecast_card_label(weather, today: date | None = None) -> str:
    """Return a compact label for a selectable forecast day."""
    forecast_date = weather.forecast_date
    if forecast_date is None:
        return "Bugün"

    reference_day = today or date.today()
    if forecast_date == reference_day:
        day_label = "Bugün"
    else:
        day_label = TURKISH_DAY_NAMES[forecast_date.weekday()]

    if (
        weather.minimum_temperature_celsius is not None
        and weather.maximum_temperature_celsius is not None
    ):
        temperature_label = (
            f"{weather.minimum_temperature_celsius:.0f}-"
            f"{weather.maximum_temperature_celsius:.0f}°C"
        )
    else:
        temperature_label = f"{weather.temperature_celsius:.0f}°C"

    return (
        f"{day_label}\n"
        f"{temperature_label}\n"
        f"%{weather.precipitation_probability_percent} yağış · "
        f"{format_severity(weather.severity_level.value)}"
    )


def _extract_clicked_coordinates(
    map_output: dict[str, Any] | None,
) -> tuple[float, float] | None:
    """Return latitude/longitude from Google Maps or Folium output."""
    if not map_output:
        return None

    if "latitude" in map_output or "longitude" in map_output:
        click_payload = map_output
        latitude_key = "latitude"
        longitude_key = "longitude"
    else:
        click_payload = map_output.get("last_clicked")
        latitude_key = "lat"
        longitude_key = "lng"
    if not isinstance(click_payload, dict):
        return None

    latitude = click_payload.get(latitude_key)
    longitude = click_payload.get(longitude_key)
    if latitude is None or longitude is None:
        return None

    latitude = float(latitude)
    longitude = float(longitude)
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return None

    return latitude, longitude


def _format_coordinate_label(latitude: float, longitude: float) -> str:
    """Return a compact user-facing coordinate label."""
    return f"{latitude:.5f}, {longitude:.5f}"


def format_view_mode(mode: str) -> str:
    """Return a readable label for a UI view mode."""
    if mode == DEVELOPER_MODE:
        return "Developer Mode"
    return "User Mode"


def format_activity_name(activity_name: str) -> str:
    """Return a Turkish display label for a known activity name."""
    return ACTIVITY_NAME_LABELS.get(activity_name, activity_name)


def format_activity_type(activity_type: str) -> str:
    """Return a Turkish display label for an activity type."""
    return ACTIVITY_TYPE_LABELS.get(activity_type, activity_type)


def format_warning(warning: str) -> str:
    """Return a user-facing warning label."""
    return WARNING_LABELS.get(warning, warning)


def format_condition(condition: str) -> str:
    """Return a Turkish condition label."""
    return CONDITION_LABELS.get(condition, condition)


def format_severity(severity: str) -> str:
    """Return a Turkish severity label."""
    return SEVERITY_LABELS.get(severity, severity.lower())


def format_cost_level(cost_level: CostLevel) -> str:
    """Return a Turkish cost level label."""
    return COST_LEVEL_LABELS.get(cost_level, cost_level.value)


def format_intensity(intensity: ActivityIntensity | None) -> str:
    """Return a Turkish intensity label."""
    return INTENSITY_LABELS.get(
        intensity,
        intensity.value if intensity is not None else "Fark etmez",
    )


def format_participant_preference(suitable_for: str | None) -> str:
    """Return a Turkish participant preference label."""
    return PARTICIPANT_LABELS.get(suitable_for, suitable_for or "Fark etmez")


def format_transport_ease(transport_ease: TransportEase) -> str:
    """Return a Turkish transport ease preference label."""
    return TRANSPORT_EASE_LABELS.get(transport_ease, transport_ease.value)


def format_venue_transport_ease(transport_ease: TransportEase) -> str:
    """Return a user-facing venue transport label."""
    return VENUE_TRANSPORT_LABELS.get(transport_ease, transport_ease.value)


def format_venue_distance(distance_km: float) -> str:
    """Return a compact user-facing venue distance label."""
    if distance_km < 1:
        return f"{round(distance_km * 1000):.0f} m"
    return f"{distance_km:.1f} km"


def format_venue_distance_level(distance_km: float) -> str:
    """Return a simple proximity label for a venue distance."""
    if distance_km <= 1:
        return "çok yakın"
    if distance_km <= 5:
        return "yakın"
    if distance_km <= 10:
        return "orta uzaklıkta"
    return "uzak"


def format_reservation_requirement(requires_reservation: bool) -> str:
    """Return a simple reservation label for a venue."""
    if requires_reservation:
        return "rezervasyon gerekebilir"
    return "rezervasyonsuz olabilir"


def format_venue_filter_status(passed: bool) -> str:
    """Return a readable venue filter trace status."""
    return "Geçti" if passed else "Elendi"


def format_venue_provider_label(provider: str) -> str:
    """Return a readable label for the active venue provider."""
    if provider == "json":
        return "JSON demo katalog"
    if provider == "external":
        return "External provider"
    if provider == "google_places":
        return "Google Places"
    return provider


def calculate_map_center(
    coordinates: list[tuple[float, float]],
) -> tuple[float, float]:
    """Return the center point for a list of latitude/longitude pairs."""
    if not coordinates:
        return DEFAULT_MAP_LATITUDE, DEFAULT_MAP_LONGITUDE

    return (
        sum(latitude for latitude, _ in coordinates) / len(coordinates),
        sum(longitude for _, longitude in coordinates) / len(coordinates),
    )


def format_feedback_value(feedback: FeedbackValue | None) -> str:
    """Return a user-facing feedback label."""
    if feedback is FeedbackValue.POSITIVE:
        return "Beğendin"
    if feedback is FeedbackValue.NEGATIVE:
        return "Beğenmedin"
    return "Henüz yok"


def format_history_status(status: str) -> str:
    """Return a user-facing history status label."""
    if status == "completed":
        return "Öneri hazırlandı"
    if status == "no_recommendation":
        return "Güvenli öneri bulunamadı"
    return status


def format_history_recommendations(
    recommendations: list[RecommendationHistoryItem],
) -> str:
    """Return compact user-facing activity names for a history record."""
    if not recommendations:
        return "Öneri yok"
    return ", ".join(
        format_activity_name(item.activity_name) for item in recommendations
    )


def format_evaluation_verdict(verdict: str) -> str:
    """Return a readable evaluator verdict label."""
    if verdict == "approved":
        return "Onaylandı"
    if verdict == "rejected":
        return "Reddedildi"
    if verdict == "no_recommendation":
        return "Güvenli öneri yok"
    return verdict


def format_scenario_result(passed: bool) -> str:
    """Return a compact scenario result label."""
    return "Geçti" if passed else "Kaldı"


def _render_header(developer_mode: bool) -> None:
    st.title("Weather Decision Agent")
    st.markdown(
        """
        Bugünkü hava ve tercihlerini birlikte düşünerek sana en rahat
        aktiviteyi önerir. Hava açık alan için iyi değilse yakın bir kapalı
        alternatif bulur.
        """
    )
    if developer_mode:
        st.caption(
            "Karar kuralları ve puanlar deterministiktir. LLM yalnızca aday, "
            "açıklama ve ikinci görüş desteği verir."
        )
    else:
        st.caption(
            "Açık alan iyi görünmüyorsa daha rahat bir kapalı alternatif "
            "önerir."
        )


def _render_view_mode() -> str:
    with st.sidebar:
        st.header("Mod")
        mode_label = st.radio(
            "Görünüm",
            options=["User Mode", "Developer Mode"],
            horizontal=True,
        )
    return DEVELOPER_MODE if mode_label == "Developer Mode" else USER_MODE


def _render_preference_form(
    activity_types: list[str],
) -> dict[str, object] | None:
    with st.sidebar:
        st.header("Tercihler")
        location_mode = st.radio(
            "Konum",
            options=[LOCATION_MODE_CITY, LOCATION_MODE_COORDINATES],
            horizontal=True,
        )
        st.session_state["active_location_mode"] = location_mode
        if location_mode == LOCATION_MODE_CITY:
            city = st.text_input("Şehir", value="Istanbul")
            location_label = city.strip()
            weather_tool = None
            venue_origin = None
            target_date = _render_city_forecast_selector(city)
        else:
            location_label = st.text_input(
                "Konum adı",
                value="Seçilen konum",
            )
            latitude, longitude = _render_location_map_picker()
            weather_tool = CoordinateWeatherTool(
                latitude,
                longitude,
                location_label.strip() or "Seçilen konum",
            )
            venue_origin = (latitude, longitude)
            target_date = _render_coordinate_forecast_selector(
                latitude,
                longitude,
                location_label.strip() or "Seçilen konum",
            )

        with st.form("recommendation_form"):
            preferred_activity_type = st.selectbox(
                "Tercih edilen aktivite türü",
                options=activity_types,
                index=_default_activity_index(activity_types),
                format_func=format_activity_type,
            )
            setting = st.radio(
                "Ortam tercihi",
                options=["Açık alan", "Kapalı alan"],
                horizontal=True,
            )
            temperature_level = st.selectbox(
                "Sıcaklık tercihi",
                options=list(TEMPERATURE_LEVEL_RANGES),
                index=1,
            )
            precipitation_level = st.selectbox(
                "Yağış toleransı",
                options=list(PRECIPITATION_LEVEL_LIMITS),
                index=1,
            )
            wind_level = st.selectbox(
                "Rüzgâr toleransı",
                options=list(WIND_LEVEL_LIMITS),
                index=1,
            )
            with st.expander("Daha fazla tercih", expanded=False):
                max_cost_level = st.selectbox(
                    "En fazla bütçe",
                    options=list(CostLevel),
                    index=list(CostLevel).index(CostLevel.HIGH),
                    format_func=format_cost_level,
                )
                duration_level = st.selectbox(
                    "Süre",
                    options=list(DURATION_LEVEL_LIMITS),
                    index=2,
                )
                preferred_intensity = st.selectbox(
                    "Yoğunluk",
                    options=[
                        None,
                        ActivityIntensity.LOW,
                        ActivityIntensity.MODERATE,
                        ActivityIntensity.HIGH,
                    ],
                    index=0,
                    format_func=format_intensity,
                )
                avoid_reservations = st.checkbox(
                    "Rezervasyon istemiyorum",
                    value=False,
                )
                suitable_for = st.selectbox(
                    "Kimle?",
                    options=[None, "solo", "friends", "families"],
                    index=0,
                    format_func=format_participant_preference,
                )
                max_transport_ease = st.selectbox(
                    "Ulaşım kolaylığı",
                    options=[
                        TransportEase.EASY,
                        TransportEase.MODERATE,
                        TransportEase.HARD,
                    ],
                    index=2,
                    format_func=format_transport_ease,
                )
            recommendation_limit = st.slider(
                "Öneri sayısı",
                min_value=1,
                max_value=5,
                value=3,
            )
            use_llm = st.checkbox(
                "LLM aday üretimi, açıklaması ve ikinci hakem",
                value=True,
                help=(
                    "Açıldığında güvenli sonuç bulunamazsa aday üretir; "
                    "doğrulanmış sonuçları açıklar ve ikinci değerlendirme "
                    "yapar."
                ),
            )
            submitted = st.form_submit_button(
                "Öneri üret",
                use_container_width=True,
                type="primary",
            )

    if not submitted:
        return None

    if len(location_label.strip()) < 2:
        raise ValueError("Şehir adı en az iki karakter olmalıdır.")

    return {
        "city": location_label.strip(),
        "target_date": target_date,
        "recommendation_limit": recommendation_limit,
        "use_llm": use_llm,
        "weather_tool": weather_tool,
        "venue_origin": venue_origin,
        "preferences": {
            "preferred_activity_type": preferred_activity_type,
            "prefers_outdoor": setting == "Açık alan",
            "temperature_range": TEMPERATURE_LEVEL_RANGES[temperature_level],
            "max_precipitation_probability_percent": (
                PRECIPITATION_LEVEL_LIMITS[precipitation_level]
            ),
            "max_wind_speed_kmh": WIND_LEVEL_LIMITS[wind_level],
            "max_cost_level": max_cost_level,
            "max_duration_minutes": DURATION_LEVEL_LIMITS[duration_level],
            "preferred_intensity": preferred_intensity,
            "avoid_reservations": avoid_reservations,
            "suitable_for": suitable_for,
            "max_transport_ease": max_transport_ease,
        },
    }


def _render_location_map_picker() -> tuple[float, float]:
    latitude = float(
        st.session_state.get("selected_map_latitude", DEFAULT_MAP_LATITUDE)
    )
    longitude = float(
        st.session_state.get("selected_map_longitude", DEFAULT_MAP_LONGITUDE)
    )

    with st.container(border=True):
        st.markdown("**Seçilen nokta**")
        st.caption(_format_coordinate_label(latitude, longitude))
        st.button(
            "Haritada seç",
            key="open_location_picker_dialog",
            use_container_width=True,
            on_click=_open_location_picker_dialog,
            type="secondary",
        )

    if st.session_state.get("show_location_picker_dialog"):
        _render_location_picker_dialog()

    maps_settings = load_google_maps_settings()
    if (
        not maps_settings.browser_api_key
        and (folium is None or st_folium is None)
    ):
        st.info(
            "Google Maps tarayıcı anahtarı veya streamlit-folium gerekli. "
            "Şimdilik koordinatı elle girebilirsin."
        )

    with st.expander(
        "Koordinatı elle düzelt",
        expanded=(
            not maps_settings.browser_api_key
            and (folium is None or st_folium is None)
        ),
    ):
        latitude = st.number_input(
            "Enlem",
            min_value=-90.0,
            max_value=90.0,
            value=latitude,
            format="%.6f",
        )
        longitude = st.number_input(
            "Boylam",
            min_value=-180.0,
            max_value=180.0,
            value=longitude,
            format="%.6f",
        )

    st.session_state["selected_map_latitude"] = latitude
    st.session_state["selected_map_longitude"] = longitude
    return latitude, longitude


def _open_location_picker_dialog() -> None:
    st.session_state["show_location_picker_dialog"] = True


@st.dialog("Haritada konum seç", width="large")
def _render_location_picker_dialog() -> None:
    latitude = float(
        st.session_state.get("selected_map_latitude", DEFAULT_MAP_LATITUDE)
    )
    longitude = float(
        st.session_state.get("selected_map_longitude", DEFAULT_MAP_LONGITUDE)
    )

    st.markdown("**Haritada istediğin noktaya tıkla.**")
    st.caption(
        "Seçim yapılınca pencere kapanır ve hava tahmini bu noktadan alınır."
    )

    maps_settings = load_google_maps_settings()
    if maps_settings.browser_api_key:
        map_output = google_map(
            api_key=maps_settings.browser_api_key,
            center=(latitude, longitude),
            zoom=DEFAULT_MAP_ZOOM,
            origin=(latitude, longitude),
            interactive=True,
            height=560,
            key="google_location_picker_dialog_map",
        )
        clicked_coordinates = _extract_clicked_coordinates(map_output)
        if clicked_coordinates is not None:
            _save_map_selection(*clicked_coordinates)
        st.caption(
            f"Şu an seçili: {_format_coordinate_label(latitude, longitude)}"
        )
        if st.button("Vazgeç", use_container_width=True):
            st.session_state["show_location_picker_dialog"] = False
            st.rerun()
        return

    if folium is None or st_folium is None:
        st.warning(
            "Google Maps tarayıcı anahtarı ayarlanmamış ve fallback harita "
            "kullanılamıyor. "
            "Koordinatı sidebar'dan elle girebilirsin."
        )
        if st.button("Kapat", use_container_width=True):
            st.session_state["show_location_picker_dialog"] = False
            st.rerun()
        return

    map_object = folium.Map(
        location=[latitude, longitude],
        zoom_start=DEFAULT_MAP_ZOOM,
        tiles="CartoDB positron",
        control_scale=True,
    )
    folium.CircleMarker(
        [latitude, longitude],
        radius=8,
        color="#ff4b4b",
        fill=True,
        fill_color="#ff4b4b",
        fill_opacity=0.9,
        tooltip="Şu an seçili nokta",
    ).add_to(map_object)
    folium.LatLngPopup().add_to(map_object)

    map_output = st_folium(
        map_object,
        height=560,
        use_container_width=True,
        key="location_picker_dialog_map",
    )
    clicked_coordinates = _extract_clicked_coordinates(map_output)
    if clicked_coordinates is not None:
        _save_map_selection(*clicked_coordinates)

    st.caption(f"Şu an seçili: {_format_coordinate_label(latitude, longitude)}")
    if st.button("Vazgeç", use_container_width=True):
        st.session_state["show_location_picker_dialog"] = False
        st.rerun()


def _save_map_selection(latitude: float, longitude: float) -> None:
    """Persist a clicked map coordinate and close the picker dialog."""
    st.session_state["selected_map_latitude"] = latitude
    st.session_state["selected_map_longitude"] = longitude
    st.session_state["show_location_picker_dialog"] = False
    st.toast("Konum seçildi.")
    st.rerun()


def _render_city_forecast_selector(city: str) -> date:
    normalized_city = city.strip()
    if len(normalized_city) < 2:
        first_forecast_date, last_forecast_date = get_forecast_date_bounds()
        return st.date_input(
            "Planlanan gün",
            value=first_forecast_date,
            min_value=first_forecast_date,
            max_value=last_forecast_date,
            format="DD/MM/YYYY",
        )

    try:
        forecasts = get_sidebar_forecast(normalized_city)
    except WeatherServiceError:
        st.info("Gün kartları şu an alınamadı; tarihi elle seçebilirsin.")
        first_forecast_date, last_forecast_date = get_forecast_date_bounds()
        return st.date_input(
            "Planlanan gün",
            value=first_forecast_date,
            min_value=first_forecast_date,
            max_value=last_forecast_date,
            format="DD/MM/YYYY",
        )

    forecast_dates = [
        weather.forecast_date
        for weather in forecasts
        if weather.forecast_date is not None
    ]
    if not forecast_dates:
        first_forecast_date, last_forecast_date = get_forecast_date_bounds()
        return st.date_input(
            "Planlanan gün",
            value=first_forecast_date,
            min_value=first_forecast_date,
            max_value=last_forecast_date,
            format="DD/MM/YYYY",
        )

    selected_date = st.session_state.get("selected_forecast_date")
    if selected_date not in forecast_dates:
        selected_date = forecast_dates[0]

    st.caption("Planlanacak gün")
    columns = st.columns(2)
    for index, weather in enumerate(forecasts):
        if weather.forecast_date is None:
            continue

        is_selected = weather.forecast_date == selected_date
        clicked = columns[index % 2].button(
            format_forecast_card_label(weather),
            key=f"forecast_day_{weather.forecast_date.isoformat()}",
            type="primary" if is_selected else "secondary",
            use_container_width=True,
        )
        if clicked:
            selected_date = weather.forecast_date

    st.session_state["selected_forecast_date"] = selected_date
    return selected_date


def _render_coordinate_forecast_selector(
    latitude: float,
    longitude: float,
    label: str,
) -> date:
    try:
        forecasts = get_sidebar_forecast_for_coordinates(
            latitude,
            longitude,
            label,
        )
    except WeatherServiceError:
        st.info("Gün kartları şu an alınamadı; tarihi elle seçebilirsin.")
        first_forecast_date, last_forecast_date = get_forecast_date_bounds()
        return st.date_input(
            "Planlanan gün",
            value=first_forecast_date,
            min_value=first_forecast_date,
            max_value=last_forecast_date,
            format="DD/MM/YYYY",
        )

    forecast_dates = [
        weather.forecast_date
        for weather in forecasts
        if weather.forecast_date is not None
    ]
    if not forecast_dates:
        first_forecast_date, last_forecast_date = get_forecast_date_bounds()
        return st.date_input(
            "Planlanan gün",
            value=first_forecast_date,
            min_value=first_forecast_date,
            max_value=last_forecast_date,
            format="DD/MM/YYYY",
        )

    selected_date = st.session_state.get("selected_coordinate_forecast_date")
    if selected_date not in forecast_dates:
        selected_date = forecast_dates[0]

    st.caption("Planlanacak gün")
    columns = st.columns(2)
    for index, weather in enumerate(forecasts):
        if weather.forecast_date is None:
            continue

        is_selected = weather.forecast_date == selected_date
        clicked = columns[index % 2].button(
            format_forecast_card_label(weather),
            key=f"coordinate_forecast_day_{weather.forecast_date.isoformat()}",
            type="primary" if is_selected else "secondary",
            use_container_width=True,
        )
        if clicked:
            selected_date = weather.forecast_date

    st.session_state["selected_coordinate_forecast_date"] = selected_date
    return selected_date


def _render_empty_state(developer_mode: bool) -> None:
    st.info(
        "Soldaki tercihleri düzenleyip **Öneri üret** düğmesine basarak "
        "agent akışını başlat."
    )
    columns = st.columns(3)
    if developer_mode:
        columns[0].metric("Karar araçları", "3", "Weather, Catalog, Scoring")
        columns[1].metric("Evaluation kontrolleri", "6")
        columns[2].metric("Otomatik test", "153 başarılı")
        _render_venue_provider_status()
    else:
        columns[0].metric("Görünüm", "Sade")
        columns[1].metric("Geçmiş", "Aktif")
        columns[2].metric("Feedback", "Hazır")


def _render_venue_provider_status() -> None:
    st.subheader("Venue provider")
    inspection = inspect_venue_provider()

    columns = st.columns(4)
    columns[0].metric(
        "Aktif kaynak",
        format_venue_provider_label(inspection.provider),
    )
    columns[1].metric(
        "JSON katalog",
        inspection.json_path or "varsayılan demo",
    )
    columns[2].metric(
        "Durum",
        "hazır" if inspection.available else "hatalı",
    )
    columns[3].metric("Mekan", str(inspection.venue_count))

    if inspection.sources:
        st.caption("Kaynaklar: " + ", ".join(inspection.sources))
    if not inspection.available:
        st.error(f"Venue provider yüklenemedi: {inspection.error}")
    if inspection.provider == "external":
        st.warning(
            "External provider seçili ama canlı client henüz bağlanmadı. "
            "Bu mod için provider client wiring tamamlanmalı."
        )
    if inspection.provider == "google_places":
        st.caption(
            "Google Places canlı araması, kullanıcı bir konum seçip öneri "
            "istediğinde yapılır."
        )


def _render_workflow_result(
    result: RecommendationWorkflowResult,
    history_repository: RecommendationHistoryRepository,
    developer_mode: bool,
) -> None:
    agent_result = result.agent_result

    _render_weather(agent_result.weather, developer_mode)
    if not developer_mode:
        st.info(_format_user_weather_summary(agent_result.weather))

    if not agent_result.recommendations:
        st.warning(agent_result.message)
    else:
        st.subheader("Öneriler")
        for index, recommendation in enumerate(
            agent_result.recommendations,
            start=1,
        ):
            _render_recommendation_card(
                index=index,
                recommendation=recommendation,
                developer_mode=developer_mode,
                explanation=(
                    result.explanation.recommendation_details.get(
                        recommendation.activity.name
                    )
                    if result.explanation
                    else None
                ),
                weather=agent_result.weather,
                preferences=result.preferences,
            )

    _render_feedback_controls(result, history_repository)

    if developer_mode:
        left_column, right_column = st.columns(2)
        with left_column:
            _render_evaluation(result)
        with right_column:
            _render_llm_judgment(result)

        _render_agent_trace(agent_result.trace)


def _render_weather(weather, developer_mode: bool) -> None:
    if weather.forecast_date is None:
        heading = f"Güncel hava: {weather.city}"
        temperature_label = f"{weather.temperature_celsius:.1f} °C"
    else:
        heading = (
            f"{format_forecast_date(weather.forecast_date)} tahmini: "
            f"{weather.city}"
        )
        if (
            weather.minimum_temperature_celsius is not None
            and weather.maximum_temperature_celsius is not None
        ):
            temperature_label = (
                f"{weather.minimum_temperature_celsius:.1f} – "
                f"{weather.maximum_temperature_celsius:.1f} °C"
            )
        else:
            temperature_label = f"{weather.temperature_celsius:.1f} °C"

    st.subheader(heading)
    if not developer_mode:
        st.markdown(
            (
                f"**Hava:** {format_condition(weather.condition)} · "
                f"{temperature_label} · yağış "
                f"%{weather.precipitation_probability_percent} · "
                f"rüzgâr {weather.wind_speed_kmh:.1f} km/h · "
                f"{format_severity(weather.severity_level.value)}"
            )
        )
        return

    columns = st.columns(5)
    columns[0].metric("Sıcaklık", temperature_label)
    columns[1].metric(
        "Yağış ihtimali",
        f"%{weather.precipitation_probability_percent}",
    )
    columns[2].metric("Rüzgâr", f"{weather.wind_speed_kmh:.1f} km/h")
    columns[3].metric("Durum", format_condition(weather.condition))
    columns[4].metric("Risk", format_severity(weather.severity_level.value))

    if developer_mode:
        with st.expander("Raw weather data", expanded=False):
            st.json(
                {
                    "city": weather.city,
                    "forecast_date": (
                        weather.forecast_date.isoformat()
                        if weather.forecast_date
                        else None
                    ),
                    "temperature_celsius": weather.temperature_celsius,
                    "minimum_temperature_celsius": (
                        weather.minimum_temperature_celsius
                    ),
                    "maximum_temperature_celsius": (
                        weather.maximum_temperature_celsius
                    ),
                    "precipitation_probability_percent": (
                        weather.precipitation_probability_percent
                    ),
                    "wind_speed_kmh": weather.wind_speed_kmh,
                    "condition": weather.condition,
                    "severity_level": weather.severity_level.value,
                }
            )


def _render_recommendation_card(
    *,
    index: int,
    recommendation,
    developer_mode: bool,
    explanation: str | None,
    weather,
    preferences: UserPreferences | None,
) -> None:
    with st.container(border=True):
        title_column, score_column = st.columns([4, 1.25])
        title_column.markdown(
            f"### {index}. {format_activity_name(recommendation.activity.name)}"
        )
        if developer_mode:
            score_column.markdown(
                (
                    '<div class="score-badge">'
                    '<span>Uygunluk</span>'
                    f"<strong>{recommendation.score:.1f}/100</strong>"
                    "</div>"
                ),
                unsafe_allow_html=True,
            )
        else:
            score_column.markdown(
                (
                    '<div class="score-badge soft">'
                    '<span>Durum</span>'
                    f"<strong>{_format_user_fit_label(recommendation)}</strong>"
                    "</div>"
                ),
                unsafe_allow_html=True,
            )

        setting = (
            "Açık alan" if recommendation.activity.is_outdoor else "Kapalı alan"
        )
        activity_type_label = format_activity_type(
            recommendation.activity.activity_type
        )
        st.caption(
            f"{activity_type_label} · {setting}"
        )

        if not developer_mode:
            _render_user_recommendation_explanation(
                recommendation,
                explanation,
                weather,
                preferences,
            )
        elif explanation:
            st.markdown(explanation)
        elif developer_mode:
            st.markdown(
                "Deterministik puan bileşenleri: "
                + recommendation.reasoning
            )

        if developer_mode:
            breakdown = recommendation.score_breakdown
            score_columns = st.columns(4)
            score_columns[0].metric(
                "Hava güvenliği",
                f"{breakdown.weather_safety:.1f}/30",
            )
            score_columns[1].metric(
                "Tercih eşleşmesi",
                f"{breakdown.preference_match:.1f}/35",
            )
            score_columns[2].metric(
                "Konfor",
                f"{breakdown.comfort_match:.1f}/20",
            )
            score_columns[3].metric(
                "Pratiklik",
                f"{breakdown.practicality:.1f}/15",
            )

        for warning in recommendation.warnings:
            st.warning(format_warning(warning))

        if recommendation.venues:
            _render_venue_candidates(
                recommendation.venues,
                developer_mode,
                key_prefix=f"recommendation_{index}",
            )
        if developer_mode and recommendation.venue_filter_trace:
            _render_venue_filter_trace(recommendation.venue_filter_trace)


def _render_venue_candidates(
    venues,
    developer_mode: bool,
    key_prefix: str,
) -> None:
    st.markdown("**Mekan adayları**")
    google_venues = [
        venue for venue in venues if venue.source == "google_places"
    ]
    if google_venues:
        st.markdown(
            '<div translate="no" style="color:#5e5e5e;font-size:1rem;'
            'letter-spacing:normal;white-space:nowrap;margin-bottom:0.5rem;">'
            "Google Maps</div>",
            unsafe_allow_html=True,
        )
    for venue in venues:
        st.markdown(f"**{venue.name}**")
        st.caption(
            f"{format_venue_distance_level(venue.distance_km)} · "
            f"sana yaklaşık {format_venue_distance(venue.distance_km)} · "
            f"{format_venue_transport_ease(venue.transport_ease)}"
        )
        st.caption(
            f"{format_cost_level(venue.cost_level)} bütçe · "
            f"{format_reservation_requirement(venue.requires_reservation)}"
        )
        if developer_mode:
            st.caption(
                f"source: {venue.source} | "
                f"lat/lon: {venue.latitude:.4f}, {venue.longitude:.4f}"
            )
        if venue.google_maps_uri:
            st.link_button(
                "Google Maps'te aç",
                venue.google_maps_uri,
                icon=":material/map:",
            )
        for attribution in venue.attributions:
            if attribution.provider_uri:
                st.markdown(
                    f"Kaynak: [{attribution.provider}]"
                    f"({attribution.provider_uri})"
                )
            else:
                st.caption(f"Kaynak: {attribution.provider}")
    with st.expander("Mekanları haritada gör", expanded=False):
        _render_venue_map(venues, key_prefix)


def _render_venue_map(venues, key_prefix: str) -> None:
    google_venues = [
        venue for venue in venues if venue.source == "google_places"
    ]
    if google_venues:
        maps_settings = load_google_maps_settings()
        if not maps_settings.browser_api_key:
            st.info(
                "Google mekanlarını haritada göstermek için "
                "GOOGLE_MAPS_BROWSER_API_KEY ayarlanmalı."
            )
            return

        origin = _get_selected_map_origin()
        coordinates = [
            (venue.latitude, venue.longitude) for venue in google_venues
        ]
        if origin is not None:
            coordinates.append(origin)
        google_map(
            api_key=maps_settings.browser_api_key,
            center=calculate_map_center(coordinates),
            zoom=12,
            markers=_google_venue_marker_payload(google_venues),
            origin=origin,
            interactive=False,
            height=320,
            key=_venue_map_key(google_venues, f"google_{key_prefix}"),
        )
        return

    if folium is None or st_folium is None:
        st.info("Mekan haritası için streamlit-folium kurulmalı.")
        return

    origin = _get_selected_map_origin()
    coordinates = [(venue.latitude, venue.longitude) for venue in venues]
    if origin is not None:
        coordinates.append(origin)
    center_latitude, center_longitude = calculate_map_center(coordinates)

    map_object = folium.Map(
        location=[center_latitude, center_longitude],
        zoom_start=12,
        tiles="CartoDB positron",
        control_scale=True,
    )

    if origin is not None:
        folium.CircleMarker(
            [origin[0], origin[1]],
            radius=8,
            color="#2563eb",
            fill=True,
            fill_color="#2563eb",
            fill_opacity=0.9,
            tooltip="Seçtiğin nokta",
        ).add_to(map_object)

    for index, venue in enumerate(venues, start=1):
        folium.Marker(
            [venue.latitude, venue.longitude],
            tooltip=f"{index}. {venue.name}",
            popup=(
                f"{venue.name}<br>"
                f"{format_venue_distance_level(venue.distance_km)} · "
                f"{format_venue_distance(venue.distance_km)}"
            ),
            icon=folium.Icon(color="orange", icon="info-sign"),
        ).add_to(map_object)

    if len(coordinates) > 1:
        latitudes = [latitude for latitude, _ in coordinates]
        longitudes = [longitude for _, longitude in coordinates]
        map_object.fit_bounds(
            [
                [min(latitudes), min(longitudes)],
                [max(latitudes), max(longitudes)],
            ]
        )

    st_folium(
        map_object,
        height=260,
        use_container_width=True,
        key=_venue_map_key(venues, key_prefix),
    )


def _google_venue_marker_payload(venues) -> list[dict[str, object]]:
    """Return the minimal trusted venue payload used by the map component."""
    return [
        {
            "name": venue.name,
            "latitude": venue.latitude,
            "longitude": venue.longitude,
            "google_maps_uri": venue.google_maps_uri,
        }
        for venue in venues
    ]


def _get_selected_map_origin() -> tuple[float, float] | None:
    if st.session_state.get("active_location_mode") != LOCATION_MODE_COORDINATES:
        return None

    latitude = st.session_state.get("selected_map_latitude")
    longitude = st.session_state.get("selected_map_longitude")
    if latitude is None or longitude is None:
        return None

    latitude = float(latitude)
    longitude = float(longitude)
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return None
    return latitude, longitude


def _venue_map_key(venues, key_prefix: str) -> str:
    venue_signature = "|".join(venue.name for venue in venues)
    signature_value = sum(ord(character) for character in venue_signature)
    return f"venue_map_{key_prefix}_{signature_value}"


def _render_venue_filter_trace(venue_filter_trace) -> None:
    with st.expander("Mekan filtre izi", expanded=False):
        for trace in venue_filter_trace:
            status = format_venue_filter_status(trace.passed)
            st.markdown(f"**{status} · {trace.venue_name}**")
            st.caption(
                f"mesafe: {format_venue_distance(trace.distance_km)} | "
                f"neden: {'; '.join(trace.reasons)}"
            )


def _render_user_recommendation_explanation(
    recommendation,
    explanation: str | None,
    weather,
    preferences: UserPreferences | None,
) -> None:
    reason = (
        _select_user_explanation(
            recommendation,
            explanation,
            weather,
            preferences,
        )
        if explanation
        else _format_user_recommendation_reason(
            recommendation,
            weather,
            preferences,
        )
    )
    st.markdown("**Neden bunu önerdim?**")
    st.write(reason)

    attention_items = _build_attention_items(
        recommendation,
        weather,
        preferences,
    )
    if attention_items:
        st.markdown("**Dikkat et**")
        for item in attention_items:
            st.caption(f"- {item}")


def _format_user_recommendation_reason(
    recommendation,
    weather=None,
    preferences: UserPreferences | None = None,
) -> str:
    setting = "açık alan" if recommendation.activity.is_outdoor else "kapalı alan"
    activity_type = format_activity_type(
        recommendation.activity.activity_type
    ).lower()
    if (
        not recommendation.activity.is_outdoor
        and preferences is not None
        and preferences.prefers_outdoor
    ):
        preferred_type = format_activity_type(
            preferences.preferred_activity_type
        ).lower()
        recommendation_name = format_activity_name(
            recommendation.activity.name
        ).lower()
        reasons = _format_weather_limit_reasons(weather, preferences)
        if reasons:
            return (
                f"İlk tercihin açık alanda {preferred_type} yapmaktı; "
                f"{_join_reason_parts(reasons)}. Bu yüzden "
                f"{recommendation_name} daha rahat bir seçenek."
            )
        return (
            f"Açık alan bugün biraz temkin istiyor. Bu yüzden "
            f"{recommendation_name} daha kontrollü ve rahat bir alternatif."
        )

    if not recommendation.activity.is_outdoor:
        return (
            f"Hava dışarıda pek rahat görünmediği için bu {activity_type} "
            f"seçeneği daha güvenli ve konforlu bir {setting} alternatifi."
        )

    if weather is not None and preferences is not None:
        return (
            f"Bu {activity_type} seçeneği hava sınırlarınla uyumlu görünüyor: "
            f"yağış %{weather.precipitation_probability_percent}, rüzgâr "
            f"{weather.wind_speed_kmh:.0f} km/h ve risk "
            f"{format_severity(weather.severity_level.value)}."
        )

    return (
        f"Seçtiğin aktivite türüne yakın, hava koşullarıyla uyumlu bir "
        f"{setting} seçeneği."
    )


def _select_user_explanation(
    recommendation,
    explanation: str,
    weather=None,
    preferences: UserPreferences | None = None,
) -> str:
    technical_markers = (
        "/100",
        "/30",
        "/35",
        "/20",
        "/15",
        "puan",
        "score",
        "breakdown",
        "deterministik",
        "evaluator",
    )
    normalized = explanation.casefold()
    if any(marker in normalized for marker in technical_markers):
        return _format_user_recommendation_reason(
            recommendation,
            weather,
            preferences,
        )
    return explanation


def _format_weather_limit_reasons(
    weather,
    preferences: UserPreferences,
) -> list[str]:
    if weather is None:
        return []

    reasons: list[str] = []
    if weather.severity_level.value == "SEVERE":
        reasons.append("hava çok riskli görünüyor")
    elif weather.severity_level.value == "HIGH":
        reasons.append("hava riskli görünüyor")

    precipitation = weather.precipitation_probability_percent
    if precipitation > preferences.max_precipitation_probability_percent:
        reasons.append(
            f"yağış ihtimali %{precipitation}, sınırın olan "
            f"%{preferences.max_precipitation_probability_percent} değerini aşıyor"
        )

    wind_speed = weather.wind_speed_kmh
    if wind_speed > preferences.max_wind_speed_kmh:
        reasons.append(
            f"rüzgâr {wind_speed:.0f} km/h, sınırın olan "
            f"{preferences.max_wind_speed_kmh:.0f} km/h değerini aşıyor"
        )

    temperature = weather.temperature_celsius
    if temperature < preferences.min_temperature_celsius:
        reasons.append(
            f"sıcaklık {temperature:.0f}°C, konfor aralığının altında"
        )
    elif temperature > preferences.max_temperature_celsius:
        reasons.append(
            f"sıcaklık {temperature:.0f}°C, konfor aralığının üstünde"
        )

    return reasons


def _join_reason_parts(reasons: list[str]) -> str:
    if len(reasons) <= 1:
        return "".join(reasons)
    return ", ".join(reasons[:-1]) + " ve " + reasons[-1]


def _build_attention_items(
    recommendation,
    weather=None,
    preferences: UserPreferences | None = None,
) -> list[str]:
    items = [format_warning(warning) for warning in recommendation.warnings]
    if (
        not recommendation.activity.is_outdoor
        and preferences is not None
        and preferences.prefers_outdoor
    ):
        reasons = _format_weather_limit_reasons(weather, preferences)
        if reasons:
            items.append(
                "Açık alanı yine de tercih edersen hava değişimini tekrar "
                "kontrol et."
            )
    if not recommendation.activity.is_outdoor and not items:
        items.append(
            "Kapalı alan olduğu için hava koşullarından daha az etkilenir."
        )
    return items


def _format_user_fit_label(recommendation) -> str:
    if recommendation.score >= 85:
        return "Çok uygun"
    if recommendation.score >= 70:
        return "Uygun"
    return "Dikkatli"


def _format_user_weather_summary(weather) -> str:
    if weather.severity_level.value in {"HIGH", "SEVERE"}:
        return (
            "Hava açık alan için zorlayıcı görünüyor. Bu yüzden daha güvenli "
            "kapalı seçeneklere öncelik verdim."
        )
    if weather.severity_level.value == "MODERATE":
        return (
            "Hava fena değil ama biraz temkin istiyor. Açık alan yerine daha "
            "rahat bir kapalı alternatif öne çıkabilir."
        )
    return (
        "Hava genel olarak rahat görünüyor; tercihlerine yakın seçenekler "
        "önde."
    )


def _render_feedback_controls(
    result: RecommendationWorkflowResult,
    history_repository: RecommendationHistoryRepository,
) -> None:
    record = result.history_record
    if record is None:
        return

    st.subheader("Geri bildirim")
    if record.feedback is not None:
        st.caption(
            f"Kaydedilen geri bildirim: {format_feedback_value(record.feedback)}"
        )

    note = st.text_input(
        "Kısa not",
        value=record.feedback_note,
        key=f"feedback_note_{record.record_id}",
        placeholder="İstersen bu önerinin neden iyi/kötü olduğunu yaz.",
    )
    positive_column, negative_column = st.columns(2)

    if positive_column.button(
        "Beğendim",
        key=f"feedback_positive_{record.record_id}",
        use_container_width=True,
    ):
        _store_feedback(
            result,
            history_repository,
            FeedbackValue.POSITIVE,
            note,
        )

    if negative_column.button(
        "Beğenmedim",
        key=f"feedback_negative_{record.record_id}",
        use_container_width=True,
    ):
        _store_feedback(
            result,
            history_repository,
            FeedbackValue.NEGATIVE,
            note,
        )


def _store_feedback(
    result: RecommendationWorkflowResult,
    history_repository: RecommendationHistoryRepository,
    feedback: FeedbackValue,
    note: str,
) -> None:
    if result.history_record is None:
        return

    try:
        updated_record = history_repository.update_feedback(
            result.history_record.record_id,
            feedback,
            note,
        )
    except RecommendationHistoryError as exc:
        st.error(f"Geri bildirim kaydedilemedi: {exc}")
        return

    st.session_state["last_workflow_result"] = replace(
        result,
        history_record=updated_record,
    )
    st.success("Geri bildirim kaydedildi.")


def _render_recent_history(
    history_repository: RecommendationHistoryRepository,
    developer_mode: bool,
) -> None:
    try:
        recent_records = history_repository.list_recent(limit=5)
    except RecommendationHistoryError as exc:
        st.warning(f"Geçmiş okunamadı: {exc}")
        return

    if not recent_records:
        return

    if developer_mode:
        _render_developer_history(recent_records)
    else:
        _render_user_history(recent_records)


def _render_user_history(recent_records) -> None:
    st.subheader("Son önerilerin")
    with st.expander("Geçmişi göster", expanded=False):
        for record in recent_records:
            with st.container(border=True):
                st.markdown(
                    f"**{record.city} · {format_history_status(record.status)}**"
                )
                st.caption(format_history_recommendations(record.recommendations))
                st.caption(
                    f"Geri bildirim: {format_feedback_value(record.feedback)}"
                )


def _render_developer_history(recent_records) -> None:
    st.subheader("Son çalışmalar")
    with st.expander("Öneri geçmişi", expanded=False):
        for record in recent_records:
            source_label = (
                "generated" if record.used_generated_candidates else "catalog"
            )
            st.markdown(
                f"**{record.city} · {record.status} · {source_label}**"
            )
            st.caption(
                f"{record.created_at} | feedback: "
                f"{format_feedback_value(record.feedback)} | "
                f"fallback: {record.used_safe_fallback}"
            )
            st.caption(format_history_recommendations(record.recommendations))
            with st.expander(f"Raw record: {record.record_id}", expanded=False):
                st.json(
                    {
                        "record_id": record.record_id,
                        "target_date": record.target_date,
                        "weather": record.weather,
                        "preferences": record.preferences,
                        "recommendations": [
                            {
                                "activity_name": item.activity_name,
                                "activity_type": item.activity_type,
                                "is_outdoor": item.is_outdoor,
                                "score": item.score,
                            }
                            for item in record.recommendations
                        ],
                    }
                )


def _render_evaluation_dashboard() -> None:
    st.subheader("Evaluation dashboard")
    st.caption(
        "Kayıtlı senaryolarla agent karar akışını yeniden çalıştırır ve "
        "beklenen davranışla karşılaştırır."
    )

    if not st.button(
        "Evaluation senaryolarını çalıştır",
        key="run_evaluation_dashboard",
    ):
        st.info("Senaryoları görmek için evaluation çalıştır.")
        return

    try:
        report = EvaluationRunner().run()
    except EvaluationDataError as exc:
        st.error(f"Evaluation çalıştırılamadı: {exc}")
        return

    summary = report.summary
    columns = st.columns(4)
    columns[0].metric(
        "Senaryo",
        f"{summary.passed_cases}/{summary.total_cases}",
        f"%{summary.scenario_pass_rate_percent:.0f}",
    )
    columns[1].metric(
        "Sistem geçerliliği",
        f"%{summary.system_validity_rate_percent:.0f}",
    )
    columns[2].metric(
        "Öneri başarısı",
        f"%{summary.recommendation_success_rate_percent:.0f}",
    )
    columns[3].metric(
        "Ortalama kalite",
        f"{summary.average_quality_score:.0f}/100",
    )

    if summary.passed_cases == summary.total_cases:
        st.success("Tüm evaluation senaryoları geçti.")
    else:
        st.error("Bazı evaluation senaryoları beklenen davranışı vermedi.")

    with st.expander("Senaryo detayları", expanded=True):
        for scenario in report.scenarios:
            result_label = format_scenario_result(scenario.passed)
            st.markdown(
                f"**{result_label} · {scenario.case_id}**"
            )
            st.caption(scenario.description)
            top_activity = (
                format_activity_name(scenario.actual_top_activity)
                if scenario.actual_top_activity
                else "Öneri yok"
            )
            st.caption(
                f"status: {scenario.actual_status} | top: {top_activity} | "
                f"fallback: {scenario.used_safe_fallback} | verdict: "
                f"{format_evaluation_verdict(scenario.evaluator_verdict)} | "
                f"quality: {scenario.quality_score:.0f}/100"
            )
            for mismatch in scenario.mismatches:
                st.warning(mismatch)


def _render_evaluation(result: RecommendationWorkflowResult) -> None:
    evaluation = result.deterministic_evaluation
    st.subheader("Deterministik evaluator")
    st.metric(
        "Kalite puanı",
        f"{evaluation.quality_score:.0f}/100",
        evaluation.verdict.value,
    )

    for check in evaluation.checks:
        marker = "PASS" if check.passed else "FAIL"
        st.markdown(f"**{marker} · {check.name}**")
        st.caption(check.detail)


def _render_llm_judgment(result: RecommendationWorkflowResult) -> None:
    st.subheader("LLM ikinci görüş")

    if result.llm_judgment is None:
        st.info("Bu çalışmada LLM ikinci görüşü kullanılmadı.")
        return

    judgment = result.llm_judgment
    st.metric(
        "Karar",
        judgment.verdict.value,
        f"Güven: %{judgment.confidence * 100:.0f}",
    )
    st.write(judgment.rationale)
    for concern in judgment.concerns:
        st.warning(concern)

    if result.explanation:
        with st.expander("LLM hava özeti"):
            st.write(result.explanation.summary)
            st.write(result.explanation.weather_context)
            if result.explanation.fallback_note:
                st.caption(result.explanation.fallback_note)


def _render_agent_trace(trace: Iterable) -> None:
    st.subheader("Agent karar izi")
    with st.expander("Agent hangi adımları seçti?", expanded=True):
        for index, step in enumerate(trace, start=1):
            st.markdown(
                f"**{index}. {format_trace_action(step.action)}**"
            )
            st.caption(step.detail)


def _default_activity_index(activity_types: list[str]) -> int:
    try:
        return activity_types.index("walking")
    except ValueError:
        return 0


def _render_styles() -> None:
    st.markdown(
        """
        <style>
        .block-container {
            max-width: 1180px;
            padding-top: 2rem;
            padding-bottom: 4rem;
        }
        [data-testid="stMetric"] {
            background: rgba(90, 120, 150, 0.08);
            border: 1px solid rgba(120, 140, 160, 0.18);
            border-radius: 12px;
            padding: 0.8rem;
        }
        .score-badge {
            background: rgba(90, 120, 150, 0.08);
            border: 1px solid rgba(120, 140, 160, 0.18);
            border-radius: 12px;
            padding: 0.65rem 0.8rem;
        }
        .score-badge span {
            color: rgba(220, 225, 235, 0.72);
            display: block;
            font-size: 0.8rem;
            margin-bottom: 0.15rem;
        }
        .score-badge strong {
            display: block;
            font-size: 1.45rem;
            white-space: nowrap;
        }
        .score-badge.soft strong {
            font-size: 1.1rem;
        }
        div[data-testid="stDialog"] div[role="dialog"] {
            max-width: min(1120px, 94vw);
        }
        div[data-testid="stDialog"] iframe {
            border: 0;
            border-radius: 18px;
            box-shadow: 0 18px 48px rgba(0, 0, 0, 0.18);
        }
        section[data-testid="stSidebar"] [data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 14px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
