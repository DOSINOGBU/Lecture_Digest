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

    def test_openai_generate_quizzes_dry_run_does_not_save_quizzes(self):
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
                    "--openai",
                    "--dry-run",
                    "--batch-size-sections",
                    "10",
                ]
            )

        self.assertEqual(exit_code, 0)
        output = stdout.getvalue()
        self.assertIn("openai dry-run", output)
        self.assertIn("willSave=false", output)
        payload = json.loads(self.store.read_text(encoding="utf-8"))
        self.assertEqual(payload[0]["status"], "note_approved")
        self.assertEqual(payload[0]["quiz_items"], [])

    def test_start_quiz_session_and_submit_answer_outputs_success(self):
        lecture_id = _prepare_quizzes(self.store, self.root, ["multiple_choice"])
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            exit_code = main(
                [
                    "--store",
                    str(self.store),
                    "start-quiz-session",
                    "--lecture-id",
                    lecture_id,
                    "--count",
                    "1",
                    "--seed",
                    "5",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertIn("start-quiz-session start", stdout.getvalue())
        payload = json.loads(self.store.read_text(encoding="utf-8"))
        session = payload[0]["quiz_metadata"]["sessions"][0]
        quiz_id = session["quiz_ids"][0]
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            exit_code = main(
                [
                    "--store",
                    str(self.store),
                    "submit-quiz-answer",
                    "--lecture-id",
                    lecture_id,
                    "--session-id",
                    session["session_id"],
                    "--quiz-id",
                    quiz_id,
                    "--answer",
                    "A",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertIn("quiz-session success", stdout.getvalue())
        payload = json.loads(self.store.read_text(encoding="utf-8"))
        self.assertEqual(payload[0]["quiz_metadata"]["sessions"][0]["answers"][0]["quiz_id"], quiz_id)

    def test_grade_quiz_session_requires_openai_flag(self):
        lecture_id = _prepare_quizzes(self.store, self.root, ["written"])
        _start_and_answer_first_quiz(self.store, lecture_id, "written answer")
        payload = json.loads(self.store.read_text(encoding="utf-8"))
        session_id = payload[0]["quiz_metadata"]["sessions"][0]["session_id"]
        stderr = io.StringIO()

        with contextlib.redirect_stderr(stderr):
            exit_code = main(
                [
                    "--store",
                    str(self.store),
                    "grade-quiz-session",
                    "--lecture-id",
                    lecture_id,
                    "--session-id",
                    session_id,
                ]
            )

        self.assertEqual(exit_code, 1)
        self.assertIn("openai_required_for_written_grading", stderr.getvalue())


def _prepare_approved_note(store: Path, root: Path) -> str:
    lecture_id = _register_lecture(store, root)
    _run_silent(["--store", str(store), "generate-notes", "--lecture-id", lecture_id])
    candidate_id = _first_candidate_id(store)
    _run_silent(
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


def _prepare_quizzes(store: Path, root: Path, question_types: list[str]) -> str:
    lecture_id = _prepare_approved_note(store, root)
    args = [
        "--store",
        str(store),
        "generate-quizzes",
        "--lecture-id",
        lecture_id,
        "--quiz-count",
        "2",
        "--seed",
        "7",
    ]
    for question_type in question_types:
        args.extend(["--question-type", question_type])
    _run_silent(args)
    return lecture_id


def _start_and_answer_first_quiz(store: Path, lecture_id: str, answer: str) -> None:
    _run_silent(
        [
            "--store",
            str(store),
            "start-quiz-session",
            "--lecture-id",
            lecture_id,
            "--count",
            "1",
        ]
    )
    payload = json.loads(store.read_text(encoding="utf-8"))
    session = payload[0]["quiz_metadata"]["sessions"][0]
    _run_silent(
        [
            "--store",
            str(store),
            "submit-quiz-answer",
            "--lecture-id",
            lecture_id,
            "--session-id",
            session["session_id"],
            "--quiz-id",
            session["quiz_ids"][0],
            "--answer",
            answer,
        ]
    )


def _register_lecture(store: Path, root: Path) -> str:
    video = root / "lecture.mp4"
    subtitle = root / "lecture.srt"
    video.write_bytes(b"fake video")
    subtitle.write_text(
        "1\n00:00:00,000 --> 00:00:10,000\nReact renders components.\n\n"
        "2\n00:00:10,000 --> 00:00:20,000\napp.py shows browser output.\n",
        encoding="utf-8",
    )
    _run_silent(
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


def _run_silent(args: list[str]) -> int:
    with contextlib.redirect_stdout(io.StringIO()):
        return main(args)


def _first_candidate_id(store: Path) -> str:
    payload = json.loads(store.read_text(encoding="utf-8"))
    return str(payload[0]["note_candidates"][0]["candidate_id"])


if __name__ == "__main__":
    unittest.main()
