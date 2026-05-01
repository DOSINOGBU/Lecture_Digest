import unittest

from lecturedigest.note_difficulty import detect_difficult_concepts
from lecturedigest.note_markdown import NoteSourceUnit
from lecturedigest.note_prd import markdown_from_sections, validate_prd_candidate
from lecturedigest.note_profile import build_content_profile


class NoteDifficultyTest(unittest.TestCase):
    def test_detects_difficult_concepts_from_acronyms_and_jargon(self):
        concepts = detect_difficult_concepts(_source_units(), limit=5)
        terms = {str(item["term"]) for item in concepts}

        self.assertIn("DOM", terms)
        self.assertIn("JavaScript", terms)
        dom = next(item for item in concepts if item["term"] == "DOM")
        self.assertEqual(dom["expanded_form"], "Document Object Model")
        self.assertEqual(dom["expansion_known"], True)
        self.assertTrue(any("렌더링" in term for term in terms))

    def test_requires_easy_explanations_for_standard_notes(self):
        units = _source_units()
        profile = build_content_profile(units)
        sections = _sections()
        markdown = _browser_markdown(sections)

        validation = validate_prd_candidate(
            markdown=markdown,
            sections=sections,
            source_units=units,
            content_profile=profile,
            generator_notes={},
        )

        self.assertEqual(profile.strategy, "standard")
        self.assertIn(
            "difficult_concept_explanation_missing",
            validation["failed_rules"],
        )

    def test_accepts_beginner_explanations_in_metadata_and_markdown(self):
        units = _source_units()
        profile = build_content_profile(units)
        sections = _sections(include_easy_explanations=True)
        markdown = _browser_markdown(sections)

        validation = validate_prd_candidate(
            markdown=markdown,
            sections=sections,
            source_units=units,
            content_profile=profile,
            generator_notes=_generator_notes(),
        )

        self.assertEqual(validation["status"], "review_required")
        self.assertNotIn(
            "difficult_concept_explanation_missing",
            validation["failed_rules"],
        )
        self.assertEqual(
            validation["difficulty_explanations"]["metrics"]["explanation_count"],
            3,
        )
        self.assertNotIn("acronym_explanation_missing", validation["failed_rules"])

    def test_rejects_known_acronym_without_expansion_metadata(self):
        units = _source_units()
        profile = build_content_profile(units)
        sections = _sections(include_easy_explanations=True)
        markdown = _browser_markdown(sections)
        notes = _generator_notes()
        notes["difficulty_explanations"][0].pop("expanded_form")
        notes["difficulty_explanations"][0].pop("expansion_known")

        validation = validate_prd_candidate(
            markdown=markdown,
            sections=sections,
            source_units=units,
            content_profile=profile,
            generator_notes=notes,
        )

        self.assertIn("acronym_explanation_missing", validation["failed_rules"])

    def test_rejects_unknown_acronym_expansion(self):
        units = _source_units()
        profile = build_content_profile(units)
        sections = _sections(include_easy_explanations=True)
        markdown = _browser_markdown(sections)
        notes = _generator_notes()
        notes["difficulty_explanations"].append(
            {
                "term": "XYZ",
                "reason": "english_acronym",
                "difficulty": "high",
                "expanded_form": "Xylophone Yield Zone",
                "expansion_known": True,
                "plain_explanation": "?쎄쾶 留먰븯硫? XYZ???낅Ц?먭? 吏꾩엯?????덇쾶 ?ㅻ챸?쒕떎.",
                "source_segment_ids": ["seg-1"],
                "analogy_used": False,
            }
        )

        validation = validate_prd_candidate(
            markdown=markdown,
            sections=sections,
            source_units=units,
            content_profile=profile,
            generator_notes=notes,
        )

        self.assertIn("unsupported_acronym_expansion", validation["failed_rules"])

    def test_rejects_jargony_easy_explanation(self):
        units = _source_units()
        profile = build_content_profile(units)
        sections = _sections(include_easy_explanations=True)
        markdown = _browser_markdown(sections)
        notes = _generator_notes(
            explanation="DOM CSS API JS DOM CSS API JS DOM CSS API JS"
        )

        validation = validate_prd_candidate(
            markdown=markdown,
            sections=sections,
            source_units=units,
            content_profile=profile,
            generator_notes=notes,
        )

        self.assertIn("easy_explanation_too_jargony", validation["failed_rules"])

    def test_tiny_simple_lecture_does_not_force_easy_explanation(self):
        units = [
            NoteSourceUnit(
                segment_id="seg-1",
                start_ts="00:00:00.000",
                end_ts="00:00:10.000",
                text="오늘은 계약 전에 확인할 일을 짧게 정리합니다.",
            )
        ]
        profile = build_content_profile(units)
        sections = [
            _section("one_line_summary", "계약 전 확인 사항을 짧게 정리한다."),
            _section("learning_goals", "- 확인할 일을 말할 수 있다."),
            _section("topic_1", "계약 전에는 주요 조건을 다시 확인해야 한다."),
            _section("practical_takeaways", "- 체크리스트를 보고 확인한다."),
            _section("key_terms", "| 용어 | 의미 |\n| --- | --- |\n| 계약 | 약속한 조건 |"),
            _section("review_questions", "1. 계약 전 무엇을 확인해야 하는가?"),
            _section("final_summary", "짧은 강의는 짧고 명확하게 정리한다."),
        ]
        markdown = markdown_from_sections(title="Tiny", sections=sections)

        validation = validate_prd_candidate(
            markdown=markdown,
            sections=sections,
            source_units=units,
            content_profile=profile,
            generator_notes={},
        )

        self.assertEqual(profile.strategy, "tiny")
        self.assertEqual(validation["status"], "review_required")
        self.assertEqual(
            validation["difficulty_explanations"]["metrics"]["expected_count"],
            0,
        )

    def test_rejects_overused_easy_explanation_marker(self):
        units = _source_units()
        profile = build_content_profile(units)
        repeated = "\n".join(
            f"쉽게 말하면, DOM 설명 {index}입니다."
            for index in range(1, 8)
        )
        sections = _sections(include_easy_explanations=True, extra_text=repeated)
        markdown = _browser_markdown(sections)

        validation = validate_prd_candidate(
            markdown=markdown,
            sections=sections,
            source_units=units,
            content_profile=profile,
            generator_notes=_generator_notes(),
        )

        self.assertIn("easy_explanation_overused", validation["failed_rules"])


