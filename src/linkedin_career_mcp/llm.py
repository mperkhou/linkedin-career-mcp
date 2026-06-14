from __future__ import annotations

from linkedin_career_mcp.api_client import ApiLlmClient
from linkedin_career_mcp.config import Settings
from linkedin_career_mcp.errors import WorkflowError
from linkedin_career_mcp.ollama import OllamaClient


def build_llm_client(
    settings: Settings,
    *,
    api_model: str | None = None,
) -> ApiLlmClient | OllamaClient:
    """Build the configured LLM client for ARO workflows."""
    provider = settings.llm_provider.casefold().strip()
    if provider == "ollama":
        return OllamaClient(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            timeout_seconds=settings.ollama_timeout_seconds,
        )
    if provider != "api":
        raise WorkflowError(
            "Unsupported LLM provider. Set LINKEDIN_CAREER_MCP_LLM_PROVIDER to 'api' "
            "or 'ollama'."
        )
    if not settings.llm_api_key:
        raise WorkflowError(
            "LINKEDIN_CAREER_MCP_LLM_API_KEY is required when "
            "LINKEDIN_CAREER_MCP_LLM_PROVIDER=api."
        )
    return ApiLlmClient(
        base_url=settings.llm_api_base_url,
        model=api_model or settings.llm_api_model,
        api_key=settings.llm_api_key,
        timeout_seconds=settings.llm_api_timeout_seconds,
    )


def build_planner_llm_client(
    settings: Settings,
    artifact_llm: ApiLlmClient | OllamaClient,
) -> ApiLlmClient | OllamaClient:
    if settings.llm_provider.casefold().strip() != "api":
        return artifact_llm
    planner_model = settings.llm_planner_api_model.strip() or settings.llm_api_model
    if planner_model == settings.llm_api_model:
        return artifact_llm
    return build_llm_client(settings, api_model=planner_model)


def llm_settings_label(settings: Settings) -> str:
    provider = settings.llm_provider.casefold().strip()
    if provider == "ollama":
        return f"ollama:{settings.ollama_model} ({settings.ollama_base_url})"
    return f"{provider}:{settings.llm_api_model} ({settings.llm_api_base_url})"


def workflow_llm_settings_label(settings: Settings) -> str:
    provider = settings.llm_provider.casefold().strip()
    if provider != "api":
        return llm_settings_label(settings)
    planner_model = settings.llm_planner_api_model.strip() or settings.llm_api_model
    if planner_model == settings.llm_api_model:
        return llm_settings_label(settings)
    return (
        f"{provider}:draft={settings.llm_api_model}; "
        f"planner={planner_model} ({settings.llm_api_base_url})"
    )
