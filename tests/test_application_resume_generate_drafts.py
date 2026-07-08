from __future__ import annotations

import asyncio
import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_generate_drafts_script() -> ModuleType:
    module_name = "application_resume_generate_drafts_for_tests"
    module_path = PROJECT_ROOT / "scripts" / "application_resume_generate_drafts.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


drafts = _load_generate_drafts_script()


def test_first_draft_llm_timeout_defaults_to_300_seconds() -> None:
    args = drafts.build_arg_parser().parse_args([])

    assert args.llm_timeout_seconds == 300.0
    assert args.llm_retries == 1


@pytest.mark.asyncio
async def test_first_draft_llm_step_times_out_with_job_and_step(capsys) -> None:
    async def slow_operation() -> dict[str, bool]:
        await asyncio.sleep(1)
        return {"ok": True}

    with pytest.raises(TimeoutError) as exc_info:
        await drafts._run_llm_step(
            job_id="url-123",
            step_name="core skill matching",
            timeout_seconds=0.01,
            operation=slow_operation,
        )

    message = str(exc_info.value)
    stderr = capsys.readouterr().err
    assert "core skill matching timed out for url-123 after 0.01 seconds." in message
    assert "[url-123] core skill matching: started (timeout=0.01s)" in stderr
    assert "[url-123] core skill matching: timed out after" in stderr
    assert "core skill matching timed out for url-123 after 0.01 seconds." in stderr


@pytest.mark.asyncio
async def test_first_draft_llm_step_logs_elapsed_completion(capsys) -> None:
    async def fast_operation() -> dict[str, bool]:
        return {"ok": True}

    result = await drafts._run_llm_step(
        job_id="url-123",
        step_name="JOD target extraction",
        timeout_seconds=300,
        operation=fast_operation,
    )

    stderr = capsys.readouterr().err
    assert result == {"ok": True}
    assert "[url-123] JOD target extraction: started (timeout=300s)" in stderr
    assert re.search(
        r"\[url-123\] JOD target extraction: completed in \d+\.\ds",
        stderr,
    )


@pytest.mark.asyncio
async def test_first_draft_llm_step_retries_timeout_once(capsys) -> None:
    calls = 0

    async def flaky_operation() -> dict[str, bool]:
        nonlocal calls
        calls += 1
        if calls == 1:
            await asyncio.sleep(1)
        return {"ok": True}

    result = await drafts._run_llm_step(
        job_id="url-123",
        step_name="Oracle experience rewrite",
        timeout_seconds=0.01,
        retry_count=1,
        operation=flaky_operation,
    )

    stderr = capsys.readouterr().err
    assert result == {"ok": True}
    assert calls == 2
    assert "Oracle experience rewrite attempt 1/2: timed out" in stderr
    assert "Oracle experience rewrite: retrying after timeout (attempt 2/2)" in stderr
    assert "Oracle experience rewrite attempt 2/2: completed" in stderr


