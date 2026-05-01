from __future__ import annotations

import json

from lecturedigest.models import LectureRecord
from lecturedigest.note_depth import body_depth_policy
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
If the note is too short or shallow, expand the existing source-backed topic bodies instead of padding with generic summary.
For standard, expanded, and chaptered sources, a short outline-like repaired answer is invalid.
Keep source traceability in source_segment_ids for every section.
Do not write visible source citations, segment IDs, or timestamps in any rendered Markdown text.
Do not reuse a fixed `Concept / Why It Matters / Lecture Flow / Example` template across topics.
When validation reports missing or weak easy explanations, repair only the relevant difficult concepts.
Easy explanations must be beginner-friendly, natural in the note body, and source-grounded.
Known acronyms must include expanded_form and a beginner meaning; unknown acronyms must not get invented full names.
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
            "body_depth_policy": body_depth_policy(content_profile),
            "repair_targets": _repair_targets(validation),
            "difficulty_explanation_policy": {
                "placement": "inside_relevant_markdown_body",
                "reader_level": "beginner_across_any_domain",
                "metadata_required": [
                    "term",
                    "reason",
                    "difficulty",
                    "expanded_form",
                    "expansion_known",
                    "plain_explanation",
                    "source_segment_ids",
                    "analogy_used",
                ],
                "external_knowledge": "limited to intuition aids; no unsupported factual claims",
            },
            "hard_requirements": [
                "Return exactly one candidate in candidates.",
                "Keep the same variant unless the requested variant is invalid.",
                "Preserve the PRD section order.",
                "For standard notes, include 5-10 distinct core topic sections when source evidence supports them.",
                "For standard notes, include at least 8 review questions when source evidence supports them.",
                "For standard notes, include at least 8 key terms when source evidence supports them.",
                "The repaired note will be rejected if it is shorter than body_depth_policy.min_document_chars.",
                "The repaired note will be rejected if topic_N average body length is below body_depth_policy.min_topic_avg_chars.",
                "Use body_depth_policy.target_document_chars and topic_count_range for adaptive length instead of a fixed character target.",
                "For tiny or compact notes, stay concise and do not force tables, diagrams, or extra topics.",
                "For standard notes, write enough body detail to match the supplied reference note density when source evidence supports it.",
                "For expanded notes, use many numbered topic_N sections and natural H3 subsections rather than one huge section.",
                "For chaptered notes, do not compress the entire lecture into a single short note; produce chapter-level sections plus a master summary.",
                "The repaired note will be rejected if generic headings such as `### Concept`, `### Why It Matters`, `### Lecture Flow`, or `### Example` appear.",
                "The repaired note will be rejected if topic sections repeat the same internal heading template.",
                "Under each topic_N ### heading, write 2-3 short source-backed paragraphs, not a single sentence.",
                "Make practical_takeaways and final_summary substantial sections, not short bullet-only summaries.",
                "When body_depth_gap is present, expand beyond that gap instead of making tiny edits.",
                "Do not delete existing useful source-backed content while repairing body depth.",
                "Every section must include source_segment_ids from the supplied source chunks.",
                "Do not include `(source:`, `seg-000001`, `@ 00:00:00.000`, or any visible timestamp citation in text/title fields.",
                "For difficult concepts, include beginner-friendly explanations in the relevant Markdown body.",
                "For known acronyms, include expanded_form and an easy beginner meaning in notes.difficulty_explanations.",
                "For unknown acronyms, do not guess the full name; set expansion_known=false and leave expanded_form empty.",
                "When adding an easy explanation, use a clear beginner cue such as `쉽게 말하면`, `쉽게 풀이`, or `초보자를 위한 TIP` at least once.",
                "Record repaired easy explanations in notes.difficulty_explanations.",
                "Do not repeat the same `쉽게 말하면` sentence structure mechanically across many topics.",
                "Do not add facts, examples, commands, or code that are not supported by the source.",
            ],
            "source_mapping_policy": {
                "visible_citations": False,
                "source_segment_ids_required": True,
                "timestamps_in_markdown": False,
                "source_panel_future_ui": True,
            },
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
                            },
                            {
                                "section_key": "topic_1",
                                "title": "## 1. repaired topic",
                                "text": _example_repair_topic_text(),
                                "source_segment_ids": ["seg-000001"],
                            }
                        ],
                        "notes": {
                            "repair_summary": "What was changed and why.",
                            "code_not_evident": False,
                            "flow_not_evident": False,
                            "difficulty_explanations": [
                                {
                                    "term": "DOM",
                                    "reason": "english_acronym",
                                    "difficulty": "high",
                                    "expanded_form": "Document Object Model",
                                    "expansion_known": True,
                                    "plain_explanation": (
                                        "쉽게 말하면, DOM은 브라우저가 HTML 문서를 "
                                        "다룰 수 있게 정리해 둔 구조입니다."
                                    ),
                                    "source_segment_ids": ["seg-000001"],
                                    "analogy_used": True,
                                }
                            ],
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
        "body_depth": _dict(validation.get("body_depth")),
        "body_depth_gap": _body_depth_gap(validation),
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
            "Add enough distinct topic_N sections to meet the strategy target count."
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
    if "body_too_short" in flags:
        instructions.append(
            "Expand the whole note by at least body_depth_gap.missing_document_chars plus a safety margin."
        )
    if "topic_body_too_shallow" in flags:
        instructions.append(
            "Expand shallow topic_N sections with definition, importance, flow context, and supported examples."
        )
    if "insufficient_subsections" in flags:
        instructions.append("Add supported ### subsections inside topic_N sections.")
    if "missing_explanatory_depth" in flags:
        instructions.append(
            "Add explanatory paragraphs instead of one-sentence topic summaries."
        )
    if "difficult_concept_explanation_missing" in flags:
        instructions.append(
            "Add source-backed beginner explanations for the detected difficult concepts and record them in notes.difficulty_explanations."
        )
    if "acronym_explanation_missing" in flags:
        instructions.append(
            "Add expanded_form, expansion_known, and beginner plain_explanation for known acronyms detected in the source."
        )
    if "unsupported_acronym_expansion" in flags:
        instructions.append(
            "Remove invented acronym expansions; keep expanded_form empty and expansion_known=false unless the acronym is in the known acronym policy."
        )
    if "easy_explanation_too_jargony" in flags:
        instructions.append(
            "Rewrite plain_explanation entries using everyday beginner language instead of more jargon."
        )
    if "unsupported_easy_explanation" in flags:
        instructions.append(
            "Remove unsupported factual claims and keep only source-grounded intuition or analogies."
        )
    if "easy_explanation_overused" in flags:
        instructions.append(
            "Vary the easy explanation style and avoid repeating the same marker in every topic."
        )
    if "visible_source_artifacts" in flags:
        instructions.append(
            "Remove visible source markers, segment IDs, and timestamps from all Markdown text while preserving source_segment_ids."
        )
    if "generic_subheading_present" in flags:
        instructions.append(
            "Replace generic English H3 headings with natural topic-specific headings or prose."
        )
    if "repetitive_topic_template" in flags:
        instructions.append(
            "Vary the internal structure of topic_N sections instead of repeating the same heading sequence."
        )
    if "insufficient_style_variety" in flags:
        instructions.append(
            "Use suitable mixed formats such as narrative, bullets, tables, comparisons, flow diagrams, examples, or checklists when supported."
        )
    if not instructions:
        instructions.append("Repair any validation failure visible in the report.")
    return instructions


def _body_depth_gap(validation: dict[str, object]) -> dict[str, object]:
    body_depth = _dict(validation.get("body_depth"))
    policy = _dict(body_depth.get("policy"))
    metrics = _dict(body_depth.get("metrics"))
    min_document = _number(policy.get("min_document_chars"))
    min_topic_avg = _number(policy.get("min_topic_avg_chars"))
    current_document = _number(metrics.get("markdown_chars"))
    current_topic_avg = _number(metrics.get("topic_avg_chars"))
    return {
        "missing_document_chars": max(0, min_document - current_document),
        "missing_topic_avg_chars": max(0, min_topic_avg - current_topic_avg),
        "current_document_chars": current_document,
        "current_topic_avg_chars": current_topic_avg,
    }


def _candidate_payload(candidate: dict[str, object]) -> dict[str, object]:
    return {
        "candidate_id": candidate.get("candidate_id"),
        "variant": candidate.get("variant"),
        "validation": _dict(candidate.get("validation")),
        "sections": candidate.get("sections", []),
        "markdown_excerpt": str(candidate.get("markdown") or "")[:12000],
    }


def _example_repair_topic_text() -> str:
    return "\n\n".join(
        [
            (
                "이 주제는 원문에서 확인되는 설명을 바탕으로 학습자가 이해해야 할 흐름을 정리한다.\n\n"
                "부족했던 본문은 새로운 사실을 더하는 방식이 아니라, 이미 제공된 근거를 더 자세히 풀어 쓰는 방식으로 보강한다."
            ),
            (
                "- 핵심 개념을 먼저 설명한다.\n"
                "- 강의 흐름에서 어디에 위치하는지 연결한다.\n"
                "- 복습할 때 확인해야 할 포인트를 분리한다."
            ),
            (
                "| 보강 대상 | 처리 방식 |\n"
                "| --- | --- |\n"
                "| 얕은 설명 | 원문 근거 안에서 문맥과 이유를 확장 |\n"
                "| 반복 템플릿 | 주제에 맞는 서술, 목록, 표를 선택 |"
            ),
        ]
    )


def _dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _number(value: object) -> int:
    return int(value) if isinstance(value, (int, float)) else 0


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


__all__ = [
    "OPENAI_NOTE_REPAIR_USE_CASE",
    "build_note_repair_request",
]
