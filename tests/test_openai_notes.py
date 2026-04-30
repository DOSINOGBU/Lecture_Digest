import json
import unittest
from dataclasses import replace

from lecturedigest.models import TranscriptChunk
from lecturedigest.openai_notes import (
    DEFAULT_OPENAI_NOTE_MODEL,
    build_note_request,
    generate_note_candidates_with_openai,
    parse_note_response,
)
from support import (
    chunked_lecture,
    json_response,
    lecture_record,
    openai_client,
    segment,
    sequence_openai_client,
)


class OpenAINotesTest(unittest.TestCase):
    def test_builds_responses_request_for_note_generation(self):
        record = chunked_lecture()

        request = build_note_request(record, tone="formal")

        self.assertEqual(request.endpoint, "/v1/responses")
        self.assertEqual(request.use_case, "note_generation")
        self.assertEqual(request.model, DEFAULT_OPENAI_NOTE_MODEL)
        self.assertEqual(
            request.external_data_boundary,
            "lecture transcript chunks to OpenAI Responses API",
        )
        payload = json.loads(request.body.decode("utf-8"))
        self.assertEqual(payload["model"], DEFAULT_OPENAI_NOTE_MODEL)
        self.assertEqual(payload["text"]["format"]["type"], "json_object")
        prompt_text = payload["input"][1]["content"][0]["text"]
        self.assertIn("source_chunks", prompt_text)
        self.assertIn("content_profile", prompt_text)
        self.assertIn("required_markdown_order", prompt_text)
        self.assertIn("difficulty_explanation_policy", prompt_text)

    def test_generates_openai_note_candidates_from_response_text(self):
        record = chunked_lecture()
        client = sequence_openai_client(
            [
                _single_candidate_response(_candidate_payload("balanced")),
                _single_candidate_response(_candidate_payload("concept_focused")),
                _single_candidate_response(_candidate_payload("action_focused")),
            ]
        )

        result = _generate_with_openai(record, client)

        self.assertEqual(result.record.status, "note_candidates_ready")
        self.assertEqual(len(result.record.note_candidates), 3)
        candidate = result.record.note_candidates[0]
        self.assertTrue(str(candidate["candidate_id"]).startswith("note-candidate-openai-"))
        self.assertEqual(candidate["model"], DEFAULT_OPENAI_NOTE_MODEL)
        self.assertEqual(candidate["validation"]["status"], "review_required")
        self.assertIn("provider_metadata", candidate)
        self.assertTrue(str(candidate["markdown"]).startswith("# Intro"))
        self.assertIn("## 강의 한 줄 요약", str(candidate["markdown"]))
        self.assertIn("## 핵심 용어 정리", str(candidate["markdown"]))
        self.assertEqual(len(candidate["sections"]), 7)
        self.assertEqual(candidate["content_profile"]["strategy"], "tiny")
        self.assertEqual(candidate["sections"][0]["segment_ids"], ["seg-1", "seg-2"])
        self.assertEqual(
            candidate["generator_notes"]["difficulty_explanations"][0]["term"],
            "React",
        )

    def test_marks_previous_approved_note_stale(self):
        record = chunked_lecture()
        record = replace(
            record,
            approved_note={
                "status": "approved",
                "model": "local-scriptdigest-v1",
                "prompt_version": "markdown-note-v1",
            },
        )
        client = sequence_openai_client(
            [
                _single_candidate_response(_candidate_payload("balanced")),
                _single_candidate_response(_candidate_payload("concept_focused")),
                _single_candidate_response(_candidate_payload("action_focused")),
            ]
        )

        result = _generate_with_openai(record, client)

        self.assertEqual(result.record.approved_note["status"], "stale")
        self.assertTrue(result.record.note_metadata["approved_note_stale"])

    def test_rejects_incomplete_candidate_response(self):
        record = chunked_lecture()

        with self.assertRaises(Exception) as context:
            parse_note_response(
                json.dumps({"candidates": [_candidate_payload("balanced")]}),
                record=record,
                source_units=[],
                tone="formal",
                model=DEFAULT_OPENAI_NOTE_MODEL,
                prompt_version="openai-markdown-note-v1",
                client_result=openai_client(_note_response()).send(
                    build_note_request(record, tone="formal"),
                    dry_run=True,
                ),
            )

        self.assertIn("3 candidate", str(context.exception))

    def test_repairs_flagged_openai_candidate(self):
        record = _standard_lecture()
        client = sequence_openai_client(
            [
                _single_candidate_response(_standard_candidate_payload("balanced", topics=1, questions=2)),
                _single_candidate_response(_standard_candidate_payload("concept_focused")),
                _single_candidate_response(_standard_candidate_payload("action_focused")),
                _single_candidate_response(_standard_candidate_payload("balanced")),
            ]
        )

        result = _generate_with_openai(record, client, repair=True)

        self.assertEqual(len(result.record.note_candidates), 3)
        self.assertEqual(len(result.client_results), 4)
        repaired = result.record.note_candidates[0]
        self.assertEqual(repaired["validation"]["status"], "review_required")
        self.assertEqual(repaired["repair_metadata"]["applied"], True)
        self.assertEqual(
            repaired["provider_metadata"]["use_case"],
            "note_generation_repair",
        )
        self.assertEqual(result.record.note_metadata["repair_attempted_count"], 1)
        self.assertEqual(result.record.note_metadata["repair_success_count"], 1)

    def test_candidate_limit_generates_one_candidate_and_checkpoints(self):
        record = chunked_lecture()
        client = sequence_openai_client(
            [_single_candidate_response(_candidate_payload("balanced"))]
        )
        checkpoints = []

        result = _generate_with_openai(
            record,
            client,
            candidate_limit=1,
            checkpoint=checkpoints.append,
        )

        self.assertEqual(result.record.status, "note_candidates_ready")
        self.assertEqual(len(result.record.note_candidates), 1)
        self.assertEqual(len(client.transport.calls), 1)
        self.assertEqual(len(checkpoints), 1)
        self.assertEqual(len(checkpoints[0].note_candidates), 1)
        progress = result.record.note_metadata["generation_progress"]
        self.assertEqual(progress["completed_variants"], ["balanced"])
        self.assertEqual(progress["pending_variants"], [])

    def test_resume_skips_existing_candidate(self):
        record = chunked_lecture()
        first_client = sequence_openai_client(
            [_single_candidate_response(_candidate_payload("balanced"))]
        )
        first = _generate_with_openai(record, first_client, candidate_limit=1)
        resume_client = sequence_openai_client([])

        result = _generate_with_openai(
            first.record,
            resume_client,
            candidate_limit=1,
            resume=True,
        )

        self.assertEqual(result.record.status, "note_candidates_ready")
        self.assertEqual(len(result.record.note_candidates), 1)
        self.assertEqual(len(resume_client.transport.calls), 0)
        progress = result.record.note_metadata["generation_progress"]
        self.assertEqual(progress["skipped_variants"], ["balanced"])
        self.assertEqual(progress["call_count"], 0)

    def test_time_budget_saves_partial_without_openai_call(self):
        record = chunked_lecture()
        client = sequence_openai_client(
            [_single_candidate_response(_candidate_payload("balanced"))]
        )

        result = _generate_with_openai(
            record,
            client,
            candidate_limit=1,
            time_budget_seconds=0,
        )

        self.assertEqual(result.record.status, "note_candidates_partial")
        self.assertEqual(result.record.note_candidates, [])
        self.assertEqual(len(client.transport.calls), 0)
        progress = result.record.note_metadata["generation_progress"]
        self.assertEqual(progress["status"], "partial")
        self.assertEqual(progress["pending_variants"], ["balanced"])
        self.assertTrue(progress["time_budget_exhausted"])


