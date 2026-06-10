from __future__ import annotations

import pytest

from linkedin_career_mcp.api_client import ApiLlmClient
from linkedin_career_mcp.config import Settings
from linkedin_career_mcp.errors import WorkflowError
from linkedin_career_mcp.ollama import OllamaClient
from linkedin_career_mcp.workflows.matching import _build_llm_client, _build_planner_llm_client


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


async def test_build_llm_client_accepts_api_model_override():
    settings = Settings(
        llm_provider="api",
        llm_api_key="test-key",
        llm_api_model="deepseek/deepseek-v4-pro",
    )

    client = _build_llm_client(settings, api_model="deepseek/deepseek-v4-flash")
    try:
        assert isinstance(client, ApiLlmClient)
        assert client.model == "deepseek/deepseek-v4-flash"
    finally:
        await client.aclose()


async def test_build_planner_llm_client_uses_separate_api_model_when_configured():
    settings = Settings(
        llm_provider="api",
        llm_api_key="test-key",
        llm_api_model="deepseek/deepseek-v4-pro",
        llm_planner_api_model="deepseek/deepseek-v4-flash",
    )

    artifact_client = _build_llm_client(settings)
    planner_client = _build_planner_llm_client(settings, artifact_client)
    try:
        assert isinstance(planner_client, ApiLlmClient)
        assert planner_client is not artifact_client
        assert artifact_client.model == "deepseek/deepseek-v4-pro"
        assert planner_client.model == "deepseek/deepseek-v4-flash"
    finally:
        await planner_client.aclose()
        await artifact_client.aclose()


async def test_build_planner_llm_client_reuses_artifact_client_when_models_match():
    settings = Settings(
        llm_provider="api",
        llm_api_key="test-key",
        llm_api_model="deepseek/deepseek-v4-pro",
        llm_planner_api_model="deepseek/deepseek-v4-pro",
    )

    artifact_client = _build_llm_client(settings)
    try:
        planner_client = _build_planner_llm_client(settings, artifact_client)
        assert planner_client is artifact_client
    finally:
        await artifact_client.aclose()


async def test_build_llm_client_uses_ollama_only_when_explicitly_requested():
    settings = Settings(llm_provider="ollama", llm_api_key="")

    client = _build_llm_client(settings)
    try:
        assert isinstance(client, OllamaClient)
    finally:
        await client.aclose()
