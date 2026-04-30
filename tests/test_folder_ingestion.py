import tempfile
import unittest
from pathlib import Path

from lecturedigest.errors import ValidationError
from lecturedigest.folder_ingestion import register_lecture_folder


class FolderIngestionTest(unittest.TestCase):
    def test_registers_folder_clips_with_stem_matched_subtitles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Course"
            middle = root / "Major" / "Middle"
            subtitles = middle / "subtitles"
            subtitles.mkdir(parents=True)
            video = middle / "clip-one.mp4"
            subtitle = subtitles / "clip-one.srt"
            video.write_bytes(b"fake video")
            subtitle.write_text(
                "1\n00:00:01,000 --> 00:00:02,000\nhello\n",
                encoding="utf-8",
            )

            result = register_lecture_folder(
                folder_path=root,
                instructor="Teacher",
            )

            self.assertEqual(len(result.records), 1)
            record = result.records[0]
            self.assertEqual(record.status, "transcript_ready")
            self.assertEqual(record.transcript_source, "subtitle")
            self.assertEqual(record.input_mode, "folder")
            self.assertEqual(record.lecture_title, "Course")
            self.assertEqual(record.major_category, "Major")
            self.assertEqual(record.middle_category, "Middle")
            self.assertEqual(record.clip_title, "clip-one")
            self.assertEqual(len(record.segments), 1)

    def test_registers_folder_without_subtitles_as_stt_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Course"
            middle = root / "Major" / "Middle"
            middle.mkdir(parents=True)
            (middle / "one.mp4").write_bytes(b"fake video")
            (middle / "two.webm").write_bytes(b"fake video")

            result = register_lecture_folder(
                folder_path=root,
                instructor="Teacher",
            )

            self.assertEqual(len(result.records), 2)
            self.assertTrue(
                all(record.status == "stt_required" for record in result.records)
            )
            self.assertTrue(
                all(
                    record.transcript_source == "stt_pending"
                    for record in result.records
                )
            )

    def test_subtitle_folder_unmatched_clip_does_not_fallback_to_stt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Course"
            middle = root / "Major" / "Middle"
            subtitles = middle / "captions"
            subtitles.mkdir(parents=True)
            (middle / "clip-one.mp4").write_bytes(b"fake video")
            (subtitles / "different.srt").write_text(
                "1\n00:00:01,000 --> 00:00:02,000\nhello\n",
                encoding="utf-8",
            )

            result = register_lecture_folder(
                folder_path=root,
                instructor="Teacher",
            )

            self.assertEqual(len(result.records), 1)
            record = result.records[0]
            self.assertEqual(record.status, "subtitle_unmatched")
            self.assertEqual(record.transcript_source, "subtitle_unmatched")
            self.assertEqual(record.issues[0].code, "subtitle_unmatched")

    def test_matches_subtitles_by_number_prefix_after_stem_miss(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Course"
            middle = root / "Major" / "Middle"
            subtitles = middle / "subtitles"
            subtitles.mkdir(parents=True)
            (middle / "01 intro.mp4").write_bytes(b"fake video")
            subtitle = subtitles / "01 captions.srt"
            subtitle.write_text(
                "1\n00:00:01,000 --> 00:00:02,000\nhello\n",
                encoding="utf-8",
            )

            result = register_lecture_folder(
                folder_path=root,
                instructor="Teacher",
            )

            self.assertEqual(len(result.records), 1)
            self.assertEqual(result.records[0].subtitle_path, str(subtitle.resolve()))

    def test_empty_folder_returns_empty_result_with_issue(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Course"
            root.mkdir()

            result = register_lecture_folder(
                folder_path=root,
                instructor="Teacher",
            )

            self.assertEqual(result.records, [])
            self.assertEqual(result.issues[0].code, "folder_empty")

    def test_missing_folder_fails_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValidationError) as context:
                register_lecture_folder(
                    folder_path=Path(tmp) / "missing",
                    instructor="Teacher",
                )

            self.assertEqual(context.exception.detail.code, "folder_not_found")


if __name__ == "__main__":
    unittest.main()
