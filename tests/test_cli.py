import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lecturedigest.cli import main
from lecturedigest.media_preflight import MediaPreflightResult
from lecturedigest.media_transcription import LargeOpenAITranscriptionResult
from lecturedigest.openai_transcription import MAX_TRANSCRIPTION_UPLOAD_BYTES


class CliTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.store = self.root / "lectures.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_list_outputs_empty_state(self):
        exit_code, output = self._run_stdout(["list"])

        self.assertEqual(exit_code, 0)
        self.assertIn("No lectures registered yet", output)

    def test_register_outputs_loading_and_success_state(self):
        video = self.root / "lecture.mp4"
        video.write_bytes(b"fake video")

        exit_code, output = self._run_stdout(
            [
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
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("register start", output)
        self.assertIn("status=stt_required", output)

    def test_register_outputs_error_state(self):
        exit_code, _, stderr = self._run_output(
            [
                "register",
                "--video",
                str(self.root / "missing.mp4"),
                "--title",
                "Intro",
                "--instructor",
                "Teacher",
                "--category",
                "Coding",
            ]
        )

        self.assertEqual(exit_code, 1)
        self.assertIn("command failed", stderr)
        self.assertIn("video_not_found", stderr)

    def test_register_folder_outputs_loading_and_success_state(self):
        folder = self.root / "Course"
        middle = folder / "Major" / "Middle"
        middle.mkdir(parents=True)
        (middle / "lecture.mp4").write_bytes(b"fake video")

        exit_code, output = self._run_stdout(
            [
                "register-folder",
                "--folder",
                str(folder),
                "--instructor",
                "Teacher",
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("register-folder start", output)
        self.assertIn("register-folder success", output)
        self.assertIn("records=1", output)
        self.assertIn("sttRequired=1", output)

    def test_register_folder_outputs_empty_state(self):
        folder = self.root / "Course"
        folder.mkdir()

        exit_code, output = self._run_stdout(
            [
                "register-folder",
                "--folder",
                str(folder),
                "--instructor",
                "Teacher",
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("register-folder empty", output)
        self.assertIn("records=0", output)

    def test_register_folder_outputs_error_state(self):
        exit_code, _, stderr = self._run_output(
            [
                "register-folder",
                "--folder",
                str(self.root / "missing"),
                "--instructor",
                "Teacher",
            ]
        )

        self.assertEqual(exit_code, 1)
        self.assertIn("command failed", stderr)
        self.assertIn("folder_not_found", stderr)

    def test_chunk_outputs_empty_state(self):
        exit_code, output = self._run_stdout(
            [
                "chunk",
                "--lecture-id",
                "lec_missing",
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("No lectures registered yet", output)

    def test_import_stt_outputs_empty_state(self):
        exit_code, output = self._run_stdout(
            [
                "import-stt",
                "--lecture-id",
                "lec_missing",
                "--stt-result",
                str(self.root / "stt.srt"),
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("No lectures registered yet", output)

    def test_import_stt_outputs_loading_and_success_state(self):
        video = self.root / "lecture.mp4"
        stt_result = self.root / "stt.srt"
        video.write_bytes(b"fake video")
        stt_result.write_text(
            "1\n00:00:00,000 --> 00:00:10,000\none\n",
            encoding="utf-8",
        )
        lecture_id = self._register_video(video)

        exit_code, output = self._run_stdout(
            [
                "import-stt",
                "--lecture-id",
                lecture_id,
                "--stt-result",
                str(stt_result),
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("import-stt start", output)
        self.assertIn("import-stt success", output)
        self.assertIn("transcriptSource=stt", output)
        self.assertIn("segments=1", output)

    def test_import_stt_outputs_error_state(self):
        video = self.root / "lecture.mp4"
        stt_result = self.root / "stt.srt"
        video.write_bytes(b"fake video")
        stt_result.write_text("", encoding="utf-8")
        lecture_id = self._register_video(video)

        exit_code, _, stderr = self._run_output(
            [
                "import-stt",
                "--lecture-id",
                lecture_id,
                "--stt-result",
                str(stt_result),
            ]
        )

        self.assertEqual(exit_code, 1)
        self.assertIn("command failed", stderr)
        self.assertIn("stt_result_empty", stderr)

    def test_transcribe_outputs_empty_state(self):
        exit_code, output = self._run_stdout(
            [
                "transcribe",
                "--lecture-id",
                "lec_missing",
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("No lectures registered yet", output)

    def test_transcribe_dry_run_outputs_loading_without_updating_store(self):
        video = self.root / "lecture.mp4"
        video.write_bytes(b"fake video")
        lecture_id = self._register_video(video)

        exit_code, output = self._run_stdout(
            [
                "transcribe",
                "--lecture-id",
                lecture_id,
                "--dry-run",
            ]
        )

        payload = _read_lecture_payload(self.store)
        self.assertEqual(exit_code, 0)
        self.assertIn("transcribe start", output)
        self.assertIn("transcribe dry-run", output)
        self.assertIn("willUpload=false", output)
        self.assertEqual(payload["status"], "stt_required")
        self.assertEqual(payload["transcript_source"], "stt_pending")
        self.assertEqual(payload["segments"], [])

    def test_transcribe_large_dry_run_outputs_media_preflight(self):
        video = self.root / "lecture.mp4"
        with video.open("wb") as handle:
            handle.truncate(MAX_TRANSCRIPTION_UPLOAD_BYTES + 1)
        large_lecture_id = self._register_video(video)

        with mock.patch(
            "lecturedigest.transcribe_cli.transcribe_large_lecture_with_openai",
            return_value=_large_dry_run_result(video),
        ):
            exit_code, output = self._run_stdout(
                [
                    "transcribe",
                    "--lecture-id",
                    large_lecture_id,
                    "--dry-run",
                ]
            )

        payload = _read_lecture_payload(self.store)
        self.assertEqual(exit_code, 0)
        self.assertIn("transcribe start", output)
        self.assertIn("preflight success", output)
        self.assertIn("requiresSplit=True", output)
        self.assertEqual(payload["segments"], [])

    def test_transcribe_outputs_error_when_api_key_is_missing(self):
        video = self.root / "lecture.mp4"
        video.write_bytes(b"fake video")
        missing_key_lecture_id = self._register_video(video)

        with mock.patch.dict("os.environ", {}, clear=True):
            exit_code, stdout, stderr = self._run_output(
                [
                    "transcribe",
                    "--lecture-id",
                    missing_key_lecture_id,
                ]
            )

        self.assertEqual(exit_code, 1)
        self.assertIn("transcribe start", stdout)
        self.assertIn("command failed", stderr)
        self.assertIn("openai_api_key_missing", stderr)

    def test_import_ocr_outputs_empty_state(self):
        exit_code, output = self._run_stdout(
            [
                "import-ocr",
                "--lecture-id",
                "lec_missing",
                "--ocr-result",
                str(self.root / "ocr.json"),
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("No lectures registered yet", output)

    def test_import_ocr_outputs_loading_and_success_state(self):
        video = self.root / "lecture.mp4"
        subtitle = self.root / "lecture.srt"
        ocr_result = self.root / "ocr.json"
        video.write_bytes(b"fake video")
        subtitle.write_text(
            "1\n00:00:00,000 --> 00:00:03,000\none\n",
            encoding="utf-8",
        )
        _write_ocr_result(ocr_result)
        lecture_id = self._register_video(video, subtitle)

        exit_code, output = self._run_stdout(
            [
                "import-ocr",
                "--lecture-id",
                lecture_id,
                "--ocr-result",
                str(ocr_result),
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("import-ocr start", output)
        self.assertIn("import-ocr success", output)
        self.assertIn("slides=1", output)
        self.assertIn("enrichedSegments=1", output)

    def test_import_ocr_outputs_error_state(self):
        video = self.root / "lecture.mp4"
        subtitle = self.root / "lecture.srt"
        video.write_bytes(b"fake video")
        subtitle.write_text(
            "1\n00:00:00,000 --> 00:00:03,000\none\n",
            encoding="utf-8",
        )
        lecture_id = self._register_video(video, subtitle)

        exit_code, _, stderr = self._run_output(
            [
                "import-ocr",
                "--lecture-id",
                lecture_id,
                "--ocr-result",
                str(self.root / "missing.json"),
            ]
        )

        self.assertEqual(exit_code, 1)
        self.assertIn("command failed", stderr)
        self.assertIn("ocr_result_not_found", stderr)

    def test_chunk_outputs_loading_and_success_state(self):
        video = self.root / "lecture.mp4"
        subtitle = self.root / "lecture.srt"
        video.write_bytes(b"fake video")
        subtitle.write_text(
            "1\n00:00:00,000 --> 00:00:30,000\none\n\n"
            "2\n00:00:30,000 --> 00:01:00,000\ntwo\n",
            encoding="utf-8",
        )
        lecture_id = self._register_video(video, subtitle)

        exit_code, output = self._run_stdout(
            [
                "chunk",
                "--lecture-id",
                lecture_id,
                "--window-seconds",
                "90",
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("chunk start", output)
        self.assertIn("chunk success", output)
        self.assertIn("chunks=1", output)

    def test_chunk_outputs_error_for_missing_segments(self):
        video = self.root / "lecture.mp4"
        video.write_bytes(b"fake video")
        lecture_id = self._register_video(video)

        exit_code, _, stderr = self._run_output(
            [
                "chunk",
                "--lecture-id",
                lecture_id,
            ]
        )

        self.assertEqual(exit_code, 1)
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


def _read_lecture_id(store: Path) -> str:
    import json

    payload = json.loads(store.read_text(encoding="utf-8"))
    return str(payload[0]["lecture_id"])


def _read_lecture_payload(store: Path) -> dict[str, object]:
    import json

    payload = json.loads(store.read_text(encoding="utf-8"))
    return payload[0]


def _large_dry_run_result(video: Path) -> LargeOpenAITranscriptionResult:
    media_preflight = MediaPreflightResult(
        source_path=video,
        file_size_bytes=MAX_TRANSCRIPTION_UPLOAD_BYTES + 1,
        duration_seconds=650.0,
        has_audio=True,
        has_video=True,
        width=1920,
        height=1080,
        video_codec="h264",
        audio_codec="aac",
        warnings=[],
    )
    return LargeOpenAITranscriptionResult(
        record=None,
        media_preflight=media_preflight,
        chunk_plan=[
            {
                "chunk_id": "chunk-000001",
                "offset_seconds": 0.0,
                "duration_seconds": 600.0,
            },
            {
                "chunk_id": "chunk-000002",
                "offset_seconds": 600.0,
                "duration_seconds": 50.0,
            },
        ],
        client_results=[],
        dry_run=True,
    )


def _write_ocr_result(path: Path) -> None:
    import json

    path.write_text(
        json.dumps(
            {
                "provider_metadata": {
                    "provider": "openai_vision",
                    "model": "vision-capable-model",
                    "prompt_version": "ocr-v1",
                    "detail": "original",
                    "status": "succeeded",
                },
                "frames": [
                    {
                        "source_frame_ts": "00:00:00,500",
                        "change_score": 1.0,
                        "raw_ocr_text": "Raw",
                        "refined_ocr_text": "Refined",
                        "confidence": 0.95,
                        "frame_width": 1920,
                        "frame_height": 1080,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
