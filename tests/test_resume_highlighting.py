from __future__ import annotations

import json
import subprocess

import pytest

from linkedin_career_mcp.resume_highlighting import (
    ResumeHighlightError,
    apply_highlight_response,
    build_resume_highlight_prompt,
    collect_highlight_bullets,
    collect_highlight_bullets_for_jobs,
    parse_highlight_response,
    run_codex_highlight,
)


def test_collect_highlight_bullets_returns_rendered_professional_experience_only():
    bullets = collect_highlight_bullets(_sample_resume())

    assert [(bullet.job_order, bullet.bullet_order) for bullet in bullets] == [
        ("1", "1"),
        ("2", "1"),
    ]
    assert bullets[0].job_label == "Oracle | Principal Member of Technical Staff"
    assert "mission-critical OCI automation clusters" in bullets[0].text


def test_collect_highlight_bullets_can_filter_to_one_company():
    bullets = collect_highlight_bullets_for_jobs(
        _sample_resume(),
        experience_company="Oracle",
    )

    assert [(bullet.job_order, bullet.bullet_order) for bullet in bullets] == [("1", "1")]
    assert "mission-critical OCI automation clusters" in bullets[0].text


def test_build_resume_highlight_prompt_limits_codex_to_structured_emphasis():
    prompt = build_resume_highlight_prompt(
        _sample_resume(),
        job_id="url-123",
        company="Example Co",
        job_title="Staff Platform Engineer",
    )

    assert "post-generation resume polish workflow" in prompt
    assert "Return only valid JSON" in prompt
    assert "Use only <strong> tags" in prompt
    assert '"job_id": "url-123"' in prompt
    assert "mission-critical OCI automation clusters" in prompt


def test_build_resume_highlight_prompt_can_limit_payload_to_one_company():
    prompt = build_resume_highlight_prompt(
        _sample_resume(),
        job_id="url-123",
        company="Example Co",
        job_title="Staff Platform Engineer",
        experience_company="Oracle",
    )

    assert '"experience_company_filter": "Oracle"' in prompt
    assert "mission-critical OCI automation clusters" in prompt
    assert "Built Python automation" not in prompt


def test_apply_highlight_response_adds_strong_tags_without_changing_plain_text():
    response = json.dumps(
        {
            "bullet_updates": [
                {
                    "job_order": "1",
                    "bullet_order": "1",
                    "text": (
                        "Led incident response and postmortems for "
                        "<strong>mission-critical OCI automation clusters</strong>, "
                        "debugging complex identity bugs under high pressure."
                    ),
                },
                {
                    "job_order": "2",
                    "bullet_order": "1",
                    "text": (
                        "Built <strong>Python automation</strong> for internal platform "
                        "teams and reduced manual release work."
                    ),
                },
            ]
        }
    )

    updated, stats = apply_highlight_response(_sample_resume(), response)

    assert stats.bullet_count == 2
    assert stats.strong_span_count == 2
    first_text = updated["professional_experience"]["jobs"][0]["bullet_points"][0]["text"]
    assert "<strong>mission-critical OCI automation clusters</strong>" in first_text
    assert "under high pressure." in first_text


def test_apply_highlight_response_can_limit_updates_to_one_company():
    response = json.dumps(
        {
            "bullet_updates": [
                {
                    "job_order": "1",
                    "bullet_order": "1",
                    "text": (
                        "Led incident response and postmortems for "
                        "<strong>mission-critical OCI automation clusters</strong>, "
                        "debugging complex identity bugs under high pressure."
                    ),
                }
            ]
        }
    )

    updated, stats = apply_highlight_response(
        _sample_resume(),
        response,
        experience_company="Oracle",
    )

    assert stats.bullet_count == 1
    assert stats.strong_span_count == 1
    oracle_text = updated["professional_experience"]["jobs"][0]["bullet_points"][0]["text"]
    geico_text = updated["professional_experience"]["jobs"][1]["bullet_points"][0]["text"]
    assert "<strong>mission-critical OCI automation clusters</strong>" in oracle_text
    assert "<strong>" not in geico_text


def test_apply_highlight_response_rejects_changed_text():
    response = json.dumps(
        {
            "bullet_updates": [
                {
                    "job_order": "1",
                    "bullet_order": "1",
                    "text": (
                        "Led incident response and postmortems for "
                        "<strong>mission-critical OCI automation clusters</strong>."
                    ),
                },
                {
                    "job_order": "2",
                    "bullet_order": "1",
                    "text": (
                        "Built <strong>Python automation</strong> for internal platform "
                        "teams and reduced manual release work."
                    ),
                },
            ]
        }
    )

    with pytest.raises(ResumeHighlightError, match="changed the bullet text"):
        apply_highlight_response(_sample_resume(), response)


