import json
import unittest
from dataclasses import replace
from unittest import mock

from lecturedigest.auto_pipeline import select_best_note_candidate
from lecturedigest.models import TranscriptChunk
from lecturedigest.openai_longform_notes import (
    LONGFORM_NOTE_PROMPT_VERSION,
    should_use_longform_notes,
)
from lecturedigest.openai_notes import generate_note_candidates_with_openai
from lecturedigest.note_markdown import source_units
from lecturedigest.note_profile import build_content_profile
from support import json_response, lecture_record, segment, sequence_openai_client
from lecturedigest.openai_types import OpenAITransportResponse


class OpenAILongformNotesTest(unittest.TestCase):
    def test_expanded_profile_uses_longform_plan_section_assembly_flow(self):
        record = _long_lecture()
        client = sequence_openai_client(
            [
                _wrapped_response({"plan": _plan(record, topic_count=10)}),
                _wrapped_response({"sections": _topic_sections(record, 1, 4)}),
                _wrapped_response({"sections": _topic_sections(record, 5, 8)}),
                _wrapped_response({"sections": _topic_sections(record, 9, 10)}),
                _wrapped_response({"candidates": [_candidate_payload(record, topic_count=10)]}),
            ]
        )

        result = generate_note_candidates_with_openai(
            record,
            client=client,
            tone="formal",
            candidate_limit=1,
            repair=True,
        )

        self.assertEqual(result.record.status, "note_candidates_ready")
        self.assertEqual(len(result.record.note_candidates), 1)
        candidate = result.record.note_candidates[0]
        self.assertEqual(candidate["prompt_version"], LONGFORM_NOTE_PROMPT_VERSION)
        self.assertEqual(candidate["validation"]["status"], "review_required")
        self.assertEqual(
            [call.metadata.use_case for call in result.client_results],
            [
                "note_generation_longform_plan",
                "note_generation_longform_section",
                "note_generation_longform_section",
                "note_generation_longform_section",
                "note_generation_longform_assembly",
            ],
        )
        metadata = result.record.note_metadata["longform_generation"]
        self.assertTrue(metadata["enabled"])
        self.assertEqual(
            metadata["auto_approval_candidate_id"],
            candidate["candidate_id"],
        )

    def test_body_too_short_assembly_is_reassembled_from_section_batches(self):
        record = _long_lecture()
        client = sequence_openai_client(
            [
                _wrapped_response({"plan": _plan(record, topic_count=10)}),
                _wrapped_response({"sections": _topic_sections(record, 1, 4)}),
                _wrapped_response({"sections": _topic_sections(record, 5, 8)}),
                _wrapped_response({"sections": _topic_sections(record, 9, 10)}),
                _wrapped_response({"candidates": [_candidate_payload(record, topic_count=10, shallow=True)]}),
            ]
        )

        result = generate_note_candidates_with_openai(
            record,
            client=client,
            tone="formal",
            candidate_limit=1,
            repair=True,
        )

        candidate = result.record.note_candidates[0]
        self.assertEqual(candidate["validation"]["status"], "review_required")
        self.assertNotIn("body_too_short", candidate["validation"]["failed_rules"])
        self.assertEqual(result.record.note_metadata["repair_attempted_count"], 0)

    def test_failed_rules_still_block_auto_approval(self):
        record = _long_lecture()
        client = sequence_openai_client(
            [
                _wrapped_response({"plan": _plan(record, topic_count=10)}),
                _wrapped_response({"sections": _topic_sections(record, 1, 4)}),
                _wrapped_response({"sections": _topic_sections(record, 5, 8)}),
                _wrapped_response({"sections": _topic_sections(record, 9, 10)}),
                _wrapped_response({"candidates": [_candidate_payload_with_visible_source(record, topic_count=10)]}),
            ]
        )

        result = generate_note_candidates_with_openai(
            record,
            client=client,
            tone="formal",
            candidate_limit=1,
            repair=False,
        )

        with self.assertRaises(Exception) as context:
            select_best_note_candidate(result.record)

        self.assertEqual(context.exception.detail.code, "auto_note_candidate_blocked")

    def test_missing_plan_topics_uses_source_backed_fallback_plan(self):
        record = _long_lecture()
        client = sequence_openai_client(
            [
                _wrapped_response({"plan": {"notes": "missing topics"}}),
                _wrapped_response({"sections": _topic_sections(record, 1, 4)}),
                _wrapped_response({"sections": _topic_sections(record, 5, 8)}),
                _wrapped_response({"sections": _topic_sections(record, 9, 10)}),
                _wrapped_response({"candidates": [_candidate_payload(record, topic_count=10)]}),
            ]
        )

        result = generate_note_candidates_with_openai(
            record,
            client=client,
            tone="formal",
            candidate_limit=1,
            repair=True,
        )

        plan = result.record.note_metadata["longform_generation"]["plan"]["balanced"]
        self.assertTrue(plan["fallback_plan_used"])
        self.assertEqual(result.record.note_candidates[0]["validation"]["status"], "review_required")

    def test_assembly_with_missing_sources_is_reassembled_from_section_batches(self):
        record = _long_lecture()
        client = sequence_openai_client(
            [
                _wrapped_response({"plan": _plan(record, topic_count=10)}),
                _wrapped_response({"sections": _topic_sections(record, 1, 4)}),
                _wrapped_response({"sections": _topic_sections(record, 5, 8)}),
                _wrapped_response({"sections": _topic_sections(record, 9, 10)}),
                _wrapped_response(
                    {"candidates": [_candidate_payload_without_sources(topic_count=10)]}
                ),
            ]
        )

        result = generate_note_candidates_with_openai(
            record,
            client=client,
            tone="formal",
            candidate_limit=1,
            repair=True,
        )

        candidate = result.record.note_candidates[0]
        self.assertEqual(candidate["validation"]["status"], "review_required")
        self.assertNotIn("source_mapping_missing", candidate["validation"]["failed_rules"])
        self.assertGreaterEqual(
            candidate["validation"]["body_depth"]["metrics"]["style_kind_count"],
            3,
        )

    def test_retryable_longform_section_failure_is_retried(self):
        record = _long_lecture()
        client = sequence_openai_client(
            [
                _wrapped_response({"plan": _plan(record, topic_count=10)}),
                _wrapped_response({"sections": _topic_sections(record, 1, 4)}),
                OpenAITransportResponse(
                    status_code=429,
                    body=b'{"error": {"message": "rate limited"}}',
                ),
                _wrapped_response({"sections": _topic_sections(record, 5, 8)}),
                _wrapped_response({"sections": _topic_sections(record, 9, 10)}),
                _wrapped_response({"candidates": [_candidate_payload(record, topic_count=10)]}),
            ]
        )

        with mock.patch("lecturedigest.openai_longform_notes.time.sleep") as sleep:
            result = generate_note_candidates_with_openai(
                record,
                client=client,
                tone="formal",
                candidate_limit=1,
                repair=True,
            )

        self.assertEqual(result.record.note_candidates[0]["validation"]["status"], "review_required")
        self.assertEqual(len(result.client_results), 6)
        sleep.assert_called_once()

    def test_chunk_count_can_route_to_longform_even_before_expanded_profile(self):
        record = _long_lecture(segment_count=60, chunk_count=12, words_per_segment=8)
        units = source_units(record.segments)
        profile = build_content_profile(units, chunks=record.chunks)

        self.assertTrue(should_use_longform_notes(record, profile))