def _source_units() -> list[NoteSourceUnit]:
    return [
        NoteSourceUnit(
            segment_id=f"seg-{index}",
            start_ts=f"00:00:{index - 1:02d}.000",
            end_ts=f"00:00:{index:02d}.000",
            text=(
                "DOM JavaScript CSS 렌더링 엔진 파싱 브라우저 구조 "
                "호환성 최적화 개념 설명 흐름 "
            ),
        )
        for index in range(1, 141)
    ]


def _browser_markdown(sections: list[dict[str, object]]) -> str:
    return markdown_from_sections(title="Browser", sections=sections)


def _sections(
    *,
    include_easy_explanations: bool = False,
    extra_text: str = "",
) -> list[dict[str, object]]:
    easy = (
        "\n\n쉽게 말하면, DOM은 브라우저가 HTML을 다룰 수 있게 정리한 목록입니다. "
        "처음 보는 사람은 화면 뒤쪽에 있는 정리표라고 생각하면 됩니다."
        if include_easy_explanations
        else ""
    )
    sections = [
        _section("one_line_summary", "브라우저 구조를 학습한다."),
        _section(
            "learning_goals",
            "\n".join(f"- 브라우저 목표 {index}를 설명할 수 있다." for index in range(1, 5)),
        ),
    ]
    for index in range(1, 6):
        topic_text = _paragraph(f"브라우저 렌더링 주제 {index}", 16)
        if index == 2:
            topic_text += "\n\n- DOM은 구조를 만든다.\n- CSS는 화면 모양에 영향을 준다."
        if index == 3:
            topic_text += "\n\n| 개념 | 쉬운 의미 |\n| --- | --- |\n| DOM | 정리된 문서 구조 |"
        if index == 4:
            topic_text += "\n\n```text\nHTML -> DOM -> 화면\n```"
        if include_easy_explanations and index <= 2:
            topic_text += easy
        if extra_text:
            topic_text += "\n" + extra_text
        sections.append(
            _section(
                f"topic_{index}",
                topic_text,
            )
        )
    sections.extend(
        [
            _section("practical_takeaways", _paragraph("실무 적용", 10)),
            _section(
                "key_terms",
                "| 용어 | 의미 |\n| --- | --- |\n"
                + "\n".join(f"| DOM {index} | 설명 {index}. |" for index in range(1, 9)),
            ),
            _section(
                "review_questions",
                "\n".join(f"{index}. 왜 중요한가?" for index in range(1, 9)),
            ),
            _section("final_summary", _paragraph("최종 정리", 12)),
        ]
    )
    return sections


def _section(section_key: str, text: str) -> dict[str, object]:
    return {
        "section_key": section_key,
        "title": "## " + section_key,
        "text": text,
        "segment_ids": [f"seg-{index}" for index in range(1, 141)],
    }


def _generator_notes(
    *,
    explanation: str = (
        "쉽게 말하면, DOM은 브라우저가 HTML을 다룰 수 있게 정리한 목록입니다."
    ),
) -> dict[str, object]:
    return {
        "difficulty_explanations": [
            {
                "term": "DOM",
                "reason": "english_acronym",
                "difficulty": "high",
                "expanded_form": "Document Object Model",
                "expansion_known": True,
                "plain_explanation": explanation,
                "source_segment_ids": ["seg-1", "seg-2"],
                "analogy_used": True,
            },
            {
                "term": "CSS",
                "reason": "english_acronym",
                "difficulty": "high",
                "expanded_form": "Cascading Style Sheets",
                "expansion_known": True,
                "plain_explanation": (
                    "CSS controls the visual style of a web page, such as color, size, spacing, and layout."
                ),
                "source_segment_ids": ["seg-1", "seg-2"],
                "analogy_used": False,
            },
            {
                "term": "JavaScript",
                "reason": "technical_tool_or_keyword",
                "difficulty": "medium",
                "plain_explanation": (
                    "쉽게 말하면, JavaScript는 화면이 사용자의 행동에 반응하도록 "
                    "움직임을 정하는 언어입니다."
                ),
                "source_segment_ids": ["seg-1", "seg-2"],
                "analogy_used": True,
            },
        ]
    }


def _paragraph(prefix: str, count: int) -> str:
    return " ".join(
        f"{prefix} 문장 {index}은 입문자가 이해할 수 있게 근거를 풀어 설명한다."
        for index in range(1, count + 1)
    )


if __name__ == "__main__":
    unittest.main()
