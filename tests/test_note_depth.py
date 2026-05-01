import unittest

from lecturedigest.note_depth import body_depth_policy
from lecturedigest.note_difficulty import beginner_explanation_for
from lecturedigest.note_markdown import NoteSourceUnit
from lecturedigest.note_prd import markdown_from_sections, validate_prd_candidate
from lecturedigest.note_profile import build_content_profile


class NoteDepthTest(unittest.TestCase):
    def test_flags_shallow_standard_note_body(self):
        units = _source_units()
        profile = build_content_profile(units)
        sections = _sections(topic_text="One sentence only.")
        markdown = markdown_from_sections(title="Browser", sections=sections)

        validation = validate_prd_candidate(
            markdown=markdown,
            sections=sections,
            source_units=units,
            content_profile=profile,
            generator_notes={
                "difficulty_explanations": [
                    {
                        "term": "JavaScript",
                        "reason": "mixed_or_camel_case_term",
                        "difficulty": "medium",
                        "plain_explanation": beginner_explanation_for("JavaScript"),
                        "source_segment_ids": ["seg-000001"],
                        "analogy_used": True,
                    }
                ]
            },
        )

        self.assertEqual(profile.strategy, "standard")
        self.assertEqual(validation["status"], "flagged")
        self.assertIn("body_too_short", validation["failed_rules"])
        self.assertIn("topic_body_too_shallow", validation["failed_rules"])

    def test_rejects_visible_source_artifacts(self):
        units = _source_units()
        profile = build_content_profile(units)
        sections = _sections(
            topic_text=(
                "A visible source marker should not be rendered. "
                "(source: seg-000001..seg-000070 @ 00:00:00.000-00:01:10.000)"
            )
        )
        markdown = markdown_from_sections(title="Browser", sections=sections)

        validation = validate_prd_candidate(
            markdown=markdown,
            sections=sections,
            source_units=units,
            content_profile=profile,
            generator_notes={
                "difficulty_explanations": [
                    {
                        "term": "JavaScript",
                        "reason": "mixed_or_camel_case_term",
                        "difficulty": "medium",
                        "plain_explanation": beginner_explanation_for("JavaScript"),
                        "source_segment_ids": ["seg-000001"],
                        "analogy_used": True,
                    }
                ]
            },
        )

        self.assertIn("visible_source_artifacts", validation["failed_rules"])
        self.assertTrue(validation["visible_source_artifacts"])

    def test_accepts_varied_textbook_style_standard_note_body(self):
        units = _source_units()
        profile = build_content_profile(units)
        sections = _sections()
        markdown = markdown_from_sections(title="Browser", sections=sections)
        generator_notes = {
            "difficulty_explanations": [
                {
                    "term": "JavaScript",
                    "reason": "mixed_or_camel_case_term",
                    "difficulty": "medium",
                    "plain_explanation": beginner_explanation_for("JavaScript"),
                    "source_segment_ids": ["seg-000001"],
                    "analogy_used": True,
                }
            ]
        }

        validation = validate_prd_candidate(
            markdown=markdown,
            sections=sections,
            source_units=units,
            content_profile=profile,
            generator_notes=generator_notes,
        )

        self.assertEqual(validation["status"], "review_required")
        self.assertNotIn("body_too_short", validation["failed_rules"])
        self.assertNotIn("topic_body_too_shallow", validation["failed_rules"])
        self.assertNotIn("visible_source_artifacts", validation["failed_rules"])
        self.assertGreaterEqual(
            validation["body_depth"]["metrics"]["style_kind_count"],
            3,
        )

    def test_tiny_profile_does_not_force_six_thousand_chars(self):
        units = [
            NoteSourceUnit(
                segment_id="seg-000001",
                start_ts="00:00:00.000",
                end_ts="00:00:20.000",
                text="Short lecture about browser basics.",
            )
        ]
        profile = build_content_profile(units)
        sections = _tiny_sections()
        markdown = markdown_from_sections(title="Tiny", sections=sections)

        validation = validate_prd_candidate(
            markdown=markdown,
            sections=sections,
            source_units=units,
            content_profile=profile,
        )

        self.assertEqual(profile.strategy, "tiny")
        self.assertLess(len(markdown), 6000)
        self.assertEqual(validation["status"], "review_required")
        self.assertNotIn("body_too_short", validation["failed_rules"])

    def test_chaptered_policy_allows_longer_than_ten_thousand_chars(self):
        units = [
            NoteSourceUnit(
                segment_id=f"seg-{index:06d}",
                start_ts=f"00:{index // 60:02d}:{index % 60:02d}.000",
                end_ts=f"00:{index // 60:02d}:{(index + 1) % 60:02d}.000",
                text=("topic shift browser rendering architecture " * 30),
            )
            for index in range(1, 501)
        ]
        profile = build_content_profile(units)
        policy = body_depth_policy(profile)

        self.assertEqual(profile.strategy, "chaptered")
        self.assertTrue(policy["chaptered_required"])
        self.assertIsNone(policy["max_single_note_chars"])

    def test_rejects_repetitive_generic_topic_template(self):
        units = _source_units()
        profile = build_content_profile(units)
        sections = _sections(topic_text=_generic_template_topic_text())
        markdown = markdown_from_sections(title="Browser", sections=sections)

        validation = validate_prd_candidate(
            markdown=markdown,
            sections=sections,
            source_units=units,
            content_profile=profile,
        )

        self.assertIn("generic_subheading_present", validation["failed_rules"])
        self.assertIn("repetitive_topic_template", validation["failed_rules"])


