from __future__ import annotations

import json

from lecturedigest.models import LectureRecord
from lecturedigest.note_depth import body_depth_policy
from lecturedigest.note_markdown import NoteSourceUnit
from lecturedigest.note_profile import NoteContentProfile, build_content_profile
from lecturedigest.note_prd import FIXED_SECTION_TITLES
from lecturedigest.openai_client import json_body
from lecturedigest.openai_types import OpenAIRequest

OPENAI_NOTE_ENDPOINT = "/v1/responses"
OPENAI_NOTE_USE_CASE = "note_generation"
DEFAULT_OPENAI_NOTE_MODEL = "gpt-4.1"
DEFAULT_OPENAI_NOTE_PROMPT_VERSION = "openai-markdown-note-prd-v6"
OPENAI_NOTE_CANDIDATE_COUNT = 3
NOTE_STAGE = "note_generation"
EXAMPLE_SEGMENT_IDS = ["seg-000001", "seg-000038"]
REQUIRED_NOTE_SECTIONS = tuple(FIXED_SECTION_TITLES.items())
NOTE_VARIANTS = ("balanced", "concept_focused", "action_focused")

OPENAI_NOTE_PROMPT = """You are LectureDigest's expert learning-note writer.
Write high-quality Korean Markdown study notes from the provided lecture chunks only.
Do not produce a brief summary when the source is large enough for a full study note.
For standard, expanded, and chaptered sources, a short outline-like answer is invalid.
Do not add facts that are not supported by the source chunks.
Do not write visible source citations, segment IDs, or timestamps in any rendered Markdown text.
Keep traceability only in each section's source_segment_ids metadata.
The first rendered Markdown line must be the lecture title as an H1.
Follow the Lecture Note PRD structure: one-line summary, learning goals, numbered core topics, practical takeaways, key terms, review questions, and final summary.
Use compact notes for short sources without inventing missing concepts. Use expanded or chaptered structure for long sources.
For standard or longer notes, write textbook-style body sections with explanations, importance, lecture-flow context, examples, tables, lists, and cautions where supported.
Do not reuse a fixed `Concept / Why It Matters / Lecture Flow / Example` template across topics.
Choose each topic's format naturally from the evidence: narrative paragraphs, bullets, tables, flow diagrams, comparisons, examples, checklists, or code blocks.
When a concept is hard for a beginner, add a natural easy explanation inside the relevant body section.
Easy explanations may use simple analogies, but they must not introduce new unsupported facts.
When a known acronym appears, explain its expanded form and beginner meaning at first useful mention.
Do not invent expanded forms for unknown acronyms; explain only the role visible in the lecture context.
Preserve technical terms, code terms, URLs, browser/API names, and English keywords exactly when important.
Return JSON only. Do not wrap the JSON in Markdown fences."""


def build_note_request(
    record: LectureRecord,
    *,
    source_units: list[NoteSourceUnit],
    tone: str,
    model: str = DEFAULT_OPENAI_NOTE_MODEL,
    prompt_version: str = DEFAULT_OPENAI_NOTE_PROMPT_VERSION,
    variant: str | None = None,
) -> OpenAIRequest:
    content_profile = build_content_profile(source_units, chunks=record.chunks)
    prompt_payload = _prompt_contract(
        record,
        source_units,
        tone,
        content_profile=content_profile,
        variant=variant,
    )
    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": OPENAI_NOTE_PROMPT}],
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
        "max_output_tokens": _max_output_tokens(content_profile),
    }
    body = json_body(payload)
    return OpenAIRequest(
        endpoint=OPENAI_NOTE_ENDPOINT,
        use_case=OPENAI_NOTE_USE_CASE,
        model=model,
        prompt_version=prompt_version,
        body=body,
        input_size_bytes=len(body),
        external_data_boundary="lecture transcript chunks to OpenAI Responses API",
    )


