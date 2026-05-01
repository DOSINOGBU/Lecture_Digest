from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from lecturedigest.models import CorrectionLogEntry, LectureRecord
from lecturedigest.note_quality import inspect_note_quality
from lecturedigest.storage import JsonLectureRepository

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CARD_MANIFEST = Path("docs/golden-samples/card-browser-understanding-set-3.json")
DEFAULT_QUIZ_MANIFEST = Path("docs/golden-samples/quiz-browser-understanding-combined.json")


@dataclass(frozen=True)
class LibraryState:
    lectures: list[LectureRecord]
    error_message: str | None = None

    @property
    def is_empty(self) -> bool:
        return not self.lectures and self.error_message is None


@dataclass(frozen=True)
class NoteQualityState:
    result: dict[str, object] = field(default_factory=dict)
    error_message: str | None = None


@dataclass(frozen=True)
class ReviewArtifactState:
    manifest_path: str
    manifest: dict[str, object] = field(default_factory=dict)
    summary: dict[str, object] = field(default_factory=dict)
    items: list[dict[str, object]] = field(default_factory=list)
    expected_counts: dict[str, int] = field(default_factory=dict)
    source_counts: dict[str, int] = field(default_factory=dict)
    error_messages: list[str] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return bool(self.error_messages)


def load_library(repository: JsonLectureRepository) -> LibraryState:
    try:
        return LibraryState(lectures=repository.list_lectures())
    except Exception as exc:  # UI boundary: preserve context without crashing the app.
        return LibraryState(
            lectures=[],
            error_message=f"{exc.__class__.__name__}: {exc}",
        )


def lecture_label(record: LectureRecord) -> str:
    category = " / ".join(
        item
        for item in [
            record.lecture_title,
            record.major_category,
            record.middle_category,
        ]
        if item
    )
    suffix = f" | {category}" if category else ""
    return f"{record.title}{suffix} ({record.status})"


def status_counts(record: LectureRecord) -> dict[str, int]:
    return {
        "segments": len(record.segments),
        "chunks": len(record.chunks),
        "slides": len(record.slides),
        "issues": len(record.issues),
        "note_candidates": len(record.note_candidates),
        "review_corrections": len(correction_review_queue(record)),
        "cards": len(record.flashcards),
        "quizzes": len(record.quiz_items),
    }


def correction_review_queue(record: LectureRecord) -> list[CorrectionLogEntry]:
    return [
        entry
        for entry in record.correction_log
        if entry.status == "review_required"
    ]


def note_candidates(record: LectureRecord) -> list[dict[str, object]]:
    return [candidate for candidate in record.note_candidates if isinstance(candidate, dict)]


def note_quality_review(record: LectureRecord) -> NoteQualityState:
    try:
        return NoteQualityState(result=inspect_note_quality(record))
    except Exception as exc:  # UI boundary: show quality failures without hiding details.
        return NoteQualityState(error_message=f"{exc.__class__.__name__}: {exc}")


def card_review_state(
    manifest_path: str | Path = DEFAULT_CARD_MANIFEST,
) -> ReviewArtifactState:
    manifest, errors = _read_json_dict(manifest_path, label="card manifest")
    if not manifest:
        return ReviewArtifactState(
            manifest_path=str(manifest_path),
            error_messages=errors,
        )

    artifact_paths = _dict(manifest.get("artifact_paths"))
    summary, summary_errors = _read_optional_json_dict(
        artifact_paths.get("summary"),
        label="card summary",
    )
    cards, card_errors = _read_card_items(artifact_paths.get("cards"))
    expected_counts = _int_dict(manifest.get("expected_counts"))
    return ReviewArtifactState(
        manifest_path=str(manifest_path),
        manifest=manifest,
        summary=summary,
        items=cards,
        expected_counts=expected_counts,
        error_messages=errors + summary_errors + card_errors,
    )


def quiz_review_state(
    manifest_path: str | Path = DEFAULT_QUIZ_MANIFEST,
) -> ReviewArtifactState:
    manifest, errors = _read_json_dict(manifest_path, label="quiz manifest")
    if not manifest:
        return ReviewArtifactState(
            manifest_path=str(manifest_path),
            error_messages=errors,
        )

    items: list[dict[str, object]] = []
    source_counts: dict[str, int] = {}
    sources = _dict(manifest.get("sources"))
    for source_name, source in sources.items():
        source_info = _dict(source)
        badge = str(source_info.get("source_badge") or source_name)
        source_items, source_errors = _read_quiz_source(source_info, badge=badge)
        source_counts[badge] = len(source_items)
        items.extend(source_items)
        errors.extend(source_errors)
        expected_count = int(source_info.get("expected_count") or 0)
        if expected_count and expected_count != len(source_items):
            errors.append(
                f"{badge} expected {expected_count} quiz items but loaded {len(source_items)}."
            )

    expected_total = int(manifest.get("expected_total") or 0)
    if expected_total and expected_total != len(items):
        errors.append(
            f"Combined quiz manifest expected {expected_total} items but loaded {len(items)}."
        )

    return ReviewArtifactState(
        manifest_path=str(manifest_path),
        manifest=manifest,
        summary={
            "expected_total": expected_total,
            "actual_total": len(items),
            "source_policy": str(manifest.get("source_policy") or ""),
            "dedupe_policy": str(manifest.get("dedupe_policy") or ""),
        },
        items=items,
        expected_counts={"expected_total": expected_total},
        source_counts=source_counts,
        error_messages=errors,
    )


