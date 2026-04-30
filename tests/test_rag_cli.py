import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from lecturedigest.cli import main


class RagCliTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.store = self.root / "lectures.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_index_outputs_empty_state(self):
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            exit_code = main(
                [
                    "--store",
                    str(self.store),
                    "index",
                    "--lecture-id",
                    "lec_missing",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertIn("No lectures registered yet", stdout.getvalue())

    def test_index_summarize_and_ask_output_success_states(self):
        lecture_id = _register_and_chunk(self.store, self.root)
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            index_exit = main(
                [
                    "--store",
                    str(self.store),
                    "index",
                    "--lecture-id",
                    lecture_id,
                ]
            )
            summarize_exit = main(
                [
                    "--store",
                    str(self.store),
                    "summarize",
                    "--lecture-id",
                    lecture_id,
                ]
            )
            ask_exit = main(
                [
                    "--store",
                    str(self.store),
                    "ask",
                    "--lecture-id",
                    lecture_id,
                    "--question",
                    "React DOM",
                ]
            )

        output = stdout.getvalue()
        self.assertEqual(index_exit, 0)
        self.assertEqual(summarize_exit, 0)
        self.assertEqual(ask_exit, 0)
        self.assertIn("index start", output)
        self.assertIn("index success", output)
        self.assertIn("summarize success", output)
        self.assertIn("ask answered", output)
        self.assertIn("lecturedigest://lecture/", output)

    def test_ask_outputs_insufficient_evidence_state(self):
        lecture_id = _register_and_chunk(self.store, self.root)
        with contextlib.redirect_stdout(io.StringIO()):
            main(["--store", str(self.store), "index", "--lecture-id", lecture_id])
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            exit_code = main(
                [
                    "--store",
                    str(self.store),
                    "ask",
                    "--lecture-id",
                    lecture_id,
                    "--question",
                    "database transaction",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertIn("ask insufficient_evidence", stdout.getvalue())

    def test_ask_outputs_error_before_indexing(self):
        lecture_id = _register_and_chunk(self.store, self.root)
        stdout = io.StringIO()
        stderr = io.StringIO()

        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = main(
                [
                    "--store",
                    str(self.store),
                    "ask",
                    "--lecture-id",
                    lecture_id,
                    "--question",
                    "React",
                ]
            )

        self.assertEqual(exit_code, 1)
        self.assertIn("search_index_required", stderr.getvalue())


def _register_and_chunk(store: Path, root: Path) -> str:
    video = root / "lecture.mp4"
    subtitle = root / "lecture.srt"
    video.write_bytes(b"fake video")
    subtitle.write_text(
        "1\n00:00:00,000 --> 00:00:10,000\nReact renders components\n\n"
        "2\n00:00:10,000 --> 00:00:20,000\nReact DOM updates the screen\n",
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
    lecture_id = _read_lecture_id(store)
    with contextlib.redirect_stdout(io.StringIO()):
        main(
            [
                "--store",
                str(store),
                "chunk",
                "--lecture-id",
                lecture_id,
                "--chapter",
                "chapter-a",
            ]
        )
    return lecture_id


def _read_lecture_id(store: Path) -> str:
    payload = json.loads(store.read_text(encoding="utf-8"))
    return str(payload[0]["lecture_id"])


if __name__ == "__main__":
    unittest.main()
