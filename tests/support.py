from __future__ import annotations

import json
from dataclasses import replace

from lecturedigest.models import LectureRecord, TranscriptChunk, TranscriptSegment
from lecturedigest.openai_client import OpenAIClient
from lecturedigest.openai_types import OpenAITransportResponse

TEST_OPENAI_API_KEY = "test-openai-key"


class FakeTransport:
    def __init__(self, response: OpenAITransportResponse | None = None) -> None:
        self.response = response or json_response({})
        self.calls = []

    def send(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class TimeoutTransport:
    def send(self, **kwargs):
        raise TimeoutError("network timeout")


def openai_env(api_key: str = TEST_OPENAI_API_KEY) -> dict[str, str]:
    return {"OPENAI_API_KEY": api_key}


def openai_client(
    response: OpenAITransportResponse,
    *,
    api_key: str = TEST_OPENAI_API_KEY,
) -> OpenAIClient:
    return OpenAIClient(
        transport=FakeTransport(response),
        env=openai_env(api_key),
    )


def json_response(
    payload: dict[str, object],
    *,
    status_code: int = 200,
) -> OpenAITransportResponse:
    return OpenAITransportResponse(
        status_code=status_code,
        body=json.dumps(payload).encode("utf-8"),
    )


def stt_success_response() -> OpenAITransportResponse:
    return json_response(
        {
            "segments": [
                {
                    "start": 1.0,
                    "end": 2.5,
                    "text": "hello",
                    "speaker": "speaker_1",
                }
            ]
        }
    )


def embedding_response(vectors: list[list[float]]) -> OpenAITransportResponse:
    return json_response(
        {
            "data": [
                {"index": index, "embedding": vector}
                for index, vector in enumerate(vectors)
            ]
        }
    )


def chunked_lecture() -> LectureRecord:
    chunk = TranscriptChunk(
        chunk_id="chunk-000001",
        lecture_id="lec_1",
        chapter="chapter-a",
        start_ts="00:00:00.000",
        end_ts="00:00:20.000",
        text="React renders components",
        segment_ids=["seg-1", "seg-2"],
        ocr_text="React DOM",
    )
    return replace(
        lecture_record(
            [
                segment("seg-1", "00:00:00.000", "00:00:10.000", "React renders"),
                segment("seg-2", "00:00:10.000", "00:00:20.000", "components"),
            ]
        ),
        status="chunks_ready",
        stage="chunking",
        chunks=[chunk],
    )


def lecture_record(segments: list[TranscriptSegment]) -> LectureRecord:
    return LectureRecord(
        lecture_id="lec_1",
        title="Intro",
        instructor="Teacher",
        category="Coding",
        source_path="lecture.mp4",
        subtitle_path="lecture.srt",
        status="transcript_ready",
        stage="transcription",
        transcript_source="subtitle",
        segments=segments,
    )


def segment(
    segment_id: str,
    start_ts: str,
    end_ts: str,
    text: str,
) -> TranscriptSegment:
    return TranscriptSegment(
        segment_id=segment_id,
        start_ts=start_ts,
        end_ts=end_ts,
        text=text,
    )
