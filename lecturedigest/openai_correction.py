from __future__ import annotations

import json
from dataclasses import dataclass

from lecturedigest.correction import (
    DEFAULT_CORRECTION_CONFIDENCE_THRESHOLD,
    DEFAULT_CORRECTION_MODEL,
    DEFAULT_CORRECTION_PROMPT_VERSION,
    DEFAULT_CORRECTION_REVIEW_THRESHOLD,
    finalize_transcript_payload,
    protected_terms_for_text,
)
from lecturedigest.errors import CorrectionError, ErrorDetail, ValidationError
from lecturedigest.models import LectureRecord, TranscriptSegment
from lecturedigest.openai_client import OpenAIClient, json_body
from lecturedigest.openai_types import OpenAIClientResult, OpenAIRequest

OPENAI_CORRECTION_ENDPOINT = "/v1/responses"
OPENAI_CORRECTION_USE_CASE = "transcript_correction"
DEFAULT_CORRECTION_BATCH_SIZE = 8
CORRECTION_STAGE = "correction"

CORRECTION_PROMPT = (
    "You correct lecture transcript segments conservatively. Fix obvious spacing, "
    "typos, STT/subtitle errors, and context mistakes only when the lecture meaning "
    "is preserved. Do not rewrite style, add new facts, or change protected terms, "
    "code, URLs, file paths, numbers, APIs, or product names. Return JSON only with "
    "a corrections array. Each item must include segment_id, corrected_text, "
    "confidence from 0 to 1, and reason."
)


@dataclass(frozen=True)
class OpenAITranscriptCorrectionResult:
    record: LectureRecord
    correction_payload: dict[str, object]
    client_results: list[OpenAIClientResult]
    dry_run: bool = False

    @property
    def failed_request_count(self) -> int:
        return sum(1 for result in self.client_results if not result.succeeded)


def correct_transcript_with_openai(
    record: LectureRecord,
    *,
    client: OpenAIClient | None = None,
    model: str = DEFAULT_CORRECTION_MODEL,
    prompt_version: str = DEFAULT_CORRECTION_PROMPT_VERSION,
    batch_size: int = DEFAULT_CORRECTION_BATCH_SIZE,
    confidence_threshold: float = DEFAULT_CORRECTION_CONFIDENCE_THRESHOLD,
    review_threshold: float = DEFAULT_CORRECTION_REVIEW_THRESHOLD,
    dry_run: bool = False,
) -> OpenAITranscriptCorrectionResult:
    _validate_correction_request(record, batch_size)
    openai_client = client or OpenAIClient()
    client_results: list[OpenAIClientResult] = []
    corrections: list[dict[str, object]] = []

    for batch_index, batch in enumerate(_segment_batches(record.segments, batch_size), start=1):
        request = build_correction_request(
            record,
            batch,
            model=model,
            prompt_version=prompt_version,
            batch_index=batch_index,
        )
        result = openai_client.send(request, dry_run=dry_run)
        client_results.append(result)
        if dry_run:
            continue
        if not result.succeeded:
            corrections.extend(_failed_batch_corrections(batch, result))
            continue
        corrections.extend(parse_correction_response(result.body))

    payload = _correction_payload(
        corrections=corrections,
        client_results=client_results,
        model=model,
        prompt_version=prompt_version,
        segment_count=len(record.segments),
    )
    if dry_run:
        return OpenAITranscriptCorrectionResult(
            record=record,
            correction_payload=payload,
            client_results=client_results,
            dry_run=True,
        )
    updated = finalize_transcript_payload(
        record,
        correction_payload=payload,
        confidence_threshold=confidence_threshold,
        review_threshold=review_threshold,
    )
    return OpenAITranscriptCorrectionResult(
        record=updated,
        correction_payload=payload,
        client_results=client_results,
        dry_run=False,
    )


