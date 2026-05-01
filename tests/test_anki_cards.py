import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from lecturedigest.anki_cards import export_anki_cards, generate_anki_cards
from lecturedigest.anki_validation import validate_card
from lecturedigest.errors import AnkiExportError
from lecturedigest.models import LectureRecord, TranscriptSegment


class AnkiCardsTest(unittest.TestCase):
    def test_generates_cards_from_approved_note_with_sources(self):
        record = _approved_record()

        updated = generate_anki_cards(record)

        self.assertEqual(updated.status, "anki_cards_ready")
        self.assertEqual(updated.stage, "anki")
        self.assertIn("qa", _card_types(updated))
        self.assertIn("cloze", _card_types(updated))
        self.assertIn("code", _card_types(updated))
        self.assertGreaterEqual(updated.card_metadata["validity_rate"], 0.8)
        self.assertEqual(updated.card_metadata["source"], "approved_note")
        first = updated.flashcards[0]
        self.assertEqual(first["lecture_id"], "lec_1")
        self.assertEqual(first["note_section_id"], "note-sec-summary")
        self.assertEqual(first["source_note_candidate_id"], "note-1")
        self.assertIn("difficulty_", " ".join(first["tags"]))
        self.assertEqual(first["source"]["segment_ids"], ["seg-1"])
        self.assertEqual(first["source"]["start_ts"], "00:00:00.000")
        self.assertEqual(first["source"]["mapping_status"], "mapped")

    def test_generates_application_cards_from_action_sections(self):
        record = _approved_record(
            sections=[
                {
                    "note_section_id": "note-sec-action",
                    "section_key": "action",
                    "title": "Action",
                    "text": "Apply DOM knowledge by checking how updates affect the screen.",
                    "segment_ids": ["seg-1"],
                    "start_ts": "00:00:00.000",
                    "end_ts": "00:00:10.000",
                }
            ]
        )

        updated = generate_anki_cards(record, card_types="application")

        self.assertEqual(_card_types(updated), {"application"})
        self.assertEqual(updated.flashcards[0]["status"], "ready")

    def test_skips_code_cards_when_note_has_no_code_or_command(self):
        record = _approved_record(
            sections=[
                {
                    "note_section_id": "note-sec-concept",
                    "title": "Concept",
                    "text": "The browser renders the page from structured documents.",
                    "segment_ids": ["seg-1"],
                    "start_ts": "00:00:00.000",
                    "end_ts": "00:00:10.000",
                }
            ]
        )

        updated = generate_anki_cards(record, card_types="code")

        self.assertEqual(updated.flashcards, [])
        self.assertEqual(updated.card_metadata["card_count"], 0)

    def test_uses_adaptive_card_count_when_max_cards_is_not_provided(self):
        sections = [
            {
                "note_section_id": f"note-sec-{index}",
                "title": f"Topic {index}",
                "text": "DOM and CSS explain browser rendering.",
                "segment_ids": ["seg-1"],
                "start_ts": "00:00:00.000",
                "end_ts": "00:00:10.000",
            }
            for index in range(1, 12)
        ]
        record = _approved_record(sections=sections, strategy="standard", estimated_tokens=2200)

        updated = generate_anki_cards(record)

        plan = updated.card_metadata["generation_plan"]
        self.assertEqual(plan["strategy"], "standard")
        self.assertGreaterEqual(plan["target_card_count"], 24)
        self.assertLessEqual(len(updated.flashcards), plan["target_card_count"])

    def test_max_cards_limits_adaptive_count(self):
        updated = generate_anki_cards(
            _approved_record(strategy="standard", estimated_tokens=2200),
            max_cards=2,
        )

        self.assertLessEqual(len(updated.flashcards), 2)
        self.assertEqual(updated.card_metadata["generation_plan"]["requested_max_cards"], 2)

    def test_requires_approved_note_before_card_generation(self):
        with self.assertRaises(AnkiExportError) as context:
            generate_anki_cards(_base_record())

        self.assertEqual(context.exception.detail.code, "approved_note_required")

    def test_flags_cards_without_source_mapping(self):
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

        updated = generate_anki_cards(record)

        self.assertTrue(updated.flashcards)
        self.assertEqual(updated.flashcards[0]["status"], "flagged")
        self.assertIn(
            "source_mapping_required",
            updated.flashcards[0]["validation"]["failed_rules"],
        )

    def test_validation_flags_answer_leaked_in_front(self):
        card = validate_card(
            {
                "card_type": "qa",
                "front": "DOM is the Document Object Model. What is DOM?",
                "back": "DOM is the Document Object Model.",
                "source": {"mapping_status": "mapped"},
            }
        )

        self.assertEqual(card["status"], "flagged")
        self.assertIn("answer_leaked_in_front", card["validation"]["failed_rules"])

    def test_duplicate_cards_are_removed(self):
        sections = [
            {
                "note_section_id": f"note-sec-{index}",
                "title": "Repeated Topic",
                "text": "The browser renders structured documents.",
                "segment_ids": ["seg-1"],
                "start_ts": "00:00:00.000",
                "end_ts": "00:00:10.000",
            }
            for index in range(2)
        ]

        updated = generate_anki_cards(_approved_record(sections=sections), card_types="qa")

        self.assertEqual(len(updated.flashcards), 1)
        self.assertEqual(updated.card_metadata["removed_duplicate_count"], 1)

    def test_exports_ready_cards_to_anki_tsv(self):
        record = generate_anki_cards(_approved_record())
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "cards.tsv"

            updated, result = export_anki_cards(record, output_path=output)

            self.assertEqual(updated.status, "anki_exported")
            self.assertEqual(result.export_format, "anki_tsv")
            self.assertEqual(result.exported_count, len(record.flashcards))
            self.assertTrue(output.exists())
            exported = output.read_text(encoding="utf-8")
            self.assertIn("Deck\tNote Type\tFront\tBack\tTags\tSource", exported)
            self.assertIn("LectureDigest", exported)
            self.assertIn("source: seg-1", exported)
            self.assertEqual(len(updated.anki_exports), 1)

    def test_export_skips_flagged_cards_by_default(self):
        record = generate_anki_cards(
            _approved_record(
                sections=[
                    {
                        "note_section_id": "note-sec-missing",
                        "title": "Missing Source",
                        "text": "React renders components.",
                        "segment_ids": [],
                    },
                    {
                        "note_section_id": "note-sec-ready",
                        "title": "Ready Source",
                        "text": "The browser renders a page.",
                        "segment_ids": ["seg-1"],
                        "start_ts": "00:00:00.000",
                        "end_ts": "00:00:10.000",
                    },
                ]
            ),
            card_types="qa",
        )
        with tempfile.TemporaryDirectory() as tmp:
            _, result = export_anki_cards(record, output_path=Path(tmp) / "cards.tsv")

            self.assertEqual(result.exported_count, 1)
            self.assertEqual(result.skipped_flagged_count, 1)

    def test_exports_cards_to_json_with_prd_fields(self):
        record = generate_anki_cards(_approved_record(), max_cards=1)
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "cards.json"

            _, result = export_anki_cards(
                record,
                output_path=output,
                export_format="json",
            )

            payload = json.loads(output.read_text(encoding="utf-8"))
            card = payload["cards"][0]
            self.assertEqual(result.export_format, "json")
            self.assertEqual(card["lecture_id"], "lec_1")
            self.assertEqual(card["source_segment_ids"], ["seg-1"])
            self.assertIn("jump_link", card)

    def test_export_requires_generated_cards(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(AnkiExportError) as context:
                export_anki_cards(_approved_record(), output_path=Path(tmp) / "x.tsv")

        self.assertEqual(context.exception.detail.code, "flashcards_required")


def _card_types(record: LectureRecord) -> set[str]:
    return {str(card["card_type"]) for card in record.flashcards}


def _approved_record(
    sections: list[dict[str, object]] | None = None,
    *,
    strategy: str = "tiny",
    estimated_tokens: int = 240,
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
            "text": "`app.py` receives browser output from ReactDOM.",
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
        note_metadata={
            "content_profile": {
                "strategy": strategy,
                "estimated_tokens": estimated_tokens,
            }
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
