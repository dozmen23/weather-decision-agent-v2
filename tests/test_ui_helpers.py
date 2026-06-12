"""Tests for Streamlit-independent UI helper behavior."""

import unittest

from app.agent.planner import AgentAction
from app.models.user_preferences import UserPreferences
from app.ui.streamlit_app import (
    build_preferences,
    format_trace_action,
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


if __name__ == "__main__":
    unittest.main()
