from __future__ import annotations

import json
from dataclasses import dataclass

DEFAULT_CODEX_COMMAND = "codex"
DEFAULT_CODEX_TIMEOUT_SECONDS = 900


@dataclass(frozen=True, slots=True)
class CodexModelConfig:
    model: str
    reasoning_effort: str


def resolve_codex_model_config(
    *,
    default_model: str,
    default_reasoning_effort: str,
    workflow_model_override: str | None = None,
    workflow_reasoning_effort_override: str | None = None,
    legacy_model_override: str | None = None,
    legacy_reasoning_effort_override: str | None = None,
) -> CodexModelConfig:
    """Resolve model and effort independently with presence-aware overrides."""

    return CodexModelConfig(
        model=_resolve_setting(
            workflow_override=workflow_model_override,
            legacy_override=legacy_model_override,
            default=default_model,
        ),
        reasoning_effort=_resolve_setting(
            workflow_override=workflow_reasoning_effort_override,
            legacy_override=legacy_reasoning_effort_override,
            default=default_reasoning_effort,
        ),
    )


def append_codex_reasoning_effort(args: list[str], reasoning_effort: str) -> None:
    effort = reasoning_effort.strip()
    if not effort:
        return
    args.extend(["-c", f"model_reasoning_effort={json.dumps(effort)}"])


def _resolve_setting(
    *,
    workflow_override: str | None,
    legacy_override: str | None,
    default: str,
) -> str:
    if workflow_override is not None:
        return workflow_override.strip()
    if legacy_override is not None:
        return legacy_override.strip()
    return default
