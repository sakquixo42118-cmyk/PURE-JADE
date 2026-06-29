"""Shared OpenAI-compatible API helpers for PURE-JADE scripts.

This module keeps API wiring separate from pipeline logic:

    .env / CLI args -> ApiConfig
    messages + ApiConfig -> chat-completions response text
    raw model text -> JSON object

Pipeline scripts should build prompts and validate cards themselves, but use
this module for configuration, HTTP calls, and common response parsing.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_ENV_FILE = Path(".env")
DEFAULT_API_URL = "https://api.openai.com/v1/chat/completions"


@dataclass
class ApiConfig:
    url: str
    api_key: str
    model: str
    temperature: float
    timeout_seconds: int
    max_retries: int
    json_mode: bool


def strip_env_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = strip_env_value(value)


def read_bool_env(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def read_int_env(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def read_float_env(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def normalize_chat_completions_url(url: str) -> str:
    normalized = url.strip().rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"


def load_api_config(args: Any, default_api_url: str = DEFAULT_API_URL) -> tuple[ApiConfig | None, list[str]]:
    env_file = getattr(args, "env_file", DEFAULT_ENV_FILE)
    load_env_file(env_file)
    errors: list[str] = []

    api_url = getattr(args, "api_url", None)
    api_model = getattr(args, "api_model", None)
    api_temperature = getattr(args, "api_temperature", None)
    api_timeout = getattr(args, "api_timeout", None)
    api_max_retries = getattr(args, "api_max_retries", None)

    url = normalize_chat_completions_url(api_url or os.environ.get("PURE_JADE_API_URL") or default_api_url)
    api_key = os.environ.get("PURE_JADE_API_KEY", "")
    model = api_model or os.environ.get("PURE_JADE_API_MODEL", "")
    temperature = api_temperature if api_temperature is not None else read_float_env("PURE_JADE_API_TEMPERATURE", 0.2)
    timeout_seconds = api_timeout if api_timeout is not None else read_int_env("PURE_JADE_API_TIMEOUT_SECONDS", 60)
    max_retries = (
        api_max_retries if api_max_retries is not None else read_int_env("PURE_JADE_API_MAX_RETRIES", 1)
    )
    json_mode = read_bool_env("PURE_JADE_API_JSON_MODE", True)

    if not api_key:
        errors.append("missing PURE_JADE_API_KEY")
    if not model:
        errors.append("missing PURE_JADE_API_MODEL")
    if not url:
        errors.append("missing PURE_JADE_API_URL")
    if timeout_seconds <= 0:
        errors.append("PURE_JADE_API_TIMEOUT_SECONDS must be positive")
    if max_retries < 0:
        errors.append("PURE_JADE_API_MAX_RETRIES must be 0 or greater")

    if errors:
        return None, errors
    return (
        ApiConfig(
            url=url,
            api_key=api_key,
            model=model,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            json_mode=json_mode,
        ),
        [],
    )


def config_summary(config: ApiConfig) -> dict[str, Any]:
    return {
        "url": config.url,
        "model": config.model,
        "temperature": config.temperature,
        "timeout_seconds": config.timeout_seconds,
        "max_retries": config.max_retries,
        "json_mode": config.json_mode,
        "api_key_present": bool(config.api_key),
    }


def build_chat_payload(messages: list[dict[str, str]], config: ApiConfig) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": config.model,
        "messages": messages,
        "temperature": config.temperature,
    }
    if config.json_mode:
        payload["response_format"] = {"type": "json_object"}
    return payload


def request_chat_completion(messages: list[dict[str, str]], config: ApiConfig) -> tuple[str, dict[str, Any]]:
    payload = build_chat_payload(messages, config)
    request = urllib.request.Request(
        config.url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        error_body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"API HTTP {error.code}: {error_body}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"API connection failed: {error}") from error

    response_json = json.loads(body)
    return extract_chat_content(response_json), response_json


def extract_chat_content(response_json: dict[str, Any]) -> str:
    choices = response_json.get("choices")
    if isinstance(choices, list) and choices:
        first_choice = choices[0]
        if isinstance(first_choice, dict):
            message = first_choice.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    text_parts = []
                    for part in content:
                        if isinstance(part, dict) and isinstance(part.get("text"), str):
                            text_parts.append(part["text"])
                    if text_parts:
                        return "".join(text_parts)
            if isinstance(first_choice.get("text"), str):
                return first_choice["text"]

    output_text = response_json.get("output_text")
    if isinstance(output_text, str):
        return output_text

    raise RuntimeError("API response did not contain a supported text field")


def extract_json_object(raw_output: str) -> tuple[dict[str, Any] | None, str | None]:
    text = raw_output.strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict):
        return parsed, None
    if parsed is not None:
        return None, "model output must be a JSON object"

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None, "model output did not contain a JSON object"

    candidate = text[start : end + 1]
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as error:
        return None, f"model output is not valid JSON: {error}"
    if not isinstance(parsed, dict):
        return None, "model output must be a JSON object"
    return parsed, None


def retry_user_prompt(validation_errors: list[str], raw_output: str) -> str:
    return f"""上一轮输出无法通过 JSON 或 Schema 校验。
请只输出一个修正后的合法 JSON 对象，不要输出 Markdown 或解释文字。

[校验错误]
{json.dumps(validation_errors, ensure_ascii=False, indent=2)}

[上一轮原始输出]
{raw_output}
"""
