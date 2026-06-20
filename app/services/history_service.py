"""JSONL-backed recommendation history persistence."""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.models.recommendation_history import (
    FeedbackValue,
    RecommendationHistoryItem,
    RecommendationHistoryRecord,
)


DEFAULT_HISTORY_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "recommendation_history.jsonl"
)


class RecommendationHistoryError(RuntimeError):
    """Raised when recommendation history cannot be read or written."""


class RecommendationHistoryRepository:
    """Persist recommendation runs and feedback as newline-delimited JSON."""

    def __init__(self, history_path: Path = DEFAULT_HISTORY_PATH) -> None:
        self.history_path = history_path

    def append(
        self,
        record: RecommendationHistoryRecord,
    ) -> RecommendationHistoryRecord:
        """Append one history record and return it."""
        try:
            self.history_path.parent.mkdir(parents=True, exist_ok=True)
            with self.history_path.open("a", encoding="utf-8") as history_file:
                history_file.write(json.dumps(_record_to_dict(record), sort_keys=True))
                history_file.write("\n")
        except OSError as exc:
            raise RecommendationHistoryError(
                f"Recommendation history could not be written: {self.history_path}"
            ) from exc

        return record

    def list_recent(self, limit: int = 20) -> list[RecommendationHistoryRecord]:
        """Return the most recent history records, newest first."""
        if limit <= 0:
            return []
        records = self._read_all()
        return list(reversed(records[-limit:]))

    def update_feedback(
        self,
        record_id: str,
        feedback: FeedbackValue,
        note: str = "",
    ) -> RecommendationHistoryRecord:
        """Update feedback for an existing history record."""
        records = self._read_all()
        updated_record: RecommendationHistoryRecord | None = None

        for record in records:
            if record.record_id == record_id:
                record.feedback = feedback
                record.feedback_note = note.strip()
                updated_record = record
                break

        if updated_record is None:
            raise RecommendationHistoryError(
                f"Recommendation history record was not found: {record_id}"
            )

        self._write_all(records)
        return updated_record

    def _read_all(self) -> list[RecommendationHistoryRecord]:
        if not self.history_path.exists():
            return []

        records: list[RecommendationHistoryRecord] = []
        try:
            for line_number, line in enumerate(
                self.history_path.read_text(encoding="utf-8").splitlines(),
                start=1,
            ):
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise RecommendationHistoryError(
                        "Recommendation history contains invalid JSON on line "
                        f"{line_number}."
                    ) from exc
                records.append(_record_from_dict(payload))
        except OSError as exc:
            raise RecommendationHistoryError(
                f"Recommendation history could not be read: {self.history_path}"
            ) from exc

        return records

    def _write_all(self, records: list[RecommendationHistoryRecord]) -> None:
        try:
            self.history_path.parent.mkdir(parents=True, exist_ok=True)
            payload = "\n".join(
                json.dumps(_record_to_dict(record), sort_keys=True)
                for record in records
            )
            if payload:
                payload += "\n"
            self.history_path.write_text(payload, encoding="utf-8")
        except OSError as exc:
            raise RecommendationHistoryError(
                f"Recommendation history could not be written: {self.history_path}"
            ) from exc


def _record_to_dict(record: RecommendationHistoryRecord) -> dict[str, Any]:
    payload = asdict(record)
    payload["feedback"] = record.feedback.value if record.feedback else None
    return payload


def _record_from_dict(payload: Any) -> RecommendationHistoryRecord:
    if not isinstance(payload, dict):
        raise RecommendationHistoryError("Recommendation history record is invalid.")

    try:
        raw_recommendations = payload["recommendations"]
        if not isinstance(raw_recommendations, list):
            raise TypeError

        feedback = payload.get("feedback")
        return RecommendationHistoryRecord(
            record_id=str(payload["record_id"]),
            created_at=str(payload["created_at"]),
            city=str(payload["city"]),
            target_date=(
                str(payload["target_date"])
                if payload.get("target_date") is not None
                else None
            ),
            status=str(payload["status"]),
            used_safe_fallback=bool(payload["used_safe_fallback"]),
            used_generated_candidates=bool(payload["used_generated_candidates"]),
            weather=dict(payload["weather"]),
            preferences=dict(payload["preferences"]),
            recommendations=[
                _history_item_from_dict(item)
                for item in raw_recommendations
                if isinstance(item, dict)
            ],
            feedback=FeedbackValue(feedback) if feedback is not None else None,
            feedback_note=str(payload.get("feedback_note", "")),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise RecommendationHistoryError(
            "Recommendation history record is incomplete."
        ) from exc


def _history_item_from_dict(payload: dict[str, Any]) -> RecommendationHistoryItem:
    venue_names = payload.get("venue_names", [])
    if not isinstance(venue_names, list):
        raise TypeError

    return RecommendationHistoryItem(
        activity_name=str(payload["activity_name"]),
        activity_type=str(payload["activity_type"]),
        is_outdoor=bool(payload["is_outdoor"]),
        score=float(payload["score"]),
        venue_names=tuple(str(venue_name) for venue_name in venue_names),
    )
