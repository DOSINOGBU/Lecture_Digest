import unittest
from dataclasses import replace

from lecturedigest.correction_review import (
    approve_correction_candidate,
    reject_correction_candidate,
)
from lecturedigest.errors import ValidationError
from lecturedigest.models import CorrectionLogEntry
from support import lecture_record, segment


class CorrectionReviewTest(unittest.TestCase):
    def test_approves_review_candidate_and_updates_segment_text(self):
        record = _record_with_review_candidate()

        updated = approve_correction_candidate(record, segment_id="seg-1")

        self.assertEqual(updated.status, "transcript_finalized")
        self.assertEqual(updated.stage, "correction_review")
        self.assertEqual(updated.segments[0].text, "React DOM")
        self.assertEqual(updated.correction_log[0].status, "applied")
        self.assertTrue(updated.correction_log[0].applied)
        self.assertEqual(
            updated.correction_log[0].provider_metadata["review_decision"],
            "approved",
        )

    def test_rejects_review_candidate_without_changing_segment_text(self):
        record = _record_with_review_candidate()

        updated = reject_correction_candidate(
            record,
            segment_id="seg-1",
            reason="keep original wording",
        )

        self.assertEqual(updated.segments[0].text, "React dum")
        self.assertEqual(updated.correction_log[0].status, "rejected")
        self.assertFalse(updated.correction_log[0].applied)
        self.assertEqual(
            updated.correction_log[0].provider_metadata["rejection_reason"],
            "keep original wording",
        )

    def test_rejects_non_reviewable_candidate(self):
        record = replace(
            _record_with_review_candidate(),
            correction_log=[
                replace(
                    _record_with_review_candidate().correction_log[0],
                    status="applied",
                )
            ],
        )

        with self.assertRaises(ValidationError) as context:
            approve_correction_candidate(record, segment_id="seg-1")

        self.assertEqual(
            context.exception.detail.code,
            "correction_candidate_not_found",
        )


def _record_with_review_candidate():
    return replace(
        lecture_record(
            [
                segment("seg-1", "00:00:00.000", "00:00:10.000", "React dum"),
            ]
        ),
        correction_log=[
            CorrectionLogEntry(
                segment_id="seg-1",
                start_ts="00:00:00.000",
                end_ts="00:00:10.000",
                original_text="React dum",
                corrected_text="React DOM",
                confidence=0.82,
                reason="likely typo",
                status="review_required",
                source="subtitle",
            )
        ],
    )


if __name__ == "__main__":
    unittest.main()
