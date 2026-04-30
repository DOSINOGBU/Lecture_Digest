import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from lecturedigest.cli import main


class QuizCliTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.store = self.root / "lectures.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_generate_quizzes_outputs_empty_state(self):
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            exit_code = main(
                [
                    "--store",
                    str(self.store),
                    "generate-quizzes",
                    "--lecture-id",
                    "lec_missing",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertIn("No lectures registered yet", stdout.getvalue())

    def test_generate_quizzes_outputs_success_state(self):
        lecture_id = _prepare_approved_note(self.store, self.root)
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            exit_code = main(
                [
                    "--store",
                    str(self.store),
                    "generate-quizzes",
                    "--lecture-id",
                    lecture_id,
                    "--quiz-count",
                    "4",
                    "--seed",
                    "3",
                ]
            )

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("generate-quizzes start", output)
        self.assertIn("generate-quizzes success", output)
        self.assertIn("quizzes=4", output)
        payload = json.loads(self.store.read_text(encoding="utf-8"))
        self.assertEqual(payload[0]["status"], "quizzes_ready")
        self.assertEqual(payload[0]["quiz_metadata"]["seed"], 3)
        self.assertTrue(payload[0]["quiz_items"])

    def test_generate_quizzes_outputs_error_without_approved_note(self):
        lecture_id = _register_lecture(self.store, self.root)
        stdout = io.StringIO()
        stderr = io.StringIO()

        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = main(
                [
                    "--store",
                    str(self.store),
                    "generate-quizzes",
                    "--lecture-id",
                    lecture_id,
                ]
            )

        self.assertEqual(exit_code, 1)
        self.assertIn("command failed", stderr.getvalue())
        self.assertIn("approved_note_required", stderr.getvalue())


def _prepare_approved_note(store: Path, root: Path) -> str:
    lecture_id = _register_lecture(store, root)
    with contextlib.redirect_stdout(io.StringIO()):
        main(["--store", str(store), "generate-notes", "--lecture-id", lecture_id])
    candidate_id = _first_candidate_id(store)
    with contextlib.redirect_stdout(io.StringIO()):
        main(
            [
                "--store",
                str(store),
                "approve-note",
                "--lecture-id",
                lecture_id,
                "--candidate-id",
                candidate_id,
            ]
        )
    return lecture_id


def _register_lecture(store: Path, root: Path) -> str:
    video = root / "lecture.mp4"
    subtitle = root / "lecture.srt"
    video.write_bytes(b"fake video")
    subtitle.write_text(
        "1\n00:00:00,000 --> 00:00:10,000\nReact renders components.\n\n"
        "2\n00:00:10,000 --> 00:00:20,000\napp.py shows browser output.\n",
        encoding="utf-8",
    )
    with contextlib.redirect_stdout(io.StringIO()):
        main(
            [
                "--store",
                str(store),
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
    payload = json.loads(store.read_text(encoding="utf-8"))
    return str(payload[0]["lecture_id"])


def _first_candidate_id(store: Path) -> str:
    payload = json.loads(store.read_text(encoding="utf-8"))
    return str(payload[0]["note_candidates"][0]["candidate_id"])


if __name__ == "__main__":
    unittest.main()