def _source_units() -> list[NoteSourceUnit]:
    return [
        NoteSourceUnit(
            segment_id=f"seg-{index:06d}",
            start_ts=f"00:00:{index - 1:02d}.000",
            end_ts=f"00:00:{index:02d}.000",
            text=(
                "browser rendering document model layout paint developer "
                "tool architecture engine javascript parser flow source "
            ),
        )
        for index in range(1, 71)
    ]


def _sections(*, topic_text: str | None = None) -> list[dict[str, object]]:
    sections = [
        _section("one_line_summary", "Browser rendering needs careful study."),
        _section(
            "learning_goals",
            "\n".join(f"- Learning goal {index}." for index in range(1, 5)),
        ),
    ]
    for index in range(1, 6):
        sections.append(_section(f"topic_{index}", topic_text or _varied_topic_text(index)))
    sections.extend(
        [
            _section("practical_takeaways", _paragraph("Practical takeaway", 12)),
            _section(
                "key_terms",
                "| Term | Meaning |\n| --- | --- |\n"
                + "\n".join(f"| Term {index} | Meaning {index}. |" for index in range(1, 9)),
            ),
            _section(
                "review_questions",
                "\n".join(
                    f"{index}. Why does browser topic {index} matter?"
                    for index in range(1, 9)
                ),
            ),
            _section("final_summary", _paragraph("Final summary", 12)),
        ]
    )
    return sections


def _tiny_sections() -> list[dict[str, object]]:
    return [
        _section("one_line_summary", "Browser basics are introduced."),
        _section("learning_goals", "- Explain the browser's basic role."),
        _section("topic_1", "The browser is the runtime where web pages become visible."),
        _section("practical_takeaways", "- Revisit the browser role before deeper study."),
        _section("key_terms", "| Term | Meaning |\n| --- | --- |\n| Browser | Web runtime |"),
        _section("review_questions", "1. What does the browser do?"),
        _section("final_summary", "A short source should stay concise."),
    ]


def _section(section_key: str, text: str) -> dict[str, object]:
    return {
        "section_key": section_key,
        "title": "## " + section_key,
        "text": text,
        "segment_ids": [f"seg-{index:06d}" for index in range(1, 71)],
    }


def _varied_topic_text(index: int) -> str:
    if index == 1:
        return "\n\n".join(
            [
                _paragraph("Browser runtime narrative detail", 8),
                (
                    "쉽게 말하면, JavaScript는 화면이 사용자의 행동에 반응하도록 "
                    "움직임을 정하는 언어입니다."
                ),
                "- HTML is parsed into structure.\n- CSS affects visible style.\n- JavaScript changes behavior.",
            ]
        )
    if index == 2:
        return "\n\n".join(
            [
                _paragraph("Rendering engine explanation", 9),
                "| Step | Meaning |\n| --- | --- |\n| Parse | Build structure |\n| Paint | Draw pixels |",
            ]
        )
    if index == 3:
        return "\n\n".join(
            [
                "```text\nHTML/CSS/JS -> DOM and style -> layout -> paint\n```",
                _paragraph("Flow explanation for browser rendering", 9),
            ]
        )
    if index == 4:
        return _paragraph("Compatibility topic contrasts browser behavior", 12)
    return "\n\n".join(
        [
            "### Debugging focus\n\n" + _paragraph("Developer tools expose rendering work", 6),
            _paragraph("This topic connects browser structure to practical debugging", 6),
        ]
    )


def _generic_template_topic_text() -> str:
    return "\n\n".join(
        [
            "### Concept\n\n" + _paragraph("Definition explains the browser concept", 8),
            "### Why It Matters\n\n" + _paragraph("Importance connects the concept to debugging", 8),
            "### Lecture Flow / Example\n\n" + _paragraph("Flow places the concept inside rendering steps", 8),
        ]
    )


def _paragraph(prefix: str, count: int) -> str:
    return " ".join(
        f"{prefix} sentence {index} adds source-backed detail for study."
        for index in range(1, count + 1)
    )


if __name__ == "__main__":
    unittest.main()
