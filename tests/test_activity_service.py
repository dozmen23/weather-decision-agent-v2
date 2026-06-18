"""Tests for the activity catalog service."""

import json
import tempfile
import unittest
from pathlib import Path

from app.models.activity import (
    ActivityIntensity,
    CostLevel,
    WeatherSensitivity,
)
from app.services.activity_service import ActivityCatalogError, ActivityService


class ActivityServiceTests(unittest.TestCase):
    priority_activity_types = {
        "walking",
        "running",
        "cycling",
        "sports",
        "culture",
        "social",
        "study",
        "photography",
        "relaxation",
    }

    def test_default_catalog_loads_and_contains_indoor_and_outdoor_options(
        self,
    ) -> None:
        activities = ActivityService().get_all()

        self.assertEqual(len(activities), 43)
        self.assertTrue(any(activity.is_outdoor for activity in activities))
        self.assertTrue(any(not activity.is_outdoor for activity in activities))
        self.assertTrue(all(activity.tags for activity in activities))
        self.assertTrue(all(activity.suitable_for for activity in activities))

        park_walk = next(
            activity
            for activity in activities
            if activity.name == "Park Walk"
        )
        self.assertEqual(park_walk.intensity, ActivityIntensity.LOW)
        self.assertEqual(park_walk.cost_level, CostLevel.FREE)
        self.assertEqual(
            park_walk.weather_sensitivity,
            WeatherSensitivity.MODERATE,
        )

    def test_priority_categories_have_indoor_and_outdoor_options(self) -> None:
        activities = ActivityService().get_all()

        for activity_type in self.priority_activity_types:
            matching_activities = [
                activity
                for activity in activities
                if activity.activity_type == activity_type
            ]

            with self.subTest(activity_type=activity_type):
                self.assertTrue(
                    any(activity.is_outdoor for activity in matching_activities)
                )
                self.assertTrue(
                    any(not activity.is_outdoor for activity in matching_activities)
                )

    def test_find_candidates_filters_by_type_and_setting(self) -> None:
        candidates = ActivityService().find_candidates(
            activity_type="SOCIAL",
            is_outdoor=False,
        )

        self.assertEqual(
            {activity.name for activity in candidates},
            {
                "Board Game Meetup",
                "Cafe Meetup",
                "Community Center Meetup",
                "Covered Market Visit",
            },
        )

    def test_similar_candidates_prioritize_exact_indoor_activity_type(
        self,
    ) -> None:
        candidates = ActivityService().find_similar_candidates(
            activity_type="walking",
            is_outdoor=False,
        )

        self.assertEqual(candidates[0].activity_type, "walking")
        self.assertFalse(candidates[0].is_outdoor)
        self.assertIn("walking", candidates[0].tags)
        self.assertEqual(
            [activity.name for activity in candidates[:3]],
            ["Indoor Track Walk", "Mall Walk", "Treadmill Walk"],
        )

    def test_priority_fallbacks_keep_activity_type_when_possible(self) -> None:
        service = ActivityService()

        for activity_type in self.priority_activity_types:
            candidates = service.find_similar_candidates(
                activity_type=activity_type,
                is_outdoor=False,
                limit=3,
            )

            with self.subTest(activity_type=activity_type):
                self.assertGreaterEqual(len(candidates), 1)
                self.assertEqual(candidates[0].activity_type, activity_type)
                self.assertFalse(candidates[0].is_outdoor)

    def test_unknown_activity_type_has_no_similar_candidates(self) -> None:
        candidates = ActivityService().find_similar_candidates(
            activity_type="unknown-category",
            is_outdoor=False,
        )

        self.assertEqual(candidates, [])

    def test_missing_required_field_is_rejected(self) -> None:
        invalid_catalog = [{"name": "Incomplete activity"}]

        with self.assertRaisesRegex(ActivityCatalogError, "missing fields"):
            self._load_temporary_catalog(invalid_catalog)

    def test_invalid_activity_limits_are_rejected(self) -> None:
        invalid_catalog = [
            {
                **self._valid_activity(),
                "name": "Impossible activity",
                "min_temperature_celsius": 30,
                "max_temperature_celsius": 10,
                "max_precipitation_probability_percent": 120,
                "max_wind_speed_kmh": -1,
            }
        ]

        with self.assertRaisesRegex(
            ActivityCatalogError,
            "invalid temperature range",
        ):
            self._load_temporary_catalog(invalid_catalog)

    def test_duplicate_names_are_rejected_case_insensitively(self) -> None:
        activity = self._valid_activity()
        duplicate = {**activity, "name": "park walk"}

        with self.assertRaisesRegex(ActivityCatalogError, "must be unique"):
            self._load_temporary_catalog([activity, duplicate])

    def test_invalid_model_metadata_is_rejected(self) -> None:
        invalid_catalog = [
            {
                **self._valid_activity(),
                "intensity": "extreme",
            }
        ]

        with self.assertRaisesRegex(
            ActivityCatalogError,
            "invalid intensity",
        ):
            self._load_temporary_catalog(invalid_catalog)

    def test_empty_tag_list_is_rejected(self) -> None:
        invalid_catalog = [
            {
                **self._valid_activity(),
                "tags": [],
            }
        ]

        with self.assertRaisesRegex(ActivityCatalogError, "non-empty tags"):
            self._load_temporary_catalog(invalid_catalog)

    @staticmethod
    def _valid_activity() -> dict[str, object]:
        return {
            "name": "Park Walk",
            "activity_type": "walking",
            "is_outdoor": True,
            "min_temperature_celsius": 5,
            "max_temperature_celsius": 30,
            "max_precipitation_probability_percent": 40,
            "max_wind_speed_kmh": 25,
            "purpose": "light exercise",
            "intensity": "low",
            "duration_minutes": 60,
            "cost_level": "free",
            "weather_sensitivity": "moderate",
            "requires_reservation": False,
            "suitable_for": ["solo", "friends"],
            "tags": ["walking", "outdoor"],
        }

    def _load_temporary_catalog(self, catalog: object) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            catalog_path = Path(temporary_directory) / "activities.json"
            catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
            ActivityService(catalog_path).get_all()


if __name__ == "__main__":
    unittest.main()
