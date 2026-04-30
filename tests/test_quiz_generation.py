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
        self.assertEqual(item["source"]["mapping_status"], "mapped")
        self.assertNotIn("source:", item["question"].lower())

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

    def test_ready_cards_are_used_before_note_sections(self):
        record = _approved_record(
            flashcards=[
                _ready_card("card-1", "What is DOM?", "DOM is the browser object tree.", "seg-1"),
                _ready_card("card-2", "What is CSS?", "CSS styles the rendered page.", "seg-2"),
            ]
        )

        updated = generate_quizzes(
            record,
            quiz_count=2,
            seed=2,
            question_types=["multiple_choice"],
        )

        self.assertEqual(updated.quiz_metadata["source"], "ready_cards")
        self.assertTrue(all(item["source_card_ids"] for item in updated.quiz_items))
        self.assertTrue(
            all(item["input_origin"] == "ready_card" for item in updated.quiz_items)
        )

    def test_flagged_cards_are_excluded_from_quiz_inputs(self):
        record = _approved_record(
            flashcards=[
                _ready_card("card-ready", "What is DOM?", "DOM is the browser object tree.", "seg-1"),
                {
                    **_ready_card(
                        "card-flagged",
                        "What is CSS?",
                        "CSS styles the rendered page.",
                        "seg-2",
                    ),
                    "status": "flagged",
                },
            ]
        )

        updated = generate_quizzes(
            record,
            quiz_count=1,
            seed=3,
            question_types=["multiple_choice"],
        )

        self.assertEqual(updated.quiz_items[0]["source_card_ids"], ["card-ready"])

    def test_note_sections_fill_when_ready_cards_are_insufficient(self):
        record = _approved_record(
            flashcards=[
                _ready_card("card-1", "What is DOM?", "DOM is the browser object tree.", "seg-1"),
            ]
        )

        updated = generate_quizzes(
            record,
            quiz_count=3,
            seed=5,
            question_types=["multiple_choice"],
        )

        self.assertEqual(updated.quiz_metadata["source"], "mixed")
        origins = {item["input_origin"] for item in updated.quiz_items}
        self.assertEqual(origins, {"ready_card", "approved_note"})

    def test_default_quiz_count_is_adaptive(self):
        tiny = generate_quizzes(_approved_record(), seed=1)
        standard = generate_quizzes(
            _approved_record(
                sections=_many_sections(20),
                note_metadata={"content_profile": {"strategy": "standard", "estimated_tokens": 2200}},
            ),
            seed=1,
        )

        self.assertGreater(
            standard.quiz_metadata["generation_plan"]["target_quiz_count"],
            tiny.quiz_metadata["generation_plan"]["target_quiz_count"],
        )
        self.assertEqual(
            tiny.quiz_metadata["generation_plan"]["strategy"],
            "tiny",
        )
        self.assertEqual(
            standard.quiz_metadata["generation_plan"]["strategy"],
            "standard",
        )


def _question_types(record: LectureRecord) -> set[str]:
    return {str(item["question_type"]) for item in record.quiz_items}


def _approved_record(
    sections: list[dict[str, object]] | None = None,
    flashcards: list[dict[str, object]] | None = None,
    note_metadata: dict[str, object] | None = None,
) -> LectureRecord:
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
        note_metadata=note_metadata or {},
        flashcards=flashcards or [],
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


def _ready_card(card_id: str, front: str, back: str, segment_id: str) -> dict[str, object]:
    return {
        "card_id": card_id,
        "lecture_id": "lec_1",
        "note_section_id": "note-sec-summary",
        "card_type": "qa",
        "front": front,
        "back": back,
        "cloze_text": "",
        "extra": "",
        "tags": ["lecturedigest", "qa"],
        "difficulty": "beginner",
        "source_segment_ids": [segment_id],
        "start_ts": "00:00:00.000",
        "end_ts": "00:00:10.000",
        "jump_link": "lecturedigest://lecture/lec_1?t=0",
        "source_note_candidate_id": "note-1",
        "status": "ready",
        "validation": {"status": "passed", "failed_rules": []},
        "source": {
            "lecture_id": "lec_1",
            "lecture_title": "Intro",
            "title": "Intro",
            "chapter": "chapter-a",
            "segment_ids": [segment_id],
            "start_ts": "00:00:00.000",
            "end_ts": "00:00:10.000",
            "jump_link": "lecturedigest://lecture/lec_1?t=0",
            "mapping_status": "mapped",
        },
    }


def _many_sections(count: int) -> list[dict[str, object]]:
    sections = []
    for index in range(count):
        segment_id = "seg-1" if index % 2 == 0 else "seg-2"
        sections.append(
            {
                "note_section_id": f"note-sec-{index}",
                "title": f"Topic {index}",
                "text": f"Topic {index} explains a browser learning point.",
                "segment_ids": [segment_id],
                "start_ts": "00:00:00.000",
                "end_ts": "00:00:10.000",
                "chapter": f"chapter-{index // 10}",
            }
        )
    return sections


if __name__ == "__main__":
    unittest.main()