def cost_or_quota_issues(record: LectureRecord) -> list[str]:
    keywords = ("quota", "rate", "cost", "budget", "openai_rate_limited")
    messages = []
    for issue in record.issues:
        text = f"{issue.code} {issue.message}".lower()
        if any(keyword in text for keyword in keywords):
            messages.append(f"{issue.code}: {issue.message}")
    return messages


def has_openai_api_key(env: dict[str, str] | None = None) -> bool:
    source = env if env is not None else os.environ
    return bool(source.get("OPENAI_API_KEY", "").strip())


def paid_action_previews(record: LectureRecord) -> list[dict[str, object]]:
    return [
        {
            "name": "Transcript correction",
            "model": str(record.correction_metadata.get("model") or "gpt-4o"),
            "external_boundary": "selected transcript segment text",
            "input_size_bytes": _segments_size(record),
            "dry_run": (
                "python -m lecturedigest finalize-transcript "
                f"--lecture-id {record.lecture_id} --openai --dry-run"
            ),
        },
        {
            "name": "Embedding regeneration",
            "model": str(record.rag_metadata.get("embedding_model") or "text-embedding-3-large"),
            "external_boundary": "indexed transcript, OCR, and approved note text",
            "input_size_bytes": _search_index_size(record),
            "dry_run": (
                "python -m lecturedigest index "
                f"--lecture-id {record.lecture_id} --embed-openai --dry-run"
            ),
        },
        {
            "name": "Vision OCR",
            "model": "gpt-4o",
            "external_boundary": "selected representative frame images",
            "input_size_bytes": _slide_metadata_size(record),
            "dry_run": (
                "python -m lecturedigest ocr "
                f"--lecture-id {record.lecture_id} --dry-run"
            ),
        },
    ]


def _segments_size(record: LectureRecord) -> int:
    return len("\n".join(segment.text for segment in record.segments).encode("utf-8"))


def _search_index_size(record: LectureRecord) -> int:
    text = "\n".join(str(entry.get("indexed_text") or "") for entry in record.search_index)
    return len(text.encode("utf-8"))


def _slide_metadata_size(record: LectureRecord) -> int:
    return sum(len(str(slide.source_frame_ts).encode("utf-8")) for slide in record.slides)


def _read_card_items(path_value: object) -> tuple[list[dict[str, object]], list[str]]:
    data, errors = _read_optional_json_dict(path_value, label="card items")
    if not data:
        return [], errors
    cards = _dict_list(data.get("cards"))
    if not cards:
        errors.append(f"card items did not include a non-empty cards array: {path_value}")
    return cards, errors


def _read_quiz_source(
    source_info: dict[str, object],
    *,
    badge: str,
) -> tuple[list[dict[str, object]], list[str]]:
    artifact_path = source_info.get("artifact_path")
    data, errors = _read_json_value(artifact_path, label=f"{badge} quiz artifact")
    if data is None:
        return [], errors

    lecture_id = str(_dict(source_info.get("record_selector")).get("lecture_id") or "")
    record = _select_record(data, lecture_id)
    if not record:
        return [], errors + [f"{badge} quiz artifact did not contain lecture {lecture_id}."]

    path = str(source_info.get("quiz_items_path") or "quiz_items")
    items = _dict_list(record.get(path))
    tagged = []
    for item in items:
        tagged_item = dict(item)
        tagged_item["_review_source_badge"] = badge
        tagged_item["_review_source_role"] = str(source_info.get("role") or "")
        tagged.append(tagged_item)
    return tagged, errors


def _select_record(value: object, lecture_id: str) -> dict[str, object]:
    if isinstance(value, list):
        for item in value:
            record = _dict(item)
            if str(record.get("lecture_id") or "") == lecture_id:
                return record
        return {}
    record = _dict(value)
    if not lecture_id or str(record.get("lecture_id") or "") == lecture_id:
        return record
    if isinstance(value, dict):
        for key in ("lectures", "records"):
            for item in _dict_list(value.get(key)):
                if str(item.get("lecture_id") or "") == lecture_id:
                    return item
    return {}


def _read_optional_json_dict(
    path_value: object,
    *,
    label: str,
) -> tuple[dict[str, object], list[str]]:
    if not path_value:
        return {}, []
    data, errors = _read_json_value(path_value, label=label)
    return _dict(data), errors


def _read_json_dict(
    path_value: object,
    *,
    label: str,
) -> tuple[dict[str, object], list[str]]:
    data, errors = _read_json_value(path_value, label=label)
    if errors:
        return {}, errors
    result = _dict(data)
    if not result:
        return {}, [f"{label} must be a JSON object: {path_value}"]
    return result, []


def _read_json_value(path_value: object, *, label: str) -> tuple[object | None, list[str]]:
    path = _resolve_repo_path(path_value)
    if not path:
        return None, [f"{label} path is missing."]
    try:
        return json.loads(path.read_text(encoding="utf-8")), []
    except FileNotFoundError:
        return None, [f"{label} not found: {path}"]
    except json.JSONDecodeError as exc:
        return None, [f"{label} is not valid JSON: {path} ({exc})"]
    except OSError as exc:
        return None, [f"{label} could not be read: {path} ({exc})"]


def _resolve_repo_path(path_value: object) -> Path | None:
    if not path_value:
        return None
    path = Path(str(path_value))
    return path if path.is_absolute() else REPO_ROOT / path


def _dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _int_dict(value: object) -> dict[str, int]:
    result: dict[str, int] = {}
    for key, item in _dict(value).items():
        if isinstance(item, bool):
            continue
        if isinstance(item, int):
            result[str(key)] = item
    return result
