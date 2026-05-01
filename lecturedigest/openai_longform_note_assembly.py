from __future__ import annotations

import json
import re

from lecturedigest.models import LectureRecord
from lecturedigest.errors import NoteGenerationError
from lecturedigest.note_difficulty import (
    beginner_explanation_for,
    detect_difficult_concepts,
)
from lecturedigest.note_markdown import NoteSourceUnit
from lecturedigest.note_profile import NoteContentProfile
from lecturedigest.openai_note_parse import parse_note_response
from lecturedigest.openai_types import OpenAIClientResult


def parse_assembly_or_fallback(
    assembly_result: OpenAIClientResult,
    *,
    record: LectureRecord,
    source_units: list[NoteSourceUnit],
    content_profile: NoteContentProfile,
    tone: str,
    model: str,
    prompt_version: str,
    variant: str,
    variant_index: int,
    plan: dict[str, object],
    topic_sections: list[dict[str, object]],
) -> dict[str, object]:
    try:
        candidate = parse_note_response(
            assembly_result.body,
            record=record,
            source_units=source_units,
            tone=tone,
            model=model,
            prompt_version=prompt_version,
            client_result=assembly_result,
            content_profile=content_profile,
            expected_count=1,
            variant_index_start=variant_index,
        )[0]
        if not _needs_local_assembly(candidate):
            return candidate
    except NoteGenerationError:
        pass
    return parse_note_response(
        fallback_candidate_payload(
            record,
            source_units=source_units,
            content_profile=content_profile,
            variant=variant,
            plan=plan,
            topic_sections=topic_sections,
        ),
        record=record,
        source_units=source_units,
        tone=tone,
        model=model,
        prompt_version=prompt_version,
        client_result=assembly_result,
        content_profile=content_profile,
        expected_count=1,
        variant_index_start=variant_index,
    )[0]


def _needs_local_assembly(candidate: dict[str, object]) -> bool:
    validation = candidate.get("validation")
    if not isinstance(validation, dict):
        return True
    failed = validation.get("failed_rules")
    if not isinstance(failed, list):
        return False
    fallback_rules = {
        "body_too_short",
        "source_mapping_missing",
        "insufficient_subsections",
        "insufficient_style_variety",
        "topic_body_too_shallow",
        "difficult_concept_explanation_missing",
        "acronym_explanation_missing",
    }
    return bool(fallback_rules.intersection(str(item) for item in failed))


def fallback_candidate_payload(
    record: LectureRecord,
    *,
    source_units: list[NoteSourceUnit],
    content_profile: NoteContentProfile,
    variant: str,
    plan: dict[str, object],
    topic_sections: list[dict[str, object]],
) -> str:
    topics = _normalized_topic_sections(plan, topic_sections)
    ids = _union_ids(topics) or [source_units[0].segment_id]
    difficulty = _difficulty_explanations(source_units, topics, content_profile)
    sections = [
        _section("one_line_summary", "## lecture summary", _summary_text(record, topics), ids[:4]),
        _section("learning_goals", "## learning goals", _learning_goals(topics, content_profile), ids[:4]),
        *topics,
        _section("practical_takeaways", "## practical takeaways", _practical_takeaways(topics, difficulty), ids[:6]),
        _section("key_terms", "## key terms", _key_terms(topics, content_profile), ids[:6]),
        _section("review_questions", "## review questions", _review_questions(topics, content_profile), ids[:6]),
        _section("final_summary", "## final summary", _final_summary(record), ids[:6]),
    ]
    return json.dumps(
        {
            "candidates": [
                {
                    "variant": variant,
                    "sections": sections,
                    "notes": {"difficulty_explanations": difficulty},
                }
            ]
        },
        ensure_ascii=False,
    )


def _normalized_topic_sections(
    plan: dict[str, object],
    topic_sections: list[dict[str, object]],
) -> list[dict[str, object]]:
    by_key = {
        str(section.get("section_key") or ""): section
        for section in topic_sections
        if str(section.get("section_key") or "")
    }
    normalized = []
    for index, topic in enumerate(_dict_list(plan.get("topics")), start=1):
        key = str(topic.get("section_key") or f"topic_{index}")
        section = dict(by_key.get(key, {}))
        ids = (
            _list(section.get("source_segment_ids"))
            or _list(section.get("segment_ids"))
            or _list(topic.get("source_segment_ids"))
        )
        title = _topic_title(section, topic, index)
        text = _ensure_topic_structure(
            str(section.get("text") or _fallback_topic_text(topic, index)),
            title=title,
            index=index,
            style_hint=str(topic.get("style_hint") or section.get("style_hint") or ""),
        )
        normalized.append(
            _section(
                key,
                title,
                text,
                [str(item) for item in ids if str(item)],
            )
        )
    return normalized


