import unittest
from dataclasses import replace

from lecturedigest.errors import IndexingError, ValidationError
from lecturedigest.models import TranscriptChunk
from lecturedigest.rag import answer_question, build_search_index, generate_summaries
from lecturedigest.rag_vector import attach_embedding
from support import chunked_lecture, lecture_record, segment


class RagTest(unittest.TestCase):
    def test_builds_index_payload_with_cache_key_and_mapping(self):
        record = chunked_lecture()

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
        self.assertEqual(entry["vector_store"], "local_json")
        self.assertTrue(str(entry["cache_key"]).startswith("embedding:"))
        self.assertIn("source_hash", entry)
        self.assertEqual(entry["embedding_status"], "pending_external_embedding")

    def test_generates_l1_l2_l3_summaries_with_citations(self):
        record = chunked_lecture()

        summarized = generate_summaries(record)

        self.assertEqual(summarized.status, "summaries_ready")
        self.assertEqual(summarized.stage, "summarization")
        self.assertEqual(len(summarized.summaries["l1"]), 1)
        self.assertEqual(len(summarized.summaries["l2"]), 1)
        self.assertIn("tldr", summarized.summaries["l3"])
        self.assertIn("[Intro - chapter-a - 00:00]", summarized.summaries["l1"][0]["citation"])

    def test_answers_with_citations_and_jump_links(self):
        record = build_search_index(chunked_lecture())

        answer = answer_question(record, question="React DOM")

        self.assertEqual(answer.status, "answered")
        self.assertEqual(answer.search_strategy, "local_lexical_fallback")
        self.assertEqual(len(answer.citations), 1)
        self.assertIn("[Intro - chapter-a - 00:00]", answer.answer)
        self.assertEqual(answer.citations[0].segment_ids, ["seg-1", "seg-2"])
        self.assertTrue(answer.citations[0].jump_link.startswith("lecturedigest://"))

    def test_refuses_answer_when_evidence_is_insufficient(self):
        record = build_search_index(chunked_lecture())

        answer = answer_question(record, question="database transaction")

        self.assertEqual(answer.status, "insufficient_evidence")
        self.assertEqual(answer.citations, [])
        self.assertIn("검색 근거가 충분하지 않아", answer.answer)

    def test_vector_search_uses_embedding_score_before_lexical_fallback(self):
        indexed = build_search_index(_two_chunk_lecture())
        entries = [
            attach_embedding(
                indexed.search_index[0],
                [0.0, 1.0],
                metadata={"provider": "fake"},
            ),
            attach_embedding(
                indexed.search_index[1],
                [1.0, 0.0],
                metadata={"provider": "fake"},
            ),
        ]
        record = replace(indexed, search_index=entries)

        answer = answer_question(
            record,
            question="React",
            query_embedding=[1.0, 0.0],
            min_score=0.1,
        )

        self.assertEqual(answer.status, "answered")
        self.assertEqual(answer.search_strategy, "vector")
        self.assertEqual(answer.citations[0].chunk_id, "chunk-000002")

    def test_stale_embedding_uses_lexical_fallback(self):
        indexed = build_search_index(chunked_lecture())
        stale_entry = {
            **indexed.search_index[0],
            "embedding_status": "stale",
            "embedding_vector": [1.0, 0.0],
        }
        record = replace(indexed, search_index=[stale_entry])

        answer = answer_question(
            record,
            question="React DOM",
            query_embedding=[1.0, 0.0],
        )

        self.assertEqual(answer.status, "answered")
        self.assertEqual(answer.search_strategy, "lexical_fallback")

    def test_indexes_note_sections_with_original_segment_mapping(self):
        record = replace(
            chunked_lecture(),
            approved_note={"status": "approved"},
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
        self.assertEqual(note_entries[0]["note_section_id"], "note-sec-1")

    def test_requires_chunks_before_indexing(self):
        with self.assertRaises(IndexingError) as context:
            build_search_index(lecture_record([]))

        self.assertEqual(context.exception.detail.code, "chunks_required")

    def test_rejects_empty_question(self):
        record = build_search_index(chunked_lecture())

        with self.assertRaises(ValidationError) as context:
            answer_question(record, question=" ")

        self.assertEqual(context.exception.detail.code, "question_required")


def _two_chunk_lecture():
    first = TranscriptChunk(
        chunk_id="chunk-000001",
        lecture_id="lec_1",
        chapter="chapter-a",
        start_ts="00:00:00.000",
        end_ts="00:00:10.000",
        text="Database transaction isolation",
        segment_ids=["seg-1"],
    )
    second = TranscriptChunk(
        chunk_id="chunk-000002",
        lecture_id="lec_1",
        chapter="chapter-a",
        start_ts="00:00:10.000",
        end_ts="00:00:20.000",
        text="React component rendering",
        segment_ids=["seg-2"],
    )
    return replace(
        lecture_record(
            [
                segment("seg-1", "00:00:00.000", "00:00:10.000", first.text),
                segment("seg-2", "00:00:10.000", "00:00:20.000", second.text),
            ]
        ),
        status="chunks_ready",
        stage="chunking",
        chunks=[first, second],
    )

if __name__ == "__main__":
    unittest.main()
