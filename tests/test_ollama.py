from __future__ import annotations

from linkedin_career_mcp.ollama import OllamaClient


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._payload


class FakeHttpClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    async def post(self, url: str, json: dict[str, object]) -> FakeResponse:
        return FakeResponse(self._payload)


async def test_generate_json_falls_back_to_qwen_thinking_field():
    client = OllamaClient(
        base_url="http://127.0.0.1:11434",
        model="qwen3:4b",
        timeout_seconds=1,
        client=FakeHttpClient(
            {
                "response": "",
                "thinking": '{"queries": [{"keywords": "platform engineer"}]}',
            }
        ),
    )

    result = await client.generate_json("prompt")

    assert result == {"queries": [{"keywords": "platform engineer"}]}
