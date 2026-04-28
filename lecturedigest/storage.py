from __future__ import annotations

import json
from pathlib import Path

from lecturedigest.models import LectureRecord


class JsonLectureRepository:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def list_lectures(self) -> list[LectureRecord]:
        if not self.path.exists():
            return []
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            return []
        return [
            LectureRecord.from_dict(item)
            for item in payload
            if isinstance(item, dict)
        ]

    def get_lecture(self, lecture_id: str) -> LectureRecord | None:
        for lecture in self.list_lectures():
            if lecture.lecture_id == lecture_id:
                return lecture
        return None

    def save(self, record: LectureRecord) -> None:
        lectures = self.list_lectures()
        updated = [item for item in lectures if item.lecture_id != record.lecture_id]
        updated.append(record)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                [item.to_dict() for item in updated],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
