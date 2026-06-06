from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

import httpx

from linkedin_career_mcp.errors import OllamaError


class OllamaClient:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
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
        payload: dict[str, object] = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0},
        }
        if json_response:
            payload["format"] = "json"

        try:
            response = await self._client.post(f"{self._base_url}/api/generate", json=payload)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            raise OllamaError(f"Ollama generation failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise OllamaError("Ollama returned a non-JSON HTTP response.") from exc

        text = data.get("response") or data.get("thinking")
        if not isinstance(text, str) or not text.strip():
            raise OllamaError("Ollama returned an empty generation.")
        return _strip_thinking(text.strip())


def _parse_json_object(text: str) -> Mapping[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise OllamaError("Ollama did not return a JSON object.") from None
        try:
            value = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise OllamaError("Ollama returned malformed JSON.") from exc

    if not isinstance(value, Mapping):
        raise OllamaError("Ollama returned JSON that was not an object.")
    return value


def _strip_thinking(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE).strip()
