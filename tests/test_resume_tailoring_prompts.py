from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest
from fixture_loaders import load_linkedin_job_fixture

from linkedin_career_mcp.config import load_settings
from linkedin_career_mcp.workflows.matching import (
    AI_GENERATION_NOTE,
    DEFAULT_SCJDIR,
    RESUME_HEADER_CONTACT,
    RESUME_HEADER_NAME,
    ProfileDocument,
    _coerce_core_skill_sections,
    _looks_like_recommendations,
    _render_resume_template,
    _resume_sections_prompt,
    _scjdir_prompt,
)

SAMPLE_RESUME = f"""
Max Perkhounkov
Senior Platform Software Engineer

Professional Summary
Platform engineer focused on distributed systems, automation, APIs, and reliability.

Professional Experience
{DEFAULT_SCJDIR}

Earlier Experience
Built healthcare integrations, analytics workflows, and operational software.
""".strip()

SAMPLE_CJD = """
Senior Platform Software Engineer IC3
Owns platform automation services, API integrations, observability pipelines, CI/CD release
automation, infrastructure-as-code, Linux automation, cross-team technical leadership, and
operational reliability for globally distributed infrastructure.
""".strip()


def test_cached_previous_run_job_fixtures_have_descriptions():
    headspace = load_linkedin_job_fixture("4419204491")
    terzo = load_linkedin_job_fixture("4423512582")

    assert headspace.company == "Headspace"
    assert headspace.title == "Senior Software Engineer, Backend"
    assert "Python/Django" in (headspace.description or "")
    assert terzo.company == "Terzo"
    assert terzo.title == "(Sr/Staff) Frontend Engineer"
    assert "React" in (terzo.description or "")


def test_scjdir_prompt_targets_current_role_not_general_advice():
    job = load_linkedin_job_fixture("4419204491")
    prompt = _scjdir_prompt(
        source_resume=ProfileDocument(Path("MP-RESUME-AGENTIC.pdf"), SAMPLE_RESUME),
        current_job_description=ProfileDocument(
            Path("Senior_Platform_Software_Engineer(IC3).pdf"),
            SAMPLE_CJD,
        ),
        job=job,
    )

    assert "Return only the replacement SCJDiR block" in prompt
    assert "Do not return advice" in prompt
    assert "Original SCJDiR:" in prompt
    assert "Current job description (CJD):" in prompt
    assert "Job opening description (JOD):" in prompt
    assert "Python/Django" in prompt


def test_resume_sections_prompt_limits_model_to_dynamic_sections():
    job = load_linkedin_job_fixture("4423512582")
    prompt = _resume_sections_prompt(
        source_resume=ProfileDocument(Path("MP-RESUME-AGENTIC.pdf"), SAMPLE_RESUME),
        current_job_description=ProfileDocument(
            Path("Senior_Platform_Software_Engineer(IC3).pdf"),
            SAMPLE_CJD,
        ),
        tailored_scjdir="Oracle | Remote\nSenior Technical Lead - Cloud Automation Engineer",
        job=job,
    )

    assert "Return only valid JSON" in prompt
    assert "Do not return markdown fences" in prompt
    assert "You only control:" in prompt
    assert "core_technical_skills" in prompt
    assert "prior_experience" in prompt
    assert "Do not include the header" in prompt
    assert "Tailored Oracle current-role SCJDiR" in prompt
    assert "React" in prompt


def test_render_resume_template_preserves_static_sections():
    text = _render_resume_template(
        tailored_scjdir=(
            "Oracle | Remote / International Datacenters\n"
            "Senior Technical Lead - Cloud Automation Engineer | Feb 2022 - Present\n"
            "- Built platform automation APIs."
        ),
        sections_plan={
            "core_technical_skills": [
                {"category": "Languages & Frameworks", "skills": ["Python", "Django", "LLMs"]},
            ],
            "prior_experience": [],
        },
    )

    assert RESUME_HEADER_NAME in text
    assert RESUME_HEADER_CONTACT in text
    assert AI_GENERATION_NOTE in text
    assert "Professional Summary" in text
    assert "Core Technical Skills" in text
    assert "- Languages & Frameworks: Python, Django, LLMs" in text
    assert "Professional Experience" in text
    assert "Education & Certifications" in text
    assert "Oracle Cloud Infrastructure AI Foundations Associate" in text


def test_core_skills_falls_back_to_missing_template_categories():
    sections = _coerce_core_skill_sections(
        [{"category": "Languages & Frameworks", "skills": ["Python", "LLMs"]}]
    )

    assert sections[0] == ("Languages & Frameworks", ["Python", "LLMs"])
    assert sections[1][0] == "Distributed Systems & Cloud"
    assert "AWS" in sections[1][1]


def test_recommendations_detection_distinguishes_resume_from_advice():
    assert _looks_like_recommendations("Here are recommendations to improve the resume.")
    assert not _looks_like_recommendations(
        "Max Perkhounkov\nProfessional Summary\nOracle | Remote\nBuilt platform APIs."
    )


@pytest.mark.skipif(
    os.getenv("LINKEDIN_CAREER_MCP_RUN_OLLAMA_FIXTURE_TESTS") != "1",
    reason="set LINKEDIN_CAREER_MCP_RUN_OLLAMA_FIXTURE_TESTS=1 to run local Qwen fixture tests",
)
async def test_qwen_accepts_cached_fixture_jod_smoke():
    settings = load_settings()
    job = load_linkedin_job_fixture("4419204491")
    prompt = f"""
Return one concise resume keyword phrase for this job opening.
Title: {job.title}
Company: {job.company}
JOD excerpt: {(job.description or "")[:300]}
""".strip()
    async with httpx.AsyncClient(timeout=45) as client:
        response = await client.post(
            f"{settings.ollama_base_url}/api/generate",
            json={
                "model": settings.ollama_model,
                "prompt": prompt,
                "stream": False,
                "think": False,
                "options": {"temperature": 0, "num_predict": 96},
            },
        )

    response.raise_for_status()
    data = response.json()
    text = data.get("response") or data.get("thinking") or ""

    assert isinstance(text, str)
    assert text.strip()
