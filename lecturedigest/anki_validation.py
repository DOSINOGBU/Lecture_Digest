from __future__ import annotations

import re

CLOZE_PATTERN = re.compile(r"\{\{c\d+::([^}]+)\}\}")
SOURCE_ARTIFACT_PATTERN = re.compile(r"\bsource:\s*|seg-\d+|@\s*\d{2}:\d{2}:\d{2}", re.IGNORECASE)
WORD_PATTERN = re.compile(r"[0-9A-Za-z\uac00-\ud7a3]+")
BROAD_FRONT_PATTERNS = (
    "key point",
    "main point",
    "summarize the whole",
    "give an overview",
    "what should you remember",
    "explain everything",
)
LOW_VALUE_FRONTS = {
    "what is this",
    "what is it",
    "explain",
    "remember this",
}


def validate_card(card: dict[str, object]) -> dict[str, object]:
    failed = []
    front = _text(card.get("front") or card.get("cloze_text"))
    back = _text(card.get("back"))
    cloze_text = _text(card.get("cloze_text"))
    card_type = str(card.get("card_type") or "")

    if not front:
        failed.append("front_required")
    if card_type != "cloze" and not back:
        failed.append("back_required")

    source = card.get("source", {})
    if not isinstance(source, dict) or source.get("mapping_status") != "mapped":
        failed.append("source_mapping_required")

    if SOURCE_ARTIFACT_PATTERN.search(str(card.get("front") or "")):
        failed.append("source_visible_on_front")
    if card_type == "cloze" and _bad_cloze(cloze_text):
        failed.append("bad_cloze")
    if card_type != "cloze" and _answer_leaked_in_front(front, back):
        failed.append("answer_leaked_in_front")
    if _too_broad(front):
        failed.append("too_broad")
    if _too_many_facts(front):
        failed.append("too_many_facts")
    if _no_learning_value(front, back, cloze_text):
        failed.append("no_learning_value")
    if card.get("unsupported_fact"):
        failed.append("unsupported_fact")

    failed = _unique(failed)
    return _with_status(card, failed)


def remove_duplicate_cards(
    cards: list[dict[str, object]],
) -> tuple[list[dict[str, object]], int]:
    seen = set()
    unique_cards = []
    duplicate_count = 0
    for card in cards:
        signature = card_signature(card)
        if signature in seen:
            duplicate_count += 1
            continue
        seen.add(signature)
        unique_cards.append(card)
    return unique_cards, duplicate_count


def card_signature(card: dict[str, object]) -> str:
    front = _normalize_for_match(card.get("cloze_text") or card.get("front") or "")
    card_type = str(card.get("card_type") or "")
    return f"{card_type}:{front}"


def _with_status(
    card: dict[str, object],
    failed_rules: list[str],
) -> dict[str, object]:
    status = "ready" if not failed_rules else "flagged"
    return {
        **card,
        "status": status,
        "validation": {
            "status": "passed" if not failed_rules else "flagged",
            "failed_rules": failed_rules,
        },
    }


def _bad_cloze(cloze_text: str) -> bool:
    matches = CLOZE_PATTERN.findall(cloze_text)
    if len(matches) != 1:
        return True
    hidden = matches[0].strip()
    return not hidden or len(hidden) > 80 or len(hidden.split()) > 8


def _answer_leaked_in_front(front: str, back: str) -> bool:
    normalized_front = _normalize_for_match(front)
    normalized_back = _normalize_for_match(back)
    if not normalized_front or not normalized_back:
        return False
    answer_phrase = " ".join(normalized_back.split()[:10])
    return len(answer_phrase) >= 30 and answer_phrase in normalized_front


def _too_broad(front: str) -> bool:
    lower = front.lower()
    return any(pattern in lower for pattern in BROAD_FRONT_PATTERNS)


def _too_many_facts(front: str) -> bool:
    return front.count("?") > 1


def _no_learning_value(front: str, back: str, cloze_text: str) -> bool:
    if cloze_text:
        return False
    words = WORD_PATTERN.findall(front)
    if len(words) < 4:
        return True
    return _normalize_for_match(front) in LOW_VALUE_FRONTS and not back


def _text(value: object) -> str:
    return str(value or "").strip()


def _normalize_for_match(value: object) -> str:
    tokens = WORD_PATTERN.findall(str(value).lower())
    return " ".join(tokens)


def _unique(values: list[str]) -> list[str]:
    result = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
