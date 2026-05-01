from __future__ import annotations

import re
from collections import Counter
from typing import Any

from lecturedigest.note_profile import NoteContentProfile

CORE_TOPIC_PREFIX = "topic_"
H2_PATTERN = re.compile(r"(?m)^##\s+")
H3_PATTERN = re.compile(r"(?m)^###\s+(.+?)\s*$")
CODE_FENCE_PATTERN = re.compile(r"```")
TABLE_ROW_PATTERN = re.compile(r"(?m)^\|")
SENTENCE_PATTERN = re.compile(r"[.!?。？！]")
SOURCE_CITATION_PATTERN = re.compile(r"\(source:\s*[^)]*\)", re.IGNORECASE)
SEGMENT_ID_PATTERN = re.compile(r"\bseg-\d+\b", re.IGNORECASE)
TIMESTAMP_PATTERN = re.compile(
    r"(?:@\s*)?\b\d{2}:\d{2}:\d{2}(?:[.,]\d{3})?"
    r"(?:\s*-\s*\d{2}:\d{2}:\d{2}(?:[.,]\d{3})?)?\b"
)
GENERIC_SUBHEADING_PATTERN = re.compile(
    r"(?im)^###\s*(?:concept|why it matters|lecture flow|example|"
    r"lecture flow\s*/\s*example)\s*$"
)
BULLET_PATTERN = re.compile(r"(?m)^\s*[-*]\s+\S+")
NUMBERED_PATTERN = re.compile(r"(?m)^\s*\d+[.)]\s+\S+")


def body_depth_policy(content_profile: NoteContentProfile) -> dict[str, object]:
    policy_by_strategy: dict[str, dict[str, object]] = {
        "tiny": {
            "min_document_chars": 350,
            "target_document_chars": [500, 1200],
            "max_single_note_chars": 1500,
            "chaptered_required": False,
            "topic_count_range": [1, 2],
            "topic_avg_chars": 180,
            "min_topic_avg_chars": 120,
            "min_topic_sentences_avg": 1,
            "min_h3_count": 0,
        },
        "compact": {
            "min_document_chars": 800,
            "target_document_chars": [1000, 2500],
            "max_single_note_chars": 3000,
            "chaptered_required": False,
            "topic_count_range": [1, 3],
            "topic_avg_chars": 260,
            "min_topic_avg_chars": 180,
            "min_topic_sentences_avg": 2,
            "min_h3_count": 0,
        },
        "short": {
            "min_document_chars": 2000,
            "target_document_chars": [2500, 5000],
            "max_single_note_chars": 6000,
            "chaptered_required": False,
            "topic_count_range": [3, 5],
            "topic_avg_chars": 360,
            "min_topic_avg_chars": 260,
            "min_topic_sentences_avg": 3,
            "min_h3_count": 0,
        },
        "standard": {
            "min_document_chars": 5000,
            "target_document_chars": [5000, 10000],
            "max_single_note_chars": 12000,
            "chaptered_required": False,
            "topic_count_range": [5, 10],
            "topic_avg_chars": 500,
            "min_topic_avg_chars": 360,
            "min_topic_sentences_avg": 4,
            "min_h3_count": 0,
        },
        "expanded": {
            "min_document_chars": 9000,
            "target_document_chars": [10000, 20000],
            "max_single_note_chars": 22000,
            "chaptered_required": False,
            "topic_count_range": [8, 14],
            "topic_avg_chars": 560,
            "min_topic_avg_chars": 400,
            "min_topic_sentences_avg": 5,
            "min_h3_count": 2,
        },
        "chaptered": {
            "min_document_chars": 12000,
            "target_document_chars": [14000, 24000],
            "max_single_note_chars": None,
            "chaptered_required": True,
            "topic_count_range": [10, 20],
            "topic_avg_chars": 600,
            "min_topic_avg_chars": 420,
            "min_topic_sentences_avg": 5,
            "min_h3_count": 4,
        },
    }
    return dict(policy_by_strategy.get(content_profile.strategy, policy_by_strategy["standard"]))


def visible_source_artifacts(markdown: str) -> list[str]:
    artifacts: list[str] = []
    for pattern in (SOURCE_CITATION_PATTERN, SEGMENT_ID_PATTERN, TIMESTAMP_PATTERN):
        for match in pattern.findall(markdown):
            value = match if isinstance(match, str) else match[0]
            if value and value not in artifacts:
                artifacts.append(value)
    return artifacts


def strip_visible_source_artifacts(markdown: str) -> str:
    stripped = SOURCE_CITATION_PATTERN.sub(" ", markdown)
    stripped = SEGMENT_ID_PATTERN.sub(" ", stripped)
    stripped = TIMESTAMP_PATTERN.sub(" ", stripped)
    return re.sub(r"[ \t]+", " ", stripped)


def evaluate_body_depth(
    *,
    markdown: str,
    sections: list[dict[str, object]],
    source_units: list[Any],
    content_profile: NoteContentProfile,
) -> dict[str, object]:
    policy = body_depth_policy(content_profile)
    display_markdown = strip_visible_source_artifacts(markdown)
    display_sections = _display_sections(sections)
    topic_sections = _topic_sections(display_sections)
    topic_lengths = [_body_chars(section) for section in topic_sections]
    topic_sentence_counts = [_sentence_count(str(section.get("text") or "")) for section in topic_sections]
    style_metrics = _style_metrics(topic_sections)
    metrics = {
        "raw_markdown_chars": len(markdown),
        "markdown_chars": len(display_markdown),
        "line_count": len(display_markdown.splitlines()),
        "h2_count": len(H2_PATTERN.findall(display_markdown)),
        "h3_count": len(H3_PATTERN.findall(display_markdown)),
        "code_fence_count": len(CODE_FENCE_PATTERN.findall(display_markdown)) // 2,
        "table_row_count": len(TABLE_ROW_PATTERN.findall(display_markdown)),
        "topic_count": len(topic_sections),
        "topic_avg_chars": _average(topic_lengths),
        "topic_min_chars": min(topic_lengths) if topic_lengths else 0,
        "topic_avg_sentences": _average(topic_sentence_counts),
        "source_coverage_ratio": _source_coverage_ratio(sections, source_units),
        **style_metrics,
    }
    failed = _failed_depth_rules(metrics, policy, content_profile, display_markdown)
    warnings = _warning_depth_rules(metrics, content_profile)
    return {
        "policy": policy,
        "metrics": metrics,
        "failed_rules": failed,
        "warnings": warnings,
        "quality_flags": _unique([*failed, *warnings]),
    }


