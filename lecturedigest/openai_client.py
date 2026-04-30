from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from lecturedigest.errors import ErrorDetail, OpenAIClientError
from lecturedigest.openai_redaction import OPENAI_API_KEY_ENV, redact_sensitive
from lecturedigest.openai_types import (
    OPENAI_STAGE,
    OpenAICallMetadata,
    OpenAIClientResult,
    OpenAIRequest,
    OpenAITransport,
    OpenAITransportResponse,
)

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com"
DEFAULT_TIMEOUT_SECONDS = 60.0


class UrllibOpenAITransport:
    def send(
        self,
        *,
        url: str,
        method: str,
        headers: dict[str, str],
        body: bytes,
        timeout_seconds: float,
    ) -> OpenAITransportResponse:
        request = urllib.request.Request(
            url=url,
            data=body if body else None,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                return OpenAITransportResponse(
                    status_code=response.status,
                    body=response.read(),
                    headers=dict(response.headers.items()),
                )
        except urllib.error.HTTPError as exc:
            return OpenAITransportResponse(
                status_code=exc.code,
                body=exc.read(),
                headers=dict(exc.headers.items()) if exc.headers else {},
            )
        except urllib.error.URLError as exc:
            reason = exc.reason
            if isinstance(reason, TimeoutError):
                raise reason from exc
            raise OSError(str(reason)) from exc


class OpenAIClient:
    def __init__(
        self,
        *,
        transport: OpenAITransport | None = None,
        base_url: str = DEFAULT_OPENAI_BASE_URL,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        env: dict[str, str] | None = None,
    ) -> None:
        self.transport = transport or UrllibOpenAITransport()
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.env = env

    def send(
        self,
        request: OpenAIRequest,
        *,
        dry_run: bool = False,
    ) -> OpenAIClientResult:
        started = time.perf_counter()
        if dry_run:
            return self._result(
                request,
                started=started,
                status="dry_run",
                retryable=False,
            )

        api_key = load_openai_api_key(self.env)
        headers = self._headers(request, api_key)
        try:
            response = self.transport.send(
                url=self._url(request.endpoint),
                method=request.method,
                headers=headers,
                body=request.body,
                timeout_seconds=self.timeout_seconds,
            )
        except TimeoutError as exc:
            return self._failure(
                request,
                started=started,
                error_code="openai_request_timeout",
                message=str(exc) or "OpenAI request timed out.",
                retryable=True,
            )
        except OSError as exc:
            return self._failure(
                request,
                started=started,
                error_code="openai_request_failed",
                message=str(exc) or "OpenAI request failed.",
                retryable=True,
            )

        if 200 <= response.status_code < 300:
            return self._result(
                request,
                started=started,
                status="succeeded",
                retryable=False,
                status_code=response.status_code,
                body=response.body,
            )

        return self._failure(
            request,
            started=started,
            error_code=error_code_for_status(response.status_code),
            message=_failure_message(response),
            retryable=is_retryable_status(response.status_code),
            status_code=response.status_code,
            body=response.body,
        )

    def _headers(self, request: OpenAIRequest, api_key: str) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "LectureDigest/1",
            **request.headers,
        }
        if request.body and "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"
        return headers

    def _url(self, endpoint: str) -> str:
        if endpoint.startswith(("http://", "https://")):
            return endpoint
        return f"{self.base_url}/{endpoint.lstrip('/')}"

    def _result(
        self,
        request: OpenAIRequest,
        *,
        started: float,
        status: str,
        retryable: bool,
        status_code: int | None = None,
        body: bytes = b"",
    ) -> OpenAIClientResult:
        return OpenAIClientResult(
            metadata=_metadata(
                request,
                duration_ms=_elapsed_ms(started),
                status=status,
                retryable=retryable,
            ),
            status_code=status_code,
            body=body,
        )

    def _failure(
        self,
        request: OpenAIRequest,
        *,
        started: float,
        error_code: str,
        message: str,
        retryable: bool,
        status_code: int | None = None,
        body: bytes = b"",
    ) -> OpenAIClientResult:
        return OpenAIClientResult(
            metadata=_metadata(
                request,
                duration_ms=_elapsed_ms(started),
                status="failed",
                retryable=retryable,
            ),
            status_code=status_code,
            body=body,
            error_code=error_code,
            error_message=redact_sensitive(message, env=self.env),
        )


def load_openai_api_key(env: dict[str, str] | None = None) -> str:
    source = env if env is not None else os.environ
    api_key = source.get(OPENAI_API_KEY_ENV, "").strip()
    if not api_key:
        raise OpenAIClientError(
            ErrorDetail(
                code="openai_api_key_missing",
                message="OPENAI_API_KEY environment variable is required.",
                stage=OPENAI_STAGE,
                retryable=False,
            )
        )
    return api_key


def is_retryable_status(status_code: int | None) -> bool:
    if status_code is None:
        return False
    return status_code in {408, 429} or 500 <= status_code <= 599


def error_code_for_status(status_code: int | None) -> str:
    if status_code == 401 or status_code == 403:
        return "openai_auth_failed"
    if status_code == 429:
        return "openai_rate_limited"
    if status_code is not None and 500 <= status_code <= 599:
        return "openai_server_error"
    if status_code is not None and 400 <= status_code <= 499:
        return "openai_client_error"
    return "openai_request_failed"


def format_dry_run_result(result: OpenAIClientResult) -> str:
    metadata = result.metadata
    return (
        "[OpenAIClient] request dry-run "
        f"{{ endpoint={metadata.endpoint}; useCase={metadata.use_case}; "
        f"model={metadata.model}; promptVersion={metadata.prompt_version}; "
        f"inputSizeBytes={metadata.input_size_bytes}; "
        f"externalDataBoundary={metadata.external_data_boundary}; "
        f"estimatedCost={metadata.estimated_cost} }}"
    )


def json_body(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _metadata(
    request: OpenAIRequest,
    *,
    duration_ms: int,
    status: str,
    retryable: bool,
) -> OpenAICallMetadata:
    return OpenAICallMetadata(
        provider="openai",
        endpoint=request.endpoint,
        use_case=request.use_case,
        model=request.model,
        prompt_version=request.prompt_version,
        input_size_bytes=request.input_size_bytes,
        duration_ms=duration_ms,
        status=status,
        retryable=retryable,
        estimated_cost=request.estimated_cost,
        external_data_boundary=request.external_data_boundary,
    )


def _failure_message(response: OpenAITransportResponse) -> str:
    text = response.body.decode("utf-8", errors="replace").strip()
    if text:
        return text
    return f"OpenAI request failed with status {response.status_code}."


def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)

