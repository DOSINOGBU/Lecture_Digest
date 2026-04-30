import unittest
from dataclasses import replace

from lecturedigest.openai_quiz_grading import grade_quiz_session_with_openai
from lecturedigest.quiz_session import start_quiz_session, submit_quiz_answer
from support import json_response, lecture_record, openai_client, segment


class OpenAIQuizGradingTest(unittest.TestCase):
    def test_dry_run_does_not_change_record(self):
        record = _answered_written_session()
        session_id = record.quiz_metadata["sessions"][0]["session_id"]

        result = grade_quiz_session_with_openai(
            record,
            session_id=session_id,
            client=openai_client(json_response({"grades": []})),
            dry_run=True,
        )

        self.assertTrue(result.dry_run)
        self.assertEqual(result.record, record)
        self.assertEqual(result.client_result.metadata.status, "dry_run")

    def test_grades_written_answer_and_stores_feedback(self):
        record = _answered_written_session()
        session_id = record.quiz_metadata["sessions"][0]["session_id"]
        client = openai_client(
            json_response(
                {
                    "grades": [
                        {
                            "quiz_id": "quiz-written-1",
                            "score": 0.75,
                            "feedback": "핵심은 맞지만 CSS와 DOM 차이를 더 구분하세요.",
                            "rubric_results": ["mentions DOM", "needs sharper contrast"],
                        }
                    ]
                }
            )
        )

        result = grade_quiz_session_with_openai(
            record,
            session_id=session_id,
            client=client,
        )

        session = result.record.quiz_metadata["sessions"][0]
        answer = session["answers"][0]
        self.assertEqual(session["status"], "graded")
        self.assertEqual(session["grading"]["status"], "completed")
        self.assertEqual(answer["grading_status"], "graded")
        self.assertEqual(answer["score"], 0.75)
        self.assertIn("provider_metadata", answer)

    def test_openai_failure_is_stored_as_retryable_grading_state(self):
        record = _answered_written_session()
        session_id = record.quiz_metadata["sessions"][0]["session_id"]
        client = openai_client(json_response({"error": "rate limit"}, status_code=429))

        result = grade_quiz_session_with_openai(
            record,
            session_id=session_id,
            client=client,
        )

        session = result.record.quiz_metadata["sessions"][0]
        self.assertEqual(session["status"], "grading_failed")
        self.assertEqual(session["grading"]["status"], "failed")
        self.assertEqual(session["grading"]["code"], "openai_rate_limited")
        self.assertTrue(session["grading"]["retryable"])

    def test_session_without_written_answers_finishes_without_openai_call(self):
        record = start_quiz_session(_record_with_items([_mcq_item()]))
        session_id = record.quiz_metadata["sessions"][0]["session_id"]
        record = submit_quiz_answer(
            record,
            session_id=session_id,
            quiz_id="quiz-mcq-1",
            answer="A",
        )

        result = grade_quiz_session_with_openai(record, session_id=session_id)

        session = result.record.quiz_metadata["sessions"][0]
        self.assertEqual(session["status"], "graded")
        self.assertEqual(session["grading"]["status"], "no_written_answers")


def _answered_written_session():
    record = start_quiz_session(_record_with_items([_written_item()]))
    session_id = record.quiz_metadata["sessions"][0]["session_id"]
    return submit_quiz_answer(
        record,
        session_id=session_id,
        quiz_id="quiz-written-1",
        answer="DOM is the browser object tree for the page.",
    )


def _record_with_items(items):
    return replace(
        lecture_record([segment("seg-1", "00:00:00.000", "00:00:10.000", "DOM")]),
        status="quizzes_ready",
        stage="quiz",
        quiz_items=items,
    )


def _written_item():
    return {
        "quiz_id": "quiz-written-1",
        "question_type": "written",
        "question": "Explain DOM in your own words.",
        "choices": [],
        "correct_answer": "",
        "expected_answer": "DOM is the browser object tree for a page.",
        "rubric": ["mentions browser object tree"],
        "explanation": "DOM represents the page as objects.",
        "source": _source(),
        "status": "ready",
    }


def _mcq_item():
    return {
        "quiz_id": "quiz-mcq-1",
        "question_type": "multiple_choice",
        "question": "What is DOM?",
        "choices": [
            {"id": "A", "text": "The browser object tree", "is_correct": True},
            {"id": "B", "text": "A network protocol", "is_correct": False},
            {"id": "C", "text": "A CSS rule", "is_correct": False},
            {"id": "D", "text": "A server", "is_correct": False},
        ],
        "correct_answer": "A",
        "expected_answer": "The browser object tree",
        "rubric": [],
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


if __name__ == "__main__":
    unittest.main()
