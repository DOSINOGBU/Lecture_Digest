import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from lecturedigest.cli import main


class NoteCliTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.store = self.root / "lectures.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_generate_notes_outputs_empty_state(self):
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            exit_code = main(
                [
                    "--store",
                    str(self.store),
                    "generate-notes",
                    "--lecture-id",
                    "lec_missing",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertIn("No lectures registered yet", stdout.getvalue())

    def test_generate_approve_and_reject_outputs_states(self):
        lecture_id = _register_lecture(self.store, self.root)
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            generate_exit = main(
                [
                    "--store",
                    str(self.store),
                    "generate-notes",
                    "--lecture-id",
                    lecture_id,
                ]
            )
        candidate_ids = _candidate_ids(self.store)
        with contextlib.redirect_stdout(stdout):
            reject_exit = main(
                [
                    "--store",
                    str(self.store),
                    "reject-note",
                    "--lecture-id",
                    lecture_id,
                    "--candidate-id",
                    candidate_ids[0],
                    "--reason",
                    "too broad",
                ]
            )
            approve_exit = main(
                [
                    "--store",
                    str(self.store),
                    "approve-note",
                    "--lecture-id",
                    lecture_id,
                    "--candidate-id",
                    candidate_ids[1],
                ]
            )

        output = stdout.getvalue()
        self.assertEqual(generate_exit, 0)
        self.assertEqual(reject_exit, 0)
        self.assertEqual(approve_exit, 0)
        self.assertIn("generate-notes start", output)
        self.assertIn("generate-notes success", output)
        self.assertIn("candidates=3", output)
        self.assertIn("reject-note success", output)
        self.assertIn("approve-note success", output)
        payload = json.loads(self.store.read_text(encoding="utf-8"))
        self.assertEqual(payload[0]["status"], "note_approved")
        self.assertEqual(len(payload[0]["note_sections"]), 4)

    def test_approve_note_outputs_error_for_missing_candidate(self):
        lecture_id = _register_lecture(self.store, self.root)
        stdout = io.StringIO()
        stderr = io.StringIO()

        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = main(
                [
                    "--store",
                    str(self.store),
                    "approve-note",
                    "--lecture-id",
                    lecture_id,
                    "--candidate-id",
                    "missing",
                ]
            )

        self.assertEqual(exit_code, 1)
        self.assertIn("command failed", stderr.getvalue())
        self.assertIn("note_candidates_required", stderr.getvalue())


def _register_lecture(store: Path, root: Path) -> str:
    video = root / "lecture.mp4"
    subtitle = root / "lecture.srt"
    video.write_bytes(b"fake video")
    subtitle.write_text(
        "1\n00:00:00,000 --> 00:00:10,000\nReact renders components.\n\n"
        "2\n00:00:10,000 --> 00:00:20,000\nReact DOM updates the screen.\n",
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


def _candidate_ids(store: Path) -> list[str]:
    payload = json.loads(store.read_text(encoding="utf-8"))
    return [str(candidate["candidate_id"]) for candidate in payload[0]["note_candidates"]]


if __name__ == "__main__":
    unittest.main()
