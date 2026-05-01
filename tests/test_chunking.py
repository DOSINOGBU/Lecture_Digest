import unittest

from lecturedigest.chunking import build_chunks, chunk_lecture
from lecturedigest.errors import IndexingError, ValidationError
from lecturedigest.models import LectureRecord, TranscriptSegment


class ChunkingTest(unittest.TestCase):
    def test_builds_overlapping_chunks_with_segment_mapping(self):
        chunks = build_chunks(
            lecture_id="lec_1",
            segments=[
                _segment("seg-1", "00:00:00.000", "00:00:30.000", "one"),
                _segment("seg-2", "00:00:30.000", "00:01:00.000", "two"),
                _segment("seg-3", "00:01:00.000", "00:01:30.000", "three"),
                _segment("seg-4", "00:01:30.000", "00:02:00.000", "four"),
            ],
            window_seconds=90,
            overlap_seconds=15,
            chapter="chapter-a",
        )

        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0].segment_ids, ["seg-1", "seg-2", "seg-3"])
        self.assertEqual(chunks[0].start_ts, "00:00:00.000")
        self.assertEqual(chunks[0].end_ts, "00:01:30.000")
        self.assertEqual(chunks[0].text, "one two three")
        self.assertEqual(chunks[0].chapter, "chapter-a")
        self.assertEqual(chunks[1].segment_ids, ["seg-3", "seg-4"])

    def test_chunk_lecture_updates_status_and_stage(self):
        record = _lecture([_segment("seg-1", "00:00:00.000", "00:00:10.000", "one")])

        updated = chunk_lecture(record, window_seconds=90, overlap_seconds=15)

        self.assertEqual(updated.status, "chunks_ready")
        self.assertEqual(updated.stage, "chunking")
        self.assertEqual(len(updated.chunks), 1)

    def test_empty_segments_fail_with_indexing_error(self):
        record = _lecture([])

        with self.assertRaises(IndexingError) as context:
            chunk_lecture(record)

        self.assertEqual(context.exception.detail.code, "segments_required")

    def test_invalid_overlap_fails_validation(self):
        with self.assertRaises(ValidationError) as context:
            build_chunks(
                lecture_id="lec_1",
                segments=[_segment("seg-1", "00:00:00.000", "00:00:10.000", "one")],
                window_seconds=30,
                overlap_seconds=30,
            )

        self.assertEqual(context.exception.detail.code, "chunk_overlap_too_large")


def _segment(segment_id: str, start_ts: str, end_ts: str, text: str) -> TranscriptSegment:
    return TranscriptSegment(
        segment_id=segment_id,
        start_ts=start_ts,
        end_ts=end_ts,
        text=text,
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


if __name__ == "__main__":
    unittest.main()
