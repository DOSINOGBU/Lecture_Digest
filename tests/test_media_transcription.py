import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lecturedigest.ingestion import register_lecture
from lecturedigest.media_preflight import MediaToolPaths
from lecturedigest.media_transcription import (
    format_large_transcription_dry_run,
    transcribe_large_lecture_with_openai,
)
from lecturedigest.openai_client import OpenAIClient
from lecturedigest.openai_transcription import MAX_TRANSCRIPTION_UPLOAD_BYTES
from lecturedigest.openai_types import OpenAITransportResponse
from support import FakeTransport, openai_env, stt_success_response


class MediaTranscriptionTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_dry_run_returns_preflight_and_split_plan_without_api_call(self):
        record = _record(_large_video(self.root))
        transport = FakeTransport(stt_success_response())
        client = OpenAIClient(transport=transport, env=openai_env())
        runner = FakeMediaRunner()

        result = transcribe_large_lecture_with_openai(
            record,
            client=client,
            dry_run=True,
            tools=_tools(),
            runner=runner,
        )

        output = format_large_transcription_dry_run(result)
        self.assertTrue(result.dry_run)
        self.assertEqual(len(result.chunk_plan), 2)
        self.assertEqual(transport.calls, [])
        self.assertEqual(len(runner.ffmpeg_commands), 0)
        self.assertIn("preflight success", output)
        self.assertIn("requiresSplit=True", output)
        self.assertIn("willUpload=false", output)

    def test_split_transcription_merges_segments_on_original_timeline(self):
        record = _record(_large_video(self.root))
        transport = FakeTransport(stt_success_response())
        client = OpenAIClient(transport=transport, env=openai_env())
        runner = FakeMediaRunner()

        result = transcribe_large_lecture_with_openai(
            record,
            client=client,
            tools=_tools(),
            runner=runner,
            temp_root=self.root,
        )

        self.assertEqual(result.record.status, "transcript_ready")
        self.assertEqual(result.record.transcript_source, "stt")
        self.assertEqual(len(result.record.segments), 2)
        self.assertEqual(result.record.segments[0].start_ts, "00:00:01.000")
        self.assertEqual(result.record.segments[1].start_ts, "00:10:01.000")
        self.assertEqual(len(transport.calls), 2)
        self.assertEqual(len(runner.ffmpeg_commands), 2)

    def test_temp_paths_are_not_persisted_in_transcript_metadata(self):
        record = _record(_large_video(self.root))
        client = OpenAIClient(
            transport=FakeTransport(stt_success_response()),
            env=openai_env(),
        )

        result = transcribe_large_lecture_with_openai(
            record,
            client=client,
            tools=_tools(),
            runner=FakeMediaRunner(),
            temp_root=self.root,
        )

        metadata_text = json.dumps(result.record.transcript_metadata)
        self.assertNotIn("lecturedigest-stt-", metadata_text)
        self.assertIn("chunk-000001.m4a", metadata_text)
        self.assertIn("media_preflight", result.record.transcript_metadata)

    def test_api_failure_is_recorded_with_chunk_context(self):
        record = _record(_large_video(self.root))
        client = OpenAIClient(
            transport=FakeTransport(
                response=OpenAITransportResponse(
                    status_code=429,
                    body=b'{"error": "rate limited"}',
                )
            ),
            env=openai_env(),
        )

        result = transcribe_large_lecture_with_openai(
            record,
            client=client,
            tools=_tools(),
            runner=FakeMediaRunner(),
            temp_root=self.root,
        )

        self.assertEqual(result.record.status, "stt_failed")
        self.assertEqual(result.record.issues[-1].code, "openai_rate_limited")
        self.assertIn("chunk-000001", result.record.issues[-1].message)

    def test_temp_cleanup_failure_is_recorded_as_warning_issue(self):
        record = _record(_large_video(self.root))
        client = OpenAIClient(
            transport=FakeTransport(stt_success_response()),
            env=openai_env(),
        )

        with mock.patch(
            "lecturedigest.media_transcription.shutil.rmtree",
            side_effect=OSError("locked"),
        ):
            result = transcribe_large_lecture_with_openai(
                record,
                client=client,
                tools=_tools(),
                runner=FakeMediaRunner(),
                temp_root=self.root,
            )

        self.assertEqual(result.record.status, "transcript_ready")
        self.assertEqual(result.record.issues[-1].code, "temp_cleanup_failed")
        self.assertTrue(result.record.issues[-1].retryable)


class FakeMediaRunner:
    def __init__(self):
        self.ffmpeg_commands = []

    def __call__(self, command, *, capture_output, text, check):
        if command[0] == "ffprobe":
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(_ffprobe_payload()),
                stderr="",
            )
        self.ffmpeg_commands.append(command)
        output_path = Path(command[-1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake audio")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")


def _record(video: Path):
    return register_lecture(
        video_path=video,
        title="Intro",
        instructor="Teacher",
        category="Coding",
    )


def _large_video(root: Path) -> Path:
    video = root / "lecture.mp4"
    with video.open("wb") as handle:
        handle.truncate(MAX_TRANSCRIPTION_UPLOAD_BYTES + 1)
    return video


def _tools() -> MediaToolPaths:
    return MediaToolPaths(ffmpeg_path="ffmpeg", ffprobe_path="ffprobe")


def _ffprobe_payload() -> dict[str, object]:
    return {
        "format": {"duration": "650.0"},
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,
            },
            {"codec_type": "audio", "codec_name": "aac"},
        ],
    }


if __name__ == "__main__":
    unittest.main()