def _note_response():
    return json_response(
        {
            "output": [
                {
                    "content": [
                        {
                            "text": json.dumps(
                                {
                                    "candidates": [
                                        _candidate_payload("balanced"),
                                        _candidate_payload("concept_focused"),
                                        _candidate_payload("action_focused"),
                                    ]
                                }
                            )
                        }
                    ]
                }
            ]
        }
    )


def _generate_with_openai(record, client, **kwargs):
    return generate_note_candidates_with_openai(
        record,
        client=client,
        tone="formal",
        **kwargs,
    )


def _single_candidate_response(candidate: dict[str, object]):
    return json_response(
        {
            "output": [
                {
                    "content": [
                        {"text": json.dumps({"candidates": [candidate]})}
                    ]
                }
            ]
        }
    )


def _candidate_payload(variant: str) -> dict[str, object]:
    return {
        "variant": variant,
        "sections": [
            _section("one_line_summary", "## 강의 한 줄 요약", "React renders components."),
            _section("learning_goals", "## 학습 목표", "- React rendering을 설명할 수 있다."),
            _section("topic_1", "## 1. React rendering", "Components describe UI, then React DOM updates."),
            _section("practical_takeaways", "## 실무 관점에서 기억할 것", "- Review component rendering."),
            _section(
                "key_terms",
                "## 핵심 용어 정리",
                "| 용어 | 의미 |\n| --- | --- |\n| React | UI rendering library. |",
            ),
            _section("review_questions", "## 복습 질문", "1. React DOM은 무엇을 업데이트하는가?"),
            _section("final_summary", "## 최종 정리", "React components describe UI and React DOM updates it."),
        ],
        "notes": {
            "difficulty_explanations": [
                {
                    "term": "React",
                    "reason": "technical_tool_or_keyword",
                    "difficulty": "medium",
                    "expanded_form": "",
                    "expansion_known": False,
                    "plain_explanation": (
                        "쉽게 말하면, React는 화면을 작은 조각으로 나누어 "
                        "관리하도록 돕는 도구입니다."
                    ),
                    "source_segment_ids": ["seg-1", "seg-2"],
                    "analogy_used": True,
                },
                {
                    "term": "UI",
                    "reason": "english_acronym",
                    "difficulty": "high",
                    "expanded_form": "User Interface",
                    "expansion_known": True,
                    "plain_explanation": "쉽게 말하면 사용자가 직접 보고 누르고 입력하는 화면 부분입니다.",
                    "source_segment_ids": ["seg-1", "seg-2"],
                    "analogy_used": False,
                },
                {
                    "term": "DOM",
                    "reason": "english_acronym",
                    "difficulty": "high",
                    "expanded_form": "Document Object Model",
                    "expansion_known": True,
                    "plain_explanation": "쉽게 말하면 브라우저가 HTML 문서를 다루기 쉽게 정리해 둔 구조입니다.",
                    "source_segment_ids": ["seg-1", "seg-2"],
                    "analogy_used": False,
                }
            ]
        },
    }


