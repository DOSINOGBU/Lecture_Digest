import json
import unittest
from dataclasses import replace

from lecturedigest.errors import QuizGenerationError
from lecturedigest.openai_quiz_prompt import (
    DEFAULT_OPENAI_QUIZ_MODEL,
    build_quiz_request,
)
from lecturedigest.openai_quizzes import generate_quizzes_with_openai
from lecturedigest.quiz_policy import resolve_quiz_generation_plan
from support import json_response, lecture_record, segment, sequence_openai_client


class OpenAIQuizzesTest(unittest.TestCase):
    def test_builds_responses_request_for_quiz_generation(self):
        record = _approved_record()
        sections = record.note_sections
        cards = record.flashcards
        plan = resolve_quiz_generation_plan(
            record,
            sections,
            cards,
            quiz_count=4,
            question_types=["multiple_choice", "written"],
        )

        request = build_quiz_request(
            record,
            sections=sections,
            ready_cards=cards,
            batch_id="batch-001",
            question_types=["multiple_choice", "written"],
            plan=plan,
            seed=3,
        )

        self.assertEqual(request.endpoint, "/v1/responses")
        self.assertEqual(request.use_case, "quiz_generation")
        self.assertEqual(request.model, DEFAULT_OPENAI_QUIZ_MODEL)
        payload = json.loads(request.body.decode("utf-8"))
        self.assertEqual(payload["model"], DEFAULT_OPENAI_QUIZ_MODEL)
        self.assertEqual(payload["text"]["format"]["type"], "json_object")
        prompt_text = payload["input"][1]["content"][0]["text"]
        self.assertIn("ready_cards", prompt_text)
        self.assertIn("approved_note", prompt_text)
        self.assertIn("allowed_question_types", prompt_text)

    def test_dry_run_builds_openai_request_without_saving_quizzes(self):
        record = _approved_record()

        result = generate_quizzes_with_openai(record, dry_run=True)

        self.assertTrue(result.dry_run)
        self.assertEqual(result.record.quiz_items, [])
        self.assertEqual(len(result.client_results), 1)
        call = result.client_results[0].metadata
        self.assertEqual(call.status, "dry_run")
        self.assertEqual(call.use_case, "quiz_generation")
        self.assertEqual(call.model, DEFAULT_OPENAI_QUIZ_MODEL)

    def test_generates_ai_quizzes_from_openai_response(self):
        record = _approved_record()
        client = sequence_openai_client([_quiz_response(_quiz_payload())])

        result = generate_quizzes_with_openai(record, client=client, quiz_count=2)

        self.assertEqual(result.record.status, "quizzes_ready")
        self.assertEqual(result.record.quiz_metadata["provider"], "openai_responses")
        self.assertEqual(len(result.record.quiz_items), 2)
        self.assertEqual(_question_types(result.record), {"multiple_choice", "written"})
        for item in result.record.quiz_items:
            self.assertEqual(item["status"], "ready")
            self.assertEqual(item["source"]["segment_ids"], ["seg-1"])
            self.assertEqual(item["source_note_candidate_id"], "note-1")
            self.assertEqual(item["model"], DEFAULT_OPENAI_QUIZ_MODEL)

    def test_requires_approved_note(self):
        with self.assertRaises(QuizGenerationError) as context:
            generate_quizzes_with_openai(lecture_record([]), dry_run=True)

        self.assertEqual(context.exception.detail.code, "approved_note_required")

    def test_flags_ai_quiz_without_source_mapping(self):
        record = _approved_record()
        client = sequence_openai_client(
            [
                _quiz_response(
                    [
                        {
                            "question_type": "written",
                            "note_section_id": "note-sec-1",
                            "question": "Explain DOM in your own words.",
                            "expected_answer": "DOM is the browser object tree.",
                            "rubric": ["mentions DOM"],
                            "source_segment_ids": [],
                        }
                    ]
                )
            ]
        )

        result = generate_quizzes_with_openai(record, client=client, quiz_count=1)

        self.assertEqual(result.record.quiz_items[0]["status"], "flagged")
        self.assertIn(
            "source_mapping_required",
            result.record.quiz_items[0]["validation"]["failed_rules"],
        )

    def test_flags_visible_source_in_question(self):
        record = _approved_record()
        client = sequence_openai_client(
            [
                _quiz_response(
                    [
                        {
                            "question_type": "written",
                            "note_section_id": "note-sec-1",
                            "question": "source: seg-1 @ 00:00:00 Explain DOM.",
                            "expected_answer": "DOM is the browser object tree.",
                            "rubric": ["mentions DOM"],
                            "source_segment_ids": ["seg-1"],
                        }
                    ]
                )
            ]
        )

        result = generate_quizzes_with_openai(record, client=client, quiz_count=1)

        self.assertEqual(result.record.quiz_items[0]["status"], "flagged")
        self.assertIn(
            "source_visible_in_question",
            result.record.quiz_items[0]["validation"]["failed_rules"],
        )

    def test_removes_duplicate_ai_quizzes(self):
        record = _approved_record()
        duplicate = _quiz_payload()[0]
        client = sequence_openai_client([_quiz_response([duplicate, dict(duplicate)])])

        result = generate_quizzes_with_openai(record, client=client, quiz_count=4)

        self.assertEqual(len(result.record.quiz_items), 1)
        self.assertEqual(
            result.record.quiz_metadata["generation_progress"]["completed_batches"],
            ["batch-001"],
        )

    def test_resume_skips_completed_batch(self):
        record = _approved_record()
        first = generate_quizzes_with_openai(
            record,
            client=sequence_openai_client([_quiz_response(_quiz_payload()[:1])]),
            quiz_count=1,
        )
        second_client = sequence_openai_client([])

        result = generate_quizzes_with_openai(
            first.record,
            client=second_client,
            quiz_count=1,
            resume=True,
        )

        self.assertEqual(len(second_client.transport.calls), 0)
        self.assertEqual(
            result.record.quiz_metadata["generation_progress"]["skipped_batches"],
            ["batch-001"],
        )
        self.assertEqual(len(result.record.quiz_items), 1)

    def test_time_budget_saves_partial_without_openai_call(self):
        record = _approved_record()
        client = sequence_openai_client([_quiz_response(_quiz_payload())])

        result = generate_quizzes_with_openai(
            record,
            client=client,
            time_budget_seconds=0,
        )

        self.assertEqual(result.record.status, "quizzes_partial")
        self.assertEqual(len(client.transport.calls), 0)
        progress = result.record.quiz_metadata["generation_progress"]
        self.assertEqual(progress["status"], "partial")
        self.assertEqual(progress["pending_batches"], ["batch-001"])
        self.assertTrue(progress["time_budget_exhausted"])

    def test_rate_limit_failure_is_retryable_metadata(self):
        record = _approved_record()
        client = sequence_openai_client(
            [json_response({"error": {"message": "rate limit"}}, status_code=429)]
        )

        result = generate_quizzes_with_openai(record, client=client)

        progress = result.record.quiz_metadata["generation_progress"]
        self.assertEqual(result.record.status, "quizzes_partial")
        self.assertEqual(progress["failed_batches"][0]["code"], "openai_rate_limited")
        self.assertTrue(progress["failed_batches"][0]["retryable"])