def _prompt_contract(
    record: LectureRecord,
    units: list[NoteSourceUnit],
    tone: str,
    *,
    content_profile: NoteContentProfile,
    variant: str | None = None,
) -> dict[str, object]:
    variants = [variant] if variant else list(NOTE_VARIANTS)
    return {
        "contract": {
            "language": "ko",
            "tone": tone,
            "candidate_count": len(variants),
            "variants": variants,
            "content_profile": content_profile.to_dict(),
            "body_depth_policy": body_depth_policy(content_profile),
            "required_markdown_order": [
                "# 강의 제목",
                "## 강의 한 줄 요약",
                "## 학습 목표",
                "## 1. 첫 번째 핵심 주제",
                "## 2. 두 번째 핵심 주제",
                "## 실무 관점에서 기억할 것",
                "## 핵심 용어 정리",
                "## 복습 질문",
                "## 최종 정리",
            ],
            "section_keys": {
                "one_line_summary": "1-3 supported sentences",
                "learning_goals": "measurable bullet goals",
                "topic_N": "numbered core topic sections with 3 or more ### subsections",
                "practical_takeaways": "practice or work-context takeaways",
                "key_terms": "Markdown table of source-backed terms",
                "review_questions": "numbered self-check questions",
                "final_summary": "2-4 paragraphs when enough source exists",
            },
            "adaptive_policy": _adaptive_policy(content_profile),
            "difficulty_explanation_policy": _difficulty_explanation_policy(),
            "hard_requirements": [
                "Return exactly one candidate for the requested variant.",
                "The candidate must include one_line_summary, learning_goals, at least one topic_N section, practical_takeaways, key_terms, review_questions, and final_summary.",
                "Do not omit source_segment_ids for any section.",
                "Do not include `(source:`, `seg-000001`, `@ 00:00:00.000`, or any visible timestamp citation in text/title fields.",
                "Do not invent goals, terms, examples, tables, code, or diagrams just to satisfy counts.",
                "If the source is too short for PRD minimums, keep the compact note concise and set source_insufficient_for_full_note in notes.",
                "The note will be rejected if it is shorter than body_depth_policy.min_document_chars.",
                "The note will be rejected if topic_N average body length is below body_depth_policy.min_topic_avg_chars.",
                "The note will be rejected if generic headings such as `### Concept`, `### Why It Matters`, `### Lecture Flow`, or `### Example` appear.",
                "The note will be rejected if topic sections repeat the same internal heading template.",
                "Use body_depth_policy.target_document_chars and topic_count_range for adaptive length instead of a fixed character target.",
                "For tiny or compact notes, stay concise and do not force tables, diagrams, or extra topics.",
                "For standard notes, write enough body detail to match the supplied reference note density when source evidence supports it.",
                "For expanded notes, use many numbered topic_N sections and H3 subsections rather than one huge section.",
                "For chaptered notes, do not compress the entire lecture into a single short note; produce chapter-level sections plus a master summary.",
                "Under each natural subsection, write supported paragraphs, not a single sentence.",
                "Make practical_takeaways and final_summary substantial sections, not short bullet-only summaries.",
                "Each topic_N should use the most suitable format for its content: narrative, bullet list, table, flow diagram, comparison, checklist, example, or code block.",
                "Detect difficult concepts such as jargon, English acronyms, abstract terms, tools, and concepts that require prerequisite knowledge.",
                "For difficult concepts, include a beginner-friendly explanation in the relevant topic body using natural Korean.",
                "For known acronyms, include expanded_form and an easy beginner meaning in notes.difficulty_explanations.",
                "For unknown acronyms, do not guess the full name; set expansion_known=false and leave expanded_form empty.",
                "When adding an easy explanation, use a clear beginner cue such as `쉽게 말하면`, `쉽게 풀이`, or `초보자를 위한 TIP` at least once.",
                "Do not force an easy explanation into every topic; use it only where it helps understanding.",
                "Do not repeat the same `쉽게 말하면` pattern mechanically across many topics.",
                "Record each difficult concept explanation in notes.difficulty_explanations with term, reason, difficulty, expanded_form, expansion_known, plain_explanation, source_segment_ids, and analogy_used.",
                "Easy analogies are allowed only as intuition aids; do not add unsupported facts or external claims.",
            ],
            "style_reference_metrics": {
                "standard_reference_chars": 7858,
                "standard_reference_lines": 343,
                "standard_reference_h2": 17,
                "standard_reference_h3": 5,
                "standard_reference_code_blocks": 4,
                "note": "Use these as density guidance, not as source facts.",
            },
            "source_mapping_policy": {
                "visible_citations": False,
                "source_segment_ids_required": True,
                "timestamps_in_markdown": False,
                "source_panel_future_ui": True,
            },
            "response_shape": {
                "candidates": [
                    {
                        "variant": variants[0],
                        "sections": _example_sections(),
                        "notes": {
                            "source_insufficient_for_full_note": (
                                content_profile.source_insufficient_for_full_note
                            ),
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
                                    "source_segment_ids": EXAMPLE_SEGMENT_IDS,
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
        "source_chunks": _source_chunks(record, units),
    }


def _adaptive_policy(content_profile: NoteContentProfile) -> dict[str, object]:
    return {
        "strategy": content_profile.strategy,
        "target_counts": content_profile.to_dict()["target_counts"],
        "body_depth_policy": body_depth_policy(content_profile),
        "tiny_rule": "For under 300 estimated tokens, produce a short but useful note and avoid forced expansion.",
        "compact_rule": "For 300-700 estimated tokens, preserve PRD order but do not fabricate missing items.",
        "short_rule": "For 700-1800 estimated tokens, cover 3-5 source-backed core topics when supported.",
        "standard_rule": "For 1800-4500 estimated tokens, produce a dense study-note body, not a brief summary.",
        "expanded_rule": "For 4500-12000 estimated tokens, use many numbered topics and natural H3 subsections.",
        "chaptered_rule": "For very long sources or many topic shifts, produce chapter-level sections and a master summary.",
        "style_rule": "Do not repeat a fixed topic template; choose forms that fit each topic.",
    }


def _difficulty_explanation_policy() -> dict[str, object]:
    return {
        "placement": "inside_relevant_markdown_body",
        "reader_level": "beginner_across_any_domain",
        "detect": [
            "domain jargon",
            "English acronyms",
            "abstract concepts",
            "tools or named technologies",
            "concepts that require prerequisite knowledge",
        ],
        "allowed_forms": [
            "plain Korean explanation",
            "short analogy",
            "step-by-step breakdown",
            "small table or example when supported",
        ],
        "external_knowledge": "limited to intuition aids; no unsupported factual claims",
        "acronym_policy": {
            "known_acronyms": {
                "HTML": "HyperText Markup Language",
                "CSS": "Cascading Style Sheets",
                "JS": "JavaScript",
                "DOM": "Document Object Model",
                "API": "Application Programming Interface",
                "UI": "User Interface",
                "URL": "Uniform Resource Locator",
                "HTTP": "Hypertext Transfer Protocol",
                "JSON": "JavaScript Object Notation",
                "OCR": "Optical Character Recognition",
                "STT": "Speech To Text",
                "RAG": "Retrieval-Augmented Generation",
                "LLM": "Large Language Model",
                "CLI": "Command Line Interface",
            },
            "unknown_acronyms": "Do not invent expanded forms; explain only the role supported by source context.",
        },
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
    }


def _max_output_tokens(content_profile: NoteContentProfile) -> int:
    if content_profile.strategy == "chaptered":
        return 16000
    if content_profile.strategy == "expanded":
        return 14000
    if content_profile.strategy == "standard":
        return 10000
    if content_profile.strategy == "short":
        return 8000
    return 6000


def _source_chunks(
    record: LectureRecord,
    units: list[NoteSourceUnit],
) -> list[dict[str, object]]:
    unit_by_id = {unit.segment_id: unit for unit in units}
    if record.chunks:
        chunks = []
        for chunk in record.chunks:
            segment_ids = [
                segment_id for segment_id in chunk.segment_ids if segment_id in unit_by_id
            ]
            if not segment_ids:
                continue
            chunks.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "chapter": chunk.chapter,
                    "start_ts": chunk.start_ts,
                    "end_ts": chunk.end_ts,
                    "segment_ids": [segment_ids[0], segment_ids[-1]],
                    "text": chunk.text,
                    "ocr_text": chunk.ocr_text or "",
                }
            )
        if chunks:
            return chunks

    grouped = []
    batch_size = 40
    for start in range(0, len(units), batch_size):
        batch = units[start : start + batch_size]
        grouped.append(
            {
                "chunk_id": f"segments-{start + 1:06d}",
                "chapter": record.middle_category or record.category or "unassigned",
                "start_ts": batch[0].start_ts,
                "end_ts": batch[-1].end_ts,
                "segment_ids": [batch[0].segment_id, batch[-1].segment_id],
                "text": " ".join(unit.text for unit in batch),
                "ocr_text": " ".join(unit.ocr_text or "" for unit in batch).strip(),
            }
        )
    return grouped


def _example_sections() -> list[dict[str, object]]:
    return [
        _example_section(
            "one_line_summary",
            "## 강의 한 줄 요약",
            "Markdown body for the section without visible source markers.",
        ),
        _example_section(
            "learning_goals",
            "## 학습 목표",
            "- 학습자가 설명할 수 있는 목표",
        ),
        _example_section(
            "topic_1",
            "## 1. 첫 번째 핵심 주제",
            _example_topic_text(),
        ),
        _example_section(
            "practical_takeaways",
            "## 실무 관점에서 기억할 것",
            "- 실무 연결 포인트",
        ),
        _example_section(
            "key_terms",
            "## 핵심 용어 정리",
            "| 용어 | 의미 |\n| --- | --- |\n| 용어 | 의미 |",
        ),
        _example_section(
            "review_questions",
            "## 복습 질문",
            "1. 무엇을 설명할 수 있는가?",
        ),
        _example_section(
            "final_summary",
            "## 최종 정리",
            "Final summary paragraph without visible source markers.",
        ),
    ]


def _example_section(section_key: str, title: str, text: str) -> dict[str, object]:
    return {
        "section_key": section_key,
        "title": title,
        "text": text,
        "source_segment_ids": EXAMPLE_SEGMENT_IDS,
    }


def _example_topic_text() -> str:
    return "\n\n".join(
        [
            (
                "이 주제는 강의 원문에서 확인되는 핵심 흐름을 설명한다.\n\n"
                "학습자가 개념을 실제 상황에 연결할 수 있도록 배경과 맥락을 함께 정리한다."
            ),
            (
                "- 핵심 포인트를 짧게 정리한다.\n"
                "- 강의에서 강조한 순서와 연결 관계를 유지한다.\n"
                "- 근거가 부족한 예시는 추가하지 않는다."
            ),
            (
                "| 관점 | 정리 |\n"
                "| --- | --- |\n"
                "| 개념 | 원문에서 확인되는 설명만 사용한다. |\n"
                "| 적용 | 복습 가능한 문장으로 바꾼다. |"
            ),
        ]
    )
