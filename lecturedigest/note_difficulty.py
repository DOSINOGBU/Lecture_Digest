from __future__ import annotations

import re
from typing import Any

from lecturedigest.note_profile import NoteContentProfile

DIFFICULT_TERM_PATTERN = re.compile(
    r"\b(?:[A-Z]{2,}[A-Za-z0-9]*|[A-Za-z]+[A-Z][A-Za-z0-9]*|"
    r"JavaScript|TypeScript|React|Babel|Webpack|Vite|caniuse\.com)\b"
)
KOREAN_JARGON_PATTERN = re.compile(
    r"[가-힣A-Za-z0-9]*(?:아키텍처|렌더링|파싱|인터프리터|트랜스파일러|"
    r"컴파일러|인덱스|엔진|트리|모델|스토리지|호환성|최적화)[가-힣A-Za-z0-9]*"
)
EASY_MARKER_PATTERN = re.compile(
    r"쉽게 말하면|한마디로|처음 보는 사람|일상(?:적인)? 비유|비유하자면|"
    r"풀어서 말하면|단계별로 보면|쉽게 풀이|초보자를 위한|초보자(?:도|가)?"
)
WORD_PATTERN = re.compile(r"[0-9A-Za-z가-힣]+")
GENERIC_OVERUSE_PATTERN = re.compile(r"(?m)^\s*(?:[-*]\s*)?쉽게 말하면[,，:]")
ACRONYM_GLOSSARY: dict[str, dict[str, str]] = {
    "HTML": {
        "expanded_form": "HyperText Markup Language",
        "plain_explanation": "쉽게 말하면 웹 문서의 뼈대와 내용을 적는 언어입니다.",
    },
    "CSS": {
        "expanded_form": "Cascading Style Sheets",
        "plain_explanation": "쉽게 말하면 화면의 색, 크기, 간격, 배치를 정하는 꾸미기 규칙입니다.",
    },
    "JS": {
        "expanded_form": "JavaScript",
        "plain_explanation": "쉽게 말하면 웹 화면이 사용자의 행동에 반응하게 만드는 언어입니다.",
    },
    "DOM": {
        "expanded_form": "Document Object Model",
        "plain_explanation": "쉽게 말하면 브라우저가 HTML 문서를 다루기 쉽게 정리해 둔 구조입니다.",
    },
    "API": {
        "expanded_form": "Application Programming Interface",
        "plain_explanation": "쉽게 말하면 서로 다른 프로그램이 약속된 방식으로 요청하고 응답하는 통로입니다.",
    },
    "UI": {
        "expanded_form": "User Interface",
        "plain_explanation": "쉽게 말하면 사용자가 직접 보고 누르고 입력하는 화면 부분입니다.",
    },
    "URL": {
        "expanded_form": "Uniform Resource Locator",
        "plain_explanation": "쉽게 말하면 웹에서 어떤 자원이 어디에 있는지 가리키는 주소입니다.",
    },
    "HTTP": {
        "expanded_form": "Hypertext Transfer Protocol",
        "plain_explanation": "쉽게 말하면 브라우저와 서버가 웹 데이터를 주고받을 때 쓰는 약속입니다.",
    },
    "JSON": {
        "expanded_form": "JavaScript Object Notation",
        "plain_explanation": "쉽게 말하면 데이터를 이름과 값의 묶음으로 주고받기 쉬운 텍스트 형식입니다.",
    },
    "OCR": {
        "expanded_form": "Optical Character Recognition",
        "plain_explanation": "쉽게 말하면 이미지나 화면 속 글자를 컴퓨터가 읽을 수 있는 텍스트로 바꾸는 기술입니다.",
    },
    "STT": {
        "expanded_form": "Speech To Text",
        "plain_explanation": "쉽게 말하면 사람의 음성을 글자로 바꾸는 기술입니다.",
    },
    "RAG": {
        "expanded_form": "Retrieval-Augmented Generation",
        "plain_explanation": "쉽게 말하면 먼저 관련 자료를 찾아보고 그 근거를 바탕으로 답을 만드는 방식입니다.",
    },
    "LLM": {
        "expanded_form": "Large Language Model",
        "plain_explanation": "쉽게 말하면 많은 텍스트를 학습해 문장을 이해하고 생성하는 AI 모델입니다.",
    },
    "CLI": {
        "expanded_form": "Command Line Interface",
        "plain_explanation": "쉽게 말하면 마우스 화면 대신 명령어를 입력해 프로그램을 다루는 방식입니다.",
    },
}


