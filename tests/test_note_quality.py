import unittest
from dataclasses import replace

from lecturedigest.errors import ValidationError
from lecturedigest.note_quality import format_note_quality_result, inspect_note_quality
from support import lecture_record, segment


class NoteQualityTest(unittest.TestCase):
    def test_summarizes_approved_candidate_metadata(self):
        record = _record_with_candidates([_candidate("cand-1")], approved_id="cand-1")

        result = inspect_note_quality(record)

        self.assertEqual(result["summary"]["overall_status"], "review_ready")
        self.assertEqual(result["summary"]["review_ready_count"], 1)
        item = result["items"][0]
        self.assertTrue(item["approved"])
        self.assertEqual(item["known_acronym_explained_count"], 2)
        self.assertEqual(item["known_acronym_expected_count"], 2)
        self.assertEqual(item["acronym_metadata_gap_count"], 0)

    def test_warning_candidate_needs_review(self):
        record = _record_with_candidates(
            [_candidate("cand-1", warnings=["coverage_too_sparse"])]
        )

        result = inspect_note_quality(record)

        self.assertEqual(result["summary"]["overall_status"], "needs_review")
        self.assertEqual(result["summary"]["warning_count"], 1)
        self.assertEqual(result["items"][0]["gate_status"], "needs_review")

    def test_blocks_visible_source_artifacts_and_mapping_gaps(self):
        record = _record_with_candidates(
            [
                _candidate(
                    "cand-1",
                    markdown="# Note\n\nsource: seg-1 @ 00:00:00",
                    sections=[_section(segment_ids=[])],
                )
            ]
        )

        result = inspect_note_quality(record)

        self.assertEqual(result["summary"]["overall_status"], "blocked")
        self.assertGreater(result["summary"]["visible_source_artifact_count"], 0)
        self.assertEqual(result["summary"]["source_mapping_gap_count"], 1)

    def test_filters_by_candidate_id(self):
        record = _record_with_candidates([_candidate("cand-1"), _candidate("cand-2")])

        result = inspect_note_quality(record, candidate_id="cand-2")

        self.assertEqual(result["inspected_count"], 1)
        self.assertEqual(result["items"][0]["candidate_id"], "cand-2")

    def test_missing_candidate_raises_validation_error(self):
        record = _record_with_candidates([_candidate("cand-1")])

        with self.assertRaises(ValidationError) as context:
            inspect_note_quality(record, candidate_id="missing")

        self.assertEqual(context.exception.detail.code, "note_candidate_not_found")

    def test_formats_empty_state(self):
        result = inspect_note_quality(_record_with_candidates([]))

        output = format_note_quality_result(result)

        self.assertIn("inspect-note-quality empty", output)
        self.assertIn("candidates=0", output)


def _record_with_candidates(candidates, *, approved_id: str = ""):
    approved_note = {"candidate_id": approved_id, "status": "approved"} if approved_id else {}
    return replace(
        lecture_record(
            [
                segment(
                    "seg-1",
                    "00:00:00.000",
                    "00:00:10.000",
                    "DOM and CSS are browser concepts.",
                )
            ]
        ),
        note_candidates=candidates,
        approved_note=approved_note,
    )


def _candidate(
    candidate_id: str,
    *,
    warnings=None,
    failed_rules=None,
    markdown: str = "# Note\n\nDOM and CSS are explained for beginners.",
    sections=None,
):
    return {
        "candidate_id": candidate_id,
        "status": "approved" if candidate_id == "cand-1" else "pending_approval",
        "variant": "balanced",
        "markdown": markdown,
        "sections": sections if sections is not None else [_section()],
        "generator_notes": {
            "difficulty_explanations": [
                _difficulty("DOM", "Document Object Model"),
                _difficulty("CSS", "Cascading Style Sheets"),
            ]
        },
        "validation": {
            "status": "flagged" if failed_rules else "review_required",
            "failed_rules": failed_rules or [],
            "warnings": warnings or [],
            "quality_flags": [*(failed_rules or []), *(warnings or [])],
            "unmapped_sections": [],
            "visible_source_artifacts": [],
            "body_depth": {"metrics": {"source_coverage_ratio": 1.0}},
            "difficulty_explanations": {
                "metrics": {
                    "expected_count": 2,
                    "explanation_count": 2,
                    "known_acronym_count": 2,
                    "easy_marker_count": 2,
                }
            },
        },
    }


def _section(*, segment_ids=None):
    return {
        "section_key": "topic_1",
        "text": "DOM means Document Object Model.",
        "segment_ids": ["seg-1"] if segment_ids is None else segment_ids,
    }


def _difficulty(term: str, expanded_form: str):
    return {
        "term": term,
        "expanded_form": expanded_form,
        "expansion_known": True,
        "plain_explanation": f"{term} is explained in beginner-friendly words.",
        "source_segment_ids": ["seg-1"],
    }


if __name__ == "__main__":
    unittest.main()