def test_apply_highlight_response_rejects_unsupported_tags():
    response = json.dumps(
        {
            "bullet_updates": [
                {
                    "job_order": "1",
                    "bullet_order": "1",
                    "text": (
                        "Led incident response and postmortems for "
                        "<em>mission-critical OCI automation clusters</em>, "
                        "debugging complex identity bugs under high pressure."
                    ),
                },
                {
                    "job_order": "2",
                    "bullet_order": "1",
                    "text": (
                        "Built <strong>Python automation</strong> for internal platform "
                        "teams and reduced manual release work."
                    ),
                },
            ]
        }
    )

    with pytest.raises(ResumeHighlightError, match="unsupported <em> tag"):
        apply_highlight_response(_sample_resume(), response)


def test_apply_highlight_response_rejects_missing_bullet_update():
    response = json.dumps(
        {
            "bullet_updates": [
                {
                    "job_order": "1",
                    "bullet_order": "1",
                    "text": (
                        "Led incident response and postmortems for "
                        "<strong>mission-critical OCI automation clusters</strong>, "
                        "debugging complex identity bugs under high pressure."
                    ),
                }
            ]
        }
    )

    with pytest.raises(ResumeHighlightError, match="Missing highlight updates"):
        apply_highlight_response(_sample_resume(), response)


def test_parse_highlight_response_accepts_fenced_json_for_cli_tolerance():
    updates = parse_highlight_response(
        """```json
{"bullet_updates": [{"job_order": "1", "bullet_order": "1", "text": "x"}]}
```"""
    )

    assert updates[0]["job_order"] == "1"


def test_run_codex_highlight_places_approval_flag_before_exec(tmp_path, monkeypatch):
    captured_args: list[str] = []

    def fake_run(args, **kwargs):
        captured_args.extend(args)
        output_path = args[args.index("--output-last-message") + 1]
        with open(output_path, "w", encoding="utf-8") as output_file:
            output_file.write('{"bullet_updates": []}')
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    response = run_codex_highlight(
        "prompt",
        project_root=tmp_path,
        codex_command="codex",
        codex_model="gpt-5.5",
    )

    assert response == '{"bullet_updates": []}'
    assert captured_args.index("--ask-for-approval") < captured_args.index("exec")
    assert captured_args[captured_args.index("--ask-for-approval") + 1] == "never"
    assert "-c" in captured_args
    assert 'model_reasoning_effort="xhigh"' in captured_args
    assert captured_args.index('model_reasoning_effort="xhigh"') < captured_args.index("exec")


def test_run_codex_highlight_retries_timeout(tmp_path, monkeypatch):
    calls = 0

    def fake_run(args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise subprocess.TimeoutExpired(cmd=args, timeout=kwargs["timeout"])
        output_path = args[args.index("--output-last-message") + 1]
        with open(output_path, "w", encoding="utf-8") as output_file:
            output_file.write('{"bullet_updates": []}')
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    response = run_codex_highlight(
        "prompt",
        project_root=tmp_path,
        codex_command="codex",
        retry_count=1,
    )

    assert calls == 2
    assert response == '{"bullet_updates": []}'


def _sample_resume() -> dict[str, object]:
    return {
        "professional_experience": {
            "jobs": [
                {
                    "order": 1,
                    "render": True,
                    "line_1": {
                        "company_name_text": "Oracle",
                        "position_name_text": "Principal Member of Technical Staff",
                    },
                    "bullet_points": [
                        {
                            "order": 1,
                            "render": True,
                            "text": (
                                "Led incident response and postmortems for "
                                "mission-critical OCI automation clusters, debugging "
                                "complex identity bugs under high pressure."
                            ),
                        },
                        {
                            "order": 2,
                            "render": False,
                            "text": "Hidden source bullet.",
                        },
                    ],
                },
                {
                    "order": 2,
                    "render": True,
                    "line_1": {
                        "company_name_text": "GEICO",
                        "position_name_text": "Automation Engineer",
                    },
                    "bullet_points": [
                        {
                            "order": 1,
                            "render": True,
                            "text": (
                                "Built Python automation for internal platform teams "
                                "and reduced manual release work."
                            ),
                        }
                    ],
                },
            ]
        },
        "education": {
            "entries": [
                {
                    "order": 1,
                    "render": True,
                    "bullet_points": [{"order": 1, "text": "Not a professional bullet."}],
                }
            ]
        },
    }