def _failed_depth_rules(
    metrics: dict[str, object],
    policy: dict[str, object],
    content_profile: NoteContentProfile,
    markdown: str,
) -> list[str]:
    if content_profile.source_insufficient_for_full_note:
        return []
    failed = []
    if _number(metrics["markdown_chars"]) < _number(policy["min_document_chars"]):
        failed.append("body_too_short")
    if _number(metrics["topic_avg_chars"]) < _number(policy["min_topic_avg_chars"]):
        failed.append("topic_body_too_shallow")
    if _number(metrics["h3_count"]) < _number(policy["min_h3_count"]):
        failed.append("insufficient_subsections")
    if _number(metrics["topic_avg_sentences"]) < _number(policy["min_topic_sentences_avg"]):
        failed.append("missing_explanatory_depth")
    if GENERIC_SUBHEADING_PATTERN.search(markdown):
        failed.append("generic_subheading_present")
    if bool(metrics.get("repetitive_topic_template")):
        failed.append("repetitive_topic_template")
    if (
        _number(metrics.get("topic_count")) >= 3
        and _number(metrics.get("style_kind_count")) < 3
    ):
        failed.append("insufficient_style_variety")
    return failed


def _warning_depth_rules(
    metrics: dict[str, object],
    content_profile: NoteContentProfile,
) -> list[str]:
    warnings = []
    if (
        not content_profile.source_insufficient_for_full_note
        and _number(metrics["source_coverage_ratio"]) < 0.08
    ):
        warnings.append("coverage_too_sparse")
    return warnings


def _display_sections(sections: list[dict[str, object]]) -> list[dict[str, object]]:
    display = []
    for section in sections:
        copied = dict(section)
        copied["text"] = strip_visible_source_artifacts(str(copied.get("text") or ""))
        display.append(copied)
    return display


def _style_metrics(topic_sections: list[dict[str, object]]) -> dict[str, object]:
    topic_kinds = [_topic_style_kinds(str(section.get("text") or "")) for section in topic_sections]
    style_kinds = sorted({kind for kinds in topic_kinds for kind in kinds})
    sequences = _topic_heading_sequences(topic_sections)
    repetitive = False
    if len(sequences) >= 3:
        counts = Counter(tuple(sequence) for sequence in sequences if sequence)
        if counts:
            repetitive = counts.most_common(1)[0][1] >= max(3, round(len(sequences) * 0.6))
    return {
        "style_kinds": style_kinds,
        "style_kind_count": len(style_kinds),
        "topic_heading_sequences": sequences,
        "repetitive_topic_template": repetitive,
    }


def _topic_style_kinds(text: str) -> set[str]:
    kinds = set()
    if H3_PATTERN.search(text):
        kinds.add("subsections")
    if BULLET_PATTERN.search(text) or NUMBERED_PATTERN.search(text):
        kinds.add("list")
    if TABLE_ROW_PATTERN.search(text):
        kinds.add("table")
    if "```" in text:
        kinds.add("code_or_flow")
    paragraphs = [item for item in re.split(r"\n\s*\n", text) if item.strip()]
    if paragraphs:
        kinds.add("narrative")
    return kinds


def _topic_heading_sequences(topic_sections: list[dict[str, object]]) -> list[list[str]]:
    sequences = []
    for section in topic_sections:
        text = str(section.get("text") or "")
        headings = [
            re.sub(r"\s+", " ", heading.strip().lower())
            for heading in H3_PATTERN.findall(text)
        ]
        if headings:
            sequences.append(headings)
    return sequences


def _topic_sections(sections: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        section
        for section in sections
        if str(section.get("section_key") or "").startswith(CORE_TOPIC_PREFIX)
    ]


def _body_chars(section: dict[str, object]) -> int:
    return len(_plain_body(str(section.get("text") or "")))


def _plain_body(text: str) -> str:
    without_fences = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    return re.sub(r"\s+", " ", without_fences).strip()


def _sentence_count(text: str) -> int:
    count = len(SENTENCE_PATTERN.findall(text))
    bullet_count = len(BULLET_PATTERN.findall(text))
    paragraph_count = len([item for item in re.split(r"\n\s*\n", text) if item.strip()])
    return max(count, bullet_count, paragraph_count)


def _source_coverage_ratio(
    sections: list[dict[str, object]],
    source_units: list[Any],
) -> float:
    if not source_units:
        return 0.0
    seen = set()
    for section in sections:
        ids = section.get("segment_ids", [])
        if not isinstance(ids, list):
            continue
        seen.update(str(segment_id) for segment_id in ids)
    return round(len(seen) / len(source_units), 3)


def _average(values: list[int]) -> int:
    if not values:
        return 0
    return round(sum(values) / len(values))


def _number(value: object) -> float:
    return float(value) if isinstance(value, (int, float)) else 0.0


def _unique(values: list[str]) -> list[str]:
    result = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