def _question_types(record):
    return {str(item["question_type"]) for item in record.quiz_items}


def _approved_record():
    sections = [
        {
            "note_section_id": "note-sec-1",
            "section_key": "topic_1",
            "title": "Browser rendering",
            "text": "DOM means Document Object Model. CSS styles the page.",
            "segment_ids": ["seg-1"],
            "start_ts": "00:00:00.000",
            "end_ts": "00:00:10.000",
        }
    ]
    return replace(
        lecture_record(
            [
                segment(
                    "seg-1",
                    "00:00:00.000",
                    "00:00:10.000",
                    "DOM and CSS help browser rendering.",
                )
            ]
        ),
        status="note_approved",
        stage="note_approval",
        note_sections=sections,
        approved_note={
            "candidate_id": "note-1",
            "status": "approved",
            "sections": sections,
        },
        flashcards=[
            {
                "card_id": "card-1",
                "note_section_id": "note-sec-1",
                "card_type": "qa",
                "front": "What does DOM mean in browser rendering?",
                "back": "DOM is the document structure the browser can use.",
                "difficulty": "beginner",
                "source_segment_ids": ["seg-1"],
                "status": "ready",
            }
        ],
        note_metadata={
            "content_profile": {
                "strategy": "tiny",
                "estimated_tokens": 250,
            }
        },
    )


def _quiz_response(items: list[dict[str, object]]):
    return json_response(
        {
            "output": [
                {
                    "content": [
                        {"text": json.dumps({"quizzes": items})}
                    ]
                }
            ]
        }
    )


def _quiz_payload():
    return [
        {
            "question_type": "multiple_choice",
            "note_section_id": "note-sec-1",
            "source_card_ids": ["card-1"],
            "question": "DOM은 브라우저 렌더링에서 어떤 역할을 하는가?",
            "choices": [
                {"id": "A", "text": "문서 구조를 브라우저가 다룰 수 있게 한다.", "is_correct": True},
                {"id": "B", "text": "네트워크 요청을 암호화한다.", "is_correct": False},
                {"id": "C", "text": "동영상 파일을 압축한다.", "is_correct": False},
                {"id": "D", "text": "운영체제를 설치한다.", "is_correct": False},
            ],
            "correct_answer": "A",
            "expected_answer": "문서 구조를 브라우저가 다룰 수 있게 한다.",
            "explanation": "DOM은 브라우저가 HTML 구조를 다루는 방식이다.",
            "difficulty": "beginner",
            "source_segment_ids": ["seg-1"],
        },
        {
            "question_type": "written",
            "note_section_id": "note-sec-1",
            "source_card_ids": ["card-1"],
            "question": "CSS가 렌더링된 페이지에서 맡는 역할을 설명하라.",
            "choices": [],
            "correct_answer": "",
            "expected_answer": "CSS는 화면의 스타일과 배치를 정한다.",
            "rubric": ["CSS가 스타일 규칙임을 언급한다", "화면 표시와 연결한다"],
            "explanation": "CSS는 렌더링 결과의 스타일을 조정한다.",
            "difficulty": "beginner",
            "source_segment_ids": ["seg-1"],
        },
    ]


if __name__ == "__main__":
    unittest.main()
