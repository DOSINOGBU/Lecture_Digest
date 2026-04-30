from __future__ import annotations

import random
import re

from lecturedigest.models import LectureRecord, TranscriptSegment
from lecturedigest.quiz_validation import validate_quiz_item

CLOZE_PATTERN = re.compile(r"\{\{c\d+::([^}]+)\}\}")
SOURCE_ARTIFACT_PATTERN = re.compile(r"\bsource:\s*|seg-\d+|@\s*\d{2}:\d{2}:\d{2}", re.IGNORECASE)


def build_quiz_candidates(
    record: LectureRecord,
    sections: list[dict[str, object]],
    ready_cards: list[dict[str, object]],
    *,
    question_types: list[str],
    target_quiz_count: int,
    rng: random.Random,
) -> list[dict[str, object]]:
    segment_lookup = {segment.segment_id: segment for segment in record.segments}
    candidates = _card_quiz_candidates(
        record,
        ready_cards,
        sections,
        segment_lookup,
        question_types,
        rng,
    )
    if len(candidates) < target_quiz_count:
        candidates.extend(
            _note_quiz_candidates(
                record,
                sections,
                segment_lookup,
                question_types,
                rng,
            )
        )
    return candidates


def _card_quiz_candidates(
    record: LectureRecord,
    cards: list[dict[str, object]],
    sections: list[dict[str, object]],
    segment_lookup,
    question_types: list[str],
    rng: random.Random,
) -> list[dict[str, object]]:
    candidates = []
    for card in cards:
        if "multiple_choice" in question_types:
            candidates.append(
                _multiple_choice_from_card(record, card, cards, sections, segment_lookup, rng)
            )
        if "written" in question_types:
            candidates.append(_written_from_card(record, card, segment_lookup))
    return candidates


def _note_quiz_candidates(
    record: LectureRecord,
    sections: list[dict[str, object]],
    segment_lookup,
    question_types: list[str],
    rng: random.Random,
) -> list[dict[str, object]]:
    candidates = []
    for section in sections:
        if "multiple_choice" in question_types:
            candidates.append(
                _multiple_choice_from_section(record, section, sections, segment_lookup, rng)
            )
        if "written" in question_types:
            candidates.append(_written_from_section(record, section, segment_lookup))
    return candidates


def _multiple_choice_from_card(
    record: LectureRecord,
    card: dict[str, object],
    cards: list[dict[str, object]],
    sections: list[dict[str, object]],
    segment_lookup,
    rng: random.Random,
) -> dict[str, object]:
    source = _source_from_card(record, card, segment_lookup)
    correct = _card_answer_text(card)
    choices = _choice_payloads(correct, _card_distractors(card, cards, sections), rng)
    item = {
        "quiz_id": _quiz_id_from_card(record, card, "multiple_choice"),
        "question_type": "multiple_choice",
        "question": _card_multiple_choice_question(card),
        "choices": choices,
        "correct_answer": _correct_choice_id(choices),
        "expected_answer": correct,
        "rubric": [],
        "explanation": _card_explanation(card),
        "source": source,
        "source_card_ids": [_card_id(card)],
        "source_note_candidate_id": _source_note_candidate_id(record, card),
        "difficulty": str(card.get("difficulty") or "beginner"),
        "tags": _as_list(card.get("tags", [])),
        "input_origin": "ready_card",
    }
    return validate_quiz_item(item)


def _written_from_card(
    record: LectureRecord,
    card: dict[str, object],
    segment_lookup: dict[str, TranscriptSegment],
) -> dict[str, object]:
    source = _source_from_card(record, card, segment_lookup)
    item = {
        "quiz_id": _quiz_id_from_card(record, card, "written"),
        "question_type": "written",
        "question": _card_written_question(card),
        "choices": [],
        "correct_answer": "",
        "expected_answer": _card_answer_text(card),
        "rubric": [
            "answers the review point directly",
            "uses the approved note context",
            "does not add unsupported claims",
        ],
        "explanation": _card_explanation(card),
        "source": source,
        "source_card_ids": [_card_id(card)],
        "source_note_candidate_id": _source_note_candidate_id(record, card),
        "difficulty": str(card.get("difficulty") or "beginner"),
        "tags": _as_list(card.get("tags", [])),
        "input_origin": "ready_card",
    }
    return validate_quiz_item(item)


