"""Streamlit interface for the Weather Decision Agent."""

from collections.abc import Iterable
from dataclasses import replace
from datetime import date, timedelta

import streamlit as st

from app.agent.planner import AgentAction
from app.config import ConfigurationError
from app.llm.client import LLMServiceError
from app.llm.factory import (
    create_llm_client,
    load_llm_settings,
)
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
from app.services.weather_service import WeatherService, WeatherServiceError


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
        else:
            _render_empty_state(developer_mode)
        return

    try:
        preferences = build_preferences(**form_values["preferences"])
        service = build_recommendation_service(
            form_values["use_llm"],
            history_repository=history_repository,
        )

        with st.spinner(
            "Hava verisi alınıyor ve agent karar planını çalıştırıyor..."
        ):
            result = service.recommend(
                city=form_values["city"],
                preferences=preferences,
                recommendation_limit=form_values["recommendation_limit"],
                target_date=form_values["target_date"],
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
    )


def build_recommendation_service(
    use_llm: bool,
    history_repository: RecommendationHistoryRepository | None = None,
) -> RecommendationService:
    """Create a workflow service with optional configured LLM enrichment."""
    if not use_llm:
        return RecommendationService(history_repository=history_repository)

    settings = load_llm_settings()
    return RecommendationService(
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
        city = st.text_input("Şehir", value="Istanbul")
        target_date = _render_forecast_selector(city)

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
            temperature_range = st.slider(
                "Konfor sıcaklığı (°C)",
                min_value=-10,
                max_value=45,
                value=(12, 30),
            )
            precipitation_limit = st.slider(
                "En fazla yağış ihtimali (%)",
                min_value=0,
                max_value=100,
                value=40,
            )
            wind_limit = st.slider(
                "En fazla rüzgâr hızı (km/h)",
                min_value=0,
                max_value=100,
                value=25,
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

    if len(city.strip()) < 2:
        raise ValueError("Şehir adı en az iki karakter olmalıdır.")

    return {
        "city": city.strip(),
        "target_date": target_date,
        "recommendation_limit": recommendation_limit,
        "use_llm": use_llm,
        "preferences": {
            "preferred_activity_type": preferred_activity_type,
            "prefers_outdoor": setting == "Açık alan",
            "temperature_range": temperature_range,
            "max_precipitation_probability_percent": precipitation_limit,
            "max_wind_speed_kmh": wind_limit,
        },
    }


def _render_forecast_selector(city: str) -> date:
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


def _render_empty_state(developer_mode: bool) -> None:
    st.info(
        "Soldaki tercihleri düzenleyip **Öneri üret** düğmesine basarak "
        "agent akışını başlat."
    )
    columns = st.columns(3)
    if developer_mode:
        columns[0].metric("Karar araçları", "3", "Weather, Catalog, Scoring")
        columns[1].metric("Evaluation kontrolleri", "6")
        columns[2].metric("Otomatik test", "92 başarılı")
    else:
        columns[0].metric("Görünüm", "Sade")
        columns[1].metric("Geçmiş", "Aktif")
        columns[2].metric("Feedback", "Hazır")


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


def _render_user_recommendation_explanation(
    recommendation,
    explanation: str | None,
) -> None:
    reason = (
        _select_user_explanation(recommendation, explanation)
        if explanation
        else _format_user_recommendation_reason(recommendation)
    )
    st.markdown("**Neden bunu önerdim?**")
    st.write(reason)

    attention_items = _build_attention_items(recommendation)
    if attention_items:
        st.markdown("**Dikkat et**")
        for item in attention_items:
            st.caption(f"- {item}")


def _format_user_recommendation_reason(recommendation) -> str:
    setting = "açık alan" if recommendation.activity.is_outdoor else "kapalı alan"
    activity_type = format_activity_type(recommendation.activity.activity_type).lower()
    if not recommendation.activity.is_outdoor:
        return (
            f"Hava dışarıda pek rahat görünmediği için bu {activity_type} "
            f"seçeneği daha güvenli ve konforlu bir {setting} alternatifi."
        )
    return (
        f"Seçtiğin aktivite türüne yakın, hava koşullarıyla uyumlu bir "
        f"{setting} seçeneği."
    )


def _select_user_explanation(recommendation, explanation: str) -> str:
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
        return _format_user_recommendation_reason(recommendation)
    return explanation


def _build_attention_items(recommendation) -> list[str]:
    items = [format_warning(warning) for warning in recommendation.warnings]
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
        </style>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
