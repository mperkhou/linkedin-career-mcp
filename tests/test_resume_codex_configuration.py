from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from linkedin_career_mcp.resume_manual_pass import build_manual_pass_model_metadata
from linkedin_career_mcp.resume_manual_profiles import (
    DEFAULT_MANUAL_PASS_PROFILE,
    MANUAL_PASS_PROFILES,
    ManualPassProfileKey,
    parse_manual_pass_profile,
    resolve_manual_pass_config,
)
from scripts import application_resume_highlight_drafts as highlight_cli
from scripts import application_resume_manual_pass as manual_cli

_CONFIG_ENVIRONMENT_NAMES = (
    manual_cli.MANUAL_PASS_PROFILE_ENV,
    manual_cli.MANUAL_PASS_CODEX_MODEL_ENV,
    manual_cli.MANUAL_PASS_CODEX_REASONING_EFFORT_ENV,
    highlight_cli.HIGHLIGHT_CODEX_MODEL_ENV,
    highlight_cli.HIGHLIGHT_CODEX_REASONING_EFFORT_ENV,
    manual_cli.LEGACY_CODEX_MODEL_ENV,
    manual_cli.LEGACY_CODEX_REASONING_EFFORT_ENV,
)


@pytest.mark.parametrize(
    ("profile_key", "model", "reasoning_effort"),
    [
        ("economy", "gpt-5.6-terra", "high"),
        ("regular", "gpt-5.6-sol", "high"),
        ("premium", "gpt-5.6-sol", "xhigh"),
    ],
)
def test_manual_pass_profile_registry_and_metadata(
    profile_key: str,
    model: str,
    reasoning_effort: str,
) -> None:
    config = resolve_manual_pass_config(profile=profile_key)

    assert config.profile is MANUAL_PASS_PROFILES[ManualPassProfileKey(profile_key)]
    assert config.model == model
    assert config.reasoning_effort == reasoning_effort
    assert build_manual_pass_model_metadata(
        config=config,
        codex_command="codex",
    ) == {
        "client": "Codex CLI",
        "profile": profile_key,
        "model": model,
        "reasoning_effort": reasoning_effort,
        "codex_command": "codex",
    }


def test_manual_pass_profile_registry_is_typed_immutable_and_regular_by_default() -> None:
    assert DEFAULT_MANUAL_PASS_PROFILE is ManualPassProfileKey.REGULAR
    assert parse_manual_pass_profile(DEFAULT_MANUAL_PASS_PROFILE).model == "gpt-5.6-sol"

    with pytest.raises(TypeError):
        MANUAL_PASS_PROFILES[ManualPassProfileKey.REGULAR] = MANUAL_PASS_PROFILES[  # type: ignore[index]
            ManualPassProfileKey.ECONOMY
        ]
    with pytest.raises(FrozenInstanceError):
        MANUAL_PASS_PROFILES[ManualPassProfileKey.REGULAR].model = "changed"  # type: ignore[misc]


@pytest.mark.parametrize("value", ["", "Regular", "ultra", " premium "])
def test_manual_pass_profile_parser_rejects_non_allowlisted_values(value: str) -> None:
    with pytest.raises(ValueError, match="invalid manual-pass profile"):
        parse_manual_pass_profile(value)


def test_manual_pass_resolution_applies_model_and_effort_precedence_independently() -> None:
    config = resolve_manual_pass_config(
        profile="premium",
        workflow_model_override="workflow/model",
        legacy_model_override="legacy/model",
        legacy_reasoning_effort_override="medium",
    )

    assert config.model == "workflow/model"
    assert config.reasoning_effort == "medium"

    config = resolve_manual_pass_config(
        profile="economy",
        workflow_reasoning_effort_override="xhigh",
        legacy_model_override="legacy/model",
        legacy_reasoning_effort_override="medium",
    )

    assert config.model == "legacy/model"
    assert config.reasoning_effort == "xhigh"


def test_manual_pass_resolution_preserves_explicit_empty_effort_as_inherit() -> None:
    config = resolve_manual_pass_config(
        profile="premium",
        workflow_reasoning_effort_override="",
        legacy_reasoning_effort_override="high",
    )

    assert config.model == "gpt-5.6-sol"
    assert config.reasoning_effort == ""
    assert build_manual_pass_model_metadata(
        config=config,
        codex_command="codex --operator-config",
    )["reasoning_effort"] == ""


def test_manual_pass_explicit_operator_override_allows_sol_ultra() -> None:
    config = resolve_manual_pass_config(
        profile="regular",
        workflow_model_override="gpt-5.6-sol",
        workflow_reasoning_effort_override="ultra",
    )

    assert config.profile.key is ManualPassProfileKey.REGULAR
    assert (config.model, config.reasoning_effort) == ("gpt-5.6-sol", "ultra")