def build_correction_request(
    record: LectureRecord,
    segments: list[TranscriptSegment],
    *,
    model: str = DEFAULT_CORRECTION_MODEL,
    prompt_version: str = DEFAULT_CORRECTION_PROMPT_VERSION,
    batch_index: int = 1,
) -> OpenAIRequest:
    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": CORRECTION_PROMPT}],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": json.dumps(
                            _prompt_contract(record, segments, batch_index),
                            ensure_ascii=False,
                        ),
                    }
                ],
            },
        ],
        "text": {"format": {"type": "json_object"}},
    }
    body = json_body(payload)
    return OpenAIRequest(
        endpoint=OPENAI_CORRECTION_ENDPOINT,
        use_case=OPENAI_CORRECTION_USE_CASE,
        model=model,
        prompt_version=prompt_version,
        body=body,
        input_size_bytes=len(body),
        external_data_boundary="transcript segment text to OpenAI Responses API",
    )


def parse_correction_response(data: bytes | str) -> list[dict[str, object]]:
    payload = _decode_json_bytes(data)
    if "corrections" not in payload:
        response_text = _extract_response_text(payload)
        if response_text is None:
            raise _correction_error(
                "correction_response_malformed",
                "Correction response did not include a corrections array.",
                retryable=False,
            )
        payload = _decode_json_bytes(response_text)

    corrections = payload.get("corrections")
    if not isinstance(corrections, list):
        raise _correction_error(
            "correction_response_malformed",
            "Correction response `corrections` must be a list.",
            retryable=False,
        )
    normalized = [_normalize_correction_item(item) for item in corrections]
    if not normalized:
        raise _correction_error(
            "correction_response_empty",
            "Correction response did not contain any correction items.",
            retryable=False,
        )
    return normalized


def format_openai_correction_dry_run(
    result: OpenAITranscriptCorrectionResult,
) -> str:
    metadata = result.correction_payload["provider_metadata"]
    return (
        "[LectureCorrection] openai dry-run "
        f"{{ batches={len(result.client_results)}; "
        f"segments={metadata['segments_total']}; "
        f"model={metadata['model']}; "
        f"promptVersion={metadata['prompt_version']}; "
        "externalDataBoundary=transcript segment text to OpenAI Responses API; "
        "willUpload=false; willSave=false }}"
    )


def _prompt_contract(
    record: LectureRecord,
    segments: list[TranscriptSegment],
    batch_index: int,
) -> dict[str, object]:
    return {
        "contract": {
            "response_shape": {
                "corrections": [
                    {
                        "segment_id": "string",
                        "corrected_text": "string",
                        "confidence": "number 0..1",
                        "reason": "short string",
                    }
                ]
            },
            "apply_threshold": DEFAULT_CORRECTION_CONFIDENCE_THRESHOLD,
            "review_threshold": DEFAULT_CORRECTION_REVIEW_THRESHOLD,
            "protected_terms_policy": "preserve exactly",
        },
        "lecture": {
            "lecture_id": record.lecture_id,
            "title": record.title,
            "category": record.category,
            "transcript_source": record.transcript_source,
            "batch_index": batch_index,
        },
        "segments": [
            {
                "segment_id": segment.segment_id,
                "start_ts": segment.start_ts,
                "end_ts": segment.end_ts,
                "text": segment.text,
                "protected_terms": protected_terms_for_text(segment.text),
            }
            for segment in segments
        ],
    }


def _correction_payload(
    *,
    corrections: list[dict[str, object]],
    client_results: list[OpenAIClientResult],
    model: str,
    prompt_version: str,
    segment_count: int,
) -> dict[str, object]:
    succeeded = sum(1 for result in client_results if result.succeeded)
    total = len(client_results)
    status = "succeeded" if succeeded == total else "partial"
    if succeeded == 0 and total > 0:
        status = "failed"
    return {
        "provider_metadata": {
            "provider": "openai_responses",
            "endpoint": OPENAI_CORRECTION_ENDPOINT,
            "use_case": OPENAI_CORRECTION_USE_CASE,
            "model": model,
            "prompt_version": prompt_version,
            "status": status,
            "segments_total": segment_count,
            "corrections_total": len(corrections),
            "requests_total": total,
            "requests_succeeded": succeeded,
            "estimated_cost": "unknown",
            "openai_calls": [result.metadata.to_dict() for result in client_results],
        },
        "corrections": corrections,
    }


