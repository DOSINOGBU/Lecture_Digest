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

    def test_generates_openai_note_candidates_from_response_text(self):
        record = chunked_lecture()
        client = openai_client(_note_response())

        result = generate_note_candidates_with_openai(
            record,
            client=client,
            tone="formal",
        )

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
        self.assertEqual(candidate["content_profile"]["strategy"], "compact")
        self.assertEqual(candidate["sections"][0]["segment_ids"], ["seg-1", "seg-2"])

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
        client = openai_client(_note_response())

        result = generate_note_candidates_with_openai(
            record,
            client=client,
            tone="formal",
        )

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

        result = generate_note_candidates_with_openai(
            record,
            client=client,
            tone="formal",
            repair=True,
        )

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
    citation = "(source: seg-1..seg-2 @ 00:00:00.000-00:00:20.000)"
    return {
        "variant": variant,
        "sections": [
            _section("one_line_summary", "## 강의 한 줄 요약", f"React renders components. {citation}"),
            _section("learning_goals", "## 학습 목표", f"- React rendering을 설명할 수 있다. {citation}"),
            _section("topic_1", "## 1. React rendering", f"Components describe UI, then React DOM updates. {citation}"),
            _section("practical_takeaways", "## 실무 관점에서 기억할 것", f"- Review component rendering with the timestamp. {citation}"),
            _section(
                "key_terms",
                "## 핵심 용어 정리",
                f"| 용어 | 의미 |\n| --- | --- |\n| React | UI rendering library. {citation} |",
            ),
            _section("review_questions", "## 복습 질문", f"1. React DOM은 무엇을 업데이트하는가? {citation}"),
            _section("final_summary", "## 최종 정리", f"React components describe UI and React DOM updates it. {citation}"),
        ],
    }


def _standard_candidate_payload(
    variant: str,
    *,
    topics: int = 3,
    questions: int = 8,
    terms: int = 8,
    goals: int = 4,
) -> dict[str, object]:
    citation = "(source: seg-1..seg-2 @ 00:00:00.000-00:00:20.000)"
    sections = [
        _section(
            "one_line_summary",
            "## Lecture one-line summary",
            f"Browser rendering turns source text into visible behavior. {citation}",
        ),
        _section(
            "learning_goals",
            "## Learning goals",
            "\n".join(
                f"- Explain browser rendering goal {index}. {citation}"
                for index in range(1, goals + 1)
            ),
        ),
    ]
    for index in range(1, topics + 1):
        sections.append(
            _section(
                f"topic_{index}",
                f"## {index}. Browser topic {index}",
                f"Topic {index} explains a distinct browser behavior. {citation}",
            )
        )
    sections.extend(
        [
            _section(
                "practical_takeaways",
                "## Practical takeaways",
                f"- Trace the browser behavior from source to screen. {citation}",
            ),
            _section(
                "key_terms",
                "## Key terms",
                "| Term | Meaning |\n| --- | --- |\n"
                + "\n".join(
                    f"| Term {index} | Source-backed meaning {index}. {citation} |"
                    for index in range(1, terms + 1)
                ),
            ),
            _section(
                "review_questions",
                "## Review questions",
                "\n".join(
                    f"{index}. Why does browser behavior {index} matter? {citation}"
                    for index in range(1, questions + 1)
                ),
            ),
            _section(
                "final_summary",
                "## Final summary",
                f"The lecture connects source code, browser parsing, and visible output. {citation}",
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
