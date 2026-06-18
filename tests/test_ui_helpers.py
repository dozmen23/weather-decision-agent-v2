"""Tests for Streamlit-independent UI helper behavior."""

import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from app.agent.planner import AgentAction
from app.models.user_preferences import UserPreferences
from app.services.history_service import RecommendationHistoryRepository
from app.ui.streamlit_app import (
    build_recommendation_service,
    build_preferences,
    format_activity_name,
    format_condition,
    format_forecast_date,
    format_severity,
    format_trace_action,
    format_view_mode,
    format_warning,
    get_forecast_date_bounds,
    get_activity_types,
)


class UIHelperTests(unittest.TestCase):
    def test_catalog_activity_types_are_unique_and_sorted(self) -> None:
        activity_types = get_activity_types()

        self.assertEqual(activity_types, sorted(set(activity_types)))
        self.assertIn("walking", activity_types)
        self.assertIn("culture", activity_types)

    def test_form_values_create_domain_preferences(self) -> None:
        preferences = build_preferences(
            preferred_activity_type="walking",
            prefers_outdoor=True,
            temperature_range=(12, 30),
            max_precipitation_probability_percent=40,
            max_wind_speed_kmh=25,
        )

        self.assertEqual(
            preferences,
            UserPreferences("walking", True, 12.0, 30.0, 40, 25.0),
        )

    def test_invalid_temperature_range_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Minimum sıcaklık"):
            build_preferences(
                preferred_activity_type="walking",
                prefers_outdoor=True,
                temperature_range=(20, 20),
                max_precipitation_probability_percent=40,
                max_wind_speed_kmh=25,
            )

    def test_trace_action_has_readable_label(self) -> None:
        self.assertEqual(
            format_trace_action(AgentAction.LOAD_SAFE_ALTERNATIVES),
            "Güvenli kapalı alan alternatifleri arandı",
        )
        self.assertEqual(
            format_trace_action(AgentAction.LOAD_GENERATED_CANDIDATES),
            "LLM aday aktiviteleri üretildi",
        )

    def test_view_mode_labels_are_stable(self) -> None:
        self.assertEqual(format_view_mode("user"), "User Mode")
        self.assertEqual(format_view_mode("developer"), "Developer Mode")

    def test_user_facing_labels_are_turkish(self) -> None:
        self.assertEqual(
            format_activity_name("Indoor Track Walk"),
            "Kapalı pist yürüyüşü",
        )
        self.assertEqual(format_condition("Partly cloudy"), "Parçalı bulutlu")
        self.assertEqual(format_severity("MODERATE"), "temkinli")
        self.assertEqual(
            format_warning(
                "Indoor/outdoor setting does not match the user's preference."
            ),
            "Hava nedeniyle açık alan yerine kapalı alan öneriyorum.",
        )

    def test_service_builder_accepts_history_repository_without_llm(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            repository = RecommendationHistoryRepository(
                Path(temporary_directory) / "history.jsonl"
            )

            service = build_recommendation_service(
                use_llm=False,
                history_repository=repository,
            )

            self.assertIs(service.history_repository, repository)

    def test_forecast_date_bounds_cover_seven_days(self) -> None:
        first_day, last_day = get_forecast_date_bounds(
            date(2026, 6, 12)
        )

        self.assertEqual(first_day, date(2026, 6, 12))
        self.assertEqual(last_day, date(2026, 6, 18))

    def test_forecast_date_is_formatted_in_turkish(self) -> None:
        self.assertEqual(
            format_forecast_date(date(2026, 6, 13)),
            "13 Haziran 2026, Cumartesi",
        )


if __name__ == "__main__":
    unittest.main()
