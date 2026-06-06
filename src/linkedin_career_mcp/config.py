from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0 Safari/537.36 linkedin-career-mcp/0.1.0"
)


@dataclass(frozen=True)
class Settings:
    user_agent: str = DEFAULT_USER_AGENT
    timeout_seconds: float = 12.0
    max_results: int = 25


def load_settings() -> Settings:
    return Settings(
        user_agent=os.getenv("LINKEDIN_CAREER_MCP_USER_AGENT", DEFAULT_USER_AGENT),
        timeout_seconds=_float_env("LINKEDIN_CAREER_MCP_TIMEOUT_SECONDS", 12.0),
        max_results=_int_env("LINKEDIN_CAREER_MCP_MAX_RESULTS", 25),
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
