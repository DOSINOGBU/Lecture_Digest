from __future__ import annotations

import json

from lecturedigest.models import LectureRecord, TranscriptSegment
from lecturedigest.openai_client import json_body
from lecturedigest.openai_types import OpenAIRequest
from lecturedigest.quiz_policy import QuizGenerationPlan

OPENAI_QUIZ_ENDPOINT = "/v1/responses"
OPENAI_QUIZ_USE_CASE = "quiz_generation"
DEFAULT_OPENAI_QUIZ_MODEL = "gpt-4.1"
DEFAULT_OPENAI_QUIZ_PROMPT_VERSION = "openai-quiz-prd-v1"
QUIZ_STAGE = "quiz"

OPENAI_QUIZ_PROMPT = """You are LectureDigest's expert quiz writer.
Create quiz items from the approved study note and ready Anki cards only.
Return JSON only. Do not wrap the JSON in Markdown fences.

Hard requirements:
- Use only these question types: multiple_choice and written.
- multiple_choice must have exactly four choices and exactly one correct choice.
- written must include expected_answer and a grading rubric.
- One quiz item must test one learning point.
- Prefer ready cards as learning points, then use note sections to fill gaps.
- Do not create broad summary questions.
- Do not reveal the answer in the question text.
- Do not add facts unsupported by the approved note, ready cards, or source snippets.
- Preserve beginner-friendly explanations for acronyms and difficult concepts.
- Include source_segment_ids on every quiz item.
- Keep source labels, segment ids, and timestamps out of visible questions.
- Keep source_card_ids when the item is based on a card.

Response shape:
{"quizzes":[{"question_type":"multiple_choice","note_section_id":"...","source_card_ids":["card-1"],"question":"...","choices":[{"id":"A","text":"...","is_correct":true},{"id":"B","text":"...","is_correct":false},{"id":"C","text":"...","is_correct":false},{"id":"D","text":"...","is_correct":false}],"correct_answer":"A","expected_answer":"...","rubric":[],"explanation":"...","difficulty":"beginner","source_segment_ids":["seg-1"]}]}"""


def build_quiz_request(
    record: LectureRecord,
    *,
    sections: list[dict[str, object]],
    ready_cards: list[dict[str, object]],
    batch_id: str,
    question_types: list[str],
    plan: QuizGenerationPlan,
    seed: int | None = None,
    model: str = DEFAULT_OPENAI_QUIZ_MODEL,
    prompt_version: str = DEFAULT_OPENAI_QUIZ_PROMPT_VERSION,
) -> OpenAIRequest:
    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": OPENAI_QUIZ_PROMPT}],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": json.dumps(
                            _prompt_contract(
                                record,
                                sections,
                                ready_cards,
                                batch_id,
                                question_types,
                                plan,
                                seed,
                            ),
                            ensure_ascii=False,
                        ),
                    }
                ],
            },
        ],
        "text": {"format": {"type": "json_object"}},
        "max_output_tokens": _max_output_tokens(plan),
    }
    body = json_body(payload)
    return OpenAIRequest(
        endpoint=OPENAI_QUIZ_ENDPOINT,
        use_case=OPENAI_QUIZ_USE_CASE,
        model=model,
        prompt_version=prompt_version,
        body=body,
        input_size_bytes=len(body),
        external_data_boundary=(
            "approved note sections, ready cards, and source snippets "
            "to OpenAI Responses API"
        ),
    )


def _prompt_contract(
    record: LectureRecord,
    sections: list[dict[str, object]],
    ready_cards: list[dict[str, object]],
    batch_id: str,
    question_types: list[str],
    plan: QuizGenerationPlan,
    seed: int | None,
) -> dict[str, object]:
    return {
        "contract": {
            "language": "ko",
            "batch_id": batch_id,
            "allowed_question_types": question_types,
            "target_quiz_count_for_whole_note": plan.target_quiz_count,
            "adaptive_strategy": plan.strategy,
            "seed": seed,
            "source_note_candidate_id": record.approved_note.get("candidate_id", ""),
            "quality_rules": [
                "one_quiz_one_learning_point",
                "question_must_not_contain_answer",
                "question_must_not_contain_source_or_timestamp",
                "source_segment_ids_required",
                "source_card_ids_required_when_card_based",
                "no_unsupported_facts",
                "flag_or_omit_weak_questions",
            ],
        },
        "lecture": {
            "lecture_id": record.lecture_id,
            "title": record.title,
            "category": record.category,
        },
        "approved_note": {
            "candidate_id": record.approved_note.get("candidate_id", ""),
            "sections": [_section_payload(record, section) for section in sections],
        },
        "ready_cards": [_card_payload(card) for card in ready_cards],
    }


def _section_payload(
    record: LectureRecord,
    section: dict[str, object],
) -> dict[str, object]:
    source_ids = [str(item) for item in _as_list(section.get("segment_ids", []))]
    source_lookup = {segment.segment_id: segment for segment in record.segments}
    return {
        "note_section_id": str(section.get("note_section_id") or section.get("section_key") or ""),
        "section_key": str(section.get("section_key") or ""),
        "title": str(section.get("title") or ""),
        "text": str(section.get("text") or "")[:1800],
        "source_segment_ids": source_ids,
        "source_snippets": [
            _segment_payload(source_lookup[segment_id])
            for segment_id in source_ids
            if segment_id in source_lookup
        ],
    }


def _card_payload(card: dict[str, object]) -> dict[str, object]:
    return {
        "card_id": str(card.get("card_id") or ""),
        "note_section_id": str(card.get("note_section_id") or ""),
        "card_type": str(card.get("card_type") or ""),
        "front": str(card.get("front") or "")[:700],
        "back": str(card.get("back") or "")[:900],
        "cloze_text": str(card.get("cloze_text") or "")[:700],
        "difficulty": str(card.get("difficulty") or "beginner"),
        "source_segment_ids": [
            str(item) for item in _as_list(card.get("source_segment_ids", []))
        ],
    }


def _segment_payload(segment: TranscriptSegment) -> dict[str, object]:
    return {
        "segment_id": segment.segment_id,
        "start_ts": segment.start_ts,
        "end_ts": segment.end_ts,
        "text": segment.text[:500],
        "ocr_text": (segment.ocr_text or "")[:300],
    }


def _max_output_tokens(plan: QuizGenerationPlan) -> int:
    if plan.strategy in {"expanded", "chaptered"}:
        return 8000
    if plan.strategy == "standard":
        return 6000
    return 4000


def _as_list(value: object) -> list[object]:
    if not isinstance(value, list):
        return []
    return value
