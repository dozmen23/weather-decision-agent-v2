"""Tests for recommendation history persistence."""

import json
import tempfile
import unittest
from pathlib import Path

from app.models.recommendation_history import (
    FeedbackValue,
    RecommendationHistoryItem,
    RecommendationHistoryRecord,
)
from app.services.history_service import (
    RecommendationHistoryError,
    RecommendationHistoryRepository,
)


class RecommendationHistoryRepositoryTests(unittest.TestCase):
    def test_append_list_and_update_feedback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = RecommendationHistoryRepository(
                Path(temporary_directory) / "history.jsonl"
            )
            record = _record("first")

            repository.append(record)
            recent = repository.list_recent()

            self.assertEqual(len(recent), 1)
            self.assertEqual(recent[0].record_id, "first")
            self.assertIsNone(recent[0].feedback)
            self.assertEqual(
                recent[0].recommendations[0].venue_names,
                ("Demo Park", "Demo Track"),
            )

            updated = repository.update_feedback(
                "first",
                FeedbackValue.POSITIVE,
                "Worked well",
            )

            self.assertIs(updated.feedback, FeedbackValue.POSITIVE)
            self.assertEqual(updated.feedback_note, "Worked well")
            self.assertIs(
                repository.list_recent()[0].feedback,
                FeedbackValue.POSITIVE,
            )

    def test_list_recent_returns_newest_first_and_respects_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = RecommendationHistoryRepository(
                Path(temporary_directory) / "history.jsonl"
            )
            repository.append(_record("first"))
            repository.append(_record("second"))
            repository.append(_record("third"))

            recent = repository.list_recent(limit=2)

            self.assertEqual(
                [record.record_id for record in recent],
                ["third", "second"],
            )

    def test_update_missing_record_raises_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = RecommendationHistoryRepository(
                Path(temporary_directory) / "history.jsonl"
            )

            with self.assertRaisesRegex(
                RecommendationHistoryError,
                "was not found",
            ):
                repository.update_feedback("missing", FeedbackValue.NEGATIVE)

    def test_old_history_records_without_venue_names_still_load(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            history_path = Path(temporary_directory) / "history.jsonl"
            record = _record("old-record")
            payload = {
                "record_id": record.record_id,
                "created_at": record.created_at,
                "city": record.city,
                "target_date": record.target_date,
                "status": record.status,
                "used_safe_fallback": record.used_safe_fallback,
                "used_generated_candidates": record.used_generated_candidates,
                "weather": record.weather,
                "preferences": record.preferences,
                "recommendations": [
                    {
                        "activity_name": "Park Walk",
                        "activity_type": "walking",
                        "is_outdoor": True,
                        "score": 95.0,
                    }
                ],
                "feedback": None,
                "feedback_note": "",
            }
            history_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            repository = RecommendationHistoryRepository(history_path)

            recent = repository.list_recent()

            self.assertEqual(recent[0].recommendations[0].venue_names, ())


def _record(record_id: str) -> RecommendationHistoryRecord:
    return RecommendationHistoryRecord(
        record_id=record_id,
        created_at="2026-06-18T10:00:00+00:00",
        city="Istanbul",
        target_date=None,
        status="completed",
        used_safe_fallback=False,
        used_generated_candidates=False,
        weather={"city": "Istanbul", "severity_level": "LOW"},
        preferences={"preferred_activity_type": "walking"},
        recommendations=[
            RecommendationHistoryItem(
                activity_name="Park Walk",
                activity_type="walking",
                is_outdoor=True,
                score=95.0,
                venue_names=("Demo Park", "Demo Track"),
            )
        ],
    )


if __name__ == "__main__":
    unittest.main()
