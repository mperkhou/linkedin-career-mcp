from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

import httpx

from linkedin_career_mcp.errors import LlmError

TRANSIENT_HTTP_STATUSES = {408, 409, 425, 429, 500, 502, 503, 504}


class ApiLlmClient:
    """LLM client that talks to an OpenAI-compatible chat completions API
    (OpenRouter, DeepSeek, OpenAI, etc.)."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str,
        timeout_seconds: float,
        client: httpx.AsyncClient | None = None,
        retry_attempts: int = 4,
        retry_backoff_seconds: float = 2.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)
        self._retry_attempts = max(1, retry_attempts)
        self._retry_backoff_seconds = max(0.0, retry_backoff_seconds)
        self._sleep = sleep

    @property
    def model(self) -> str:
        return self._model

    async def generate_text(self, prompt: str) -> str:
        return await self._generate(prompt, json_response=False)

    async def generate_json(self, prompt: str) -> Mapping[str, Any]:
        response = await self._generate(prompt, json_response=True)
        return _parse_json_object(response)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _generate(self, prompt: str, *, json_response: bool) -> str:
        messages: list[dict[str, str]] = [
            {"role": "user", "content": prompt},
        ]
        payload: dict[str, object] = {
            "model": self._model,
            "messages": messages,
            "temperature": 0,
        }
        # Note: we intentionally do NOT set response_format={"type": "json_object"}
        # here because many OpenRouter models (DeepSeek, Anthropic, etc.) do not
        # support it. Instead we rely on the prompt instructing the model to return
        # JSON, plus the _parse_json_object fallback that handles markdown fences.

        headers: dict[str, str] = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            # OpenRouter-recommended headers for model routing and attribution
            "HTTP-Referer": "https://github.com/mperkhou/linkedin-career-mcp",
            "X-Title": "linkedin-career-mcp",
        }

        last_completion_error: LlmError | None = None
        for attempt in range(1, self._retry_attempts + 1):
            data: Mapping[str, Any] = {}
            try:
                response = await self._client.post(
                    f"{self._base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                data = _response_json(response)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                detail = _http_error_detail(data, exc)
                if (
                    status_code in TRANSIENT_HTTP_STATUSES
                    and attempt < self._retry_attempts
                ):
                    await self._sleep(
                        _retry_delay_seconds(
                            exc.response,
                            attempt,
                            self._retry_backoff_seconds,
                        )
                    )
                    continue
                raise LlmError(
                    f"API LLM generation failed ({status_code}): {detail}"
                ) from exc
            except httpx.HTTPError as exc:
                raise LlmError(f"API LLM generation failed: {exc}") from exc

            text, last_completion_error = _completion_text(data)
            if last_completion_error is None:
                return text

            if attempt < self._retry_attempts:
                await self._sleep(
                    _retry_delay_seconds(
                        response,
                        attempt,
                        self._retry_backoff_seconds,
                    )
                )
                continue

        if last_completion_error is not None:
            raise last_completion_error
        raise LlmError("API LLM returned no completion choices.")


def _completion_text(data: Mapping[str, Any]) -> tuple[str, LlmError | None]:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return "", LlmError("API LLM returned no completion choices.")

    choice = choices[0]
    if not isinstance(choice, Mapping):
        return "", LlmError("API LLM returned no completion choices.")
    message = choice.get("message") or {}
    if not isinstance(message, Mapping):
        return "", LlmError("API LLM returned an empty generation.")
    text = message.get("content") or ""
    if not isinstance(text, str):
        return "", LlmError("API LLM returned an empty generation.")
    stripped_text = _strip_thinking(text.strip())
    if not stripped_text:
        return "", LlmError("API LLM returned an empty generation.")
    return stripped_text, None


def _response_json(response: httpx.Response) -> Mapping[str, Any]:
    try:
        data = response.json()
    except json.JSONDecodeError as exc:
        if response.is_error:
            return {}
        raise LlmError("API LLM returned a non-JSON HTTP response.") from exc
    if isinstance(data, Mapping):
        return data
    return {}


def _http_error_detail(data: object, exc: httpx.HTTPStatusError) -> str:
    if isinstance(data, Mapping):
        error = data.get("error")
        if isinstance(error, Mapping):
            message = str(error.get("message") or "").strip()
            metadata = error.get("metadata")
            raw = ""
            provider = ""
            if isinstance(metadata, Mapping):
                raw = str(metadata.get("raw") or "").strip()
                provider = str(metadata.get("provider_name") or "").strip()
            parts = [
                part
                for part in (
                    message,
                    raw,
                    f"provider={provider}" if provider else "",
                )
                if part
            ]
            if parts:
                return " | ".join(parts)
    return str(exc)


def _retry_delay_seconds(
    response: httpx.Response,
    attempt: int,
    base_delay_seconds: float,
) -> float:
    retry_after = response.headers.get("retry-after")
    if retry_after:
        try:
            return min(max(float(retry_after), 0.0), 120.0)
        except ValueError:
            pass
    return min(base_delay_seconds * (2 ** (attempt - 1)), 60.0)


def _parse_json_object(text: str) -> Mapping[str, Any]:
    """Parse a JSON object (or array) from text, trying to extract it from
    markdown code fences or inline.  Wraps bare arrays in ``{"queries": …}``
    so callers that expect a dict can still consume array responses."""

    def _unwrap(value: object) -> Mapping[str, Any] | None:
        if isinstance(value, Mapping):
            return value
        if isinstance(value, list):
            return {"queries": value}
        return None

    # 1. Try to parse the whole text as JSON
    try:
        result = _unwrap(json.loads(text))
        if result is not None:
            return result
    except json.JSONDecodeError:
        pass

    # 2. Try extracting from markdown code fences ```json … ```
    match = re.search(
        r"```(?:json)?\s*\n?(.*?)\n?```", text, flags=re.DOTALL | re.IGNORECASE
    )
    if match:
        try:
            result = _unwrap(json.loads(match.group(1)))
            if result is not None:
                return result
        except json.JSONDecodeError:
            pass

    # 3. Try extracting an inline JSON object or array
    for pattern in (r"\{.*\}", r"\[.*\]"):
        match = re.search(pattern, text, flags=re.DOTALL)
        if match:
            try:
                result = _unwrap(json.loads(match.group(0)))
                if result is not None:
                    return result
            except json.JSONDecodeError:
                pass

    raise LlmError("API LLM did not return a valid JSON object.")


def _strip_thinking(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE).strip()
