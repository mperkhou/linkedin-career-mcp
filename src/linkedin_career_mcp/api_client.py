from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

import httpx

from linkedin_career_mcp.errors import LlmError


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
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)

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

        try:
            response = await self._client.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            data = response.json()
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # Log the response body on 4xx/5xx for debugging
            body = data if isinstance(data, dict) else {}
            detail = body.get("error", {}).get("message", str(exc))
            raise LlmError(f"API LLM generation failed: {detail}") from exc
        except httpx.HTTPError as exc:
            raise LlmError(f"API LLM generation failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise LlmError("API LLM returned a non-JSON HTTP response.") from exc

        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LlmError("API LLM returned no completion choices.")

        choice = choices[0]
        message = choice.get("message") or {}
        text = message.get("content") or ""
        if not isinstance(text, str) or not text.strip():
            raise LlmError("API LLM returned an empty generation.")
        return _strip_thinking(text.strip())


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