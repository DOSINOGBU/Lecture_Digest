import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lecturedigest.errors import EnrichmentError, ErrorDetail, ValidationError
from lecturedigest.frame_extraction import (
    extract_frame_candidates,
    plan_frame_candidates_for_dry_run,
)
from lecturedigest.media_preflight import MediaToolPaths


class FrameExtractionTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_scene_detection_falls_back_to_interval_sampling(self):
        media = _media(self.root)
        runner = FakeFrameRunner(write_scene_frames=False, write_interval_frames=True)

        result = extract_frame_candidates(
            media,
            output_dir=self.root / "frames",
            tools=_tools(),
            runner=runner,
            sample_interval_seconds=30,
        )

        self.assertTrue(result.fallback_used)
        self.assertEqual(len(result.frames), 3)
        self.assertEqual(result.frames[0].source_frame_ts, "00:00:00.000")
        self.assertEqual(result.frames[1].source_frame_ts, "00:00:30.000")
        self.assertEqual(result.frames[0].frame_width, 1920)
        self.assertEqual(result.frames[0].frame_height, 1080)
        self.assertEqual(result.frames[0].change_score, 1.0)
        self.assertTrue(any("select=gt" in " ".join(cmd) for cmd in runner.commands))

    def test_scene_detection_uses_showinfo_timestamps(self):
        media = _media(self.root)
        runner = FakeFrameRunner(write_scene_frames=True)

        result = extract_frame_candidates(
            media,
            output_dir=self.root / "frames",
            tools=_tools(),
            runner=runner,
            sample_interval_seconds=30,
        )

        self.assertFalse(result.fallback_used)
        self.assertEqual(len(result.frames), 2)
        self.assertEqual(result.frames[0].source_frame_ts, "00:00:02.500")
        self.assertEqual(result.frames[1].source_frame_ts, "00:00:35.000")
        self.assertEqual(result.frames[0].extraction_method, "scene")

    def test_missing_ffmpeg_is_reported(self):
        media = _media(self.root)
        missing = ValidationError(
            ErrorDetail(
                code="ffmpeg_not_found",
                message="ffmpeg missing",
                stage="media_preflight",
                retryable=False,
            )
        )

        with mock.patch(
            "lecturedigest.frame_extraction.locate_media_tools",
            side_effect=missing,
        ):
            with self.assertRaises(ValidationError) as context:
                extract_frame_candidates(media, output_dir=self.root / "frames")

        self.assertEqual(context.exception.detail.code, "ffmpeg_not_found")

    def test_raises_when_no_frames_are_extracted(self):
        media = _media(self.root)
        runner = FakeFrameRunner(write_scene_frames=False, write_interval_frames=False)

        with self.assertRaises(EnrichmentError) as context:
            extract_frame_candidates(
                media,
                output_dir=self.root / "frames",
                tools=_tools(),
                runner=runner,
                sample_interval_seconds=30,
            )

        self.assertEqual(context.exception.detail.code, "frame_extraction_empty")

    def test_dry_run_plans_candidates_without_frame_files(self):
        media = _media(self.root)
        runner = FakeFrameRunner()

        result = plan_frame_candidates_for_dry_run(
            media,
            tools=_tools(),
            runner=runner,
            sample_interval_seconds=30,
        )

        self.assertEqual(len(result.frames), 3)
        self.assertIsNone(result.frames[0].frame_path)
        self.assertEqual(result.frames[-1].source_frame_ts, "00:01:00.000")
        self.assertFalse((self.root / "frames").exists())


class FakeFrameRunner:
    def __init__(
        self,
        *,
        write_scene_frames: bool = False,
        write_interval_frames: bool = True,
    ):
        self.write_scene_frames = write_scene_frames
        self.write_interval_frames = write_interval_frames
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
        if any("select=gt" in item for item in command):
            return self._scene_result(command)
        return self._interval_result(command)

    def _scene_result(self, command):
        if self.write_scene_frames:
            output_pattern = Path(command[-1])
            output_dir = output_pattern.parent
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "frame-000001.jpg").write_bytes(b"frame one")
            (output_dir / "frame-000002.jpg").write_bytes(b"frame two")
            stderr = "showinfo pts_time:2.5\nshowinfo pts_time:35.0"
        else:
            stderr = ""
        return subprocess.CompletedProcess(command, 0, stdout="", stderr=stderr)

    def _interval_result(self, command):
        output_path = Path(command[-1])
        if self.write_interval_frames:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"fake frame")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")


def _media(root: Path) -> Path:
    media = root / "lecture.mp4"
    media.write_bytes(b"fake media")
    return media


def _tools() -> MediaToolPaths:
    return MediaToolPaths(ffmpeg_path="ffmpeg", ffprobe_path="ffprobe")


def _ffprobe_payload() -> dict[str, object]:
    return {
        "format": {"duration": "65.0"},
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
