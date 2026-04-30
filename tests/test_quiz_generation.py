import unittest
from dataclasses import replace

from lecturedigest.errors import QuizGenerationError, ValidationError
from lecturedigest.models import LectureRecord, TranscriptSegment
from lecturedigest.quiz_generation import generate_quizzes


class QuizGenerationTest(unittest.TestCase):
    def test_generates_mixed_quizzes_from_approved_note_with_sources(self):
        record = _approved_record()

        updated = generate_quizzes(record, quiz_count=4, seed=7)

        self.assertEqual(updated.status, "quizzes_ready")
        self.assertEqual(updated.stage, "quiz")
        self.assertEqual(len(updated.quiz_items), 4)
        self.assertIn("multiple_choice", _question_types(updated))
        self.assertIn("written", _question_types(updated))
        self.assertEqual(updated.quiz_metadata["seed"], 7)
        for item in updated.quiz_items:
            self.assertEqual(item["source"]["mapping_status"], "mapped")
            self.assertTrue(item["source"]["start_ts"])
            self.assertEqual(item["status"], "ready")

    def test_multiple_choice_has_four_choices_and_one_answer(self):
        updated = generate_quizzes(
            _approved_record(),
            quiz_count=1,
            seed=1,
            question_types=["multiple_choice"],
        )

        item = updated.quiz_items[0]
        choices = item["choices"]
        correct = [choice for choice in choices if choice["is_correct"]]
        self.assertEqual(item["question_type"], "multiple_choice")
        self.assertEqual(len(choices), 4)
        self.assertEqual(len(correct), 1)
        self.assertEqual(item["correct_answer"], correct[0]["id"])

    def test_written_quiz_includes_expected_answer_and_rubric(self):
        updated = generate_quizzes(
            _approved_record(),
            quiz_count=1,
            question_types=["written"],
        )

        item = updated.quiz_items[0]
        self.assertEqual(item["question_type"], "written")
        self.assertTrue(item["expected_answer"])
        self.assertTrue(item["rubric"])
        self.assertIn("source:", item["explanation"])

    def test_seed_makes_random_order_reproducible(self):
        first = generate_quizzes(_approved_record(), quiz_count=4, seed=42)
        second = generate_quizzes(_approved_record(), quiz_count=4, seed=42)

        self.assertEqual(
            [item["quiz_id"] for item in first.quiz_items],
            [item["quiz_id"] for item in second.quiz_items],
        )

    def test_flags_quiz_without_source_mapping(self):
        record = _approved_record(
            sections=[
                {
                    "note_section_id": "note-sec-missing",
                    "title": "Missing Source",
                    "text": "React renders components.",
                    "segment_ids": [],
                }
            ]
        )

        updated = generate_quizzes(record, quiz_count=2)

        self.assertTrue(updated.quiz_items)
        self.assertTrue(all(item["status"] == "flagged" for item in updated.quiz_items))
        self.assertIn(
            "source_mapping_required",
            updated.quiz_items[0]["validation"]["failed_rules"],
        )

    def test_requires_approved_note_before_quiz_generation(self):
        with self.assertRaises(QuizGenerationError) as context:
            generate_quizzes(_base_record())

        self.assertEqual(context.exception.detail.code, "approved_note_required")

    def test_rejects_invalid_question_type(self):
        with self.assertRaises(ValidationError) as context:
            generate_quizzes(_approved_record(), question_types=["flashcard"])

        self.assertEqual(context.exception.detail.code, "quiz_question_type_invalid")


def _question_types(record: LectureRecord) -> set[str]:
    return {str(item["question_type"]) for item in record.quiz_items}


def _approved_record(sections: list[dict[str, object]] | None = None) -> LectureRecord:
    note_sections = sections or [
        {
            "note_section_id": "note-sec-summary",
            "title": "Summary",
            "text": "React renders components and updates the screen.",
            "segment_ids": ["seg-1"],
            "start_ts": "00:00:00.000",
            "end_ts": "00:00:10.000",
            "chapter": "chapter-a",
        },
        {
            "note_section_id": "note-sec-code",
            "title": "Code",
            "text": "app.py shows browser output from ReactDOM.",
            "segment_ids": ["seg-2"],
            "start_ts": "00:00:10.000",
            "end_ts": "00:00:20.000",
            "chapter": "chapter-a",
        },
    ]
    return replace(
        _base_record(),
        status="note_approved",
        stage="note_approval",
        note_sections=note_sections,
        approved_note={
            "candidate_id": "note-1",
            "status": "approved",
            "sections": note_sections,
        },
    )


def _base_record() -> LectureRecord:
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
        segments=[
            TranscriptSegment(
                segment_id="seg-1",
                start_ts="00:00:00.000",
                end_ts="00:00:10.000",
                text="React renders components.",
            ),
            TranscriptSegment(
                segment_id="seg-2",
                start_ts="00:00:10.000",
                end_ts="00:00:20.000",
                text="ReactDOM updates app.py output.",
            ),
        ],
    )


if __name__ == "__main__":
    unittest.main()
