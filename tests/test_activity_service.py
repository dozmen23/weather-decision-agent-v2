"""Tests for the activity catalog service."""

import json
import tempfile
import unittest
from pathlib import Path

from app.services.activity_service import ActivityCatalogError, ActivityService


class ActivityServiceTests(unittest.TestCase):
    def test_default_catalog_loads_and_contains_indoor_and_outdoor_options(
        self,
    ) -> None:
        activities = ActivityService().get_all()

        self.assertEqual(len(activities), 10)
        self.assertTrue(any(activity.is_outdoor for activity in activities))
        self.assertTrue(any(not activity.is_outdoor for activity in activities))

    def test_find_candidates_filters_by_type_and_setting(self) -> None:
        candidates = ActivityService().find_candidates(
            activity_type="SOCIAL",
            is_outdoor=False,
        )

        self.assertEqual([activity.name for activity in candidates], ["Cafe Meetup"])

    def test_missing_required_field_is_rejected(self) -> None:
        invalid_catalog = [{"name": "Incomplete activity"}]

        with self.assertRaisesRegex(ActivityCatalogError, "missing fields"):
            self._load_temporary_catalog(invalid_catalog)

    def test_invalid_activity_limits_are_rejected(self) -> None:
        invalid_catalog = [
            {
                "name": "Impossible activity",
                "activity_type": "test",
                "is_outdoor": True,
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
        activity = {
            "name": "Park Walk",
            "activity_type": "walking",
            "is_outdoor": True,
            "min_temperature_celsius": 5,
            "max_temperature_celsius": 30,
            "max_precipitation_probability_percent": 40,
            "max_wind_speed_kmh": 25,
        }
        duplicate = {**activity, "name": "park walk"}

        with self.assertRaisesRegex(ActivityCatalogError, "must be unique"):
            self._load_temporary_catalog([activity, duplicate])

    def _load_temporary_catalog(self, catalog: object) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            catalog_path = Path(temporary_directory) / "activities.json"
            catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
            ActivityService(catalog_path).get_all()


if __name__ == "__main__":
    unittest.main()
