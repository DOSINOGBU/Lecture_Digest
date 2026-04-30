import unittest
from dataclasses import replace

from lecturedigest.errors import QuizGenerationError, ValidationError
from lecturedigest.quiz_session import (
    start_quiz_session,
    submit_quiz_answer,
    written_answers_for_grading,
)
from support import lecture_record, segment


class QuizSessionTest(unittest.TestCase):
    def test_starts_session_from_ready_quizzes_with_seeded_order(self):
        first = start_quiz_session(_record_with_quizzes(), count=2, seed=11)
        second = start_quiz_session(_record_with_quizzes(), count=2, seed=11)

        first_session = first.quiz_metadata["sessions"][0]
        second_session = second.quiz_metadata["sessions"][0]
        self.assertEqual(first.status, "quiz_session_ready")
        self.assertEqual(first.stage, "quiz_session")
        self.assertEqual(first_session["quiz_ids"], second_session["quiz_ids"])
        self.assertEqual(len(first_session["quiz_ids"]), 2)

    def test_requires_quizzes_before_session(self):
        with self.assertRaises(QuizGenerationError) as context:
            start_quiz_session(_base_record())

        self.assertEqual(context.exception.detail.code, "quizzes_required")

    def test_requires_ready_quizzes_before_session(self):
        record = replace(
            _base_record(),
            quiz_items=[{**_multiple_choice_item("quiz-1"), "status": "flagged"}],
        )

        with self.assertRaises(QuizGenerationError) as context:
            start_quiz_session(record)

        self.assertEqual(context.exception.detail.code, "ready_quizzes_required")

    def test_submit_multiple_choice_answer_grades_locally(self):
        record = start_quiz_session(_record_with_quizzes(), seed=1)
        session_id = record.quiz_metadata["sessions"][0]["session_id"]
        quiz_id = record.quiz_metadata["sessions"][0]["quiz_ids"][0]
        quiz_item = _quiz_lookup(record)[quiz_id]

        updated = submit_quiz_answer(
            record,
            session_id=session_id,
            quiz_id=quiz_id,
            answer=str(quiz_item["correct_answer"]),
        )

        answer = updated.quiz_metadata["sessions"][0]["answers"][0]
        self.assertEqual(answer["grading_status"], "graded")
        self.assertTrue(answer["is_correct"])
        self.assertEqual(answer["score"], 1.0)

    def test_submit_written_answer_waits_for_ai_grading(self):
        record = start_quiz_session(_record_with_quizzes(), seed=2)
        session = record.quiz_metadata["sessions"][0]
        written_id = _written_quiz_id(record)

        updated = submit_quiz_answer(
            record,
            session_id=session["session_id"],
            quiz_id=written_id,
            answer="DOM is the browser's structured representation of the page.",
        )

        answer = [
            item
            for item in updated.quiz_metadata["sessions"][0]["answers"]
            if item["quiz_id"] == written_id
        ][0]
        self.assertEqual(answer["grading_status"], "pending_ai_grading")
        self.assertIsNone(answer["score"])
        self.assertEqual(len(written_answers_for_grading(updated, session["session_id"])), 1)

    def test_rejects_quiz_not_in_session(self):
        record = start_quiz_session(_record_with_quizzes(), count=1, seed=3)
        session_id = record.quiz_metadata["sessions"][0]["session_id"]

        with self.assertRaises(ValidationError) as context:
            submit_quiz_answer(
                record,
                session_id=session_id,
                quiz_id="quiz-not-in-session",
                answer="A",
            )

        self.assertEqual(context.exception.detail.code, "quiz_not_found")


def _base_record():
    return lecture_record(
        [
            segment("seg-1", "00:00:00.000", "00:00:10.000", "DOM tree"),
            segment("seg-2", "00:00:10.000", "00:00:20.000", "CSS styles"),
        ]
    )


def _record_with_quizzes():
    return replace(
        _base_record(),
        status="quizzes_ready",
        stage="quiz",
        quiz_items=[
            _multiple_choice_item("quiz-mcq-1"),
            _multiple_choice_item("quiz-mcq-2"),
            _written_item("quiz-written-1"),
        ],
        quiz_metadata={"provider": "local"},
    )


def _multiple_choice_item(quiz_id: str):
    return {
        "quiz_id": quiz_id,
        "question_type": "multiple_choice",
        "question": "What does DOM represent?",
        "choices": [
            {"id": "A", "text": "The browser object tree", "is_correct": True},
            {"id": "B", "text": "A network protocol", "is_correct": False},
            {"id": "C", "text": "A stylesheet rule", "is_correct": False},
            {"id": "D", "text": "A server runtime", "is_correct": False},
        ],
        "correct_answer": "A",
        "expected_answer": "The browser object tree",
        "rubric": [],
        "source": _source(),
        "status": "ready",
    }


def _written_item(quiz_id: str):
    return {
        "quiz_id": quiz_id,
        "question_type": "written",
        "question": "Explain DOM in your own words.",
        "choices": [],
        "correct_answer": "",
        "expected_answer": "DOM is the browser object tree for a page.",
        "rubric": ["mentions browser object tree", "stays within lecture context"],
        "source": _source(),
        "status": "ready",
    }


def _source():
    return {
        "lecture_id": "lec_1",
        "segment_ids": ["seg-1"],
        "start_ts": "00:00:00.000",
        "end_ts": "00:00:10.000",
        "mapping_status": "mapped",
    }


def _quiz_lookup(record):
    return {item["quiz_id"]: item for item in record.quiz_items}


def _written_quiz_id(record):
    for item in record.quiz_items:
        if item["question_type"] == "written":
            return item["quiz_id"]
    raise AssertionError("written quiz missing")


if __name__ == "__main__":
    unittest.main()