def _failed_batch_corrections(
    segments: list[TranscriptSegment],
    result: OpenAIClientResult,
) -> list[dict[str, object]]:
    return [
        {
            "segment_id": segment.segment_id,
            "corrected_text": "",
            "confidence": None,
            "reason": "OpenAI correction request failed.",
            "status": "failed",
            "original_error": result.error_message or "OpenAI request failed.",
            "retryable": result.metadata.retryable,
            "provider_metadata": {
                "openai_call": result.metadata.to_dict(),
                "error_code": result.error_code or "openai_request_failed",
            },
        }
        for segment in segments
    ]


def _normalize_correction_item(item: object) -> dict[str, object]:
    if not isinstance(item, dict):
        raise _correction_error(
            "correction_response_malformed",
            "Each correction item must be an object.",
            retryable=False,
        )
    segment_id = str(item.get("segment_id") or "").strip()
    if not segment_id:
        raise _correction_error(
            "correction_response_malformed",
            "Each correction item must include segment_id.",
            retryable=False,
        )
    corrected_text = item.get("corrected_text", item.get("text"))
    if corrected_text is None:
        raise _correction_error(
            "correction_response_malformed",
            "Each correction item must include corrected_text.",
            retryable=False,
        )
    normalized = {
        "segment_id": segment_id,
        "corrected_text": str(corrected_text),
        "confidence": _optional_float(item.get("confidence")),
        "reason": str(item.get("reason") or ""),
        "status": str(item.get("status") or "succeeded"),
    }
    metadata = item.get("provider_metadata")
    if isinstance(metadata, dict):
        normalized["provider_metadata"] = {str(key): value for key, value in metadata.items()}
    return normalized


def _decode_json_bytes(data: bytes | str) -> dict[str, object]:
    text = data.decode("utf-8", errors="replace") if isinstance(data, bytes) else data
    try:
        payload = json.loads(_strip_json_fence(text.strip()))
    except json.JSONDecodeError as exc:
        raise _correction_error(
            "correction_response_invalid_json",
            f"Correction response JSON could not be parsed: {exc.msg}",
            retryable=False,
        ) from exc
    if not isinstance(payload, dict):
        raise _correction_error(
            "correction_response_malformed",
            "Correction response must be a JSON object.",
            retryable=False,
        )
    return payload


def _extract_response_text(payload: dict[str, object]) -> str | None:
    output_text = payload.get("output_text")
    if isinstance(output_text, str):
        return output_text
    output = payload.get("output", [])
    if not isinstance(output, list):
        return None
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content", [])
        if not isinstance(content, list):
            continue
        for content_item in content:
            if not isinstance(content_item, dict):
                continue
            text = content_item.get("text", content_item.get("output_text"))
            if isinstance(text, str):
                return text
    return None


def _segment_batches(segments: list[TranscriptSegment], batch_size: int):
    for start in range(0, len(segments), batch_size):
        yield segments[start : start + batch_size]


def _validate_correction_request(record: LectureRecord, batch_size: int) -> None:
    if batch_size <= 0:
        raise ValidationError(
            ErrorDetail(
                code="correction_batch_size_invalid",
                message="Correction batch size must be at least 1.",
                stage=CORRECTION_STAGE,
                retryable=False,
            )
        )
    if record.segments:
        return
    raise CorrectionError(
        ErrorDetail(
            code="segments_required",
            message="Transcript segments are required before correction.",
            stage=CORRECTION_STAGE,
            retryable=False,
        )
    )


def _strip_json_fence(text: str) -> str:
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if len(lines) >= 3 and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return text


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _correction_error(
    code: str,
    message: str,
    *,
    retryable: bool,
) -> CorrectionError:
    return CorrectionError(
        ErrorDetail(
            code=code,
            message=message,
            stage=CORRECTION_STAGE,
            retryable=retryable,
        )
    )
