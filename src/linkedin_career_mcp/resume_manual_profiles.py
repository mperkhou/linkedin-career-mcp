from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from linkedin_career_mcp.codex_cli import CodexModelConfig, resolve_codex_model_config


class ManualPassProfileKey(StrEnum):
    ECONOMY = "economy"
    REGULAR = "regular"
    PREMIUM = "premium"


@dataclass(frozen=True, slots=True)
class ManualPassProfile:
    key: ManualPassProfileKey
    model: str
    reasoning_effort: str


@dataclass(frozen=True, slots=True)
class ResolvedManualPassConfig:
    profile: ManualPassProfile
    model: str
    reasoning_effort: str


DEFAULT_MANUAL_PASS_PROFILE = ManualPassProfileKey.REGULAR
MANUAL_PASS_PROFILES: Mapping[ManualPassProfileKey, ManualPassProfile] = MappingProxyType(
    {
        ManualPassProfileKey.ECONOMY: ManualPassProfile(
            key=ManualPassProfileKey.ECONOMY,
            model="gpt-5.6-terra",
            reasoning_effort="high",
        ),
        ManualPassProfileKey.REGULAR: ManualPassProfile(
            key=ManualPassProfileKey.REGULAR,
            model="gpt-5.6-sol",
            reasoning_effort="high",
        ),
        ManualPassProfileKey.PREMIUM: ManualPassProfile(
            key=ManualPassProfileKey.PREMIUM,
            model="gpt-5.6-sol",
            reasoning_effort="xhigh",
        ),
    }
)


def parse_manual_pass_profile(value: str | ManualPassProfileKey) -> ManualPassProfile:
    """Parse an allowlisted manual-pass profile without aliases or coercion."""

    try:
        key = ManualPassProfileKey(value)
    except ValueError as exc:
        allowed = ", ".join(profile.value for profile in ManualPassProfileKey)
        raise ValueError(
            f"invalid manual-pass profile {value!r}; expected one of: {allowed}"
        ) from exc
    return MANUAL_PASS_PROFILES[key]


def parse_manual_pass_profile_key(value: str) -> ManualPassProfileKey:
    return parse_manual_pass_profile(value).key


def resolve_manual_pass_config(
    *,
    profile: str | ManualPassProfileKey = DEFAULT_MANUAL_PASS_PROFILE,
    workflow_model_override: str | None = None,
    workflow_reasoning_effort_override: str | None = None,
    legacy_model_override: str | None = None,
    legacy_reasoning_effort_override: str | None = None,
) -> ResolvedManualPassConfig:
    selected_profile = parse_manual_pass_profile(profile)
    resolved: CodexModelConfig = resolve_codex_model_config(
        default_model=selected_profile.model,
        default_reasoning_effort=selected_profile.reasoning_effort,
        workflow_model_override=workflow_model_override,
        workflow_reasoning_effort_override=workflow_reasoning_effort_override,
        legacy_model_override=legacy_model_override,
        legacy_reasoning_effort_override=legacy_reasoning_effort_override,
    )
    return ResolvedManualPassConfig(
        profile=selected_profile,
        model=resolved.model,
        reasoning_effort=resolved.reasoning_effort,
    )
