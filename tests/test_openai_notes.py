import json
import unittest
from dataclasses import replace

from lecturedigest.openai_notes import (
    DEFAULT_OPENAI_NOTE_MODEL,
    build_note_request,
    generate_note_candidates_with_openai,
    parse_note_response,
)
from support import chunked_lecture, json_response, openai_client


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
        self.assertIn("source_chunks", payload["input"][1]["content"][0]["text"])

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
        self.assertIn("[1] 강의 요약", str(candidate["markdown"]))
        self.assertEqual(len(candidate["sections"]), 4)
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


def _candidate_payload(variant: str) -> dict[str, object]:
    citation = "(source: seg-1..seg-2 @ 00:00:00.000-00:00:20.000)"
    return {
        "variant": variant,
        "sections": [
            {
                "section_key": "summary",
                "text": f"- React renders components. {citation}",
                "source_segment_ids": ["seg-1", "seg-2"],
            },
            {
                "section_key": "key_concepts",
                "text": f"- React DOM: UI updates. {citation}",
                "source_segment_ids": ["seg-1", "seg-2"],
            },
            {
                "section_key": "flow",
                "text": f"- Components describe UI, then React DOM updates. {citation}",
                "source_segment_ids": ["seg-1", "seg-2"],
            },
            {
                "section_key": "action",
                "text": f"- Review component rendering with the timestamp. {citation}",
                "source_segment_ids": ["seg-1", "seg-2"],
            },
        ],
    }


if __name__ == "__main__":
    unittest.main()
