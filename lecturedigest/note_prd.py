from __future__ import annotations

import re
from typing import Any

from lecturedigest.note_depth import evaluate_body_depth, visible_source_artifacts
from lecturedigest.note_difficulty import validate_difficulty_explanations
from lecturedigest.note_profile import NoteContentProfile

FIXED_SECTION_TITLES = {
    "one_line_summary": "## 강의 한 줄 요약",
    "learning_goals": "## 학습 목표",
    "practical_takeaways": "## 실무 관점에서 기억할 것",
    "key_terms": "## 핵심 용어 정리",
    "review_questions": "## 복습 질문",
    "final_summary": "## 최종 정리",
}
REQUIRED_FIXED_SECTION_KEYS = tuple(FIXED_SECTION_TITLES)
CORE_TOPIC_PREFIX = "topic_"
LEGACY_SECTION_KEY_MAP = {
    "summary": "one_line_summary",
    "key_concepts": "topic_1",
    "flow": "topic_2",
    "action": "practical_takeaways",
    "core_topics": "topic_1",
}


def normalize_section_key(value: object, *, fallback_topic_index: int | None = None) -> str:
    key = str(value or "").strip().lower().replace("-", "_")
    if key in LEGACY_SECTION_KEY_MAP:
        return LEGACY_SECTION_KEY_MAP[key]
    if key in FIXED_SECTION_TITLES or key.startswith(CORE_TOPIC_PREFIX):
        return key
    if fallback_topic_index is not None:
        return f"{CORE_TOPIC_PREFIX}{fallback_topic_index}"
    return key


def default_section_title(section_key: str) -> str:
    if section_key in FIXED_SECTION_TITLES:
        return FIXED_SECTION_TITLES[section_key]
    if section_key.startswith(CORE_TOPIC_PREFIX):
        number = _topic_number(section_key)
        return f"## {number}. 핵심 주제"
    return f"## {section_key.replace('_', ' ').strip() or '섹션'}"


def section_sort_key(section: dict[str, object]) -> tuple[int, int]:
    key = str(section.get("section_key") or "")
    if key == "one_line_summary":
        return (10, 0)
    if key == "learning_goals":
        return (20, 0)
    if key.startswith(CORE_TOPIC_PREFIX):
        return (30, _topic_number(key))
    if key == "practical_takeaways":
        return (40, 0)
    if key == "key_terms":
        return (50, 0)
    if key == "review_questions":
        return (60, 0)
    if key == "final_summary":
        return (70, 0)
    return (90, int(section.get("order") or 0))


def markdown_from_sections(
    *,
    title: str,
    sections: list[dict[str, object]],
) -> str:
    body = [f"# {title.strip() or '강의 제목'}", ""]
    for section in sorted(sections, key=section_sort_key):
        heading = str(section.get("title") or default_section_title(str(section.get("section_key"))))
        text = str(section.get("text") or "").strip()
        body.extend([heading, ""])
        if text:
            body.extend([text, ""])
    return "\n".join(body).rstrip() + "\n"


