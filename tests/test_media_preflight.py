import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from lecturedigest.errors import ValidationError
from lecturedigest.media_preflight import (
    MediaToolPaths,
    build_audio_chunk_plan,
    extract_audio_chunks,
    locate_media_tools,
    offset_transcript_segments,
    parse_ffprobe_json,
    run_media_preflight,
)
from lecturedigest.models import TranscriptSegment


class MediaPreflightTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_parses_ffprobe_json_with_duration_resolution_and_audio(self):
        media = _media(self.root)

        result = parse_ffprobe_json(
            _ffprobe_payload(),
            source_path=media,
            file_size_bytes=1234,
        )

        self.assertEqual(result.duration_seconds, 650.0)
        self.assertTrue(result.has_audio)
        self.assertTrue(result.has_video)
        self.assertEqual(result.width, 1920)
        self.assertEqual(result.height, 1080)
        self.assertEqual(result.audio_codec, "aac")
        self.assertEqual(result.warnings, [])
        self.assertTrue(result.direct_upload_allowed)
        self.assertFalse(result.requires_split)

    def test_preflight_flags_inputs_above_direct_upload_limit(self):
        result = parse_ffprobe_json(
            _ffprobe_payload(),
            source_path=_media(self.root),
            file_size_bytes=30_000_000,
        )

        self.assertFalse(result.direct_upload_allowed)
        self.assertTrue(result.requires_split)

    def test_marks_video_below_1080p_as_warning(self):
        payload = _ffprobe_payload(width=1280, height=720)

        result = parse_ffprobe_json(
            payload,
            source_path=_media(self.root),
            file_size_bytes=1234,
        )

        self.assertIn("video_below_1080p", result.warnings)

    def test_rejects_missing_audio_track(self):
        payload = _ffprobe_payload(audio=False)

        with self.assertRaises(ValidationError) as context:
            parse_ffprobe_json(
                payload,
                source_path=_media(self.root),
                file_size_bytes=1234,
            )

        self.assertEqual(context.exception.detail.code, "media_audio_track_missing")

    def test_rejects_missing_duration(self):
        payload = _ffprobe_payload(duration=None)

        with self.assertRaises(ValidationError) as context:
            parse_ffprobe_json(
                payload,
                source_path=_media(self.root),
                file_size_bytes=1234,
            )

        self.assertEqual(context.exception.detail.code, "media_duration_missing")

    def test_rejects_missing_video_resolution(self):
        payload = _ffprobe_payload(width=None, height=None)

        with self.assertRaises(ValidationError) as context:
            parse_ffprobe_json(
                payload,
                source_path=_media(self.root),
                file_size_bytes=1234,
            )

        self.assertEqual(context.exception.detail.code, "media_resolution_missing")

    def test_locate_media_tools_reports_missing_ffmpeg(self):
        with self.assertRaises(ValidationError) as context:
            locate_media_tools(search_path="")

        self.assertEqual(context.exception.detail.code, "ffmpeg_not_found")

    def test_locate_media_tools_reports_missing_ffprobe(self):
        with self.assertRaises(ValidationError) as context:
            locate_media_tools(ffmpeg_path="ffmpeg", search_path="")

        self.assertEqual(context.exception.detail.code, "ffprobe_not_found")

    def test_run_media_preflight_uses_ffprobe_json(self):
        media = _media(self.root)
        runner = FakeRunner()

        result = run_media_preflight(
            media,
            tools=_tools(),
            runner=runner,
        )

        self.assertEqual(result.duration_seconds, 650.0)
        self.assertEqual(runner.commands[0][0], "ffprobe")

    def test_run_media_preflight_reads_ffprobe_as_utf8(self):
        media = _media(self.root)
        runner = EncodingAwareRunner()

        result = run_media_preflight(
            media,
            tools=_tools(),
            runner=runner,
        )

        self.assertEqual(result.duration_seconds, 650.0)
        self.assertEqual(runner.encoding, "utf-8")
        self.assertEqual(runner.errors, "replace")

    def test_builds_audio_chunk_plan_with_offsets(self):
        preflight = parse_ffprobe_json(
            _ffprobe_payload(duration=650),
            source_path=_media(self.root),
            file_size_bytes=30_000_000,
        )

        chunks = build_audio_chunk_plan(preflight)

        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0].offset_seconds, 0.0)
        self.assertEqual(chunks[0].duration_seconds, 600.0)
        self.assertEqual(chunks[1].offset_seconds, 600.0)
        self.assertEqual(chunks[1].duration_seconds, 50.0)

    def test_extract_audio_chunks_writes_temp_artifacts(self):
        preflight = parse_ffprobe_json(
            _ffprobe_payload(duration=650),
            source_path=_media(self.root),
            file_size_bytes=30_000_000,
        )
        output_dir = self.root / "chunks"
        runner = FakeRunner()

        artifacts = extract_audio_chunks(
            preflight,
            output_dir=output_dir,
            tools=_tools(),
            runner=runner,
        )

        self.assertEqual(len(artifacts), 2)
        self.assertTrue(artifacts[0].path.exists())
        self.assertEqual(artifacts[0].plan.offset_seconds, 0.0)
        self.assertEqual(artifacts[1].plan.offset_seconds, 600.0)

    def test_offsets_segments_to_original_timeline(self):
        segments = [
            TranscriptSegment(
                segment_id="seg-000001",
                start_ts="00:00:01.000",
                end_ts="00:00:02.500",
                text="hello",
                speaker="speaker_1",
            )
        ]

        offset = offset_transcript_segments(
            segments,
            offset_seconds=600,
            start_index=3,
        )

        self.assertEqual(offset[0].segment_id, "seg-000003")
        self.assertEqual(offset[0].start_ts, "00:10:01.000")
        self.assertEqual(offset[0].end_ts, "00:10:02.500")


class FakeRunner:
    def __init__(self):
        self.commands = []

    def __call__(self, command, *, capture_output, text, check):
        self.commands.append(command)
        if command[0] == "ffprobe":
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(_ffprobe_payload()),
                stderr="",
            )
        output_path = Path(command[-1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake audio")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")


class EncodingAwareRunner:
    def __init__(self):
        self.encoding = None
        self.errors = None

    def __call__(self, command, *, capture_output, text, check, encoding, errors):
        self.encoding = encoding
        self.errors = errors
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(_ffprobe_payload(), ensure_ascii=False),
            stderr="경고 없음",
        )


def _media(root: Path) -> Path:
    media = root / "lecture.mp4"
    media.write_bytes(b"fake media")
    return media


def _tools() -> MediaToolPaths:
    return MediaToolPaths(ffmpeg_path="ffmpeg", ffprobe_path="ffprobe")


def _ffprobe_payload(
    *,
    duration: float | None = 650.0,
    width: int | None = 1920,
    height: int | None = 1080,
    audio: bool = True,
    video: bool = True,
) -> dict[str, object]:
    streams = []
    if video:
        streams.append(
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": width,
                "height": height,
            }
        )
    if audio:
        streams.append({"codec_type": "audio", "codec_name": "aac"})
    return {
        "format": {"duration": str(duration) if duration is not None else None},
        "streams": streams,
    }


if __name__ == "__main__":
    unittest.main()
