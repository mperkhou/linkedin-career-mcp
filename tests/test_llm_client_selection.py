from __future__ import annotations

import pytest

from linkedin_career_mcp.api_client import ApiLlmClient
from linkedin_career_mcp.config import Settings
from linkedin_career_mcp.errors import WorkflowError
from linkedin_career_mcp.ollama import OllamaClient
from linkedin_career_mcp.workflows.matching import _build_llm_client


def test_build_llm_client_requires_api_key_in_api_mode():
    settings = Settings(llm_provider="api", llm_api_key="")

    with pytest.raises(WorkflowError, match="LINKEDIN_CAREER_MCP_LLM_API_KEY is required"):
        _build_llm_client(settings)


async def test_build_llm_client_uses_api_when_api_key_is_present():
    settings = Settings(llm_provider="api", llm_api_key="test-key")

    client = _build_llm_client(settings)
    try:
        assert isinstance(client, ApiLlmClient)
    finally:
        await client.aclose()


async def test_build_llm_client_uses_ollama_only_when_explicitly_requested():
    settings = Settings(llm_provider="ollama", llm_api_key="")

    client = _build_llm_client(settings)
    try:
        assert isinstance(client, OllamaClient)
    finally:
        await client.aclose()
