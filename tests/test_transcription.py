import tempfile
import unittest
import json
from pathlib import Path

from lecturedigest.errors import TranscriptionError, ValidationError
from lecturedigest.ingestion import register_lecture
from lecturedigest.transcription import apply_stt_result


class TranscriptionTest(unittest.TestCase):
    def test_applies_stt_result_to_pending_lecture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "lecture.mp4"
            stt_result = root / "stt.srt"
            video.write_bytes(b"fake video")
            stt_result.write_text(
                "1\n00:00:01,000 --> 00:00:02,500\nhello\n",
                encoding="utf-8",
            )
            record = register_lecture(
                video_path=video,
                title="Intro",
                instructor="Teacher",
                category="Coding",
            )

            updated = apply_stt_result(record, stt_result_path=stt_result)

            self.assertEqual(updated.status, "transcript_ready")
            self.assertEqual(updated.stage, "transcription")
            self.assertEqual(updated.transcript_source, "stt")
            self.assertEqual(updated.issues, [])
            self.assertEqual(len(updated.segments), 1)
            self.assertEqual(updated.segments[0].start_ts, "00:00:01.000")
            self.assertEqual(updated.segments[0].end_ts, "00:00:02.500")

    def test_rejects_empty_stt_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "lecture.mp4"
            stt_result = root / "stt.srt"
            video.write_bytes(b"fake video")
            stt_result.write_text("", encoding="utf-8")
            record = register_lecture(
                video_path=video,
                title="Intro",
                instructor="Teacher",
                category="Coding",
            )

            with self.assertRaises(TranscriptionError) as context:
                apply_stt_result(record, stt_result_path=stt_result)

            self.assertEqual(context.exception.detail.code, "stt_result_empty")

    def test_applies_diarized_json_stt_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "lecture.mp4"
            stt_result = root / "stt.json"
            video.write_bytes(b"fake video")
            stt_result.write_text(
                json.dumps(
                    {
                        "provider_metadata": {
                            "provider": "openai_transcriptions",
                            "model": "gpt-4o-transcribe-diarize",
                            "response_format": "diarized_json",
                            "duration_ms": 1200,
                        },
                        "segments": [
                            {
                                "start": 1.25,
                                "end": 2.5,
                                "text": "hello",
                                "speaker": "speaker_1",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            record = register_lecture(
                video_path=video,
                title="Intro",
                instructor="Teacher",
                category="Coding",
            )

            updated = apply_stt_result(record, stt_result_path=stt_result)

            self.assertEqual(updated.status, "transcript_ready")
            self.assertEqual(updated.segments[0].start_ts, "00:00:01.250")
            self.assertEqual(updated.segments[0].end_ts, "00:00:02.500")
            self.assertEqual(updated.segments[0].speaker, "speaker_1")
            self.assertEqual(
                updated.transcript_metadata["response_format"],
                "diarized_json",
            )

    def test_rejects_invalid_stt_timestamp_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "lecture.mp4"
            stt_result = root / "stt.srt"
            video.write_bytes(b"fake video")
            stt_result.write_text(
                "1\n00:00:03,000 --> 00:00:02,000\nbad\n",
                encoding="utf-8",
            )
            record = register_lecture(
                video_path=video,
                title="Intro",
                instructor="Teacher",
                category="Coding",
            )

            with self.assertRaises(TranscriptionError) as context:
                apply_stt_result(record, stt_result_path=stt_result)

            self.assertEqual(
                context.exception.detail.code,
                "stt_result_invalid_range",
            )

    def test_rejects_overwriting_existing_segments(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "lecture.mp4"
            subtitle = root / "lecture.srt"
            stt_result = root / "stt.srt"
            video.write_bytes(b"fake video")
            subtitle.write_text(
                "1\n00:00:01,000 --> 00:00:02,000\nsubtitle\n",
                encoding="utf-8",
            )
            stt_result.write_text(
                "1\n00:00:01,000 --> 00:00:02,000\nstt\n",
                encoding="utf-8",
            )
            record = register_lecture(
                video_path=video,
                subtitle_path=subtitle,
                title="Intro",
                instructor="Teacher",
                category="Coding",
            )

            with self.assertRaises(ValidationError) as context:
                apply_stt_result(record, stt_result_path=stt_result)

            self.assertEqual(
                context.exception.detail.code,
                "transcript_already_exists",
            )


if __name__ == "__main__":
    unittest.main()