def _multiple_choice_from_section(
    record: LectureRecord,
    section: dict[str, object],
    sections: list[dict[str, object]],
    segment_lookup: dict[str, TranscriptSegment],
    rng: random.Random,
) -> dict[str, object]:
    source = _source_from_section(record, section, segment_lookup)
    correct = _section_answer_text(section)
    choices = _choice_payloads(correct, _section_distractors(section, sections), rng)
    item = {
        "quiz_id": _quiz_id_from_section(record, section, "multiple_choice"),
        "question_type": "multiple_choice",
        "question": f'Which statement best explains "{_section_title(section)}" in this lecture?',
        "choices": choices,
        "correct_answer": _correct_choice_id(choices),
        "expected_answer": correct,
        "rubric": [],
        "explanation": _section_explanation(section),
        "source": source,
        "source_card_ids": [],
        "source_note_candidate_id": str(record.approved_note.get("candidate_id") or ""),
        "difficulty": _section_difficulty(section),
        "tags": ["lecturedigest", "quiz", "source_approved_note"],
        "input_origin": "approved_note",
    }
    return validate_quiz_item(item)


def _written_from_section(
    record: LectureRecord,
    section: dict[str, object],
    segment_lookup: dict[str, TranscriptSegment],
) -> dict[str, object]:
    source = _source_from_section(record, section, segment_lookup)
    item = {
        "quiz_id": _quiz_id_from_section(record, section, "written"),
        "question_type": "written",
        "question": f'How would you explain "{_section_title(section)}" using the lecture context?',
        "choices": [],
        "correct_answer": "",
        "expected_answer": _section_answer_text(section),
        "rubric": [
            "mentions the core concept",
            "uses the approved note context",
            "does not add unsupported claims",
        ],
        "explanation": _section_explanation(section),
        "source": source,
        "source_card_ids": [],
        "source_note_candidate_id": str(record.approved_note.get("candidate_id") or ""),
        "difficulty": _section_difficulty(section),
        "tags": ["lecturedigest", "quiz", "source_approved_note"],
        "input_origin": "approved_note",
    }
    return validate_quiz_item(item)


def _source_from_card(
    record: LectureRecord,
    card: dict[str, object],
    segment_lookup: dict[str, TranscriptSegment],
) -> dict[str, object]:
    source = card.get("source", {})
    source_dict = source if isinstance(source, dict) else {}
    segment_ids = [
        str(value)
        for value in _as_list(card.get("source_segment_ids") or source_dict.get("segment_ids", []))
    ]
    mapped_segments = [segment_lookup[item] for item in segment_ids if item in segment_lookup]
    start_ts = str(card.get("start_ts") or source_dict.get("start_ts") or "")
    end_ts = str(card.get("end_ts") or source_dict.get("end_ts") or "")
    if mapped_segments:
        start_ts = start_ts or mapped_segments[0].start_ts
        end_ts = end_ts or mapped_segments[-1].end_ts
    return {
        "lecture_id": record.lecture_id,
        "lecture_title": record.lecture_title or record.title,
        "title": record.title,
        "chapter": str(source_dict.get("chapter") or "unassigned"),
        "segment_ids": segment_ids,
        "start_ts": start_ts,
        "end_ts": end_ts,
        "jump_link": str(card.get("jump_link") or source_dict.get("jump_link") or _jump_link(record, start_ts)),
        "mapping_status": "mapped" if segment_ids and start_ts else "flagged",
    }