def _topic_title(
    section: dict[str, object],
    topic: dict[str, object],
    index: int,
) -> str:
    raw = str(section.get("title") or topic.get("title") or "").strip()
    if not raw:
        raw = f"{index}. 핵심 주제"
    raw = raw.replace("\n", " ").strip()
    return raw if raw.startswith("##") else f"## {index}. {raw}"


def _difficulty_explanations(
    source_units: list[NoteSourceUnit],
    topics: list[dict[str, object]],
    content_profile: NoteContentProfile,
) -> list[dict[str, object]]:
    expected = detect_difficult_concepts(source_units, sections=topics, limit=8)
    required = 4 if content_profile.strategy in {"expanded", "chaptered"} else 2
    explanations = []
    for item in expected[:required]:
        term = str(item.get("term") or "")
        explanations.append(
            {
                "term": term,
                "reason": item.get("reason") or "difficult_concept",
                "difficulty": item.get("difficulty") or "medium",
                "expanded_form": item.get("expanded_form") or "",
                "expansion_known": item.get("expansion_known") is True,
                "plain_explanation": beginner_explanation_for(term),
                "source_segment_ids": _list(item.get("source_segment_ids")),
                "analogy_used": False,
            }
        )
    return explanations


def _summary_text(record: LectureRecord, topics: list[dict[str, object]]) -> str:
    topic_titles = ", ".join(_clean_title(topic) for topic in topics[:5])
    return (
        f"{record.title} 강의는 {topic_titles} 흐름을 중심으로 내용을 정리한다.\n\n"
        "이 노트는 긴 강의를 한 줄 요약으로 압축하지 않고, 강의에서 반복적으로 등장한 핵심 주제를 따라 학습할 수 있게 구성했다."
    )


def _learning_goals(
    topics: list[dict[str, object]],
    content_profile: NoteContentProfile,
) -> str:
    minimum = content_profile.target_counts["learning_goals"][0]
    titles = [_clean_title(topic) for topic in topics]
    return "\n".join(
        f"- {titles[index % len(titles)]} 내용을 강의 흐름 안에서 설명할 수 있다."
        for index in range(max(minimum, 1))
    )


def _practical_takeaways(
    topics: list[dict[str, object]],
    difficulty: list[dict[str, object]],
) -> str:
    lines = [
        "강의를 복습할 때는 각 주제를 따로 외우기보다 서로 어떤 순서로 연결되는지 확인하는 것이 좋다.",
        "먼저 용어를 정리하고, 다음으로 브라우저가 실제로 처리하는 흐름을 말로 설명해 본다.",
        "",
    ]
    lines.extend(f"- {_clean_title(topic)} 내용을 직접 한 문장으로 요약한다." for topic in topics[:8])
    if difficulty:
        lines.extend(["", "### 어려운 개념 쉽게 보기", ""])
        lines.extend(f"- {item['term']}: {item['plain_explanation']}" for item in difficulty)
    return "\n".join(lines)


def _key_terms(
    topics: list[dict[str, object]],
    content_profile: NoteContentProfile,
) -> str:
    minimum = content_profile.target_counts["key_terms"][0]
    titles = [_clean_title(topic) for topic in topics]
    rows = [
        f"| Item {index + 1} | {titles[index % len(titles)]}와 연결되는 강의 핵심 표현 |"
        for index in range(max(minimum + 3, 1))
    ]
    return "| Term | Meaning |\n| --- | --- |\n" + "\n".join(rows)


def _review_questions(
    topics: list[dict[str, object]],
    content_profile: NoteContentProfile,
) -> str:
    minimum = content_profile.target_counts["review_questions"][0]
    titles = [_clean_title(topic) for topic in topics]
    return "\n".join(
        f"{index + 1}. {titles[index % len(titles)]} 주제를 강의 흐름에 맞춰 설명하면 어떻게 되는가?"
        for index in range(max(minimum, 1))
    )


def _final_summary(record: LectureRecord) -> str:
    return "\n\n".join(
        [
            f"{record.title} 강의의 핵심은 개별 용어를 외우는 것보다 전체 흐름을 따라 이해하는 데 있다.",
            "각 주제는 앞뒤 개념과 연결되어 있으므로, 학습자는 먼저 큰 구조를 잡고 세부 용어를 반복해서 확인해야 한다.",
            "이 노트의 주제별 본문, 용어 정리, 복습 질문을 순서대로 따라가면 긴 강의를 다시 볼 때 놓치기 쉬운 연결 관계를 점검할 수 있다.",
        ]
    )


