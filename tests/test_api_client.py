from __future__ import annotations

import httpx
import pytest

from linkedin_career_mcp.api_client import ApiLlmClient
from linkedin_career_mcp.errors import LlmError


class SequencedApiHttpClient:
    def __init__(self, responses: list[httpx.Response]) -> None:
        self.responses = responses
        self.calls = 0

    async def post(self, *_args: object, **_kwargs: object) -> httpx.Response:
        self.calls += 1
        return self.responses.pop(0)


def _api_response(
    status_code: int,
    payload: dict[str, object],
    *,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    return httpx.Response(
        status_code,
        json=payload,
        headers=headers,
        request=httpx.Request("POST", "https://openrouter.example/chat/completions"),
    )


async def test_api_llm_client_retries_transient_provider_throttle() -> None:
    sleeps: list[float] = []

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)

    http_client = SequencedApiHttpClient(
        [
            _api_response(
                429,
                {
                    "error": {
                        "message": "Provider returned error",
                        "metadata": {
                            "raw": "qwen/qwen3.7-plus is temporarily rate-limited upstream.",
                            "provider_name": "Alibaba",
                        },
                    }
                },
                headers={"Retry-After": "0"},
            ),
            _api_response(
                200,
                {"choices": [{"message": {"content": "hello"}}]},
            ),
        ]
    )
    client = ApiLlmClient(
        base_url="https://openrouter.example",
        model="qwen/qwen3.7-plus",
        api_key="test-key",
        timeout_seconds=1,
        client=http_client,  # type: ignore[arg-type]
        retry_attempts=2,
        retry_backoff_seconds=0,
        sleep=sleep,
    )

    assert await client.generate_text("prompt") == "hello"
    assert http_client.calls == 2
    assert sleeps == [0]


async def test_api_llm_client_reports_provider_detail_after_exhausted_retry() -> None:
    http_client = SequencedApiHttpClient(
        [
            _api_response(
                429,
                {
                    "error": {
                        "message": "Provider returned error",
                        "metadata": {
                            "raw": "qwen/qwen3.7-plus is temporarily rate-limited upstream.",
                            "provider_name": "Alibaba",
                        },
                    }
                },
            )
        ]
    )
    client = ApiLlmClient(
        base_url="https://openrouter.example",
        model="qwen/qwen3.7-plus",
        api_key="test-key",
        timeout_seconds=1,
        client=http_client,  # type: ignore[arg-type]
        retry_attempts=1,
    )

    with pytest.raises(LlmError) as exc_info:
        await client.generate_text("prompt")

    message = str(exc_info.value)
    assert "429" in message
    assert "temporarily rate-limited upstream" in message
    assert "provider=Alibaba" in message