def test_manual_cli_resolves_cli_workflow_env_legacy_and_profile_per_field(
    monkeypatch,
) -> None:
    _clear_config_environment(monkeypatch)
    monkeypatch.setenv(manual_cli.MANUAL_PASS_PROFILE_ENV, "economy")
    monkeypatch.setenv(manual_cli.MANUAL_PASS_CODEX_MODEL_ENV, "workflow-env/model")
    monkeypatch.setenv(manual_cli.LEGACY_CODEX_MODEL_ENV, "legacy/model")
    monkeypatch.setenv(manual_cli.LEGACY_CODEX_REASONING_EFFORT_ENV, "medium")
    args = manual_cli.build_arg_parser().parse_args(
        [
            "--job-id",
            "123",
            "--manual-pass-profile",
            "premium",
            "--codex-reasoning-effort",
            "xhigh",
        ]
    )

    config = manual_cli._resolve_codex_config(args)  # noqa: SLF001

    assert config.profile.key is ManualPassProfileKey.PREMIUM
    assert config.model == "workflow-env/model"
    assert config.reasoning_effort == "xhigh"


def test_manual_cli_empty_workflow_env_effort_beats_legacy(monkeypatch) -> None:
    _clear_config_environment(monkeypatch)
    monkeypatch.setenv(manual_cli.MANUAL_PASS_CODEX_REASONING_EFFORT_ENV, "")
    monkeypatch.setenv(manual_cli.LEGACY_CODEX_REASONING_EFFORT_ENV, "xhigh")
    args = manual_cli.build_arg_parser().parse_args(["--job-id", "123"])

    config = manual_cli._resolve_codex_config(args)  # noqa: SLF001

    assert config.profile.key is ManualPassProfileKey.REGULAR
    assert config.model == "gpt-5.6-sol"
    assert config.reasoning_effort == ""


def test_manual_cli_explicit_model_and_legacy_effort_precedence(monkeypatch) -> None:
    _clear_config_environment(monkeypatch)
    monkeypatch.setenv(manual_cli.MANUAL_PASS_CODEX_MODEL_ENV, "environment/model")
    monkeypatch.setenv(manual_cli.LEGACY_CODEX_REASONING_EFFORT_ENV, "medium")
    args = manual_cli.build_arg_parser().parse_args(
        ["--job-id", "123", "--codex-model", "cli/model"]
    )

    config = manual_cli._resolve_codex_config(args)  # noqa: SLF001

    assert config.model == "cli/model"
    assert config.reasoning_effort == "medium"


def test_manual_cli_legacy_model_and_workflow_effort_precedence(monkeypatch) -> None:
    _clear_config_environment(monkeypatch)
    monkeypatch.setenv(manual_cli.LEGACY_CODEX_MODEL_ENV, "legacy/model")
    monkeypatch.setenv(manual_cli.MANUAL_PASS_CODEX_REASONING_EFFORT_ENV, "xhigh")
    args = manual_cli.build_arg_parser().parse_args(["--job-id", "123"])

    config = manual_cli._resolve_codex_config(args)  # noqa: SLF001

    assert config.model == "legacy/model"
    assert config.reasoning_effort == "xhigh"


def test_manual_cli_explicit_empty_effort_beats_environment(monkeypatch) -> None:
    _clear_config_environment(monkeypatch)
    monkeypatch.setenv(manual_cli.MANUAL_PASS_CODEX_REASONING_EFFORT_ENV, "high")
    monkeypatch.setenv(manual_cli.LEGACY_CODEX_REASONING_EFFORT_ENV, "xhigh")
    args = manual_cli.build_arg_parser().parse_args(
        ["--job-id", "123", "--codex-reasoning-effort", ""]
    )

    config = manual_cli._resolve_codex_config(args)  # noqa: SLF001

    assert config.reasoning_effort == ""


def test_manual_cli_rejects_invalid_environment_profile(monkeypatch) -> None:
    _clear_config_environment(monkeypatch)
    monkeypatch.setenv(manual_cli.MANUAL_PASS_PROFILE_ENV, "ultra")
    args = manual_cli.build_arg_parser().parse_args(["--job-id", "123"])

    with pytest.raises(ValueError, match="invalid manual-pass profile"):
        manual_cli._resolve_codex_config(args)  # noqa: SLF001


