import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from lecturedigest.cli import main


class CorrectionCliTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.store = self.root / "lectures.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_finalize_transcript_outputs_empty_state(self):
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            exit_code = main(
                [
                    "--store",
                    str(self.store),
                    "finalize-transcript",
                    "--lecture-id",
                    "lec_missing",
                    "--correction-result",
                    str(self.root / "corrections.json"),
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertIn("No lectures registered yet", stdout.getvalue())

    def test_finalize_transcript_outputs_loading_and_success_state(self):
        video = self.root / "lecture.mp4"
        subtitle = self.root / "lecture.srt"
        corrections = self.root / "corrections.json"
        video.write_bytes(b"fake video")
        subtitle.write_text(
            "1\n00:00:00,000 --> 00:00:03,000\nhelo\n",
            encoding="utf-8",
        )
        _write_corrections(corrections)
        with contextlib.redirect_stdout(io.StringIO()):
            main(
                [
                    "--store",
                    str(self.store),
                    "register",
                    "--video",
                    str(video),
                    "--subtitle",
                    str(subtitle),
                    "--title",
                    "Intro",
                    "--instructor",
                    "Teacher",
                    "--category",
                    "Coding",
                ]
            )
        lecture_id = _read_lecture_id(self.store)
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            exit_code = main(
                [
                    "--store",
                    str(self.store),
                    "finalize-transcript",
                    "--lecture-id",
                    lecture_id,
                    "--correction-result",
                    str(corrections),
                ]
            )

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("finalize-transcript start", output)
        self.assertIn("finalize-transcript success", output)
        self.assertIn("status=transcript_finalized", output)
        self.assertIn("applied=1", output)

    def test_openai_dry_run_outputs_preview_without_updating_store(self):
        video = self.root / "lecture.mp4"
        subtitle = self.root / "lecture.srt"
        video.write_bytes(b"fake video")
        subtitle.write_text(
            "1\n00:00:00,000 --> 00:00:03,000\nhelo\n",
            encoding="utf-8",
        )
        with contextlib.redirect_stdout(io.StringIO()):
            main(
                [
                    "--store",
                    str(self.store),
                    "register",
                    "--video",
                    str(video),
                    "--subtitle",
                    str(subtitle),
                    "--title",
                    "Intro",
                    "--instructor",
                    "Teacher",
                    "--category",
                    "Coding",
                ]
            )
        lecture_id = _read_lecture_id(self.store)
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            exit_code = main(
                [
                    "--store",
                    str(self.store),
                    "finalize-transcript",
                    "--lecture-id",
                    lecture_id,
                    "--openai",
                    "--dry-run",
                ]
            )

        payload = json.loads(self.store.read_text(encoding="utf-8"))[0]
        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("finalize-transcript start", output)
        self.assertIn("openai dry-run", output)
        self.assertIn("willUpload=false", output)
        self.assertIn("willSave=false", output)
        self.assertEqual(payload["segments"][0]["text"], "helo")
        self.assertEqual(payload["correction_log"], [])

    def test_finalize_transcript_requires_result_without_openai(self):
        video = self.root / "lecture.mp4"
        subtitle = self.root / "lecture.srt"
        video.write_bytes(b"fake video")
        subtitle.write_text(
            "1\n00:00:00,000 --> 00:00:03,000\nhelo\n",
            encoding="utf-8",
        )
        with contextlib.redirect_stdout(io.StringIO()):
            main(
                [
                    "--store",
                    str(self.store),
                    "register",
                    "--video",
                    str(video),
                    "--subtitle",
                    str(subtitle),
                    "--title",
                    "Intro",
                    "--instructor",
                    "Teacher",
                    "--category",
                    "Coding",
                ]
            )
        lecture_id = _read_lecture_id(self.store)
        stderr = io.StringIO()

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(stderr):
            exit_code = main(
                [
                    "--store",
                    str(self.store),
                    "finalize-transcript",
                    "--lecture-id",
                    lecture_id,
                ]
            )

        self.assertEqual(exit_code, 1)
        self.assertIn("correction_result_required", stderr.getvalue())

    def test_finalize_transcript_outputs_error_state(self):
        video = self.root / "lecture.mp4"
        subtitle = self.root / "lecture.srt"
        video.write_bytes(b"fake video")
        subtitle.write_text(
            "1\n00:00:00,000 --> 00:00:03,000\nhelo\n",
            encoding="utf-8",
        )
        with contextlib.redirect_stdout(io.StringIO()):
            main(
                [
                    "--store",
                    str(self.store),
                    "register",
                    "--video",
                    str(video),
                    "--subtitle",
                    str(subtitle),
                    "--title",
                    "Intro",
                    "--instructor",
                    "Teacher",
                    "--category",
                    "Coding",
                ]
            )
        lecture_id = _read_lecture_id(self.store)
        stdout = io.StringIO()
        stderr = io.StringIO()

        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = main(
                [
                    "--store",
                    str(self.store),
                    "finalize-transcript",
                    "--lecture-id",
                    lecture_id,
                    "--correction-result",
                    str(self.root / "missing.json"),
                ]
            )

        self.assertEqual(exit_code, 1)
        self.assertIn("command failed", stderr.getvalue())
        self.assertIn("correction_result_not_found", stderr.getvalue())


def _read_lecture_id(store: Path) -> str:
    payload = json.loads(store.read_text(encoding="utf-8"))
    return str(payload[0]["lecture_id"])


def _write_corrections(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "provider_metadata": {
                    "provider": "openai_responses",
                    "model": "gpt-4o",
                    "prompt_version": "transcript-correction-v1",
                },
                "corrections": [
                    {
                        "segment_id": "seg-000001",
                        "corrected_text": "hello",
                        "confidence": 0.97,
                        "reason": "typo",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