def validate_prd_candidate(
    *,
    markdown: str,
    sections: list[dict[str, object]],
    source_units: list[Any],
    content_profile: NoteContentProfile,
    generator_notes: dict[str, object] | None = None,
) -> dict[str, object]:
    source_length = max(1, len(" ".join(str(getattr(unit, "text", "")) for unit in source_units)))
    ratio = round(len(markdown) / source_length, 3)
    failed: list[str] = []
    warnings: list[str] = []
    quality_flags: list[str] = []
    missing_sections = _missing_required_sections(sections)
    unmapped = [
        str(section.get("section_key") or "")
        for section in sections
        if not section.get("segment_ids")
    ]
    empty_sections = [
        str(section.get("section_key") or "")
        for section in sections
        if not str(section.get("text") or "").strip()
    ]

    if not markdown.startswith("# "):
        failed.append("title_must_be_first_line")
    if missing_sections:
        failed.append("required_prd_section_missing")
    if empty_sections:
        failed.append("required_section_empty")
    if unmapped:
        failed.append("source_mapping_missing")
    source_artifacts = visible_source_artifacts(markdown)
    if source_artifacts:
        failed.append("visible_source_artifacts")

    counts = {
        "learning_goals": _bullet_count(_section_text(sections, "learning_goals")),
        "core_topics": _core_topic_count(sections),
        "key_terms": _key_term_count(_section_text(sections, "key_terms")),
        "review_questions": _numbered_count(_section_text(sections, "review_questions")),
    }
    for count_key, flag in (
        ("learning_goals", "insufficient_learning_goals"),
        ("key_terms", "insufficient_key_terms"),
        ("review_questions", "insufficient_review_questions"),
    ):
        minimum = content_profile.target_counts[count_key][0]
        if counts[count_key] < minimum:
            quality_flags.append(flag)
            if not content_profile.source_insufficient_for_full_note:
                failed.append(flag)
            else:
                warnings.append(flag)
    if counts["core_topics"] < content_profile.target_counts["core_topics"][0]:
        quality_flags.append("insufficient_core_topics")
        if not content_profile.source_insufficient_for_full_note:
            failed.append("insufficient_core_topics")
        else:
            warnings.append("insufficient_core_topics")

    missing_expected_structure = _missing_expected_structure(markdown, content_profile)
    if missing_expected_structure:
        quality_flags.append("missing_expected_structure")
        warnings.extend(missing_expected_structure)

    if content_profile.source_insufficient_for_full_note:
        quality_flags.append("source_insufficient_for_full_note")
        warnings.append("source_insufficient_for_full_note")
    if ratio < 0.1:
        warnings.append("note_may_be_too_short_for_golden_review")

    body_depth = evaluate_body_depth(
        markdown=markdown,
        sections=sections,
        source_units=source_units,
        content_profile=content_profile,
    )
    failed.extend(body_depth["failed_rules"])
    warnings.extend(body_depth["warnings"])
    quality_flags.extend(body_depth["quality_flags"])

    difficulty = validate_difficulty_explanations(
        markdown=markdown,
        sections=sections,
        source_units=source_units,
        content_profile=content_profile,
        generator_notes=generator_notes,
    )
    failed.extend(difficulty["failed_rules"])
    warnings.extend(difficulty["warnings"])
    quality_flags.extend(difficulty["quality_flags"])

    return {
        "status": "flagged" if failed else "review_required",
        "length_ratio": ratio,
        "target_length_ratio": "PRD checklist + human review required",
        "failed_rules": _unique(failed),
        "warnings": _unique(warnings),
        "quality_flags": _unique(quality_flags),
        "unmapped_sections": unmapped,
        "missing_sections": missing_sections,
        "empty_sections": empty_sections,
        "visible_source_artifacts": source_artifacts,
        "content_counts": counts,
        "body_depth": body_depth,
        "difficulty_explanations": difficulty,
        "content_profile": content_profile.to_dict(),
        "human_review_required": True,
    }


def _missing_required_sections(sections: list[dict[str, object]]) -> list[str]:
    keys = {str(section.get("section_key") or "") for section in sections}
    missing = [key for key in REQUIRED_FIXED_SECTION_KEYS if key not in keys]
    if not any(key.startswith(CORE_TOPIC_PREFIX) for key in keys):
        missing.append("core_topic")
    return missing


def _missing_expected_structure(
    markdown: str,
    content_profile: NoteContentProfile,
) -> list[str]:
    missing = []
    if content_profile.has_process_flow and "```text" not in markdown:
        missing.append("missing_flow_diagram")
    if content_profile.has_comparison and "| --- |" not in markdown:
        missing.append("missing_comparison_table")
    if content_profile.has_code_or_commands and "```" not in markdown:
        missing.append("missing_code_block")
    return missing


def _section_text(sections: list[dict[str, object]], section_key: str) -> str:
    for section in sections:
        if section.get("section_key") == section_key:
            return str(section.get("text") or "")
    return ""


def _core_topic_count(sections: list[dict[str, object]]) -> int:
    return sum(
        1
        for section in sections
        if str(section.get("section_key") or "").startswith(CORE_TOPIC_PREFIX)
        and str(section.get("text") or "").strip()
    )


def _bullet_count(text: str) -> int:
    return len(re.findall(r"(?m)^\s*[-*]\s+\S+", text))


def _numbered_count(text: str) -> int:
    return len(re.findall(r"(?m)^\s*\d+[.)]\s+\S+", text))


def _key_term_count(text: str) -> int:
    table_rows = [
        line
        for line in text.splitlines()
        if line.strip().startswith("|")
        and "---" not in line
        and "용어" not in line
        and "의미" not in line
    ]
    if table_rows:
        return len(table_rows)
    return _bullet_count(text)


def _topic_number(section_key: str) -> int:
    suffix = section_key.removeprefix(CORE_TOPIC_PREFIX)
    return int(suffix) if suffix.isdigit() else 1


def _unique(values: list[str]) -> list[str]:
    result = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
