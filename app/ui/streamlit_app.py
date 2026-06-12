"""Streamlit interface for the Weather Decision Agent."""

from collections.abc import Iterable

import streamlit as st

from app.agent.planner import AgentAction
from app.config import ConfigurationError
from app.llm.client import LLMServiceError
from app.llm.factory import (
    create_llm_client,
    load_llm_settings,
)
from app.models.user_preferences import UserPreferences
from app.services.activity_service import ActivityCatalogError, ActivityService
from app.services.recommendation_service import (
    RecommendationService,
    RecommendationWorkflowResult,
)
from app.services.weather_service import WeatherServiceError


ACTION_LABELS = {
    AgentAction.FETCH_WEATHER: "Hava verisi alındı",
    AgentAction.LOAD_PREFERRED_CANDIDATES: "Tercihe uygun aktiviteler arandı",
    AgentAction.LOAD_BROADER_CANDIDATES: "Aktivite araması genişletildi",
    AgentAction.LOAD_SAFE_ALTERNATIVES: "Güvenli kapalı alan alternatifleri arandı",
    AgentAction.SCORE_CANDIDATES: "Adaylar kurallardan geçirilip puanlandı",
    AgentAction.FINALIZE: "Son öneriler hazırlandı",
    AgentAction.STOP_NO_RESULT: "Güvenli öneri bulunamadığı için duruldu",
}


def main() -> None:
    """Render the complete Streamlit application."""
    st.set_page_config(
        page_title="Weather Decision Agent",
        page_icon="W",
        layout="wide",
    )
    _render_styles()
    _render_header()

    activity_types = get_activity_types()
    form_values = _render_preference_form(activity_types)
    if form_values is None:
        _render_empty_state()
        return

    try:
        preferences = build_preferences(**form_values["preferences"])
        service = build_recommendation_service(form_values["use_llm"])

        with st.spinner(
            "Hava verisi alınıyor ve agent karar planını çalıştırıyor..."
        ):
            result = service.recommend(
                city=form_values["city"],
                preferences=preferences,
                recommendation_limit=form_values["recommendation_limit"],
            )
    except (
        ActivityCatalogError,
        ConfigurationError,
        LLMServiceError,
        WeatherServiceError,
        ValueError,
    ) as exc:
        st.error(f"İşlem tamamlanamadı: {exc}")
        return

    _render_workflow_result(result)


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


def build_recommendation_service(use_llm: bool) -> RecommendationService:
    """Create a workflow service with optional configured LLM enrichment."""
    if not use_llm:
        return RecommendationService()

    settings = load_llm_settings()
    return RecommendationService(
        llm_client=create_llm_client(settings)
    )


def format_trace_action(action: AgentAction) -> str:
    """Return a readable Turkish label for an agent action."""
    return ACTION_LABELS.get(action, action.value)


def _render_header() -> None:
    st.title("Weather Decision Agent")
    st.markdown(
        """
        Hava koşullarını, kişisel sınırlarını ve aktivite kataloğunu birlikte
        değerlendirir. Agent gerektiğinde aramayı genişletir veya güvenli kapalı
        alan alternatiflerine geçer.
        """
    )
    st.caption(
        "Karar kuralları ve puanlar deterministiktir. LLM yalnızca açıklama "
        "ve ikinci görüş üretir."
    )


def _render_preference_form(
    activity_types: list[str],
) -> dict[str, object] | None:
    with st.sidebar:
        st.header("Tercihler")
        with st.form("recommendation_form"):
            city = st.text_input("Şehir", value="Istanbul")
            preferred_activity_type = st.selectbox(
                "Tercih edilen aktivite türü",
                options=activity_types,
                index=_default_activity_index(activity_types),
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
                "LLM açıklaması ve ikinci hakem",
                value=True,
                help=(
                    "Açıldığında doğrulanmış sonuçlar OpenAI ile açıklanır ve "
                    "ikinci bir yapılandırılmış değerlendirmeden geçer."
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


def _render_empty_state() -> None:
    st.info(
        "Soldaki tercihleri düzenleyip **Öneri üret** düğmesine basarak "
        "agent akışını başlat."
    )
    columns = st.columns(3)
    columns[0].metric("Karar araçları", "3", "Weather, Catalog, Scoring")
    columns[1].metric("Evaluation kontrolleri", "6")
    columns[2].metric("Otomatik test", "54")


def _render_workflow_result(result: RecommendationWorkflowResult) -> None:
    agent_result = result.agent_result
    evaluation = result.deterministic_evaluation

    _render_weather(agent_result.weather)

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
                explanation=(
                    result.explanation.recommendation_details.get(
                        recommendation.activity.name
                    )
                    if result.explanation
                    else None
                ),
            )

    left_column, right_column = st.columns(2)
    with left_column:
        _render_evaluation(result)
    with right_column:
        _render_llm_judgment(result)

    _render_agent_trace(agent_result.trace)


def _render_weather(weather) -> None:
    st.subheader(f"Güncel hava: {weather.city}")
    columns = st.columns(4)
    columns[0].metric("Sıcaklık", f"{weather.temperature_celsius:.1f} °C")
    columns[1].metric(
        "Yağış ihtimali",
        f"%{weather.precipitation_probability_percent}",
    )
    columns[2].metric("Rüzgâr", f"{weather.wind_speed_kmh:.1f} km/h")
    columns[3].metric("Durum", weather.condition)


def _render_recommendation_card(
    *,
    index: int,
    recommendation,
    explanation: str | None,
) -> None:
    with st.container(border=True):
        title_column, score_column = st.columns([4, 1.25])
        title_column.markdown(
            f"### {index}. {recommendation.activity.name}"
        )
        score_column.markdown(
            (
                '<div class="score-badge">'
                '<span>Uygunluk</span>'
                f"<strong>{recommendation.score:.1f}/100</strong>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )

        setting = (
            "Açık alan" if recommendation.activity.is_outdoor else "Kapalı alan"
        )
        st.caption(
            f"Tür: {recommendation.activity.activity_type} | Ortam: {setting}"
        )

        if explanation:
            st.markdown(explanation)
        else:
            st.markdown(
                "Deterministik puan bileşenleri: "
                + recommendation.reasoning
            )

        for warning in recommendation.warnings:
            st.warning(warning)


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
        </style>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
