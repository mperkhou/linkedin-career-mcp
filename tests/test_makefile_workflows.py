from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _make_dry_run(*args: str) -> str:
    if shutil.which("make") is None:
        pytest.skip("make is not available")
    result = subprocess.run(  # noqa: S603
        ["make", "-n", *args],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def test_skill_link_make_target_links_agentic_controller_by_default() -> None:
    output = _make_dry_run("skill-link")

    assert "linkedin-career-mcp" in output
    assert "master-resume-yaml" in output
    assert "manual-resume-passthrough" in output
    assert "agentic-workflow-init" in output
    assert "agentic-workflow-controller" in output


def test_skill_link_make_target_honors_single_skill_override() -> None:
    output = _make_dry_run("skill-link", "SKILL_NAME=agentic-workflow-controller")

    assert "agentic-workflow-controller" in output
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


def test_highlight_draft_resumes_make_target_uses_codex_workflow() -> None:
    output = _make_dry_run(
        "highlight-draft-resumes",
        "JOB_IDS=url-123",
        "CODEX_COMMAND=codex",
        "CODEX_MODEL=gpt-5.5",
        "CODEX_REASONING_EFFORT=xhigh",
        "CODEX_TIMEOUT_SECONDS=900",
        "HIGHLIGHT_RESUME_VARIANT=v2",
        "HIGHLIGHT_EXPERIENCE_COMPANY=Oracle",
    )

    assert "scripts/application_resume_highlight_drafts.py" in output
    assert '--codex-command "codex"' in output
    assert '--codex-model "gpt-5.5"' in output
    assert '--codex-reasoning-effort "xhigh"' in output
    assert '--timeout-seconds "900"' in output
    assert '--retry-count "1"' in output
    assert "--variant-key v2" in output
    assert "--experience-company Oracle" in output
    assert "for job_id in url-123" in output
    assert 'job_args="$job_args --job-id $job_id"' in output


def test_manual_pass_resumes_make_target_uses_codex_workflow() -> None:
    output = _make_dry_run(
        "manual-pass-resumes",
        "JOB_IDS=url-123",
        "CODEX_COMMAND=codex",
        "CODEX_MODEL=gpt-5.5",
        "CODEX_REASONING_EFFORT=xhigh",
        "CODEX_TIMEOUT_SECONDS=900",
    )

    assert "scripts/application_resume_manual_pass.py" in output
    assert '--master-resume "profile/MASTER-RESUME.yml"' in output
    assert '--master-resume-text "profile/MP-MASTER-RESUME.txt"' in output
    assert '--codex-command "codex"' in output
    assert '--codex-model "gpt-5.5"' in output
    assert '--codex-reasoning-effort "xhigh"' in output
    assert '--timeout-seconds "900"' in output
    assert '--retry-count "1"' in output
    assert "for job_id in url-123" in output
    assert 'job_args="$job_args --job-id $job_id"' in output
