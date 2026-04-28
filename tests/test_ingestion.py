import tempfile
import unittest
from pathlib import Path

from lecturedigest.errors import SubtitleParseError, ValidationError
from lecturedigest.ingestion import register_lecture
from lecturedigest.storage import JsonLectureRepository


class IngestionTest(unittest.TestCase):
    def test_registers_lecture_with_subtitle_segments(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "lecture.mp4"
            subtitle = root / "lecture.srt"
            video.write_bytes(b"fake video")
            subtitle.write_text(
                "1\n00:00:01,000 --> 00:00:02,000\nhello\n",
                encoding="utf-8",
            )

            record = register_lecture(
                video_path=video,
                subtitle_path=subtitle,
                title="Intro",
                instructor="Teacher",
                category="Coding",
            )

            self.assertEqual(record.status, "transcript_ready")
            self.assertEqual(record.transcript_source, "subtitle")
            self.assertEqual(len(record.segments), 1)
            self.assertEqual(record.issues, [])

    def test_missing_subtitle_marks_stt_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "lecture.mkv"
            video.write_bytes(b"fake video")

            record = register_lecture(
                video_path=video,
                title="Intro",
                instructor="Teacher",
                category="Coding",
            )

            self.assertEqual(record.status, "stt_required")
            self.assertEqual(record.stage, "awaiting_stt")
            self.assertEqual(record.transcript_source, "stt_pending")
            self.assertEqual(len(record.segments), 0)
            self.assertEqual(record.issues[0].code, "subtitle_missing")

    def test_rejects_missing_required_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "lecture.mp4"
            video.write_bytes(b"fake video")

            with self.assertRaises(ValidationError) as context:
                register_lecture(
                    video_path=video,
                    title="",
                    instructor="Teacher",
                    category="Coding",
                )

            self.assertEqual(context.exception.detail.code, "title_required")

    def test_rejects_empty_subtitle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "lecture.mp4"
            subtitle = root / "lecture.srt"
            video.write_bytes(b"fake video")
            subtitle.write_text("", encoding="utf-8")

            with self.assertRaises(SubtitleParseError) as context:
                register_lecture(
                    video_path=video,
                    subtitle_path=subtitle,
                    title="Intro",
                    instructor="Teacher",
                    category="Coding",
                )

            self.assertEqual(context.exception.detail.code, "subtitle_empty")

    def test_repository_empty_and_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = JsonLectureRepository(root / "lectures.json")
            self.assertEqual(store.list_lectures(), [])

            video = root / "lecture.webm"
            video.write_bytes(b"fake video")
            record = register_lecture(
                video_path=video,
                title="Intro",
                instructor="Teacher",
                category="Coding",
            )

            store.save(record)
            lectures = store.list_lectures()

            self.assertEqual(len(lectures), 1)
            self.assertEqual(lectures[0].lecture_id, record.lecture_id)


if __name__ == "__main__":
    unittest.main()