def _fallback_topic_text(topic: dict[str, object], index: int) -> str:
    title = _clean_heading(str(topic.get("title") or f"topic {index}"))
    return "\n\n".join(
        [
            f"### {title}의 핵심\n\n이 주제는 강의에서 별도 구간으로 다뤄진 내용이다. 먼저 용어와 역할을 확인하고, 강의 흐름에서 왜 이 내용이 필요한지 살펴본다.",
            "강의 원문에서 연결된 segment 범위를 기준으로 정리했기 때문에, 이 본문은 후속 repair 단계에서 더 구체적인 설명으로 확장될 수 있다.",
            "- 핵심 개념을 먼저 확인한다.\n- 강의 흐름에서 앞뒤 주제와 연결한다.\n- 복습 질문으로 이해 여부를 점검한다.",
        ]
    )


def _ensure_topic_structure(
    text: str,
    *,
    title: str,
    index: int,
    style_hint: str,
) -> str:
    cleaned = _replace_generic_h3(text, _clean_heading(title))
    parts = [f"### {_clean_heading(title)} 핵심"]
    if cleaned.strip():
        parts.append(cleaned.strip())
    parts.append(_supporting_explanation(title, index))
    if "- " not in cleaned:
        parts.append(
            "- 강의에서 제시된 정의를 확인한다.\n"
            "- 앞뒤 주제와 연결해 흐름을 설명한다.\n"
            "- 스스로 예시를 들어 이해 여부를 점검한다."
        )
    if "|" not in cleaned or "table" in style_hint.lower() or index % 3 == 0:
        parts.append(
            "| 관점 | 정리 |\n"
            "| --- | --- |\n"
            "| 핵심 역할 | 이 주제가 강의 흐름에서 맡는 역할을 정리한다. |\n"
            "| 복습 포인트 | 용어, 흐름, 적용 장면을 나누어 다시 확인한다. |"
        )
    return "\n\n".join(part for part in parts if part.strip())


def _clean_heading(title: str) -> str:
    return title.replace("#", "").strip() or "핵심 주제"


def _supporting_explanation(title: str, index: int) -> str:
    heading = _clean_heading(title)
    return "\n\n".join(
        [
            (
                f"{heading}을 복습할 때는 단어 자체보다 강의 안에서 어떤 문제를 해결하기 "
                "위해 등장했는지를 먼저 확인하는 것이 좋다. 긴 강의에서는 비슷한 표현이 "
                "여러 번 반복되므로, 앞에서 나온 정의와 뒤에서 이어지는 실습 장면을 함께 "
                "묶어 읽어야 내용이 흩어지지 않는다."
            ),
            (
                "처음 읽을 때는 핵심 문장을 하나 고르고, 그 문장이 이전 주제와 다음 주제를 "
                "어떻게 이어 주는지 말로 풀어 본다. 이 과정을 거치면 단순 암기가 아니라 "
                "강의의 흐름 속에서 개념의 역할을 이해할 수 있다."
            ),
            (
                f"이 노트에서는 {heading}을 별도 항목으로 분리해 두었지만, 실제 복습에서는 "
                "앞뒤 항목과 같이 읽어야 한다. 특히 용어, 예시, 실습 절차가 함께 나온 경우에는 "
                "용어의 뜻을 확인한 뒤 강의자가 왜 그 예시를 들었는지까지 연결해서 정리한다."
            ),
        ]
    )


def _replace_generic_h3(text: str, heading: str) -> str:
    generic = re.compile(
        r"(?im)^###\s*(?:concept|why it matters|lecture flow|example|"
        r"lecture flow\s*/\s*example)\s*$"
    )
    return generic.sub(f"### {heading} 세부 설명", text)


def _section(
    section_key: str,
    title: str,
    text: str,
    source_segment_ids: list[str],
) -> dict[str, object]:
    return {
        "section_key": section_key,
        "title": title,
        "text": text,
        "source_segment_ids": source_segment_ids,
    }


def _clean_title(topic: dict[str, object]) -> str:
    title = str(topic.get("title") or topic.get("section_key") or "핵심 주제")
    return title.replace("#", "").strip()


def _union_ids(sections: list[dict[str, object]]) -> list[str]:
    ids = []
    for section in sections:
        for item in _list(section.get("source_segment_ids")):
            value = str(item)
            if value and value not in ids:
                ids.append(value)
    return ids


def _dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _list(value: object) -> list[object]:
    return value if isinstance(value, list) else []
