import json
import unittest
from dataclasses import replace

from lecturedigest.errors import AnkiExportError
from lecturedigest.openai_anki_cards import (
    DEFAULT_OPENAI_CARD_MODEL,
    generate_anki_cards_with_openai,
)
from support import json_response, lecture_record, segment, sequence_openai_client


class OpenAIAnkiCardsTest(unittest.TestCase):
    def test_dry_run_builds_openai_request_without_saving_cards(self):
        record = _approved_record()

        result = generate_anki_cards_with_openai(record, dry_run=True)

        self.assertTrue(result.dry_run)
        self.assertEqual(result.record.flashcards, [])
        self.assertEqual(len(result.client_results), 1)
        call = result.client_results[0].metadata
        self.assertEqual(call.status, "dry_run")
        self.assertEqual(call.use_case, "anki_card_generation")
        self.assertEqual(call.model, DEFAULT_OPENAI_CARD_MODEL)

    def test_generates_ai_cards_from_openai_response(self):
        record = _approved_record()

        result = _generate_with_cards(record, _cards_payload())

        self.assertEqual(result.record.status, "anki_cards_ready")
        self.assertEqual(result.record.card_metadata["provider"], "openai_responses")
        self.assertEqual(len(result.record.flashcards), 4)
        self.assertEqual(_card_types(result.record), {"qa", "cloze", "code", "application"})
        for card in result.record.flashcards:
            self.assertEqual(card["status"], "ready")
            self.assertEqual(card["source_segment_ids"], ["seg-1"])
            self.assertEqual(card["source_note_candidate_id"], "note-1")
            self.assertEqual(card["model"], DEFAULT_OPENAI_CARD_MODEL)

    def test_generates_unique_ids_for_similar_ai_cards(self):
        record = _approved_record()
        shared_prefix = "What should you remember about browser rendering when "
        cards = [
            {
                "card_id": "model-card",
                "card_type": "qa",
                "note_section_id": "note-sec-1",
                "front": shared_prefix + "the DOM structure changes?",
                "back": "Check whether the DOM structure changed as expected.",
                "source_segment_ids": ["seg-1"],
            },
            {
                "card_id": "model-card",
                "card_type": "qa",
                "note_section_id": "note-sec-1",
                "front": shared_prefix + "CSS rules affect the rendered page?",
                "back": "Check whether CSS rules are changing the visual result.",
                "source_segment_ids": ["seg-1"],
            },
        ]
        result = _generate_with_cards(record, cards)

        card_ids = [str(card["card_id"]) for card in result.record.flashcards]
        self.assertEqual(len(card_ids), 2)
        self.assertEqual(len(set(card_ids)), 2)

    def test_requires_approved_note(self):
        with self.assertRaises(AnkiExportError) as context:
            generate_anki_cards_with_openai(lecture_record([]), dry_run=True)

        self.assertEqual(context.exception.detail.code, "approved_note_required")

    def test_flags_ai_card_without_source_mapping(self):
        record = _approved_record()
        result = _generate_with_cards(
            record,
            [
                {
                    "card_type": "qa",
                    "note_section_id": "note-sec-1",
                    "front": "What does DOM mean for rendering?",
                    "back": "DOM is the structure the browser can use.",
                    "source_segment_ids": [],
                }
            ],
        )

        self.assertEqual(result.record.flashcards[0]["status"], "flagged")
        self.assertIn(
            "source_mapping_required",
            result.record.flashcards[0]["validation"]["failed_rules"],
        )

    def test_flags_visible_source_on_front(self):
        record = _approved_record()
        result = _generate_with_cards(
            record,
            [
                {
                    "card_type": "qa",
                    "note_section_id": "note-sec-1",
                    "front": "source: seg-1 @ 00:00:00 What is DOM?",
                    "back": "DOM is the document structure.",
                    "source_segment_ids": ["seg-1"],
                }
            ],
        )

        self.assertEqual(result.record.flashcards[0]["status"], "flagged")
        self.assertIn(
            "source_visible_on_front",
            result.record.flashcards[0]["validation"]["failed_rules"],
        )

    def test_flags_visible_source_on_back(self):
        record = _approved_record()
        result = _generate_with_cards(
            record,
            [
                {
                    "card_type": "qa",
                    "note_section_id": "note-sec-1",
                    "front": "What is DOM used for?",
                    "back": "DOM is the document structure. source: seg-1",
                    "source_segment_ids": ["seg-1"],
                }
            ],
        )

        self.assertEqual(result.record.flashcards[0]["status"], "flagged")
        self.assertIn(
            "source_visible_on_back",
            result.record.flashcards[0]["validation"]["failed_rules"],
        )

    def test_removes_duplicate_ai_cards(self):
        record = _approved_record()
        duplicate = {
            "card_type": "qa",
            "note_section_id": "note-sec-1",
            "front": "What does the browser rendering engine do?",
            "back": "It turns parsed content into visible output.",
            "source_segment_ids": ["seg-1"],
        }
        result = _generate_with_cards(record, [duplicate, dict(duplicate)])

        self.assertEqual(len(result.record.flashcards), 1)
        self.assertEqual(
            result.record.card_metadata["generation_progress"]["completed_batches"],
            ["batch-001"],
        )

    def test_resume_skips_completed_batch(self):
        record = _approved_record()
        first = generate_anki_cards_with_openai(
            record,
            client=sequence_openai_client([_card_response(_cards_payload()[:1])]),
        )
        second_client = sequence_openai_client([])

        result = generate_anki_cards_with_openai(
            first.record,
            client=second_client,
            resume=True,
        )

        self.assertEqual(len(second_client.transport.calls), 0)
        self.assertEqual(result.record.card_metadata["generation_progress"]["skipped_batches"], ["batch-001"])
        self.assertEqual(len(result.record.flashcards), 1)

    def test_time_budget_saves_partial_without_openai_call(self):
        record = _approved_record()
        client = sequence_openai_client([_card_response(_cards_payload())])

        result = generate_anki_cards_with_openai(
            record,
            client=client,
            time_budget_seconds=0,
        )

        self.assertEqual(result.record.status, "anki_cards_partial")
        self.assertEqual(len(client.transport.calls), 0)
        progress = result.record.card_metadata["generation_progress"]
        self.assertEqual(progress["status"], "partial")
        self.assertEqual(progress["pending_batches"], ["batch-001"])
        self.assertTrue(progress["time_budget_exhausted"])

    def test_rate_limit_failure_is_retryable_metadata(self):
        record = _approved_record()
        client = sequence_openai_client(
            [json_response({"error": {"message": "rate limit"}}, status_code=429)]
        )

        result = generate_anki_cards_with_openai(record, client=client)

        progress = result.record.card_metadata["generation_progress"]
        self.assertEqual(result.record.status, "anki_cards_partial")
        self.assertEqual(progress["failed_batches"][0]["code"], "openai_rate_limited")
        self.assertTrue(progress["failed_batches"][0]["retryable"])