def test_highlight_cli_has_distinct_fixed_default_and_ignores_manual_profile(
    monkeypatch,
) -> None:
    _clear_config_environment(monkeypatch)
    monkeypatch.setenv(manual_cli.MANUAL_PASS_PROFILE_ENV, "premium")
    manual_args = manual_cli.build_arg_parser().parse_args(["--job-id", "123"])
    highlight_args = highlight_cli.build_arg_parser().parse_args([])

    manual_config = manual_cli._resolve_codex_config(manual_args)  # noqa: SLF001
    highlight_config = highlight_cli._resolve_codex_config(highlight_args)  # noqa: SLF001

    assert (manual_config.model, manual_config.reasoning_effort) == (
        "gpt-5.6-sol",
        "xhigh",
    )
    assert (highlight_config.model, highlight_config.reasoning_effort) == (
        "gpt-5.6-luna",
        "high",
    )


def test_highlight_cli_resolves_fields_independently_and_preserves_empty_effort(
    monkeypatch,
) -> None:
    _clear_config_environment(monkeypatch)
    monkeypatch.setenv(highlight_cli.HIGHLIGHT_CODEX_MODEL_ENV, "highlight/model")
    monkeypatch.setenv(highlight_cli.HIGHLIGHT_CODEX_REASONING_EFFORT_ENV, "")
    monkeypatch.setenv(highlight_cli.LEGACY_CODEX_MODEL_ENV, "legacy/model")
    monkeypatch.setenv(highlight_cli.LEGACY_CODEX_REASONING_EFFORT_ENV, "xhigh")
    args = highlight_cli.build_arg_parser().parse_args([])

    config = highlight_cli._resolve_codex_config(args)  # noqa: SLF001

    assert config.model == "highlight/model"
    assert config.reasoning_effort == ""


def test_highlight_cli_explicit_model_and_legacy_effort_precedence(monkeypatch) -> None:
    _clear_config_environment(monkeypatch)
    monkeypatch.setenv(highlight_cli.HIGHLIGHT_CODEX_MODEL_ENV, "environment/model")
    monkeypatch.setenv(highlight_cli.LEGACY_CODEX_REASONING_EFFORT_ENV, "medium")
    args = highlight_cli.build_arg_parser().parse_args(
        ["--codex-model", "cli/model"]
    )

    config = highlight_cli._resolve_codex_config(args)  # noqa: SLF001

    assert config.model == "cli/model"
    assert config.reasoning_effort == "medium"


def test_highlight_cli_legacy_model_and_explicit_effort_precedence(monkeypatch) -> None:
    _clear_config_environment(monkeypatch)
    monkeypatch.setenv(highlight_cli.LEGACY_CODEX_MODEL_ENV, "legacy/model")
    monkeypatch.setenv(highlight_cli.HIGHLIGHT_CODEX_REASONING_EFFORT_ENV, "medium")
    args = highlight_cli.build_arg_parser().parse_args(
        ["--codex-reasoning-effort", "xhigh"]
    )

    config = highlight_cli._resolve_codex_config(args)  # noqa: SLF001

    assert config.model == "legacy/model"
    assert config.reasoning_effort == "xhigh"


def test_highlight_cli_explicit_empty_effort_beats_environment(monkeypatch) -> None:
    _clear_config_environment(monkeypatch)
    monkeypatch.setenv(highlight_cli.HIGHLIGHT_CODEX_REASONING_EFFORT_ENV, "high")
    monkeypatch.setenv(highlight_cli.LEGACY_CODEX_REASONING_EFFORT_ENV, "xhigh")
    args = highlight_cli.build_arg_parser().parse_args(
        ["--codex-reasoning-effort", ""]
    )

    config = highlight_cli._resolve_codex_config(args)  # noqa: SLF001

    assert config.reasoning_effort == ""


def test_composite_default_configs_resolve_independently(monkeypatch) -> None:
    _clear_config_environment(monkeypatch)
    manual_args = manual_cli.build_arg_parser().parse_args(["--job-id", "123"])
    highlight_args = highlight_cli.build_arg_parser().parse_args([])

    manual_config = manual_cli._resolve_codex_config(manual_args)  # noqa: SLF001
    highlight_config = highlight_cli._resolve_codex_config(highlight_args)  # noqa: SLF001

    assert manual_config.profile.key is ManualPassProfileKey.REGULAR
    assert (manual_config.model, manual_config.reasoning_effort) == (
        "gpt-5.6-sol",
        "high",
    )
    assert (highlight_config.model, highlight_config.reasoning_effort) == (
        "gpt-5.6-luna",
        "high",
    )


def _clear_config_environment(monkeypatch) -> None:
    for name in _CONFIG_ENVIRONMENT_NAMES:
        monkeypatch.delenv(name, raising=False)
