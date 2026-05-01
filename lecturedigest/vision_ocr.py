from __future__ import annotations

import base64
import json
import mimetypes
from dataclasses import dataclass

from lecturedigest.errors import EnrichmentError, ErrorDetail, ValidationError
from lecturedigest.frame_extraction import FrameCandidate
from lecturedigest.openai_client import OpenAIClient, json_body
from lecturedigest.openai_types import OpenAIClientResult, OpenAIRequest

OPENAI_VISION_OCR_ENDPOINT = "/v1/responses"
OPENAI_VISION_OCR_USE_CASE = "vision_ocr"
DEFAULT_VISION_OCR_MODEL = "gpt-4o"
DEFAULT_VISION_OCR_PROMPT_VERSION = "vision-ocr-v1"
DEFAULT_VISION_DETAIL = "original"
SUPPORTED_VISION_DETAIL = {"auto", "high", "low", "original"}
VISION_OCR_STAGE = "enrichment"

VISION_OCR_PROMPT = (
    "Read visible lecture slide or code text from this frame. Return JSON only "
    "with raw_ocr_text, refined_ocr_text, and confidence. Preserve Korean and "
    "English technical terms. Use empty strings when no readable text exists."
)


@dataclass(frozen=True)
class VisionOcrRunResult:
    ocr_payload: dict[str, object]
    client_results: list[OpenAIClientResult]

    @property
    def succeeded_frames(self) -> int:
        frames = self.ocr_payload.get("frames", [])
        if not isinstance(frames, list):
            return 0
        return sum(
            1
            for frame in frames
            if isinstance(frame, dict) and frame.get("status") == "succeeded"
        )


def build_vision_ocr_request(
    frame: FrameCandidate,
    *,
    model: str = DEFAULT_VISION_OCR_MODEL,
    prompt_version: str = DEFAULT_VISION_OCR_PROMPT_VERSION,
    detail: str = DEFAULT_VISION_DETAIL,
) -> OpenAIRequest:
    _validate_detail(detail)
    frame_bytes = _read_frame_bytes(frame)
    encoded_frame = base64.b64encode(frame_bytes).decode("ascii")
    mime_type = mimetypes.guess_type(frame.safe_frame_name)[0] or "image/jpeg"
    payload = {
        "model": model,
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": VISION_OCR_PROMPT,
                    },
                    {
                        "type": "input_image",
                        "image_url": f"data:{mime_type};base64,{encoded_frame}",
                        "detail": detail,
                    },
                ],
            }
        ],
        "text": {"format": {"type": "json_object"}},
    }
    return OpenAIRequest(
        endpoint=OPENAI_VISION_OCR_ENDPOINT,
        use_case=OPENAI_VISION_OCR_USE_CASE,
        model=model,
        prompt_version=prompt_version,
        body=json_body(payload),
        input_size_bytes=len(frame_bytes),
        external_data_boundary="extracted frame image to OpenAI Vision OCR API",
    )


def run_vision_ocr_on_frames(
    frames: list[FrameCandidate],
    *,
    extraction_metadata: dict[str, object] | None = None,
    client: OpenAIClient | None = None,
    model: str = DEFAULT_VISION_OCR_MODEL,
    prompt_version: str = DEFAULT_VISION_OCR_PROMPT_VERSION,
    detail: str = DEFAULT_VISION_DETAIL,
) -> VisionOcrRunResult:
    _validate_detail(detail)
    if not frames:
        raise _ocr_error(
            "vision_ocr_frames_empty",
            "No extracted frames were provided for Vision OCR.",
            retryable=False,
        )

    openai_client = client or OpenAIClient()
    client_results: list[OpenAIClientResult] = []
    ocr_frames: list[dict[str, object]] = []
    for frame in frames:
        request = build_vision_ocr_request(
            frame,
            model=model,
            prompt_version=prompt_version,
            detail=detail,
        )
        result = openai_client.send(request)
        client_results.append(result)
        if not result.succeeded:
            ocr_frames.append(_failed_frame_payload(frame, result, detail=detail))
            continue
        normalized = parse_vision_ocr_response(result.body)
        ocr_frames.append(
            _succeeded_frame_payload(
                frame,
                normalized,
                result,
                detail=detail,
            )
        )

    payload_metadata = _payload_metadata(
        client_results,
        extraction_metadata=extraction_metadata,
        model=model,
        prompt_version=prompt_version,
        detail=detail,
    )
    return VisionOcrRunResult(
        ocr_payload={
            "provider_metadata": payload_metadata,
            "frames": ocr_frames,
        },
        client_results=client_results,
    )


def parse_vision_ocr_response(data: bytes | str) -> dict[str, object]:
    payload = _decode_json_bytes(data)
    if _has_ocr_fields(payload):
        return _normalize_ocr_payload(payload)

    response_text = _extract_response_text(payload)
    if response_text is None:
        raise _ocr_error(
            "vision_ocr_response_malformed",
            "Vision OCR response did not include OCR JSON text.",
            retryable=False,
        )
    response_payload = _decode_json_text(response_text)
    if not isinstance(response_payload, dict):
        raise _ocr_error(
            "vision_ocr_response_malformed",
            "Vision OCR response text must decode to a JSON object.",
            retryable=False,
        )
    return _normalize_ocr_payload(response_payload)


def _succeeded_frame_payload(
    frame: FrameCandidate,
    normalized: dict[str, object],
    result: OpenAIClientResult,
    *,
    detail: str,
) -> dict[str, object]:
    return {
        "slide_id": frame.frame_id.replace("frame-", "slide-"),
        "source_frame_ts": frame.source_frame_ts,
        "change_score": frame.change_score,
        "raw_ocr_text": str(normalized.get("raw_ocr_text", "")),
        "refined_ocr_text": str(normalized.get("refined_ocr_text", "")),
        "confidence": normalized.get("confidence"),
        "frame_width": frame.frame_width,
        "frame_height": frame.frame_height,
        "status": "succeeded",
        "provider_metadata": _frame_metadata(frame, result, detail=detail),
    }