def _long_lecture(
    *,
    segment_count: int = 180,
    chunk_count: int = 15,
    words_per_segment: int = 32,
):
    segments = [
        segment(
            f"seg-{index:06d}",
            _ts(index - 1),
            _ts(index),
            _source_sentence(index, words_per_segment),
        )
        for index in range(1, segment_count + 1)
    ]
    chunks = []
    chunk_size = max(1, len(segments) // chunk_count)
    for chunk_index, start in enumerate(range(0, len(segments), chunk_size), start=1):
        batch = segments[start : start + chunk_size]
        if not batch:
            continue
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
        if len(chunks) >= chunk_count:
            break
    return replace(
        lecture_record(segments),
        status="indexed",
        stage="index",
        chunks=chunks,
    )


def _source_sentence(index: int, words_per_segment: int) -> str:
    words = [
        "browser",
        "rendering",
        "document",
        "layout",
        "paint",
        "script",
        "style",
        "structure",
        "network",
        "storage",
    ]
    return " ".join(words[index % len(words)] for _ in range(words_per_segment))


def _plan(record, *, topic_count: int) -> dict[str, object]:
    return {
        "topics": [
            {
                "section_key": f"topic_{index}",
                "title": f"## {index}. browser rendering topic {index}",
                "purpose": f"Explain topic {index}.",
                "style_hint": "narrative",
                "source_segment_ids": _ids(record, index),
            }
            for index in range(1, topic_count + 1)
        ]
    }


def _topic_sections(record, start: int, end: int) -> list[dict[str, object]]:
    return [
        {
            "section_key": f"topic_{index}",
            "title": f"## {index}. browser rendering topic {index}",
            "text": _topic_text(index),
            "source_segment_ids": _ids(record, index),
        }
        for index in range(start, end + 1)
    ]


def _candidate_payload(
    record,
    *,
    topic_count: int,
    shallow: bool = False,
) -> dict[str, object]:
    topics = _topic_sections(record, 1, topic_count)
    if shallow:
        for topic in topics:
            topic["text"] = (
                "### shallow but structured topic\n\n"
                "Short.\n\n"
                "- One point.\n\n"
                "| View | Meaning |\n| --- | --- |\n| source | short |"
            )
    sections = [
        _section(
            "one_line_summary",
            "## lecture summary",
            _dense_text("The lecture explains browser rendering.", 10),
            _ids(record, 1),
        ),
        _section(
            "learning_goals",
            "## learning goals",
            "\n".join(f"- Explain browser rendering goal {index}." for index in range(1, 7)),
            _ids(record, 1),
        ),
        *topics,
        _section(
            "practical_takeaways",
            "## practical takeaways",
            _dense_text("Practice tracing browser behavior from document to screen.", 14),
            _ids(record, topic_count - 1),
        ),
        _section(
            "key_terms",
            "## key terms",
            "| Term | Meaning |\n| --- | --- |\n"
            + "\n".join(
                f"| term {index} | source backed meaning {index}. |"
                for index in range(1, 17)
            ),
            _ids(record, topic_count),
        ),
        _section(
            "review_questions",
            "## review questions",
            "\n".join(
                f"{index}. Why does browser rendering detail {index} matter?"
                for index in range(1, 13)
            ),
            _ids(record, topic_count),
        ),
        _section(
            "final_summary",
            "## final summary",
            _dense_text("Browser rendering connects source documents and visible output.", 18),
            _ids(record, topic_count),
        ),
    ]
    return {"variant": "balanced", "sections": sections, "notes": {"difficulty_explanations": []}}


def _candidate_payload_without_sources(*, topic_count: int) -> dict[str, object]:
    return {
        "variant": "balanced",
        "sections": [
            {
                "section_key": f"topic_{index}",
                "title": f"## {index}. browser rendering topic {index}",
                "text": _dense_text("A section exists but lacks source mapping.", 4),
                "source_segment_ids": [],
            }
            for index in range(1, topic_count + 1)
        ],
        "notes": {"difficulty_explanations": []},
    }


def _candidate_payload_with_visible_source(record, *, topic_count: int) -> dict[str, object]:
    payload = _candidate_payload(record, topic_count=topic_count)
    payload["sections"][2]["text"] += "\n\n(source: seg-000001 @ 00:00:00.000)"
    return payload


def _topic_text(index: int) -> str:
    return "\n\n".join(
        [
            f"### topic detail {index}\n\n" + _dense_text(f"Topic {index} defines the browser flow.", 20),
            "- The document is parsed.\n- The screen output is prepared.\n- The learner can trace cause and effect.",
            "| View | Meaning |\n| --- | --- |\n| source | browser input |\n| screen | visible result |",
            _dense_text(f"Topic {index} also connects practice and diagnosis.", 16),
        ]
    )


def _dense_text(prefix: str, count: int) -> str:
    return " ".join(f"{prefix} Source backed detail sentence {index}." for index in range(1, count + 1))


def _section(section_key: str, title: str, text: str, ids: list[str]) -> dict[str, object]:
    return {
        "section_key": section_key,
        "title": title,
        "text": text,
        "source_segment_ids": ids,
    }


def _ids(record, index: int) -> list[str]:
    segments = record.segments
    start = min(len(segments) - 1, (index - 1) * 6)
    return [segment.segment_id for segment in segments[start : start + 4]]


def _wrapped_response(payload: dict[str, object]):
    return json_response(
        {
            "output": [
                {
                    "content": [
                        {"text": json.dumps(payload)}
                    ]
                }
            ]
        }
    )


def _ts(seconds: int) -> str:
    return f"00:{seconds // 60:02d}:{seconds % 60:02d}.000"


if __name__ == "__main__":
    unittest.main()
