import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lecturedigest.cli import main
from lecturedigest.frame_extraction import FrameCandidate, FrameExtractionResult
from lecturedigest.media_preflight import MediaPreflightResult


class OcrCliTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.store = self.root / "lectures.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_ocr_outputs_empty_state(self):
        exit_code, output = self._run_stdout(["ocr", "--lecture-id", "missing"])

        self.assertEqual(exit_code, 0)
        self.assertIn("No lectures registered yet", output)

    def test_ocr_dry_run_outputs_preflight_without_updating_store(self):
        video = self.root / "lecture.mp4"
        subtitle = self.root / "lecture.srt"
        video.write_bytes(b"fake video")
        subtitle.write_text(
            "1\n00:00:00,000 --> 00:00:03,000\none\n",
            encoding="utf-8",
        )
        lecture_id = self._register_video(video, subtitle)

        with mock.patch(
            "lecturedigest.ocr_cli.plan_frame_candidates_for_dry_run",
            return_value=_dry_run_extraction(video),
        ):
            exit_code, output = self._run_stdout(
                ["ocr", "--lecture-id", lecture_id, "--dry-run"]
            )

        payload = _read_lecture_payload(self.store)
        self.assertEqual(exit_code, 0)
        self.assertIn("ocr start", output)
        self.assertIn("ocr dry-run", output)
        self.assertIn("willUpload=false", output)
        self.assertIn("willSave=false", output)
        self.assertEqual(payload["slides"], [])
        self.assertEqual(payload["segments"][0]["ocr_text"], None)

    def test_ocr_outputs_error_without_transcript_segments(self):
        video = self.root / "lecture.mp4"
        video.write_bytes(b"fake video")
        lecture_id = self._register_video(video)

        exit_code, stdout, stderr = self._run_output(
            ["ocr", "--lecture-id", lecture_id, "--dry-run"]
        )

        self.assertEqual(exit_code, 1)
        self.assertIn("ocr start", stdout)
        self.assertIn("command failed", stderr)
        self.assertIn("segments_required", stderr)

    def _run_stdout(self, args: list[str]) -> tuple[int, str]:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = main(["--store", str(self.store), *args])
        return exit_code, stdout.getvalue()

    def _run_output(self, args: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = main(["--store", str(self.store), *args])
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def _register_video(self, video: Path, subtitle: Path | None = None) -> str:
        args = [
            "register",
            "--video",
            str(video),
            "--title",
            "Intro",
            "--instructor",
            "Teacher",
            "--category",
            "Coding",
        ]
        if subtitle is not None:
            args[3:3] = ["--subtitle", str(subtitle)]
        self._run_stdout(args)
        return _read_lecture_id(self.store)


def _dry_run_extraction(video: Path) -> FrameExtractionResult:
    media = MediaPreflightResult(
        source_path=video,
        file_size_bytes=1234,
        duration_seconds=65.0,
        has_audio=True,
        has_video=True,
        width=1920,
        height=1080,
        video_codec="h264",
        audio_codec="aac",
        warnings=[],
    )
    return FrameExtractionResult(
        media_preflight=media,
        frames=[
            FrameCandidate(
                frame_id="frame-000001",
                source_frame_ts="00:00:00.000",
                frame_path=None,
                frame_width=1920,
                frame_height=1080,
                change_score=1.0,
                extraction_method="scene_dry_run_estimate",
            ),
            FrameCandidate(
                frame_id="frame-000002",
                source_frame_ts="00:00:30.000",
                frame_path=None,
                frame_width=1920,
                frame_height=1080,
                change_score=1.0,
                extraction_method="scene_dry_run_estimate",
            ),
        ],
        method="scene",
        fallback_used=False,
        duplicate_frames_removed=0,
        sample_interval_seconds=30,
        scene_threshold=0.35,
    )


def _read_lecture_id(store: Path) -> str:
    import json

    payload = json.loads(store.read_text(encoding="utf-8"))
    return str(payload[0]["lecture_id"])


def _read_lecture_payload(store: Path) -> dict[str, object]:
    import json

    payload = json.loads(store.read_text(encoding="utf-8"))
    return payload[0]


if __name__ == "__main__":
    unittest.main()
