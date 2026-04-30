import unittest
from dataclasses import replace

from lecturedigest.errors import IndexingError, ValidationError
from lecturedigest.models import LectureRecord, TranscriptChunk, TranscriptSegment
from lecturedigest.rag import answer_question, build_search_index, generate_summaries


class RagTest(unittest.TestCase):
    def test_builds_index_payload_with_cache_key_and_mapping(self):
        record = _chunked_lecture()

        indexed = build_search_index(record)

        self.assertEqual(indexed.status, "index_ready")
        self.assertEqual(indexed.stage, "indexing")
        self.assertEqual(len(indexed.search_index), 1)
        entry = indexed.search_index[0]
        self.assertEqual(entry["lecture_id"], "lec_1")
        self.assertEqual(entry["segment_ids"], ["seg-1", "seg-2"])
        self.assertEqual(entry["corrected_text"], "React renders components")
        self.assertEqual(entry["refined_ocr_text"], "React DOM")
        self.assertEqual(entry["embedding_model"], "text-embedding-3-large")
        self.assertEqual(entry["vector_store"], "qdrant")
        self.assertTrue(str(entry["cache_key"]).startswith("embedding:"))
        self.assertEqual(entry["embedding_status"], "pending_external_embedding")

    def test_generates_l1_l2_l3_summaries_with_citations(self):
        record = _chunked_lecture()

        summarized = generate_summaries(record)

        self.assertEqual(summarized.status, "summaries_ready")
        self.assertEqual(summarized.stage, "summarization")
        self.assertEqual(len(summarized.summaries["l1"]), 1)
        self.assertEqual(len(summarized.summaries["l2"]), 1)
        self.assertIn("tldr", summarized.summaries["l3"])
        self.assertIn("[Intro - chapter-a - 00:00]", summarized.summaries["l1"][0]["citation"])

    def test_answers_with_citations_and_jump_links(self):
        record = build_search_index(_chunked_lecture())

        answer = answer_question(record, question="React DOM")

        self.assertEqual(answer.status, "answered")
        self.assertEqual(len(answer.citations), 1)
        self.assertIn("[Intro - chapter-a - 00:00]", answer.answer)
        self.assertEqual(answer.citations[0].segment_ids, ["seg-1", "seg-2"])
        self.assertTrue(answer.citations[0].jump_link.startswith("lecturedigest://"))

    def test_refuses_answer_when_evidence_is_insufficient(self):
        record = build_search_index(_chunked_lecture())

        answer = answer_question(record, question="database transaction")

        self.assertEqual(answer.status, "insufficient_evidence")
        self.assertEqual(answer.citations, [])
        self.assertIn("검색 근거가 충분하지 않아", answer.answer)

    def test_indexes_note_sections_with_original_segment_mapping(self):
        record = replace(
            _chunked_lecture(),
            note_sections=[
                {
                    "note_section_id": "note-sec-1",
                    "title": "Key Concept",
                    "chapter": "chapter-a",
                    "start_ts": "00:00:00.000",
                    "end_ts": "00:00:20.000",
                    "segment_ids": ["seg-1"],
                    "text": "React DOM is traced back to the original segment.",
                }
            ],
        )

        indexed = build_search_index(record)

        note_entries = [
            entry for entry in indexed.search_index if entry["kind"] == "note_section"
        ]
        self.assertEqual(len(note_entries), 1)
        self.assertEqual(note_entries[0]["segment_ids"], ["seg-1"])

    def test_requires_chunks_before_indexing(self):
        with self.assertRaises(IndexingError) as context:
            build_search_index(_lecture([]))

        self.assertEqual(context.exception.detail.code, "chunks_required")

    def test_rejects_empty_question(self):
        record = build_search_index(_chunked_lecture())

        with self.assertRaises(ValidationError) as context:
            answer_question(record, question=" ")

        self.assertEqual(context.exception.detail.code, "question_required")


def _chunked_lecture() -> LectureRecord:
    chunk = TranscriptChunk(
        chunk_id="chunk-000001",
        lecture_id="lec_1",
        chapter="chapter-a",
        start_ts="00:00:00.000",
        end_ts="00:00:20.000",
        text="React renders components",
        segment_ids=["seg-1", "seg-2"],
        ocr_text="React DOM",
    )
    return replace(
        _lecture(
            [
                _segment("seg-1", "00:00:00.000", "00:00:10.000", "React renders"),
                _segment("seg-2", "00:00:10.000", "00:00:20.000", "components"),
            ]
        ),
        status="chunks_ready",
        stage="chunking",
        chunks=[chunk],
    )


def _lecture(segments: list[TranscriptSegment]) -> LectureRecord:
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
        segments=segments,
    )


def _segment(
    segment_id: str,
    start_ts: str,
    end_ts: str,
    text: str,
) -> TranscriptSegment:
    return TranscriptSegment(
        segment_id=segment_id,
        start_ts=start_ts,
        end_ts=end_ts,
        text=text,
    )


if __name__ == "__main__":
    unittest.main()