def _source_from_section(
    record: LectureRecord,
    section: dict[str, object],
    segment_lookup: dict[str, TranscriptSegment],
) -> dict[str, object]:
    segment_ids = [str(value) for value in _as_list(section.get("segment_ids", []))]
    mapped_segments = [segment_lookup[item] for item in segment_ids if item in segment_lookup]
    start_ts = str(section.get("start_ts") or "")
    end_ts = str(section.get("end_ts") or "")
    if mapped_segments:
        start_ts = start_ts or mapped_segments[0].start_ts
        end_ts = end_ts or mapped_segments[-1].end_ts
    return {
        "lecture_id": record.lecture_id,
        "lecture_title": record.lecture_title or record.title,
        "title": record.title,
        "chapter": str(section.get("chapter") or "unassigned"),
        "segment_ids": segment_ids,
        "start_ts": start_ts,
        "end_ts": end_ts,
        "jump_link": _jump_link(record, start_ts),
        "mapping_status": "mapped" if segment_ids and start_ts else "flagged",
    }


def _choice_payloads(
    correct: str,
    distractors: list[str],
    rng: random.Random,
) -> list[dict[str, object]]:
    texts = [correct, *_unique_distractors(correct, distractors)]
    while len(texts) < 4:
        texts.append(f"This option is not supported by the approved note ({len(texts) + 1}).")
    texts = texts[:4]
    rng.shuffle(texts)
    labels = ["A", "B", "C", "D"]
    return [
        {
            "id": label,
            "text": text,
            "is_correct": text == correct,
        }
        for label, text in zip(labels, texts)
    ]


def _card_distractors(
    card: dict[str, object],
    cards: list[dict[str, object]],
    sections: list[dict[str, object]],
) -> list[str]:
    card_id = _card_id(card)
    candidates = [_card_answer_text(other) for other in cards if _card_id(other) != card_id]
    candidates.extend(_section_answer_text(section) for section in sections)
    candidates.extend(_generic_distractors())
    return candidates


def _section_distractors(
    section: dict[str, object],
    sections: list[dict[str, object]],
) -> list[str]:
    section_id = _section_id(section)
    candidates = [
        _section_answer_text(other)
        for other in sections
        if _section_id(other) != section_id
    ]
    candidates.extend(_generic_distractors())
    return candidates


def _unique_distractors(correct: str, candidates: list[str]) -> list[str]:
    result = []
    normalized_correct = _normalize_for_match(correct)
    for candidate in candidates:
        text = _snippet(str(candidate or ""), 260)
        if not text or _normalize_for_match(text) == normalized_correct or text in result:
            continue
        result.append(text)
        if len(result) == 3:
            break
    return result


def _generic_distractors() -> list[str]:
    return [
        "The lecture does not provide enough evidence for this choice.",
        "This choice is unrelated to the approved note.",
        "This choice repeats a label without explaining the learning point.",
    ]


def _card_multiple_choice_question(card: dict[str, object]) -> str:
    if str(card.get("card_type") or "") == "cloze":
        return f"Which option best fills the blank: {_blank_cloze(_card_front(card))}"
    front = _card_front(card)
    if front.endswith("?"):
        return f"Which answer best responds to this review prompt: {front}"
    return f"Which statement best matches this review point: {front}"


def _card_written_question(card: dict[str, object]) -> str:
    if str(card.get("card_type") or "") == "cloze":
        return f"Explain the concept represented by the blank: {_blank_cloze(_card_front(card))}"
    front = _card_front(card)
    if front.endswith("?"):
        return f"Answer this review prompt in your own words: {front}"
    return f"Explain this review point in your own words: {front}"


def _card_answer_text(card: dict[str, object]) -> str:
    if str(card.get("card_type") or "") == "cloze":
        hidden = _cloze_answer(_card_front(card))
        if hidden:
            return hidden
    return _snippet(str(card.get("back") or card.get("extra") or ""), 260)


