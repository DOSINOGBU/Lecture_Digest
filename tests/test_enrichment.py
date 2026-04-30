import json
import tempfile
import unittest
from pathlib import Path

from lecturedigest.chunking import chunk_lecture
from lecturedigest.enrichment import apply_ocr_enrichment
from lecturedigest.errors import EnrichmentError, ValidationError
from lecturedigest.ingestion import register_lecture


class EnrichmentTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_imports_slide_ocr_and_links_refined_text_to_segments(self):
        record = _lecture_with_subtitle(self.root)
        ocr_result = self.root / "ocr.json"
        _write_ocr_payload(
            ocr_result,
            frames=[
                _frame(
                    "00:00:00,500",
                    change_score=1.0,
                    raw="Raw first slide",
                    refined="Refined first slide",
                ),
                _frame(
                    "00:00:03,000",
                    change_score=0.1,
                    raw="Ignored minor change",
                    refined="Ignored minor change",
                ),
                _frame(
                    "00:00:05,000",
                    change_score=0.5,
                    raw="Raw second slide",
                    refined="Refined second slide",
                ),
            ],
        )

        updated = apply_ocr_enrichment(record, ocr_result_path=ocr_result)

        self.assertEqual(updated.status, "ocr_enriched")
        self.assertEqual(updated.stage, "enrichment")
        self.assertEqual(len(updated.slides), 2)
        self.assertEqual(updated.slides[0].raw_ocr_text, "Raw first slide")
        self.assertEqual(updated.slides[0].refined_ocr_text, "Refined first slide")
        self.assertEqual(updated.segments[0].ocr_text, "Refined first slide")
        self.assertEqual(updated.segments[0].slide_id, "slide-000001")
        self.assertEqual(updated.segments[1].ocr_text, "Refined second slide")
        self.assertEqual(updated.segments[1].source_frame_ts, "00:00:05.000")

    def test_ocr_failure_records_issue_without_blocking_transcript(self):
        record = _lecture_with_subtitle(self.root)
        ocr_result = self.root / "ocr.json"
        _write_ocr_payload(
            ocr_result,
            frames=[
                {
                    "source_frame_ts": "00:00:00,500",
                    "change_score": 1.0,
                    "status": "failed",
                    "frame_width": 1920,
                    "frame_height": 1080,
                }
            ],
        )

        updated = apply_ocr_enrichment(record, ocr_result_path=ocr_result)

        self.assertEqual(updated.status, "transcript_ready")
        self.assertEqual(updated.stage, "enrichment")
        self.assertEqual(len(updated.slides), 1)
        self.assertEqual(updated.slides[0].status, "failed")
        self.assertEqual(updated.segments[0].ocr_text, None)
        self.assertIn("ocr_failed", [issue.code for issue in updated.issues])

    def test_low_resolution_frame_is_flagged_but_still_linked(self):
        record = _lecture_with_subtitle(self.root)
        ocr_result = self.root / "ocr.json"
        _write_ocr_payload(
            ocr_result,
            frames=[
                _frame(
                    "00:00:00,500",
                    change_score=1.0,
                    raw="Raw",
                    refined="Refined",
                    width=1280,
                    height=720,
                )
            ],
        )

        updated = apply_ocr_enrichment(record, ocr_result_path=ocr_result)

        self.assertEqual(updated.segments[0].ocr_text, "Refined")
        self.assertIn(
            "ocr_frame_below_original_resolution",
            [issue.code for issue in updated.issues],
        )

    def test_chunking_carries_unique_refined_ocr_text(self):
        record = _lecture_with_subtitle(self.root)
        ocr_result = self.root / "ocr.json"
        _write_ocr_payload(
            ocr_result,
            frames=[
                _frame(
                    "00:00:00,500",
                    change_score=1.0,
                    raw="Raw first slide",
                    refined="Refined first slide",
                )
            ],
        )
        enriched = apply_ocr_enrichment(record, ocr_result_path=ocr_result)

        chunked = chunk_lecture(enriched, window_seconds=90, overlap_seconds=15)

        self.assertEqual(chunked.chunks[0].ocr_text, "Refined first slide")

    def test_requires_transcript_segments_before_enrichment(self):
        video = self.root / "lecture.mp4"
        video.write_bytes(b"fake video")
        record = register_lecture(
            video_path=video,
            title="Intro",
            instructor="Teacher",
            category="Coding",
        )
        ocr_result = self.root / "ocr.json"
        _write_ocr_payload(ocr_result, frames=[])

        with self.assertRaises(EnrichmentError) as context:
            apply_ocr_enrichment(record, ocr_result_path=ocr_result)

        self.assertEqual(context.exception.detail.code, "segments_required")

    def test_rejects_invalid_ocr_result_schema(self):
        record = _lecture_with_subtitle(self.root)
        ocr_result = self.root / "ocr.json"
        ocr_result.write_text('{"frames": "bad"}', encoding="utf-8")

        with self.assertRaises(ValidationError) as context:
            apply_ocr_enrichment(record, ocr_result_path=ocr_result)

        self.assertEqual(context.exception.detail.code, "ocr_frames_invalid")


def _lecture_with_subtitle(root: Path):
    video = root / "lecture.mp4"
    subtitle = root / "lecture.srt"
    video.write_bytes(b"fake video")
    subtitle.write_text(
        "1\n00:00:00,000 --> 00:00:03,000\none\n\n"
        "2\n00:00:05,000 --> 00:00:08,000\ntwo\n",
        encoding="utf-8",
    )
    return register_lecture(
        video_path=video,
        subtitle_path=subtitle,
        title="Intro",
        instructor="Teacher",
        category="Coding",
    )


def _write_ocr_payload(path: Path, *, frames: list[dict[str, object]]) -> None:
    path.write_text(
        json.dumps(
            {
                "provider_metadata": {
                    "provider": "openai_vision",
                    "model": "vision-capable-model",
                    "prompt_version": "ocr-v1",
                    "detail": "original",
                    "status": "succeeded",
                    "duration_ms": 120,
                    "cost_estimate_usd": 0.01,
                },
                "frames": frames,
            }
        ),
        encoding="utf-8",
    )


def _frame(
    timestamp: str,
    *,
    change_score: float,
    raw: str,
    refined: str,
    width: int = 1920,
    height: int = 1080,
) -> dict[str, object]:
    return {
        "source_frame_ts": timestamp,
        "change_score": change_score,
        "raw_ocr_text": raw,
        "refined_ocr_text": refined,
        "confidence": 0.95,
        "frame_width": width,
        "frame_height": height,
    }


if __name__ == "__main__":
    unittest.main()
