import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from lecturedigest.cli import main


class AnkiCliTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.store = self.root / "lectures.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_generate_cards_outputs_empty_state(self):
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            exit_code = main(
                [
                    "--store",
                    str(self.store),
                    "generate-cards",
                    "--lecture-id",
                    "lec_missing",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertIn("No lectures registered yet", stdout.getvalue())

    def test_generate_cards_and_export_outputs_success_states(self):
        lecture_id = _prepare_approved_note(self.store, self.root)
        output_file = self.root / "anki.tsv"
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            generate_exit = main(
                [
                    "--store",
                    str(self.store),
                    "generate-cards",
                    "--lecture-id",
                    lecture_id,
                    "--card-types",
                    "qa,cloze",
                ]
            )
            export_exit = main(
                [
                    "--store",
                    str(self.store),
                    "export-anki",
                    "--lecture-id",
                    lecture_id,
                    "--output",
                    str(output_file),
                ]
            )

        output = stdout.getvalue()
        self.assertEqual(generate_exit, 0)
        self.assertEqual(export_exit, 0)
        self.assertIn("generate-cards start", output)
        self.assertIn("cardTypes=qa,cloze", output)
        self.assertIn("generate-cards success", output)
        self.assertIn("export-anki success", output)
        self.assertTrue(output_file.exists())
        payload = json.loads(self.store.read_text(encoding="utf-8"))
        self.assertEqual(payload[0]["status"], "anki_exported")
        self.assertTrue(payload[0]["flashcards"])
        self.assertEqual(len(payload[0]["anki_exports"]), 1)

    def test_generate_cards_outputs_error_without_approved_note(self):
        lecture_id = _register_lecture(self.store, self.root)
        stdout = io.StringIO()
        stderr = io.StringIO()

        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = main(
                [
                    "--store",
                    str(self.store),
                    "generate-cards",
                    "--lecture-id",
                    lecture_id,
                ]
            )

        self.assertEqual(exit_code, 1)
        self.assertIn("command failed", stderr.getvalue())
        self.assertIn("approved_note_required", stderr.getvalue())

    def test_openai_generate_cards_dry_run_does_not_save_cards(self):
        lecture_id = _prepare_approved_note(self.store, self.root)
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            exit_code = main(
                [
                    "--store",
                    str(self.store),
                    "generate-cards",
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
        self.assertEqual(payload[0]["flashcards"], [])


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