def _card_explanation(card: dict[str, object]) -> str:
    text = str(card.get("back") or card.get("cloze_text") or card.get("front") or "")
    text = SOURCE_ARTIFACT_PATTERN.sub("", text)
    return _snippet(text, 320)


def _section_answer_text(section: dict[str, object]) -> str:
    text = _section_text(section)
    first_sentence = _first_sentence(text)
    return _snippet(first_sentence or text or _section_title(section), 260)


def _section_explanation(section: dict[str, object]) -> str:
    return _snippet(_section_text(section), 320)


def _correct_choice_id(choices: list[dict[str, object]]) -> str:
    for choice in choices:
        if choice["is_correct"]:
            return str(choice["id"])
    return ""


def _quiz_id_from_card(record: LectureRecord, card: dict[str, object], question_type: str) -> str:
    safe_card = re.sub(r"[^0-9A-Za-z_-]+", "-", _card_id(card)).strip("-")
    return f"{record.lecture_id}:card:{safe_card}:{question_type}"


def _quiz_id_from_section(
    record: LectureRecord,
    section: dict[str, object],
    question_type: str,
) -> str:
    safe_section = re.sub(r"[^0-9A-Za-z_-]+", "-", _section_id(section)).strip("-")
    return f"{record.lecture_id}:note:{safe_section}:{question_type}"


def _card_id(card: dict[str, object]) -> str:
    return str(card.get("card_id") or "card")


def _card_front(card: dict[str, object]) -> str:
    text = str(card.get("cloze_text") or card.get("front") or "")
    return SOURCE_ARTIFACT_PATTERN.sub("", text).strip()


def _source_note_candidate_id(record: LectureRecord, card: dict[str, object]) -> str:
    return str(
        card.get("source_note_candidate_id")
        or record.approved_note.get("candidate_id")
        or ""
    )


def _section_id(section: dict[str, object]) -> str:
    return str(section.get("note_section_id") or section.get("section_key") or "section")


def _section_title(section: dict[str, object]) -> str:
    return str(section.get("title") or section.get("section_key") or "note section")


def _section_text(section: dict[str, object]) -> str:
    return str(section.get("text") or section.get("body") or "").strip()


def _section_difficulty(section: dict[str, object]) -> str:
    text = f"{_section_title(section)} {_section_text(section)}".lower()
    if any(marker in text for marker in ("advanced", "architecture", "internal")):
        return "advanced"
    if any(marker in text for marker in ("engine", "api", "dom", "interpreter")):
        return "intermediate"
    return "beginner"


def _first_sentence(text: str) -> str:
    for part in re.split(r"(?<=[.!?])\s+", text):
        cleaned = part.strip(" -")
        if cleaned:
            return cleaned
    return ""


def _cloze_answer(text: str) -> str:
    match = CLOZE_PATTERN.search(text)
    if not match:
        return ""
    return match.group(1).strip()


def _blank_cloze(text: str) -> str:
    return CLOZE_PATTERN.sub("____", text)


def _jump_link(record: LectureRecord, start_ts: str) -> str:
    seconds = 0
    if start_ts:
        parts = start_ts.replace(",", ".").split(":")
        if len(parts) == 3:
            try:
                seconds = int(parts[0]) * 3600 + int(parts[1]) * 60 + round(float(parts[2]))
            except ValueError:
                seconds = 0
    return f"lecturedigest://lecture/{record.lecture_id}?t={seconds}"


def _snippet(text: str, max_chars: int) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= max_chars:
        return compact
    trimmed = compact[: max_chars + 1].rsplit(" ", maxsplit=1)[0]
    return f"{trimmed or compact[:max_chars]}..."


def _normalize_for_match(value: object) -> str:
    return " ".join(re.findall(r"[0-9A-Za-z\uac00-\ud7a3]+", str(value).lower()))


def _as_list(value: object) -> list[object]:
    if not isinstance(value, list):
        return []
    return value
