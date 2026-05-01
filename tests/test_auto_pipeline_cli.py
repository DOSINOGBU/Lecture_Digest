import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from lecturedigest.cli import main


class AutoPipelineCliTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.store = self.root / "lectures.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_process_lecture_dry_run_outputs_plan_without_api_call(self):
        lecture_id = self._register_subtitled_video("HTML and CSS")

        exit_code, output, _ = self._run_output(
            [
                "process-lecture",
                "--lecture-id",
                lecture_id,
                "--openai",
                "--dry-run",
                "--include-ocr",
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("process-lecture dry_run", output)
        self.assertIn("- ocr status=planned", output)
        self.assertIn("- generate_quizzes status=planned", output)
        self.assertEqual(self._lecture_payload().get("pipeline_metadata"), {})

    def test_process_lecture_requires_openai_flag(self):
        lecture_id = self._register_subtitled_video("HTML")

        exit_code, _, stderr = self._run_output(
            [
                "process-lecture",
                "--lecture-id",
                lecture_id,
                "--dry-run",
            ]
        )

        self.assertEqual(exit_code, 1)
        self.assertIn("openai_required_for_auto_pipeline", stderr)

    def _register_subtitled_video(self, text: str) -> str:
        video = self.root / "lecture.mp4"
        subtitle = self.root / "lecture.srt"
        video.write_bytes(b"fake video")
        subtitle.write_text(
            f"1\n00:00:00,000 --> 00:00:05,000\n{text}\n",
            encoding="utf-8",
        )
        exit_code, _, stderr = self._run_output(
            [
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
        if exit_code != 0:
            raise AssertionError(stderr)
        return str(self._lecture_payload()["lecture_id"])

    def _lecture_payload(self) -> dict[str, object]:
        return json.loads(self.store.read_text(encoding="utf-8"))[0]

    def _run_output(self, args: list[str]):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = main(["--store", str(self.store), *args])
        return exit_code, stdout.getvalue(), stderr.getvalue()


if __name__ == "__main__":
    unittest.main()