def detect_difficult_concepts(
    source_units: list[Any],
    *,
    sections: list[dict[str, object]] | None = None,
    limit: int = 8,
) -> list[dict[str, object]]:
    text_by_segment = _text_by_segment(source_units)
    source_text = " ".join(text_by_segment.values())
    if sections:
        source_text = f"{source_text} " + " ".join(
            str(section.get("title") or "") + " " + str(section.get("text") or "")
            for section in sections
        )
    candidates = []
    for term in _candidate_terms(source_text):
        segment_ids = _segment_ids_for_term(term, text_by_segment)
        if not segment_ids:
            continue
        acronym = acronym_info(term)
        candidates.append(
            {
                "term": acronym["term"] if acronym["expansion_known"] else term,
                "reason": "known_acronym" if acronym["expansion_known"] else _reason(term),
                "difficulty": _difficulty(term),
                "source_segment_ids": segment_ids,
                "expanded_form": acronym["expanded_form"],
                "expansion_known": acronym["expansion_known"],
            }
        )
        if len(candidates) >= limit:
            break
    return candidates


def beginner_explanation_for(term: str) -> str:
    acronym = acronym_info(term)
    if acronym["expansion_known"]:
        return (
            f"{acronym['term']} ({acronym['expanded_form']}): "
            f"{acronym['plain_explanation']}"
        )
    return (
        f"쉽게 말하면, {term}은 강의에서 새로 만난 개념을 바로 써먹기 전에 "
        "먼저 머릿속에 붙잡아 두기 위한 이름표입니다. 정확한 세부 원리는 "
        "뒤에서 더 공부하더라도, 지금은 강의 흐름 안에서 어떤 역할을 하는지부터 "
        "이해하면 됩니다."
    )


def acronym_info(term: str) -> dict[str, object]:
    normalized = _normalize_acronym(term)
    details = ACRONYM_GLOSSARY.get(normalized)
    if not details:
        return {
            "term": term,
            "expanded_form": "",
            "expansion_known": False,
            "plain_explanation": (
                f"{term}은 강의에서 줄여 부르는 약어로 보입니다. "
                "원어가 명확하지 않다면 임의로 풀어 쓰지 않고, 강의 맥락 안에서 맡는 역할만 설명해야 합니다."
            ),
        }
    return {
        "term": normalized,
        "expanded_form": details["expanded_form"],
        "expansion_known": True,
        "plain_explanation": details["plain_explanation"],
    }


def validate_difficulty_explanations(
    *,
    markdown: str,
    sections: list[dict[str, object]],
    source_units: list[Any],
    content_profile: NoteContentProfile,
    generator_notes: dict[str, object] | None = None,
) -> dict[str, object]:
    expected = detect_difficult_concepts(source_units, sections=sections)
    explanations = _difficulty_explanations(generator_notes or {})
    failed: list[str] = []
    warnings: list[str] = []

    if not expected:
        return _result(expected, explanations, failed, warnings, markdown)

    valid_explanations = [
        item
        for item in explanations
        if str(item.get("term") or "").strip()
        and str(item.get("plain_explanation") or "").strip()
    ]
    required_count = _required_explanation_count(expected, content_profile)
    if len(valid_explanations) < required_count:
        _append_by_profile(
            failed,
            warnings,
            "difficult_concept_explanation_missing",
            content_profile,
        )

    if valid_explanations and not EASY_MARKER_PATTERN.search(markdown):
        _append_by_profile(
            failed,
            warnings,
            "difficult_concept_explanation_missing",
            content_profile,
        )

    if any(_is_too_jargony(str(item.get("plain_explanation") or "")) for item in valid_explanations):
        _append_by_profile(
            failed,
            warnings,
            "easy_explanation_too_jargony",
            content_profile,
        )

    if any(_unsupported_explanation(item) for item in explanations):
        _append_by_profile(
            failed,
            warnings,
            "unsupported_easy_explanation",
            content_profile,
        )

    for flag in _acronym_validation_flags(expected, explanations):
        _append_by_profile(failed, warnings, flag, content_profile)

    if _easy_explanation_overused(markdown, len(valid_explanations)):
        _append_by_profile(
            failed,
            warnings,
            "easy_explanation_overused",
            content_profile,
        )

    return _result(expected, explanations, failed, warnings, markdown)


def _candidate_terms(text: str) -> list[str]:
    ordered = []
    for pattern in (DIFFICULT_TERM_PATTERN, KOREAN_JARGON_PATTERN):
        for match in pattern.findall(text):
            value = str(match).strip(".,;:()[]{}<>`'\"")
            if len(value) < 2:
                continue
            if value.lower() in {"api", "ui"}:
                reason = "short_acronym"
            else:
                reason = _reason(value)
            if not reason:
                continue
            key = value.lower()
            if key not in [item.lower() for item in ordered]:
                ordered.append(value)
    return ordered


def _reason(term: str) -> str:
    if re.fullmatch(r"[A-Z]{2,}[A-Za-z0-9]*", term):
        return "english_acronym"
    if re.search(r"[A-Za-z]+[A-Z][A-Za-z0-9]*", term):
        return "mixed_or_camel_case_term"
    if KOREAN_JARGON_PATTERN.fullmatch(term):
        return "domain_jargon"
    if term in {"JavaScript", "TypeScript", "React", "Babel", "Webpack", "Vite", "caniuse.com"}:
        return "technical_tool_or_keyword"
    return ""


