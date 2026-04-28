import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from lecturedigest.cli import main


class CliTest(unittest.TestCase):
    def test_list_outputs_empty_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                exit_code = main(["--store", str(Path(tmp) / "lectures.json"), "list"])

            self.assertEqual(exit_code, 0)
            self.assertIn("No lectures registered yet", stdout.getvalue())

    def test_register_outputs_loading_and_success_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "lecture.mp4"
            video.write_bytes(b"fake video")
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "--store",
                        str(root / "lectures.json"),
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

            output = stdout.getvalue()
            self.assertEqual(exit_code, 0)
            self.assertIn("register start", output)
            self.assertIn("status=stt_required", output)

    def test_register_outputs_error_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            stdout = io.StringIO()
            stderr = io.StringIO()

            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exit_code = main(
                    [
                        "--store",
                        str(Path(tmp) / "lectures.json"),
                        "register",
                        "--video",
                        str(Path(tmp) / "missing.mp4"),
                        "--title",
                        "Intro",
                        "--instructor",
                        "Teacher",
                        "--category",
                        "Coding",
                    ]
                )

            output = stderr.getvalue()
            self.assertEqual(exit_code, 1)
            self.assertIn("register failed", output)
            self.assertIn("video_not_found", output)


if __name__ == "__main__":
    unittest.main()
