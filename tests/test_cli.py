import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from lecturedigest.cli import main


class CliTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.store = self.root / "lectures.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_list_outputs_empty_state(self):
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            exit_code = main(["--store", str(self.store), "list"])

        self.assertEqual(exit_code, 0)
        self.assertIn("No lectures registered yet", stdout.getvalue())

    def test_register_outputs_loading_and_success_state(self):
        video = self.root / "lecture.mp4"
        video.write_bytes(b"fake video")
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            exit_code = main(
                [
                    "--store",
                    str(self.store),
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
        stdout = io.StringIO()
        stderr = io.StringIO()

        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = main(
                [
                    "--store",
                    str(self.store),
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

        output = stderr.getvalue()
        self.assertEqual(exit_code, 1)
        self.assertIn("command failed", output)
        self.assertIn("video_not_found", output)

    def test_chunk_outputs_empty_state(self):
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            exit_code = main(
                [
                    "--store",
                    str(self.store),
                    "chunk",
                    "--lecture-id",
                    "lec_missing",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertIn("No lectures registered yet", stdout.getvalue())

    def test_import_stt_outputs_empty_state(self):
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            exit_code = main(
                [
                    "--store",
                    str(self.store),
                    "import-stt",
                    "--lecture-id",
                    "lec_missing",
                    "--stt-result",
                    str(self.root / "stt.srt"),
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertIn("No lectures registered yet", stdout.getvalue())

    def test_import_stt_outputs_loading_and_success_state(self):
        video = self.root / "lecture.mp4"
        stt_result = self.root / "stt.srt"
        video.write_bytes(b"fake video")
        stt_result.write_text(
            "1\n00:00:00,000 --> 00:00:10,000\none\n",
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
                    "import-stt",
                    "--lecture-id",
                    lecture_id,
                    "--stt-result",
                    str(stt_result),
                ]
            )

        output = stdout.getvalue()
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
        with contextlib.redirect_stdout(io.StringIO()):
            main(
                [
                    "--store",
                    str(self.store),
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
        lecture_id = _read_lecture_id(self.store)
        stdout = io.StringIO()
        stderr = io.StringIO()

        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = main(
                [
                    "--store",
                    str(self.store),
                    "import-stt",
                    "--lecture-id",
                    lecture_id,
                    "--stt-result",
                    str(stt_result),
                ]
            )

        self.assertEqual(exit_code, 1)
        self.assertIn("command failed", stderr.getvalue())
        self.assertIn("stt_result_empty", stderr.getvalue())

    def test_chunk_outputs_loading_and_success_state(self):
        video = self.root / "lecture.mp4"
        subtitle = self.root / "lecture.srt"
        video.write_bytes(b"fake video")
        subtitle.write_text(
            "1\n00:00:00,000 --> 00:00:30,000\none\n\n"
            "2\n00:00:30,000 --> 00:01:00,000\ntwo\n",
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
                    "chunk",
                    "--lecture-id",
                    lecture_id,
                    "--window-seconds",
                    "90",
                ]
            )

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("chunk start", output)
        self.assertIn("chunk success", output)
        self.assertIn("chunks=1", output)

    def test_chunk_outputs_error_for_missing_segments(self):
        video = self.root / "lecture.mp4"
        video.write_bytes(b"fake video")
        with contextlib.redirect_stdout(io.StringIO()):
            main(
                [
                    "--store",
                    str(self.store),
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
        lecture_id = _read_lecture_id(self.store)
        stdout = io.StringIO()
        stderr = io.StringIO()

        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = main(
                [
                    "--store",
                    str(self.store),
                    "chunk",
                    "--lecture-id",
                    lecture_id,
                ]
            )

        self.assertEqual(exit_code, 1)
        self.assertIn("segments_required", stderr.getvalue())


def _read_lecture_id(store: Path) -> str:
    import json

    payload = json.loads(store.read_text(encoding="utf-8"))
    return str(payload[0]["lecture_id"])


if __name__ == "__main__":
    unittest.main()
