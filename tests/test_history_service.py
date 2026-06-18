"""Tests for recommendation history persistence."""

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
            )
        ],
    )


if __name__ == "__main__":
    unittest.main()
