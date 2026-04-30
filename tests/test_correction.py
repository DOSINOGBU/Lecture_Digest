import json
import tempfile
import unittest
from pathlib import Path

from lecturedigest.correction import finalize_transcript
from lecturedigest.errors import CorrectionError, ValidationError
from lecturedigest.ingestion import register_lecture


class CorrectionTest(unittest.TestCase):
    def test_applies_high_confidence_correction_and_preserves_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record = _lecture_with_subtitle(root, "helo world")
            correction_result = root / "corrections.json"
            _write_corrections(
                correction_result,
                [
                    _correction(
                        "seg-000001",
                        "hello world",
                        confidence=0.97,
                        reason="typo",
                    )
                ],
            )

            updated = finalize_transcript(
                record,
                correction_result_path=correction_result,
            )

            self.assertEqual(updated.status, "transcript_finalized")
            self.assertEqual(updated.stage, "correction")
            self.assertEqual(updated.segments[0].text, "hello world")
            self.assertEqual(updated.segments[0].segment_id, "seg-000001")
            self.assertEqual(updated.segments[0].start_ts, "00:00:01.000")
            self.assertEqual(updated.correction_log[0].original_text, "helo world")
            self.assertEqual(updated.correction_log[0].corrected_text, "hello world")
            self.assertTrue(updated.correction_log[0].applied)
            self.assertEqual(updated.correction_metadata["model"], "gpt-4o")

    def test_keeps_low_confidence_correction_for_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record = _lecture_with_subtitle(root, "helo world")
            correction_result = root / "corrections.json"
            _write_corrections(
                correction_result,
                [_correction("seg-000001", "hello world", confidence=0.72)],
            )

            updated = finalize_transcript(
                record,
                correction_result_path=correction_result,
            )

            self.assertEqual(updated.segments[0].text, "helo world")
            self.assertFalse(updated.correction_log[0].applied)
            self.assertEqual(updated.correction_log[0].status, "review_required")
            self.assertIn(
                "correction_low_confidence",
                [issue.code for issue in updated.issues],
            )

    def test_rejects_correction_that_changes_protected_terms(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record = _lecture_with_subtitle(root, "Use React 18 in app.py")
            correction_result = root / "corrections.json"
            _write_corrections(
                correction_result,
                [
                    _correction(
                        "seg-000001",
                        "Use Vue 19 in app.py",
                        confidence=0.99,
                    )
                ],
            )

            updated = finalize_transcript(
                record,
                correction_result_path=correction_result,
            )

            self.assertEqual(updated.segments[0].text, "Use React 18 in app.py")
            self.assertFalse(updated.correction_log[0].applied)
            self.assertEqual(updated.correction_log[0].protected_terms, ["18", "React"])
            self.assertIn(
                "correction_protected_token_changed",
                [issue.code for issue in updated.issues],
            )

    def test_records_failed_correction_with_retryable_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record = _lecture_with_subtitle(root, "hello")
            correction_result = root / "corrections.json"
            _write_corrections(
                correction_result,
                [
                    {
                        "segment_id": "seg-000001",
                        "status": "failed",
                        "original_error": "rate limit",
                        "retryable": True,
                    }
                ],
            )

            updated = finalize_transcript(
                record,
                correction_result_path=correction_result,
            )

            self.assertEqual(updated.segments[0].text, "hello")
            self.assertEqual(updated.correction_log[0].status, "failed")
            self.assertEqual(updated.correction_log[0].original_error, "rate limit")
            self.assertTrue(updated.correction_log[0].retryable)
            self.assertIn("correction_failed", [issue.code for issue in updated.issues])

    def test_requires_segments_before_correction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "lecture.mp4"
            video.write_bytes(b"fake video")
            record = register_lecture(
                video_path=video,
                title="Intro",
                instructor="Teacher",
                category="Coding",
            )
            correction_result = root / "corrections.json"
            _write_corrections(
                correction_result,
                [_correction("seg-000001", "hello", confidence=0.99)],
            )

            with self.assertRaises(CorrectionError) as context:
                finalize_transcript(record, correction_result_path=correction_result)

            self.assertEqual(context.exception.detail.code, "segments_required")

    def test_rejects_invalid_correction_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record = _lecture_with_subtitle(root, "hello")
            correction_result = root / "corrections.json"
            correction_result.write_text('{"corrections": "bad"}', encoding="utf-8")

            with self.assertRaises(ValidationError) as context:
                finalize_transcript(record, correction_result_path=correction_result)

            self.assertEqual(context.exception.detail.code, "correction_items_invalid")


def _lecture_with_subtitle(root: Path, text: str):
    video = root / "lecture.mp4"
    subtitle = root / "lecture.srt"
    video.write_bytes(b"fake video")
    subtitle.write_text(
        f"1\n00:00:01,000 --> 00:00:02,000\n{text}\n",
        encoding="utf-8",
    )
    return register_lecture(
        video_path=video,
        subtitle_path=subtitle,
        title="Intro",
        instructor="Teacher",
        category="Coding",
    )


def _write_corrections(path: Path, corrections: list[dict[str, object]]) -> None:
    path.write_text(
        json.dumps(
            {
                "provider_metadata": {
                    "provider": "openai_responses",
                    "model": "gpt-4o",
                    "prompt_version": "transcript-correction-v1",
                    "duration_ms": 100,
                    "cost_estimate_usd": 0.01,
                },
                "corrections": corrections,
            }
        ),
        encoding="utf-8",
    )


def _correction(
    segment_id: str,
    corrected_text: str,
    *,
    confidence: float,
    reason: str = "contextual typo",
) -> dict[str, object]:
    return {
        "segment_id": segment_id,
        "corrected_text": corrected_text,
        "confidence": confidence,
        "reason": reason,
    }


if __name__ == "__main__":
    unittest.main()
