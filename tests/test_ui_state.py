import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from lecturedigest.models import CorrectionLogEntry, ProcessingIssue
from lecturedigest.rag import build_search_index
from lecturedigest.storage import JsonLectureRepository
from lecturedigest.ui_state import (
    card_review_state,
    correction_review_queue,
    cost_or_quota_issues,
    has_openai_api_key,
    lecture_label,
    load_library,
    note_quality_review,
    paid_action_previews,
    quiz_review_state,
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

    def test_note_quality_review_exposes_gate_and_acronym_metrics(self):
        record = replace(
            chunked_lecture(),
            note_candidates=[
                {
                    "candidate_id": "note-1",
                    "variant": "balanced",
                    "status": "approved",
                    "markdown": "## HTML\nHTML은 웹 문서의 뼈대입니다.",
                    "sections": [{"section_key": "html", "segment_ids": ["seg-1"]}],
                    "validation": {
                        "status": "review_required",
                        "warnings": ["missing_flow_diagram"],
                        "difficulty_explanations": {
                            "metrics": {
                                "expected_count": 1,
                                "known_acronym_count": 1,
                                "easy_marker_count": 1,
                            }
                        },
                        "body_depth": {"metrics": {"source_coverage_ratio": 0.75}},
                    },
                    "generator_notes": {
                        "difficulty_explanations": [
                            {
                                "expansion_known": True,
                                "expanded_form": "HyperText Markup Language",
                                "plain_explanation": "웹 문서의 뼈대를 적는 언어입니다.",
                            }
                        ]
                    },
                }
            ],
            approved_note={"candidate_id": "note-1"},
        )

        state = note_quality_review(record)

        self.assertIsNone(state.error_message)
        summary = state.result["summary"]
        self.assertEqual(summary["overall_status"], "needs_review")
        item = state.result["items"][0]
        self.assertTrue(item["approved"])
        self.assertEqual(item["known_acronym_explained_count"], 1)
        self.assertEqual(item["acronym_metadata_gap_count"], 0)

    def test_card_review_state_loads_manifest_summary_and_cards(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            summary_path = base / "summary.json"
            cards_path = base / "cards.json"
            manifest_path = base / "card-manifest.json"
            summary_path.write_text(
                json.dumps({"ready_cards": 1, "visible_source_artifact_count": 0}),
                encoding="utf-8",
            )
            cards_path.write_text(
                json.dumps({"cards": [{"card_id": "card-1", "status": "ready"}]}),
                encoding="utf-8",
            )
            manifest_path.write_text(
                json.dumps(
                    {
                        "artifact_paths": {
                            "summary": str(summary_path),
                            "cards": str(cards_path),
                        },
                        "expected_counts": {
                            "ready_cards": 1,
                            "excluded_flagged_cards": 0,
                        },
                    }
                ),
                encoding="utf-8",
            )

            state = card_review_state(manifest_path)

        self.assertFalse(state.has_errors)
        self.assertEqual(state.expected_counts["ready_cards"], 1)
        self.assertEqual(state.summary["ready_cards"], 1)
        self.assertEqual(state.items[0]["card_id"], "card-1")

    def test_quiz_review_state_combines_sources_with_badges(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            legacy_path = base / "legacy.json"
            golden_path = base / "golden.json"
            manifest_path = base / "quiz-manifest.json"
            legacy_path.write_text(
                json.dumps([_quiz_record("lec-1", "legacy-q")]),
                encoding="utf-8",
            )
            golden_path.write_text(
                json.dumps([_quiz_record("lec-1", "golden-q")]),
                encoding="utf-8",
            )
            manifest_path.write_text(
                json.dumps(
                    {
                        "expected_total": 2,
                        "source_policy": "combined_manifest",
                        "dedupe_policy": "keep_all_tagged",
                        "sources": {
                            "legacy_e2e": {
                                "artifact_path": str(legacy_path),
                                "record_selector": {"lecture_id": "lec-1"},
                                "quiz_items_path": "quiz_items",
                                "expected_count": 1,
                                "source_badge": "legacy_e2e",
                            },
                            "golden_set_3": {
                                "artifact_path": str(golden_path),
                                "record_selector": {"lecture_id": "lec-1"},
                                "quiz_items_path": "quiz_items",
                                "expected_count": 1,
                                "source_badge": "golden_set_3",
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            state = quiz_review_state(manifest_path)

        self.assertFalse(state.has_errors)
        self.assertEqual(state.summary["actual_total"], 2)
        self.assertEqual(state.source_counts, {"legacy_e2e": 1, "golden_set_3": 1})
        self.assertEqual(
            [item["_review_source_badge"] for item in state.items],
            ["legacy_e2e", "golden_set_3"],
        )

    def test_review_state_reports_missing_manifest(self):
        state = card_review_state(Path("missing-card-manifest.json"))

        self.assertTrue(state.has_errors)
        self.assertIn("card manifest not found", state.error_messages[0])


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


def _quiz_record(lecture_id: str, quiz_id: str) -> dict[str, object]:
    return {
        "lecture_id": lecture_id,
        "quiz_items": [
            {
                "quiz_id": quiz_id,
                "question_type": "written",
                "question": "Explain the idea.",
                "status": "ready",
            }
        ],
    }


if __name__ == "__main__":
    unittest.main()
