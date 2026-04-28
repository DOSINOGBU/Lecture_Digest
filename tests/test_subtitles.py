import unittest

from lecturedigest.errors import SubtitleParseError
from lecturedigest.subtitles import parse_subtitle_text


class SubtitleParsingTest(unittest.TestCase):
    def test_parses_srt_segments(self):
        content = """1
00:00:01,000 --> 00:00:02,500
첫 번째 문장입니다.

2
00:00:03,000 --> 00:00:04,000
두 번째
문장입니다.
"""

        segments = parse_subtitle_text(content)

        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0].segment_id, "seg-000001")
        self.assertEqual(segments[0].start_ts, "00:00:01.000")
        self.assertEqual(segments[0].end_ts, "00:00:02.500")
        self.assertEqual(segments[1].text, "두 번째 문장입니다.")

    def test_parses_vtt_with_cue_identifier(self):
        content = """WEBVTT

intro
00:00:05.000 --> 00:00:07.000 align:start
Hello world
"""

        segments = parse_subtitle_text(content)

        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].start_ts, "00:00:05.000")
        self.assertEqual(segments[0].text, "Hello world")

    def test_rejects_invalid_range(self):
        content = """00:00:02.000 --> 00:00:01.000
bad range
"""

        with self.assertRaises(SubtitleParseError) as context:
            parse_subtitle_text(content)

        self.assertEqual(context.exception.detail.code, "subtitle_invalid_range")


if __name__ == "__main__":
    unittest.main()
