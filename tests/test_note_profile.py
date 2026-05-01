import unittest

from lecturedigest.note_markdown import NoteSourceUnit
from lecturedigest.note_profile import build_content_profile


class NoteProfileTest(unittest.TestCase):
    def test_selects_tiny_for_very_short_sources(self):
        profile = build_content_profile(
            [
                NoteSourceUnit(
                    segment_id="seg-1",
                    start_ts="00:00:00.000",
                    end_ts="00:00:10.000",
                    text="React renders UI.",
                )
            ]
        )

        self.assertEqual(profile.strategy, "tiny")
        self.assertTrue(profile.source_insufficient_for_full_note)
        self.assertLess(profile.estimated_tokens, 300)

    def test_selects_compact_for_short_sources(self):
        text = " ".join(f"개념{i} 설명 흐름" for i in range(120))

        profile = build_content_profile(
            [
                NoteSourceUnit(
                    segment_id="seg-1",
                    start_ts="00:00:00.000",
                    end_ts="00:03:00.000",
                    text=text,
                )
            ]
        )

        self.assertEqual(profile.strategy, "compact")
        self.assertTrue(profile.source_insufficient_for_full_note)

    def test_selects_standard_for_normal_text_amount(self):
        text = " ".join(f"개념{i} 설명 흐름" for i in range(700))

        profile = build_content_profile(
            [
                NoteSourceUnit(
                    segment_id="seg-1",
                    start_ts="00:00:00.000",
                    end_ts="00:10:00.000",
                    text=text,
                )
            ]
        )

        self.assertEqual(profile.strategy, "standard")
        self.assertFalse(profile.source_insufficient_for_full_note)

    def test_selects_chaptered_for_very_long_text_amount(self):
        text = " ".join(f"긴강의{i} 단계 비교" for i in range(4200))

        profile = build_content_profile(
            [
                NoteSourceUnit(
                    segment_id="seg-1",
                    start_ts="00:00:00.000",
                    end_ts="02:30:00.000",
                    text=text,
                )
            ]
        )

        self.assertEqual(profile.strategy, "chaptered")
        self.assertTrue(profile.has_process_flow)
        self.assertTrue(profile.has_comparison)


if __name__ == "__main__":
    unittest.main()
