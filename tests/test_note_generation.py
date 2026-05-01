import unittest
from dataclasses import replace

from lecturedigest.errors import NoteGenerationError, ValidationError
from lecturedigest.models import LectureRecord, TranscriptChunk, TranscriptSegment
from lecturedigest.note_generation import (
    approve_note_candidate,
    generate_note_candidates,
    reject_note_candidate,
)
from lecturedigest.note_markdown import clean_note_text


class NoteGenerationTest(unittest.TestCase):
    def test_generates_three_markdown_candidates_without_approval(self):
        record = _lecture_with_segments()

        updated = generate_note_candidates(record)

        self.assertEqual(updated.status, "note_candidates_ready")
        self.assertEqual(updated.stage, "note_generation")
        self.assertEqual(len(updated.note_candidates), 3)
        self.assertEqual(updated.note_sections, [])
        markdown = str(updated.note_candidates[0]["markdown"])
        self.assertTrue(markdown.startswith("# Intro"))
        self.assertIn("## 강의 한 줄 요약", markdown)
        self.assertIn("## 학습 목표", markdown)
        self.assertIn("## 1. React", markdown)
        self.assertIn("## 실무 관점에서 기억할 것", markdown)
        self.assertIn("## 핵심 용어 정리", markdown)
        self.assertIn("## 복습 질문", markdown)
        self.assertIn("## 최종 정리", markdown)
        self.assertNotIn("(source:", markdown)
        self.assertNotIn("seg-1", markdown)
        self.assertEqual(
            updated.note_candidates[0]["sections"][0]["segment_ids"],
            ["seg-1", "seg-2"],
        )
        self.assertIn("React DOM", markdown)
        self.assertEqual(updated.note_candidates[0]["content_profile"]["strategy"], "tiny")
        self.assertIn(
            "source_insufficient_for_full_note",
            updated.note_candidates[0]["validation"]["quality_flags"],
        )

    def test_approval_promotes_selected_candidate_to_note_sections(self):
        candidates = generate_note_candidates(_lecture_with_segments())
        candidate_id = str(candidates.note_candidates[1]["candidate_id"])

        approved = approve_note_candidate(candidates, candidate_id=candidate_id)

        self.assertEqual(approved.status, "note_approved")
        self.assertEqual(approved.stage, "note_approval")
        self.assertEqual(approved.approved_note["candidate_id"], candidate_id)
        self.assertEqual(approved.approved_note["status"], "approved")
        self.assertGreaterEqual(len(approved.note_sections), 7)
        self.assertTrue(
            all(section["segment_ids"] for section in approved.note_sections)
        )
        rejected = [
            candidate
            for candidate in approved.note_candidates
            if candidate["candidate_id"] != candidate_id
        ]
        self.assertTrue(all(candidate["status"] == "rejected" for candidate in rejected))

    def test_rejects_candidate_without_creating_final_note(self):
        candidates = generate_note_candidates(_lecture_with_segments())
        candidate_id = str(candidates.note_candidates[0]["candidate_id"])

        updated = reject_note_candidate(
            candidates,
            candidate_id=candidate_id,
            reason="needs shorter actions",
        )

        self.assertEqual(updated.status, "note_candidates_ready")
        self.assertEqual(updated.note_sections, [])
        self.assertEqual(updated.note_candidates[0]["status"], "rejected")
        self.assertEqual(updated.note_candidates[0]["rejection_reason"], "needs shorter actions")

    def test_marks_approved_note_stale_when_prompt_changes(self):
        candidates = generate_note_candidates(_lecture_with_segments())
        approved = approve_note_candidate(
            candidates,
            candidate_id=str(candidates.note_candidates[0]["candidate_id"]),
        )

        regenerated = generate_note_candidates(
            approved,
            prompt_version="markdown-note-v2",
        )

        self.assertEqual(regenerated.approved_note["status"], "stale")
        self.assertTrue(regenerated.note_metadata["approved_note_stale"])

    def test_requires_segments_before_note_generation(self):
        with self.assertRaises(NoteGenerationError) as context:
            generate_note_candidates(_lecture([]))

        self.assertEqual(context.exception.detail.code, "segments_required")

    def test_rejects_invalid_tone(self):
        with self.assertRaises(ValidationError) as context:
            generate_note_candidates(_lecture_with_segments(), tone="dramatic")

        self.assertEqual(context.exception.detail.code, "note_tone_invalid")

    def test_removes_filler_and_adjacent_repetition(self):
        cleaned = clean_note_text("um React React renders, you know, components")

        self.assertEqual(cleaned, "React renders, components")


def _lecture_with_segments() -> LectureRecord:
    return replace(
        _lecture(
            [
                _segment(
                    "seg-1",
                    "00:00:00.000",
                    "00:00:10.000",
                    "React renders components. React DOM updates the screen.",
                    ocr_text="React DOM",
                ),
                _segment(
                    "seg-2",
                    "00:00:10.000",
                    "00:00:20.000",
                    "Components describe UI flow and browser output.",
                ),
            ]
        ),
        chunks=[
            TranscriptChunk(
                chunk_id="chunk-000001",
                lecture_id="lec_1",
                chapter="chapter-a",
                start_ts="00:00:00.000",
                end_ts="00:00:20.000",
                text="React renders components. Components describe UI flow.",
                segment_ids=["seg-1", "seg-2"],
                ocr_text="React DOM",
            )
        ],
    )


def _lecture(segments: list[TranscriptSegment]) -> LectureRecord:
    return LectureRecord(
        lecture_id="lec_1",
        title="Intro",
        instructor="Teacher",
        category="Coding",
        source_path="lecture.mp4",
        subtitle_path="lecture.srt",
        status="transcript_ready",
        stage="transcription",
        transcript_source="subtitle",
        segments=segments,
    )


def _segment(
    segment_id: str,
    start_ts: str,
    end_ts: str,
    text: str,
    *,
    ocr_text: str | None = None,
) -> TranscriptSegment:
    return TranscriptSegment(
        segment_id=segment_id,
        start_ts=start_ts,
        end_ts=end_ts,
        text=text,
        ocr_text=ocr_text,
    )


if __name__ == "__main__":
    unittest.main()
