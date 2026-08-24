from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CODEX_CONFIG_ENVIRONMENT_NAMES = (
    "CODEX_MODEL",
    "CODEX_REASONING_EFFORT",
    "MANUAL_PASS_PROFILE",
    "MANUAL_PASS_CODEX_MODEL",
    "MANUAL_PASS_CODEX_REASONING_EFFORT",
    "HIGHLIGHT_CODEX_MODEL",
    "HIGHLIGHT_CODEX_REASONING_EFFORT",
    "LINKEDIN_CAREER_MCP_MANUAL_PASS_PROFILE",
    "LINKEDIN_CAREER_MCP_MANUAL_PASS_CODEX_MODEL",
    "LINKEDIN_CAREER_MCP_MANUAL_PASS_CODEX_REASONING_EFFORT",
    "LINKEDIN_CAREER_MCP_HIGHLIGHT_CODEX_MODEL",
    "LINKEDIN_CAREER_MCP_HIGHLIGHT_CODEX_REASONING_EFFORT",
    "LINKEDIN_CAREER_MCP_CODEX_MODEL",
    "LINKEDIN_CAREER_MCP_CODEX_REASONING_EFFORT",
)


def _make_dry_run(*args: str) -> str:
    if shutil.which("make") is None:
        pytest.skip("make is not available")
    environment = os.environ.copy()
    for name in _CODEX_CONFIG_ENVIRONMENT_NAMES:
        environment.pop(name, None)
    result = subprocess.run(  # noqa: S603
        ["make", "-n", *args],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    return result.stdout


def test_skill_link_make_target_links_active_default_skills() -> None:
    output = _make_dry_run("skill-link")

    expected_skill_names = (
        "linkedin-career-mcp master-resume-yaml manual-resume-passthrough "
        "agentic-feature-workflow"
    )

    assert f"for skill_name in {expected_skill_names};" in output
    assert "agentic-workflow-init" not in output
    assert "agentic-workflow-controller" not in output


@pytest.mark.parametrize(
    "legacy_skill",
    ["agentic-workflow-init", "agentic-workflow-controller"],
)
def test_skill_link_make_target_honors_legacy_single_skill_override(
    legacy_skill: str,
) -> None:
    output = _make_dry_run("skill-link", f"SKILL_NAME={legacy_skill}")

    assert f"for skill_name in {legacy_skill};" in output
    assert "linkedin-career-mcp master-resume-yaml manual-resume-passthrough" not in output


def test_regenerate_draft_resumes_make_target_uses_final_jod_workflow() -> None:
    output = _make_dry_run(
        "regenerate-draft-resumes",
        "JOB_IDS=url-123",
        "FIRST_DRAFT_FORCE=1",
    )

    assert "scripts/application_resume_generate_drafts.py" in output
    assert '--master-resume "profile/MASTER-RESUME.yml"' in output
    assert '--api-model "z-ai/glm-5.2"' in output
    assert '--jod-model "z-ai/glm-5.2"' in output
    assert '--llm-timeout-seconds "300"' in output
    assert '--llm-retries "1"' in output
    assert "for job_id in url-123" in output
    assert 'job_args="$job_args --job-id $job_id"' in output
    assert "$job_args $force_arg" in output
    assert 'force_arg="--force"' in output
    assert "experimental" not in output.casefold()


def test_regenerate_draft_resumes_make_target_honors_resume_and_model_overrides() -> None:
    output = _make_dry_run(
        "regenerate-draft-resumes",
        "JOB_IDS=url-123",
        "MASTER_RESUME=profile/custom.yml",
        "CORE_SKILL_MODEL=core/example",
        "JOD_MODEL=example/model",
        "FIRST_DRAFT_LLM_TIMEOUT_SECONDS=45",
    )

    assert '--master-resume "profile/custom.yml"' in output
    assert '--api-model "core/example"' in output
    assert '--jod-model "example/model"' in output
    assert '--llm-timeout-seconds "45"' in output
    assert '--llm-retries "1"' in output
    assert "for job_id in url-123" in output
    assert "$job_args $force_arg" in output


def test_regenerate_resumes_make_target_runs_v1_then_v2_workflow() -> None:
    output = _make_dry_run(
        "regenerate-resumes",
        "JOB_IDS=url-123",
        "FIRST_DRAFT_FORCE=1",
    )

    assert "scripts/application_resume_generate_drafts.py" in output
    assert "linkedin-career-refine-resume" in output
    assert output.index("scripts/application_resume_generate_drafts.py") < output.index(
        "linkedin-career-refine-resume"
    )
    assert '--api-model "z-ai/glm-5.2"' in output
    assert '--jod-model "z-ai/glm-5.2"' in output
    assert '--llm-timeout-seconds "300"' in output
    assert '--llm-retries "1"' in output
    assert '--api-timeout-seconds "600"' in output
    assert '--api-retries "1"' in output
    assert "for job_id in url-123" in output


def test_refine_draft_resumes_make_target_uses_glm_second_pass_model() -> None:
    output = _make_dry_run(
        "refine-draft-resumes",
        "JOB_IDS=url-123",
    )

    assert "linkedin-career-refine-resume" in output
    assert 'job_args="$job_args --job-id $job_id"' in output
    assert '--master-resume "profile/MASTER-RESUME.yml"' in output
    assert '--api-model "z-ai/glm-5.2"' in output
    assert '--api-timeout-seconds "600"' in output
    assert '--api-retries "1"' in output
    assert "for job_id in url-123" in output


def test_refine_draft_resumes_make_target_defaults_to_all_active() -> None:
    output = _make_dry_run("refine-draft-resumes")

    assert "linkedin-career-refine-resume" in output
    assert 'job_args="--all-active"' in output
    assert '--api-model "z-ai/glm-5.2"' in output
    assert '--api-timeout-seconds "600"' in output
    assert '--api-retries "1"' in output


def test_highlight_draft_resumes_make_target_uses_workflow_specific_overrides() -> None:
    output = _make_dry_run(
        "highlight-draft-resumes",
        "JOB_IDS=url-123",
        "CODEX_COMMAND=codex",
        "CODEX_MODEL=legacy/model",
        "CODEX_REASONING_EFFORT=medium",
        "HIGHLIGHT_CODEX_MODEL=highlight/model",
        "HIGHLIGHT_CODEX_REASONING_EFFORT=high",
        "CODEX_TIMEOUT_SECONDS=900",
        "HIGHLIGHT_RESUME_VARIANT=v2",
        "HIGHLIGHT_EXPERIENCE_COMPANY=Oracle",
    )

    assert "scripts/application_resume_highlight_drafts.py" in output
    assert '--codex-command "codex"' in output
    assert '--codex-model "highlight/model"' in output
    assert '--codex-reasoning-effort "high"' in output
    assert "legacy/model" not in output
    assert '--codex-reasoning-effort "medium"' not in output
    assert '--timeout-seconds "900"' in output
    assert '--retry-count "1"' in output
    assert "--variant-key v2" in output
    assert "--experience-company Oracle" in output
    assert "for job_id in url-123" in output
    assert 'job_args="$job_args --job-id $job_id"' in output


def test_manual_pass_resumes_make_target_uses_profile_and_workflow_overrides() -> None:
    output = _make_dry_run(
        "manual-pass-resumes",
        "JOB_IDS=url-123",
        "CODEX_COMMAND=codex",
        "MANUAL_PASS_PROFILE=premium",
        "MANUAL_PASS_CODEX_MODEL=manual/model",
        "MANUAL_PASS_CODEX_REASONING_EFFORT=xhigh",
        "CODEX_MODEL=legacy/model",
        "CODEX_REASONING_EFFORT=medium",
        "CODEX_TIMEOUT_SECONDS=900",
    )

    assert "scripts/application_resume_manual_pass.py" in output
    assert '--master-resume "profile/MASTER-RESUME.yml"' in output
    assert '--master-resume-text "profile/MP-MASTER-RESUME.txt"' in output
    assert '--codex-command "codex"' in output
    assert '--manual-pass-profile "premium"' in output
    assert '--codex-model "manual/model"' in output
    assert '--codex-reasoning-effort "xhigh"' in output
    assert "legacy/model" not in output
    assert '--codex-reasoning-effort "medium"' not in output
    assert '--timeout-seconds "900"' in output
    assert '--retry-count "1"' in output
    assert "for job_id in url-123" in output
    assert 'job_args="$job_args --job-id $job_id"' in output


def test_codex_make_targets_use_distinct_defaults_without_overrides() -> None:
    manual_output = _make_dry_run("manual-pass-resumes", "JOB_IDS=url-123")
    highlight_output = _make_dry_run("highlight-draft-resumes", "JOB_IDS=url-123")

    assert '--manual-pass-profile "regular"' in manual_output
    assert "--codex-model" not in manual_output
    assert "--codex-reasoning-effort" not in manual_output
    assert '--codex-model "gpt-5.6-luna"' in highlight_output
    assert '--codex-reasoning-effort "high"' in highlight_output


def test_codex_make_targets_apply_legacy_fallbacks_per_field() -> None:
    manual_output = _make_dry_run(
        "manual-pass-resumes",
        "JOB_IDS=url-123",
        "MANUAL_PASS_PROFILE=economy",
        "MANUAL_PASS_CODEX_MODEL=manual/model",
        "CODEX_REASONING_EFFORT=medium",
    )
    highlight_output = _make_dry_run(
        "highlight-draft-resumes",
        "JOB_IDS=url-123",
        "CODEX_MODEL=legacy/model",
        "HIGHLIGHT_CODEX_REASONING_EFFORT=xhigh",
    )

    assert '--manual-pass-profile "economy"' in manual_output
    assert '--codex-model "manual/model"' in manual_output
    assert '--codex-reasoning-effort "medium"' in manual_output
    assert '--codex-model "legacy/model"' in highlight_output
    assert '--codex-reasoning-effort "xhigh"' in highlight_output


def test_codex_make_targets_apply_inverse_per_field_precedence() -> None:
    manual_output = _make_dry_run(
        "manual-pass-resumes",
        "JOB_IDS=url-123",
        "CODEX_MODEL=legacy/model",
        "MANUAL_PASS_CODEX_REASONING_EFFORT=ultra",
    )
    highlight_output = _make_dry_run(
        "highlight-draft-resumes",
        "JOB_IDS=url-123",
        "HIGHLIGHT_CODEX_MODEL=highlight/model",
        "CODEX_REASONING_EFFORT=medium",
    )

    assert '--codex-model "legacy/model"' in manual_output
    assert '--codex-reasoning-effort "ultra"' in manual_output
    assert '--codex-model "highlight/model"' in highlight_output
    assert '--codex-reasoning-effort "medium"' in highlight_output


def test_workflow_environment_overrides_suppress_legacy_make_fallbacks() -> None:
    manual_output = _make_dry_run(
        "manual-pass-resumes",
        "JOB_IDS=url-123",
        "LINKEDIN_CAREER_MCP_MANUAL_PASS_CODEX_MODEL=workflow-env/model",
        "CODEX_MODEL=legacy/model",
    )
    highlight_output = _make_dry_run(
        "highlight-draft-resumes",
        "JOB_IDS=url-123",
        "LINKEDIN_CAREER_MCP_HIGHLIGHT_CODEX_REASONING_EFFORT=",
        "CODEX_REASONING_EFFORT=xhigh",
    )

    assert "--codex-model" not in manual_output
    assert "legacy/model" not in manual_output
    assert "--codex-reasoning-effort" not in highlight_output
    assert "xhigh" not in highlight_output


@pytest.mark.parametrize("target", ["manual-pass-resumes", "highlight-draft-resumes"])
def test_codex_make_targets_preserve_explicit_empty_legacy_effort(target: str) -> None:
    output = _make_dry_run(
        target,
        "JOB_IDS=url-123",
        "CODEX_REASONING_EFFORT=",
    )

    assert '--codex-reasoning-effort ""' in output


@pytest.mark.parametrize(
    ("target", "workflow_variable"),
    [
        ("manual-pass-resumes", "MANUAL_PASS_CODEX_REASONING_EFFORT="),
        ("highlight-draft-resumes", "HIGHLIGHT_CODEX_REASONING_EFFORT="),
    ],
)
def test_codex_make_targets_preserve_explicit_empty_effort(
    target: str,
    workflow_variable: str,
) -> None:
    output = _make_dry_run(
        target,
        "JOB_IDS=url-123",
        "CODEX_REASONING_EFFORT=xhigh",
        workflow_variable,
    )

    assert '--codex-reasoning-effort ""' in output
    assert '--codex-reasoning-effort "xhigh"' not in output
