import tempfile
import unittest
from pathlib import Path

from lecturedigest.errors import OpenAIClientError, TranscriptionError, ValidationError
from lecturedigest.ingestion import register_lecture
from lecturedigest.openai_client import OpenAIClient
from lecturedigest.openai_transcription import (
    MAX_TRANSCRIPTION_UPLOAD_BYTES,
    build_transcription_request,
    transcribe_lecture_with_openai,
    validate_transcription_preflight,
)
from lecturedigest.openai_types import OpenAITransportResponse
from support import FakeTransport, json_response, openai_env, stt_success_response


class OpenAITranscriptionTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_dry_run_builds_request_without_api_key_or_transport_call(self):
        video = _video(self.root)
        record = _record(video)
        transport = FakeTransport(stt_success_response())
        client = OpenAIClient(transport=transport, env={})

        result = transcribe_lecture_with_openai(
            record,
            client=client,
            dry_run=True,
        )

        self.assertEqual(result.record, record)
        self.assertEqual(result.client_result.metadata.status, "dry_run")
        self.assertEqual(result.preflight.file_size_bytes, video.stat().st_size)
        self.assertEqual(transport.calls, [])

    def test_fake_diarized_response_stores_transcript_segments(self):
        record = _record(_video(self.root))
        client = OpenAIClient(
            transport=FakeTransport(stt_success_response()),
            env=openai_env(),
        )

        result = transcribe_lecture_with_openai(record, client=client)

        self.assertTrue(result.client_result.succeeded)
        self.assertEqual(result.record.status, "transcript_ready")
        self.assertEqual(result.record.transcript_source, "stt")
        self.assertEqual(len(result.record.segments), 1)
        segment = result.record.segments[0]
        self.assertEqual(segment.segment_id, "seg-000001")
        self.assertEqual(segment.start_ts, "00:00:01.000")
        self.assertEqual(segment.end_ts, "00:00:02.500")
        self.assertEqual(segment.speaker, "speaker_1")
        self.assertEqual(segment.text, "hello")
        self.assertEqual(
            result.record.transcript_metadata["response_format"],
            "diarized_json",
        )
        self.assertIn("last_openai_call", result.record.transcript_metadata)

    def test_speaker_id_is_normalized_to_speaker(self):
        record = _record(_video(self.root))
        client = OpenAIClient(
            transport=FakeTransport(
                json_response(
                    {
                        "segments": [
                            {
                                "start": 1,
                                "end": 2,
                                "text": "hello",
                                "speaker_id": "speaker_a",
                            }
                        ]
                    }
                )
            ),
            env=openai_env(),
        )

        result = transcribe_lecture_with_openai(record, client=client)

        self.assertEqual(result.record.segments[0].speaker, "speaker_a")

    def test_api_failure_is_saved_as_retryable_issue(self):
        record = _record(_video(self.root))
        client = OpenAIClient(
            transport=FakeTransport(
                OpenAITransportResponse(
                    status_code=429,
                    body=b'{"error": "rate limited"}',
                )
            ),
            env=openai_env(),
        )

        result = transcribe_lecture_with_openai(record, client=client)

        self.assertEqual(result.record.status, "stt_failed")
        self.assertEqual(result.record.stage, "transcription")
        self.assertEqual(result.record.issues[-1].code, "openai_rate_limited")
        self.assertTrue(result.record.issues[-1].retryable)

    def test_rejects_missing_api_key_before_upload(self):
        record = _record(_video(self.root))
        client = OpenAIClient(
            transport=FakeTransport(stt_success_response()),
            env={},
        )

        with self.assertRaises(OpenAIClientError) as context:
            transcribe_lecture_with_openai(record, client=client)

        self.assertEqual(context.exception.detail.code, "openai_api_key_missing")

    def test_rejects_unsupported_extension(self):
        source = self.root / "lecture.txt"
        source.write_text("not media", encoding="utf-8")
        record = _record_with_source(source)

        with self.assertRaises(ValidationError) as context:
            validate_transcription_preflight(record)

        self.assertEqual(
            context.exception.detail.code,
            "stt_file_unsupported_extension",
        )

    def test_rejects_file_over_direct_upload_limit(self):
        video = self.root / "large.mp4"
        with video.open("wb") as handle:
            handle.truncate(MAX_TRANSCRIPTION_UPLOAD_BYTES + 1)
        record = _record(video)

        with self.assertRaises(ValidationError) as context:
            validate_transcription_preflight(record)

        self.assertEqual(context.exception.detail.code, "stt_file_too_large")

    def test_rejects_existing_transcript_segments(self):
        video = _video(self.root)
        subtitle = self.root / "lecture.srt"
        subtitle.write_text(
            "1\n00:00:00,000 --> 00:00:01,000\nsubtitle\n",
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
            validate_transcription_preflight(record)

        self.assertEqual(
            context.exception.detail.code,
            "transcript_already_exists",
        )

    def test_rejects_non_stt_pending_record(self):
        video = _video(self.root)
        record = _record_with_source(video, transcript_source="subtitle_unmatched")

        with self.assertRaises(ValidationError) as context:
            validate_transcription_preflight(record)

        self.assertEqual(context.exception.detail.code, "stt_not_expected")

    def test_rejects_missing_speaker_in_diarized_response(self):
        record = _record(_video(self.root))
        client = OpenAIClient(
            transport=FakeTransport(
                json_response(
                    {"segments": [{"start": 1, "end": 2, "text": "hello"}]}
                )
            ),
            env=openai_env(),
        )

        with self.assertRaises(TranscriptionError) as context:
            transcribe_lecture_with_openai(record, client=client)

        self.assertEqual(context.exception.detail.code, "stt_speaker_missing")

    def test_rejects_malformed_success_response(self):
        record = _record(_video(self.root))
        client = OpenAIClient(
            transport=FakeTransport(
                OpenAITransportResponse(status_code=200, body=b"not-json")
            ),
            env=openai_env(),
        )

        with self.assertRaises(TranscriptionError) as context:
            transcribe_lecture_with_openai(record, client=client)

        self.assertEqual(context.exception.detail.code, "stt_result_invalid_json")

    def test_multipart_request_contains_required_fields(self):
        record = _record(_video(self.root))
        preflight = validate_transcription_preflight(record)

        request = build_transcription_request(preflight)

        self.assertEqual(request.endpoint, "/v1/audio/transcriptions")
        self.assertIn(b'name="model"', request.body)
        self.assertIn(b"gpt-4o-transcribe-diarize", request.body)
        self.assertIn(b'name="response_format"', request.body)
        self.assertIn(b"diarized_json", request.body)
        self.assertIn(b'name="chunking_strategy"', request.body)
        self.assertIn(b"auto", request.body)


def _record(video: Path):
    return register_lecture(
        video_path=video,
        title="Intro",
        instructor="Teacher",
        category="Coding",
    )


def _record_with_source(
    source: Path,
    *,
    transcript_source: str = "stt_pending",
):
    record = _record(_video(source.parent, "placeholder.mp4"))
    return record.__class__(
        **{
            **record.to_dict(),
            "source_path": str(source),
            "transcript_source": transcript_source,
        }
    )


def _video(root: Path, name: str = "lecture.mp4") -> Path:
    video = root / name
    video.write_bytes(b"fake video")
    return video


if __name__ == "__main__":
    unittest.main()