def _failed_frame_payload(
    frame: FrameCandidate,
    result: OpenAIClientResult,
    *,
    detail: str,
) -> dict[str, object]:
    metadata = _frame_metadata(frame, result, detail=detail)
    metadata.update(
        {
            "error_code": result.error_code or "openai_request_failed",
            "error_message": result.error_message or "OpenAI Vision OCR failed.",
        }
    )
    return {
        "slide_id": frame.frame_id.replace("frame-", "slide-"),
        "source_frame_ts": frame.source_frame_ts,
        "change_score": frame.change_score,
        "raw_ocr_text": "",
        "refined_ocr_text": "",
        "confidence": None,
        "frame_width": frame.frame_width,
        "frame_height": frame.frame_height,
        "status": "failed",
        "provider_metadata": metadata,
    }


def _frame_metadata(
    frame: FrameCandidate,
    result: OpenAIClientResult,
    *,
    detail: str,
) -> dict[str, object]:
    return {
        "frame_id": frame.frame_id,
        "frame_file": frame.safe_frame_name,
        "extraction_method": frame.extraction_method,
        "detail": detail,
        "openai_call": result.metadata.to_dict(),
    }


def _payload_metadata(
    client_results: list[OpenAIClientResult],
    *,
    extraction_metadata: dict[str, object] | None,
    model: str,
    prompt_version: str,
    detail: str,
) -> dict[str, object]:
    succeeded = sum(1 for result in client_results if result.succeeded)
    total = len(client_results)
    if succeeded == total:
        status = "succeeded"
    elif succeeded == 0:
        status = "failed"
    else:
        status = "partial"
    return {
        "provider": "openai_vision",
        "endpoint": OPENAI_VISION_OCR_ENDPOINT,
        "use_case": OPENAI_VISION_OCR_USE_CASE,
        "model": model,
        "prompt_version": prompt_version,
        "detail": detail,
        "status": status,
        "frames_total": total,
        "frames_succeeded": succeeded,
        "estimated_cost": "unknown",
        "extraction": extraction_metadata or {},
        "openai_calls": [result.metadata.to_dict() for result in client_results],
    }


def _normalize_ocr_payload(payload: dict[str, object]) -> dict[str, object]:
    raw_text = _text_field(payload, "raw_ocr_text", "raw_text", "text")
    refined_text = _text_field(
        payload,
        "refined_ocr_text",
        "refined_text",
        "cleaned_text",
    )
    if refined_text == "":
        refined_text = raw_text
    return {
        "raw_ocr_text": raw_text,
        "refined_ocr_text": refined_text,
        "confidence": _optional_float(payload.get("confidence")),
    }


def _has_ocr_fields(payload: dict[str, object]) -> bool:
    keys = {"raw_ocr_text", "raw_text", "text", "refined_ocr_text", "refined_text"}
    return any(key in payload for key in keys)


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


def _decode_json_bytes(data: bytes | str) -> dict[str, object]:
    if isinstance(data, bytes):
        text = data.decode("utf-8", errors="replace")
    else:
        text = data
    decoded = _decode_json_text(text)
    if not isinstance(decoded, dict):
        raise _ocr_error(
            "vision_ocr_response_malformed",
            "Vision OCR response must be a JSON object.",
            retryable=False,
        )
    return decoded


def _decode_json_text(text: str) -> object:
    cleaned = _strip_json_fence(text.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise _ocr_error(
            "vision_ocr_response_invalid_json",
            f"Vision OCR response JSON could not be parsed: {exc.msg}",
            retryable=False,
        ) from exc


def _strip_json_fence(text: str) -> str:
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if len(lines) >= 3 and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return text


def _read_frame_bytes(frame: FrameCandidate) -> bytes:
    if frame.frame_path is None:
        raise ValidationError(
            ErrorDetail(
                code="frame_file_required",
                message="A real frame image file is required for Vision OCR.",
                stage=VISION_OCR_STAGE,
                retryable=False,
            )
        )
    if not frame.frame_path.exists() or not frame.frame_path.is_file():
        raise ValidationError(
            ErrorDetail(
                code="frame_file_not_found",
                message=f"Frame image file was not found: {frame.safe_frame_name}",
                stage=VISION_OCR_STAGE,
                retryable=False,
            )
        )
    frame_bytes = frame.frame_path.read_bytes()
    if not frame_bytes:
        raise ValidationError(
            ErrorDetail(
                code="frame_file_empty",
                message=f"Frame image file is empty: {frame.safe_frame_name}",
                stage=VISION_OCR_STAGE,
                retryable=False,
            )
        )
    return frame_bytes


def _validate_detail(detail: str) -> None:
    if detail not in SUPPORTED_VISION_DETAIL:
        supported = ", ".join(sorted(SUPPORTED_VISION_DETAIL))
        raise ValidationError(
            ErrorDetail(
                code="vision_detail_invalid",
                message=f"Vision detail must be one of: {supported}",
                stage=VISION_OCR_STAGE,
                retryable=False,
            )
        )


def _text_field(payload: dict[str, object], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if value is not None:
            return str(value)
    return ""


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _ocr_error(
    code: str,
    message: str,
    *,
    retryable: bool,
) -> EnrichmentError:
    return EnrichmentError(
        ErrorDetail(
            code=code,
            message=message,
            stage=VISION_OCR_STAGE,
            retryable=retryable,
        )
    )