@pytest.mark.asyncio
async def test_backport_candidate_wraps_all_rendered_experience_rewrites_in_timeout_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    master_resume_path = tmp_path / "MASTER-RESUME.yml"
    master_resume_path.write_text(
        yaml.safe_dump(_sample_generation_aro(), sort_keys=False),
        encoding="utf-8",
    )
    artifact_dir = tmp_path / "artifacts"
    calls: list[tuple[str, float | None, int]] = []
    stored: dict[str, object] = {}

    async def fake_run_llm_step(
        *,
        job_id: str,
        step_name: str,
        timeout_seconds: float | None,
        retry_count: int = 0,
        operation,
    ) -> object:
        assert job_id == "url-123"
        calls.append((step_name, timeout_seconds, retry_count))
        if step_name == "core skill matching":
            return {"core_technical_skills": []}
        if step_name == "JOD target extraction":
            return {"requirements_targets": ["Need Python automation."]}
        if step_name == "Oracle experience rewrite":
            return "\n".join(
                [
                    "Built Oracle automation support.",
                    "Hardened Oracle platform operations.",
                    "Improved Oracle release workflows.",
                    "Expanded Oracle observability coverage.",
                    "Protected Oracle configuration handling.",
                    "Diagnosed Oracle reliability issues.",
                ]
            )
        if step_name.startswith("experience rewrite job "):
            return "\n".join(
                [
                    f"Built {step_name} automation support.",
                    f"Supported {step_name} platform operations.",
                ]
            )
        raise AssertionError(f"unexpected step: {step_name}")

    def fake_render_resume_pdf_from_html(html: str) -> bytes:
        stored["resume_html"] = html
        return b"%PDF-test"

    def fake_store_application_resume_first_draft(**kwargs: object) -> None:
        stored.update(kwargs)

    monkeypatch.setattr(drafts, "_run_llm_step", fake_run_llm_step)
    monkeypatch.setattr(drafts, "render_resume_pdf_from_html", fake_render_resume_pdf_from_html)
    monkeypatch.setattr(
        drafts,
        "store_application_resume_first_draft",
        fake_store_application_resume_first_draft,
    )

    await drafts.backport_candidate(
        drafts.Candidate(
            job_id="url-123",
            company="Example Co",
            job_title="Platform Engineer",
            trimmed_jod="Need Python automation.",
        ),
        database_path=tmp_path / "applications.sqlite3",
        master_resume_path=master_resume_path,
        template_path=PROJECT_ROOT / "templates" / "resume" / "master_resume.html.j2",
        llm=object(),
        jod_llm=object(),
        jod_model="z-ai/glm-5.2",
        artifact_dir=artifact_dir,
        max_jod_chars=12_000,
        llm_timeout_seconds=12.5,
        llm_retry_count=2,
    )

    assert calls == [
        ("core skill matching", 12.5, 2),
        ("JOD target extraction", 12.5, 2),
        ("Oracle experience rewrite", 12.5, 2),
        ("experience rewrite job 2", 12.5, 2),
        ("experience rewrite job 3", 12.5, 2),
        ("experience rewrite job 4", 12.5, 2),
        ("experience rewrite job 5", 12.5, 2),
    ]
    rendered_html = str(stored["resume_html"])
    assert "Stamats Communications" in rendered_html
    assert "VIDA Diagnostics" in rendered_html
    stored_aro = yaml.safe_load(str(stored["application_resume_object"]))
    jobs_by_order = {
        job["order"]: job
        for job in stored_aro["professional_experience"]["jobs"]
    }
    assert [len(jobs_by_order[order]["bullet_points"]) for order in (4, 5)] == [2, 2]
    assert all(
        bullet["render"] is True
        for order in (4, 5)
        for bullet in jobs_by_order[order]["bullet_points"]
    )
    assert (artifact_dir / "url-123_job_4_rewrite_prompt.txt").exists()
    assert (artifact_dir / "url-123_job_5_rewrite_prompt.txt").exists()


def _sample_generation_aro() -> dict[str, object]:
    return {
        "header_top": {
            "line_1_name_header_text": "Max Perkhounkov",
            "contact_items": ["Iowa City, IA"],
        },
        "professional_summary": {
            "render": True,
            "paragraph": "Platform automation engineer with 10+ years of experience.",
        },
        "core_technical_skills": {"bullet_points": []},
        "professional_experience": {
            "jobs": [
                _sample_generation_job(
                    1,
                    "Oracle | Remote",
                    render=True,
                    min_bullets=6,
                    max_bullets=10,
                    bullet_count=6,
                ),
                _sample_generation_job(
                    2,
                    "University of Iowa Hospitals and Clinics | Iowa City, IA",
                    render=True,
                    min_bullets=2,
                    max_bullets=5,
                    bullet_count=3,
                ),
                _sample_generation_job(
                    3,
                    "Steindler Orthopedic Clinic | Iowa City, IA",
                    render=True,
                    min_bullets=2,
                    max_bullets=5,
                    bullet_count=3,
                ),
                _sample_generation_job(
                    4,
                    "Stamats Communications | Cedar Rapids, IA",
                    render=True,
                    min_bullets=2,
                    max_bullets=5,
                    bullet_count=3,
                ),
                _sample_generation_job(
                    5,
                    "VIDA Diagnostics | Coralville, IA",
                    render=True,
                    min_bullets=2,
                    max_bullets=5,
                    bullet_count=3,
                ),
            ]
        },
    }


def _sample_generation_job(
    order: int,
    company: str,
    *,
    render: bool,
    min_bullets: int,
    max_bullets: int,
    bullet_count: int,
) -> dict[str, object]:
    return {
        "order": order,
        "render": render,
        "min_bullet_points": min_bullets,
        "max_bullet_points": max_bullets,
        "line_1": {
            "company_name_text": company,
            "position_name_text": "Systems Engineer",
            "position_dates_text": "2020 - Present",
        },
        "bullet_points": [
            {
                "text": f"{company} source evidence bullet {index}.",
                "render": False,
                "bullet_point_total_match_count": 0,
                "skills": [],
            }
            for index in range(1, bullet_count + 1)
        ],
    }
