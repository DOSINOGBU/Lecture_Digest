import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from lecturedigest.anki_cards import export_anki_cards, generate_anki_cards
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
        first = updated.flashcards[0]
        self.assertEqual(first["source"]["segment_ids"], ["seg-1"])
        self.assertEqual(first["source"]["start_ts"], "00:00:00.000")
        self.assertEqual(first["source"]["mapping_status"], "mapped")

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

    def test_export_requires_generated_cards(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(AnkiExportError) as context:
                export_anki_cards(_approved_record(), output_path=Path(tmp) / "x.tsv")

        self.assertEqual(context.exception.detail.code, "flashcards_required")


def _card_types(record: LectureRecord) -> set[str]:
    return {str(card["card_type"]) for card in record.flashcards}


def _approved_record(sections: list[dict[str, object]] | None = None) -> LectureRecord:
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
