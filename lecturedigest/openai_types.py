from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Protocol

from lecturedigest.models import ProcessingIssue

OPENAI_STAGE = "external_api"
UNKNOWN_COST = "unknown"


@dataclass(frozen=True)
class OpenAIRequest:
    endpoint: str
    use_case: str
    model: str
    prompt_version: str = "unknown"
    method: str = "POST"
    body: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)
    input_size_bytes: int = 0
    external_data_boundary: str = "unknown"
    estimated_cost: object = UNKNOWN_COST


@dataclass(frozen=True)
class OpenAITransportResponse:
    status_code: int
    body: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class OpenAICallMetadata:
    provider: str
    endpoint: str
    use_case: str
    model: str
    prompt_version: str
    input_size_bytes: int
    duration_ms: int
    status: str
    retryable: bool
    estimated_cost: object
    external_data_boundary: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class OpenAIClientResult:
    metadata: OpenAICallMetadata
    status_code: int | None = None
    body: bytes = b""
    error_code: str | None = None
    error_message: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.metadata.status == "succeeded"

    def to_processing_issue(self, *, stage: str = OPENAI_STAGE) -> ProcessingIssue | None:
        if self.succeeded or self.metadata.status == "dry_run":
            return None
        return ProcessingIssue(
            code=self.error_code or "openai_request_failed",
            message=self.error_message or "OpenAI request failed.",
            stage=stage,
            retryable=self.metadata.retryable,
        )


class OpenAITransport(Protocol):
    def send(
        self,
        *,
        url: str,
        method: str,
        headers: dict[str, str],
        body: bytes,
        timeout_seconds: float,
    ) -> OpenAITransportResponse:
        ...
