from __future__ import annotations

import os
import re

OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
REDACTED = "[REDACTED]"
LOCAL_PATH = "[LOCAL_PATH]"

SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "password",
    "secret",
    "token",
}

BEARER_PATTERN = re.compile(r"Bearer\s+[A-Za-z0-9._\-]+")
WINDOWS_PATH_PATTERN = re.compile(r"[A-Za-z]:\\[^\s;,)]+")
UNIX_PRIVATE_PATH_PATTERN = re.compile(r"/(?:Users|home|tmp|var)/[^\s;,)]+")


def redact_sensitive(
    value: object,
    *,
    env: dict[str, str] | None = None,
    secrets: list[str] | None = None,
) -> object:
    collected_secrets = list(secrets or [])
    source = env if env is not None else os.environ
    api_key = source.get(OPENAI_API_KEY_ENV)
    if api_key:
        collected_secrets.append(api_key)

    if isinstance(value, dict):
        return _redact_dict(value, env, collected_secrets)
    if isinstance(value, list):
        return [
            redact_sensitive(item, env=env, secrets=collected_secrets)
            for item in value
        ]
    if isinstance(value, str):
        return _redact_text(value, collected_secrets)
    return value


def _redact_dict(
    value: dict[object, object],
    env: dict[str, str] | None,
    secrets: list[str],
) -> dict[str, object]:
    redacted: dict[str, object] = {}
    for key, item in value.items():
        key_text = str(key)
        if _is_sensitive_key(key_text):
            redacted[key_text] = REDACTED
        else:
            redacted[key_text] = redact_sensitive(
                item,
                env=env,
                secrets=secrets,
            )
    return redacted


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return normalized in SENSITIVE_KEYS or any(
        token in normalized for token in ("api_key", "secret", "token")
    )


def _redact_text(text: str, secrets: list[str]) -> str:
    redacted = BEARER_PATTERN.sub(f"Bearer {REDACTED}", text)
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, REDACTED)
    redacted = WINDOWS_PATH_PATTERN.sub(LOCAL_PATH, redacted)
    redacted = UNIX_PRIVATE_PATH_PATTERN.sub(LOCAL_PATH, redacted)
    return redacted