def _card_types(record):
    return {str(card["card_type"]) for card in record.flashcards}


def _generate_with_cards(record, cards):
    client = sequence_openai_client([_card_response(cards)])
    return generate_anki_cards_with_openai(record, client=client)


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
        },
        {
            "note_section_id": "note-sec-action",
            "section_key": "practical_takeaways",
            "title": "Action",
            "text": "Apply browser knowledge by inspecting DOM changes.",
            "segment_ids": ["seg-1"],
            "start_ts": "00:00:00.000",
            "end_ts": "00:00:10.000",
        },
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
        note_metadata={
            "content_profile": {
                "strategy": "tiny",
                "estimated_tokens": 250,
            }
        },
    )


def _card_response(cards: list[dict[str, object]]):
    return json_response(
        {
            "output": [
                {
                    "content": [
                        {"text": json.dumps({"cards": cards})}
                    ]
                }
            ]
        }
    )


def _cards_payload():
    return [
        {
            "card_type": "qa",
            "note_section_id": "note-sec-1",
            "front": "What does DOM mean in browser rendering?",
            "back": "DOM is the document structure the browser can use.",
            "difficulty": "beginner",
            "source_segment_ids": ["seg-1"],
        },
        {
            "card_type": "cloze",
            "note_section_id": "note-sec-1",
            "front": "{{c1::DOM}} means Document Object Model.",
            "cloze_text": "{{c1::DOM}} means Document Object Model.",
            "difficulty": "beginner",
            "source_segment_ids": ["seg-1"],
        },
        {
            "card_type": "code",
            "note_section_id": "note-sec-1",
            "front": "What role does the DOM API have here?",
            "back": "It provides an interface for working with the document structure.",
            "difficulty": "intermediate",
            "source_segment_ids": ["seg-1"],
        },
        {
            "card_type": "application",
            "note_section_id": "note-sec-action",
            "front": "How should you apply DOM knowledge after the lecture?",
            "back": "Inspect DOM changes when debugging browser rendering.",
            "difficulty": "beginner",
            "source_segment_ids": ["seg-1"],
        },
    ]


if __name__ == "__main__":
    unittest.main()
