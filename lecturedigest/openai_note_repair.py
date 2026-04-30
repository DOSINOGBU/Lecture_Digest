from __future__ import annotations

import json

from lecturedigest.models import LectureRecord
from lecturedigest.note_markdown import NoteSourceUnit
from lecturedigest.note_profile import NoteContentProfile, build_content_profile
from lecturedigest.openai_client import json_body
from lecturedigest.openai_note_prompt import (
    DEFAULT_OPENAI_NOTE_MODEL,
    DEFAULT_OPENAI_NOTE_PROMPT_VERSION,
    NOTE_STAGE,
    NOTE_VARIANTS,
    OPENAI_NOTE_ENDPOINT,
    _max_output_tokens,
    _source_chunks,
)
from lecturedigest.openai_types import OpenAIRequest

OPENAI_NOTE_REPAIR_USE_CASE = "note_generation_repair"
OPENAI_NOTE_REPAIR_PROMPT = """You repair one LectureDigest Korean Markdown note candidate.
Use only the supplied source chunks and the original candidate.
Fix the validation failures without inventing unsupported facts.
Keep valid source citations and add source_segment_ids for every section.
Every citation must use the literal format `(source: seg-000001..seg-000010 @ 00:00:00.000-00:01:00.000)`.
If a requested diagram, table, or code block is not supported by the source, explain that in notes instead of fabricating it.
Return JSON only. Do not wrap the JSON in Markdown fences."""


def build_note_repair_request(
    record: LectureRecord,
    *,
    source_units: list[NoteSourceUnit],
    candidate: dict[str, object],
    tone: str,
    model: str = DEFAULT_OPENAI_NOTE_MODEL,
    prompt_version: str = DEFAULT_OPENAI_NOTE_PROMPT_VERSION,
    variant: str | None = None,
    content_profile: NoteContentProfile | None = None,
) -> OpenAIRequest:
    profile = content_profile or build_content_profile(source_units, chunks=record.chunks)
    prompt_payload = _repair_contract(
        record,
        source_units,
        candidate=candidate,
        tone=tone,
        content_profile=profile,
        variant=variant,
    )
    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": OPENAI_NOTE_REPAIR_PROMPT}],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": json.dumps(prompt_payload, ensure_ascii=False),
                    }
                ],
            },
        ],
        "text": {"format": {"type": "json_object"}},
        "max_output_tokens": _max_output_tokens(profile),
    }
    body = json_body(payload)
    return OpenAIRequest(
        endpoint=OPENAI_NOTE_ENDPOINT,
        use_case=OPENAI_NOTE_REPAIR_USE_CASE,
        model=model,
        prompt_version=f"{prompt_version}+repair-v1",
        body=body,
        input_size_bytes=len(body),
        external_data_boundary="lecture transcript chunks and note draft to OpenAI Responses API",
    )


def _repair_contract(
    record: LectureRecord,
    units: list[NoteSourceUnit],
    *,
    candidate: dict[str, object],
    tone: str,
    content_profile: NoteContentProfile,
    variant: str | None,
) -> dict[str, object]:
    validation = _dict(candidate.get("validation"))
    requested_variant = variant or str(candidate.get("variant") or NOTE_VARIANTS[0])
    return {
        "contract": {
            "language": "ko",
            "tone": tone,
            "candidate_count": 1,
            "variant": requested_variant,
            "content_profile": content_profile.to_dict(),
            "repair_targets": _repair_targets(validation),
            "hard_requirements": [
                "Return exactly one candidate in candidates.",
                "Keep the same variant unless the requested variant is invalid.",
                "Preserve the PRD section order.",
                "For standard notes, include at least 3 distinct core topic sections when source evidence supports them.",
                "For standard notes, include at least 8 review questions when source evidence supports them.",
                "For standard notes, include at least 8 key terms when source evidence supports them.",
                "Every section must include source_segment_ids from the supplied source chunks.",
                "Every paragraph, bullet, table row, question, diagram, or code block must include a literal `(source:` citation.",
                "Do not use Korean source labels such as `출처:`; use `(source:` exactly.",
                "Do not add facts, examples, commands, or code that are not supported by the source.",
            ],
            "citation_format": (
                "(source: seg-000001..seg-000010 @ "
                "00:00:00.000-00:01:00.000)"
            ),
            "response_shape": {
                "candidates": [
                    {
                        "variant": requested_variant,
                        "sections": [
                            {
                                "section_key": "one_line_summary",
                                "title": "## lecture one-line summary",
                                "text": "Repaired source-backed Markdown body.",
                                "source_segment_ids": ["seg-000001"],
                            }
                        ],
                        "notes": {
                            "repair_summary": "What was changed and why.",
                            "code_not_evident": False,
                            "flow_not_evident": False,
                        },
                    }
                ]
            },
        },
        "lecture": {
            "lecture_id": record.lecture_id,
            "title": record.title,
            "category": record.category,
            "transcript_source": record.transcript_source,
        },
        "initial_candidate": _candidate_payload(candidate),
        "source_chunks": _source_chunks(record, units),
    }


def _repair_targets(validation: dict[str, object]) -> dict[str, object]:
    failed_rules = _string_list(validation.get("failed_rules"))
    warnings = _string_list(validation.get("warnings"))
    quality_flags = _string_list(validation.get("quality_flags"))
    return {
        "failed_rules": failed_rules,
        "warnings": warnings,
        "quality_flags": quality_flags,
        "content_counts": _dict(validation.get("content_counts")),
        "instructions": _repair_instructions(failed_rules, warnings, quality_flags),
    }


def _repair_instructions(
    failed_rules: list[str],
    warnings: list[str],
    quality_flags: list[str],
) -> list[str]:
    flags = set(failed_rules + warnings + quality_flags)
    instructions = []
    if "insufficient_core_topics" in flags:
        instructions.append(
            "Add distinct topic_N sections backed by different source ranges."
        )
    if "insufficient_review_questions" in flags:
        instructions.append(
            "Expand review_questions with mixed recall and explanation questions."
        )
    if "insufficient_key_terms" in flags:
        instructions.append("Expand key_terms with source-backed terms only.")
    if "insufficient_learning_goals" in flags:
        instructions.append("Add measurable learning goals supported by the source.")
    if "missing_flow_diagram" in flags:
        instructions.append(
            "Add a ```text flow diagram only if the source shows a process."
        )
    if "missing_comparison_table" in flags:
        instructions.append(
            "Add a Markdown comparison table only if the source supports it."
        )
    if "missing_code_block" in flags:
        instructions.append(
            "Add a code block only if actual code or commands are evident."
        )
    if not instructions:
        instructions.append("Repair any validation failure visible in the report.")
    return instructions


def _candidate_payload(candidate: dict[str, object]) -> dict[str, object]:
    return {
        "candidate_id": candidate.get("candidate_id"),
        "variant": candidate.get("variant"),
        "validation": _dict(candidate.get("validation")),
        "sections": candidate.get("sections", []),
        "markdown_excerpt": str(candidate.get("markdown") or "")[:12000],
    }


def _dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


__all__ = [
    "OPENAI_NOTE_REPAIR_USE_CASE",
    "build_note_repair_request",
]
