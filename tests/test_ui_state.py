import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from lecturedigest.models import CorrectionLogEntry, ProcessingIssue
from lecturedigest.rag import build_search_index
from lecturedigest.storage import JsonLectureRepository
from lecturedigest.ui_state import (
    correction_review_queue,
    cost_or_quota_issues,
    has_openai_api_key,
    lecture_label,
    load_library,
    paid_action_previews,
    status_counts,
)
from support import chunked_lecture


class UiStateTest(unittest.TestCase):
    def test_load_library_returns_empty_state_for_missing_store(self):
        with tempfile.TemporaryDirectory() as root:
            repository = JsonLectureRepository(Path(root) / "missing.json")

            state = load_library(repository)

        self.assertTrue(state.is_empty)
        self.assertEqual(state.lectures, [])
        self.assertIsNone(state.error_message)

    def test_load_library_preserves_corrupt_store_error_context(self):
        with tempfile.TemporaryDirectory() as root:
            store = Path(root) / "lectures.json"
            store.write_text("{not-json", encoding="utf-8")

            state = load_library(JsonLectureRepository(store))

        self.assertEqual(state.lectures, [])
        self.assertIn("JSONDecodeError", state.error_message or "")

    def test_status_counts_and_label_include_review_state(self):
        record = replace(
            chunked_lecture(),
            correction_log=[_review_entry()],
            issues=[ProcessingIssue("openai_rate_limited", "rate limit", "rag")],
            flashcards=[{"card_id": "card-1"}],
            quiz_items=[{"quiz_id": "quiz-1"}],
        )

        counts = status_counts(record)

        self.assertIn("Intro", lecture_label(record))
        self.assertEqual(counts["segments"], 2)
        self.assertEqual(counts["review_corrections"], 1)
        self.assertEqual(counts["cards"], 1)
        self.assertEqual(counts["quizzes"], 1)
        self.assertEqual(
            cost_or_quota_issues(record),
            ["openai_rate_limited: rate limit"],
        )

    def test_paid_action_previews_include_boundaries_and_dry_run_commands(self):
        record = build_search_index(chunked_lecture())

        previews = paid_action_previews(record)

        self.assertEqual(len(previews), 3)
        self.assertTrue(all(preview["input_size_bytes"] >= 0 for preview in previews))
        self.assertTrue(all("--dry-run" in str(preview["dry_run"]) for preview in previews))
        self.assertTrue(has_openai_api_key({"OPENAI_API_KEY": "key"}))
        self.assertFalse(has_openai_api_key({"OPENAI_API_KEY": ""}))

    def test_correction_review_queue_filters_non_review_entries(self):
        record = replace(
            chunked_lecture(),
            correction_log=[_review_entry(), replace(_review_entry(), status="applied")],
        )

        self.assertEqual(len(correction_review_queue(record)), 1)


def _review_entry() -> CorrectionLogEntry:
    return CorrectionLogEntry(
        segment_id="seg-1",
        start_ts="00:00:00.000",
        end_ts="00:00:10.000",
        original_text="helo",
        corrected_text="hello",
        confidence=0.82,
        status="review_required",
    )


if __name__ == "__main__":
    unittest.main()