def _standard_candidate_payload(
    variant: str,
    *,
    topics: int = 5,
    questions: int = 8,
    terms: int = 8,
    goals: int = 4,
) -> dict[str, object]:
    sections = [
        _section(
            "one_line_summary",
            "## Lecture one-line summary",
            "Browser rendering turns source text into visible behavior.",
        ),
        _section(
            "learning_goals",
            "## Learning goals",
            "\n".join(
                f"- Explain browser rendering goal {index}."
                for index in range(1, goals + 1)
            ),
        ),
    ]
    for index in range(1, topics + 1):
        sections.append(
            _section(
                f"topic_{index}",
                f"## {index}. Browser topic {index}",
                _dense_topic_text(index),
            )
        )
    sections.extend(
        [
            _section(
                "practical_takeaways",
                "## Practical takeaways",
                _dense_paragraph("Trace the browser behavior from source to screen", 12),
            ),
            _section(
                "key_terms",
                "## Key terms",
                "| Term | Meaning |\n| --- | --- |\n"
                + "\n".join(
                    f"| Term {index} | Source-backed meaning {index}. |"
                    for index in range(1, terms + 1)
                ),
            ),
            _section(
                "review_questions",
                "## Review questions",
                "\n".join(
                    f"{index}. Why does browser behavior {index} matter?"
                    for index in range(1, questions + 1)
                ),
            ),
            _section(
                "final_summary",
                "## Final summary",
                _dense_paragraph(
                    "The lecture connects source code, browser parsing, and visible output",
                    14,
                ),
            ),
        ]
    )
    return {"variant": variant, "sections": sections}


def _section(section_key: str, title: str, text: str) -> dict[str, object]:
    return {
        "section_key": section_key,
        "title": title,
        "text": text,
        "source_segment_ids": ["seg-1", "seg-2"],
    }


def _dense_topic_text(index: int) -> str:
    return "\n\n".join(
        [
            f"### Browser detail {index}\n\n"
            + _dense_paragraph(f"Topic {index} defines browser behavior", 12),
            "- The browser parses source text.\n- The rendering engine prepares visible output.",
            "| View | Meaning |\n| --- | --- |\n| Source | Input text |\n| Screen | Visible behavior |",
        ]
    )


def _dense_paragraph(prefix: str, count: int) -> str:
    return " ".join(
        f"{prefix} with source-backed detail sentence {index}."
        for index in range(1, count + 1)
    )


def _standard_lecture():
    segments = [
        segment(
            f"seg-{index}",
            _ts(index - 1),
            _ts(index),
            (
                "browser rendering document model layout paint script "
                "source behavior learning concept detail"
            ),
        )
        for index in range(1, 81)
    ]
    chunks = []
    for chunk_index, start in enumerate(range(0, len(segments), 20), start=1):
        batch = segments[start : start + 20]
        chunks.append(
            TranscriptChunk(
                chunk_id=f"chunk-{chunk_index:06d}",
                lecture_id="lec_1",
                chapter=f"chapter-{chunk_index}",
                start_ts=batch[0].start_ts,
                end_ts=batch[-1].end_ts,
                text=" ".join(item.text for item in batch),
                segment_ids=[item.segment_id for item in batch],
            )
        )
    return replace(
        lecture_record(segments),
        status="chunks_ready",
        stage="chunking",
        chunks=chunks,
    )


def _ts(seconds: int) -> str:
    return f"00:{seconds // 60:02d}:{seconds % 60:02d}.000"


if __name__ == "__main__":
    unittest.main()
