from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0 Safari/537.36 linkedin-career-mcp/0.1.2"
)
DEFAULT_LLM_API_MODEL = "deepseek/deepseek-chat"
DEFAULT_LLM_PLANNER_API_MODEL = "deepseek/deepseek-v4-flash"


@dataclass(frozen=True)
class Settings:
    user_agent: str = DEFAULT_USER_AGENT
    timeout_seconds: float = 12.0
    max_results: int = 25

    # Local Ollama settings (fallback / secondary)
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:4b"
    ollama_timeout_seconds: float = 180.0

    # External API LLM settings (primary, default)
    llm_api_base_url: str = "https://openrouter.ai/api/v1"
    llm_api_model: str = DEFAULT_LLM_API_MODEL
    llm_planner_api_model: str = DEFAULT_LLM_PLANNER_API_MODEL
    llm_api_key: str = ""
    llm_api_timeout_seconds: float = 120.0
    llm_provider: str = "api"  # "api" or "ollama"


def load_settings() -> Settings:
    return Settings(
        user_agent=os.getenv("LINKEDIN_CAREER_MCP_USER_AGENT", DEFAULT_USER_AGENT),
        timeout_seconds=_float_env("LINKEDIN_CAREER_MCP_TIMEOUT_SECONDS", 12.0),
        max_results=_int_env("LINKEDIN_CAREER_MCP_MAX_RESULTS", 25),
        ollama_base_url=os.getenv(
            "LINKEDIN_CAREER_MCP_OLLAMA_BASE_URL",
            "http://127.0.0.1:11434",
        ),
        ollama_model=os.getenv("LINKEDIN_CAREER_MCP_OLLAMA_MODEL", "qwen3:4b"),
        ollama_timeout_seconds=_float_env("LINKEDIN_CAREER_MCP_OLLAMA_TIMEOUT_SECONDS", 180.0),
        llm_api_base_url=os.getenv(
            "LINKEDIN_CAREER_MCP_LLM_API_BASE_URL",
            "https://openrouter.ai/api/v1",
        ),
        llm_api_model=os.getenv(
            "LINKEDIN_CAREER_MCP_LLM_API_MODEL",
            DEFAULT_LLM_API_MODEL,
        ),
        llm_planner_api_model=os.getenv(
            "LINKEDIN_CAREER_MCP_LLM_PLANNER_API_MODEL",
            DEFAULT_LLM_PLANNER_API_MODEL,
        ),
        llm_api_key=os.getenv("LINKEDIN_CAREER_MCP_LLM_API_KEY", ""),
        llm_api_timeout_seconds=_float_env(
            "LINKEDIN_CAREER_MCP_LLM_API_TIMEOUT_SECONDS", 120.0
        ),
        llm_provider=os.getenv("LINKEDIN_CAREER_MCP_LLM_PROVIDER", "api"),
    )


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default