def _difficulty(term: str) -> str:
    if re.fullmatch(r"[A-Z]{2,}[A-Za-z0-9]*", term) or term in {"caniuse.com", "Babel"}:
        return "high"
    return "medium"


def _normalize_acronym(term: str) -> str:
    value = str(term or "").strip(".,;:()[]{}<>`'\"")
    return value.upper() if re.fullmatch(r"[A-Za-z]{2,}", value) else value


def _text_by_segment(source_units: list[Any]) -> dict[str, str]:
    result = {}
    for index, unit in enumerate(source_units, start=1):
        segment_id = str(getattr(unit, "segment_id", "") or f"segment-{index}")
        parts = [str(getattr(unit, "text", "") or "")]
        ocr_text = str(getattr(unit, "ocr_text", "") or "")
        if ocr_text:
            parts.append(ocr_text)
        result[segment_id] = " ".join(parts)
    return result


def _segment_ids_for_term(term: str, text_by_segment: dict[str, str]) -> list[str]:
    term_lower = term.lower()
    ids = []
    for segment_id, text in text_by_segment.items():
        if term_lower in text.lower():
            ids.append(segment_id)
        if len(ids) >= 4:
            break
    return ids


def _difficulty_explanations(notes: dict[str, object]) -> list[dict[str, object]]:
    raw = notes.get("difficulty_explanations")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _required_explanation_count(
    expected: list[dict[str, object]],
    content_profile: NoteContentProfile,
) -> int:
    if content_profile.source_insufficient_for_full_note:
        return 0
    if content_profile.strategy in {"expanded", "chaptered"}:
        return min(len(expected), 4)
    return min(len(expected), 2)


def _append_by_profile(
    failed: list[str],
    warnings: list[str],
    flag: str,
    content_profile: NoteContentProfile,
) -> None:
    target = warnings if content_profile.source_insufficient_for_full_note else failed
    if flag not in target:
        target.append(flag)


def _is_too_jargony(text: str) -> bool:
    words = WORD_PATTERN.findall(text)
    if len("".join(words)) < 24:
        return True
    difficult_words = [
        word
        for word in words
        if _reason(word) or re.fullmatch(r"[A-Z]{2,}[A-Za-z0-9]*", word)
    ]
    return (
        bool(words)
        and len(difficult_words) >= 4
        and len(difficult_words) / len(words) > 0.35
    )


def _unsupported_explanation(item: dict[str, object]) -> bool:
    if item.get("unsupported") is True:
        return True
    ids = item.get("source_segment_ids")
    return not isinstance(ids, list) or not any(str(segment_id).strip() for segment_id in ids)


def _acronym_validation_flags(
    expected: list[dict[str, object]],
    explanations: list[dict[str, object]],
) -> list[str]:
    flags: list[str] = []
    explanations_by_term = {
        _normalize_acronym(str(item.get("term") or "")): item
        for item in explanations
        if str(item.get("term") or "").strip()
    }
    for item in expected:
        term = str(item.get("term") or "")
        acronym = acronym_info(term)
        if not acronym["expansion_known"]:
            continue
        explanation = explanations_by_term.get(str(acronym["term"]))
        if not explanation:
            flags.append("acronym_explanation_missing")
            continue
        if not str(explanation.get("plain_explanation") or "").strip():
            flags.append("acronym_explanation_missing")
        if explanation.get("expansion_known") is not True:
            flags.append("acronym_explanation_missing")
        if str(explanation.get("expanded_form") or "").strip() != acronym["expanded_form"]:
            flags.append("unsupported_acronym_expansion")

    for item in explanations:
        term = str(item.get("term") or "")
        if not term or not _reason(term):
            continue
        acronym = acronym_info(term)
        expanded = str(item.get("expanded_form") or "").strip()
        if acronym["expansion_known"]:
            if expanded and expanded != acronym["expanded_form"]:
                flags.append("unsupported_acronym_expansion")
        elif expanded or item.get("expansion_known") is True:
            flags.append("unsupported_acronym_expansion")
    return _unique(flags)


def _easy_explanation_overused(markdown: str, explanation_count: int) -> bool:
    starts = GENERIC_OVERUSE_PATTERN.findall(markdown)
    if len(starts) <= 4:
        return False
    return len(starts) > max(4, explanation_count)


def _result(
    expected: list[dict[str, object]],
    explanations: list[dict[str, object]],
    failed: list[str],
    warnings: list[str],
    markdown: str,
) -> dict[str, object]:
    return {
        "expected_concepts": expected,
        "explanations": explanations,
        "metrics": {
            "expected_count": len(expected),
            "explanation_count": len(explanations),
            "known_acronym_count": sum(
                1
                for item in expected
                if acronym_info(str(item.get("term") or ""))["expansion_known"]
            ),
            "easy_marker_count": len(EASY_MARKER_PATTERN.findall(markdown)),
        },
        "failed_rules": _unique(failed),
        "warnings": _unique(warnings),
        "quality_flags": _unique([*failed, *warnings]),
    }


def _unique(values: list[str]) -> list[str]:
    result = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
