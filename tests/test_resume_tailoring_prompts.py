from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import httpx
import pytest
from fixture_loaders import load_linkedin_job_fixture

from linkedin_career_mcp.ats import AtsProxyScore
from linkedin_career_mcp.config import load_settings
from linkedin_career_mcp.models import JobDetails
from linkedin_career_mcp.workflows.matching import (
    AI_GENERATION_NOTE,
    COVER_LETTER_ORACLE_OPENER,
    COVER_LETTER_PROJECT_PARAGRAPH,
    DEFAULT_SCJDIR,
    RESUME_HEADER_CONTACT,
    RESUME_HEADER_NAME,
    ProfileDocument,
    _ats_resume_repair_prompt,
    _coerce_core_skill_sections,
    _cover_letter_sections_prompt,
    _job_description_context,
    _looks_like_recommendations,
    _recommendations_prompt,
    _render_cover_letter_template,
    _render_resume_template,
    _resume_sections_prompt,
    _scjdir_prompt,
    _source_resume_evidence_for_missing_terms,
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
    assert "Preserve the seven Core Technical Skills categories exactly" in prompt
    assert "AI Tools" in prompt
    assert "Error Budgets" in prompt
    assert "Tailored Oracle current-role SCJDiR" in prompt
    assert "React" in prompt


def test_source_resume_evidence_uses_only_supported_missing_terms():
    evidence = _source_resume_evidence_for_missing_terms(
        source_resume_text=(
            "Core skills include TypeScript and Kubernetes.\n"
            "Automation work includes GitHub Actions pipelines.\n"
            "Generic cloud work should not authorize every cloud term."
        ),
        missing_terms=("typescript", "kubernetes", "github actions", "fastapi"),
    )

    assert set(evidence) == {"typescript", "kubernetes", "github actions"}
    assert "TypeScript" in evidence["typescript"]
    assert "GitHub Actions" in evidence["github actions"]


def test_source_resume_evidence_uses_limited_aliases_for_supported_terms():
    evidence = _source_resume_evidence_for_missing_terms(
        source_resume_text=(
            "AI Tools: Codex, applied AI tooling, and LLM prompting.\n"
            "Developer Tooling Innovation: improved team workflows for platform engineers.\n"
            "CI/CD & Resilience: replaced manual workflows with automated release pipelines."
        ),
        missing_terms=(
            "artificial intelligence",
            "developer productivity ci/cd",
            "computer hardware",
        ),
    )

    assert set(evidence) == {
        "artificial intelligence",
        "developer productivity ci/cd",
    }
    assert "AI Tools" in evidence["artificial intelligence"]
    assert "Developer Tooling" in evidence["developer productivity ci/cd"]
    assert "CI/CD" in evidence["developer productivity ci/cd"]


def test_ats_resume_repair_prompt_omits_cjd_and_uses_source_evidence():
    job = JobDetails(
        job_id="12345",
        title="Platform Automation Engineer",
        company="Acme",
        description="Requires TypeScript, Kubernetes, and GitHub Actions.",
    )
    prompt = _ats_resume_repair_prompt(
        source_evidence={
            "typescript": "Source resume says TypeScript platform tooling.",
            "kubernetes": "Source resume says Docker and Kubernetes.",
        },
        current_resume_text="Current generated resume text.",
        current_tailored_scjdir="Oracle | Remote\nSenior Technical Lead",
        current_sections_plan={"core_technical_skills": []},
        job=job,
        score=AtsProxyScore(
            overall_score=82,
            parsing_score=95,
            keyword_match_score=70,
            semantic_match_score=80,
            formatting_risk="Low",
            missing_high_value_terms=("typescript", "kubernetes"),
        ),
    )

    assert "You repair a generated resume after local ATS scoring" in prompt
    assert "source-resume evidence" in prompt
    assert "Source resume says TypeScript" in prompt
    assert "Requires TypeScript, Kubernetes" in prompt
    assert "Current generated resume text" in prompt
    assert "Current job description (CJD)" not in prompt
    assert "current Oracle job description" not in prompt


def test_resume_generation_prompts_include_full_job_description():
    late_marker = "AI Experience late-section marker should reach the model."
    job_description = (
        "Opening summary. "
        + ("Requires scalable platform engineering, APIs, and cloud automation. " * 90)
        + late_marker
    )
    job = JobDetails(
        job_id="12345",
        title="Senior Software Engineer",
        company="Acme",
        description=job_description,
    )
    source_resume = ProfileDocument(Path("MP-RESUME-AGENTIC.pdf"), SAMPLE_RESUME)
    current_job_description = ProfileDocument(
        Path("Senior_Platform_Software_Engineer(IC3).pdf"),
        SAMPLE_CJD,
    )

    prompts = [
        _scjdir_prompt(
            source_resume=source_resume,
            current_job_description=current_job_description,
            job=job,
        ),
        _resume_sections_prompt(
            source_resume=source_resume,
            current_job_description=current_job_description,
            tailored_scjdir="Oracle | Remote\nSenior Technical Lead - Cloud Automation Engineer",
            job=job,
        ),
        _recommendations_prompt(
            source_resume=source_resume,
            current_job_description=current_job_description,
            job=job,
            draft_text="Unusable draft.",
        ),
    ]

    assert len(job_description) > 4_000
    assert _job_description_context(job) == job_description
    for prompt in prompts:
        assert late_marker in prompt


def test_cover_letter_prompt_limits_model_to_dynamic_sections():
    job = load_linkedin_job_fixture("4419204491")
    prompt = _cover_letter_sections_prompt(
        source_resume=ProfileDocument(Path("MP-RESUME-AGENTIC.pdf"), SAMPLE_RESUME),
        current_job_description=ProfileDocument(
            Path("Senior_Platform_Software_Engineer(IC3).pdf"),
            SAMPLE_CJD,
        ),
        job=job,
    )

    assert "cover_letter_sections" in prompt
    assert "Return only valid JSON" in prompt
    assert "opening_alignment" in prompt
    assert "oracle_alignment" in prompt
    assert "prior_experience_alignment" in prompt
    assert COVER_LETTER_ORACLE_OPENER in prompt
    assert "Section 4 is a static paragraph" in prompt
    assert "Codex, Cline with DeepSeek, GitHub Copilot" in prompt
    assert "exactly 3 concise sentences" in prompt
    assert "Oracle current-role resume" in prompt
    assert "source resume, the current Oracle job description/CJD, and this JOD" in prompt
    assert "Each oracle_alignment sentence should add a distinct alignment point" in prompt
    assert "At Oracle, I have ... . That work also ... . This maps to the role ... ." in prompt
    assert "Python/Django" in prompt


def test_render_cover_letter_template_preserves_static_sections():
    job = JobDetails(
        job_id="12345",
        title="Senior AI Platform Engineer",
        company="Acme AI",
        description="Build LLM automation features.",
    )

    text = _render_cover_letter_template(
        job=job,
        letter_date=date(2026, 6, 7),
        sections_plan={
            "opening_alignment": "the LLM automation capabilities you are looking for",
            "oracle_alignment": "I have built Oracle automation platforms for distributed teams.",
            "prior_experience_alignment": "My earlier roles add Python, React, Azure, and Django.",
        },
    )

    assert text.startswith("June 7, 2026")
    assert "Dear Hiring Manager" in text
    assert "Senior AI Platform Engineer at Acme AI" in text
    assert COVER_LETTER_ORACLE_OPENER in text
    assert "My earlier experience also strengthens my fit for this position." in text
    assert COVER_LETTER_PROJECT_PARAGRAPH in text
    assert "Please find my resume attached" in text
    assert text.endswith(
        "Sincerely,\n"
        "Maxim Perkhounkov\n"
        "[linkedin.com/in/maxim-perkhounkov](https://www.linkedin.com/in/maxim-perkhounkov/)"
    )


def test_job_description_context_removes_low_signal_company_boilerplate():
    job = JobDetails(
        job_id="4342788295",
        title="Senior Software Engineer 2",
        company="Drata",
        description="""
Our Mission & Values
At Drata, we help companies earn and keep the trust of their users.
Our Culture & Work Style
Be a Driver. Move at Drata Speed. Stay Mission-Driven.
Why Join The Drata Team?
See why we are consistently recognized on workplace lists.

Job Summary
The Senior Software Engineer II helps lead platform development.
What You’ll Do
Architect highly scalable web applications and build RESTful APIs.
What You’ll Bring
7+ years of experience as a software engineer.
AI Experience
Hands-on experience building features that integrate with LLMs.
How We Support You
Shared Success, Health & Wellness, and Financial Well-being.
        """,
    )

    context = _job_description_context(job)

    assert context.startswith("Job Summary")
    assert "Our Mission" not in context
    assert "Why Join The Drata Team" not in context
    assert "How We Support You" not in context
    assert "What You’ll Bring" in context
    assert "AI Experience" in context


def test_job_description_context_keeps_concise_company_context_before_role():
    job = JobDetails(
        job_id="4423512582",
        title="Frontend Engineer",
        company="Terzo",
        description=(
            "Location : US Level : Senior Individual Contributor Team : Engineering "
            "About Terzo Terzo builds an AI-native enterprise data platform. "
            "The Opportunity Terzo is hiring a Frontend Engineer. "
            "You might thrive in this role if you have React and TypeScript experience."
        ),
    )

    context = _job_description_context(job)

    assert context.startswith("Location : US")
    assert "About Terzo" in context
    assert "The Opportunity" in context
    assert "React and TypeScript" in context


def test_job_description_context_does_not_trim_sentence_case_responsibilities():
    job = JobDetails(
        job_id="4395481257",
        title="Senior Software Engineer - HPC",
        company="NVIDIA",
        description=(
            "NVIDIA has been transforming accelerated computing for more than 25 years. "
            "We are looking for a Senior Software Engineer to improve HPC infrastructure. "
            "What We Need To See Strong coding skills in Go, Python, or C++ with a focus "
            "on backend, systems, or infrastructure engineering. Experience owning services "
            "end-to-end: architecture, reviews, implementation, testing, rollout, and "
            "observability. Maintainer or co-maintainer responsibilities for an open source "
            "component used in production at large scale. Your base salary will be determined "
            "based on your location and experience. NVIDIA is committed to fostering a diverse "
            "work environment."
        ),
    )

    context = _job_description_context(job)

    assert context.startswith("NVIDIA has been transforming")
    assert "What We Need To See" in context
    assert "co-maintainer responsibilities for an open source component" in context
    assert "Your base salary" not in context
    assert "NVIDIA is committed" not in context


def test_job_description_context_keeps_role_details_after_internal_compensation_text():
    job = JobDetails(
        job_id="4413455860",
        title="Senior Software Engineer, Content Platform",
        company="Roku",
        description=(
            "Roku is changing how the world watches TV. We offer you the opportunity to "
            "delight millions of streamers. About the role Roku continues to innovate "
            "and lead the industry. For California Only - The estimated annual salary "
            "for this position is between $300,000 - $425,000 annually. Compensation "
            "packages are based on factors unique to each candidate. This role is "
            "eligible for health insurance, equity awards, life insurance, disability "
            "benefits, parental leave, wellness benefits, and paid time off. What you'll "
            "be doing Design and Development: Architect, develop, and maintain scalable "
            "backend systems and APIs using Java and Akka. Build distributed data "
            "pipelines for batch and real-time processing."
        ),
    )

    context = _job_description_context(job)

    assert "the opportunity to delight millions" in context
    assert "About the role" in context
    assert "What you'll be doing" in context
    assert "Design and Development" in context


def test_job_description_context_preserves_long_role_prefix_before_qualifications():
    job = JobDetails(
        job_id="4423025523",
        title="Platform Engineer",
        company="DTCC",
        description=(
            "Are you ready to make an impact at DTCC? We are looking for a Platform Engineer "
            "to build cloud automation and AI infrastructure. This role designs and maintains "
            "AWS accounts, CI/CD workflows, and infrastructure governance. "
            "Responsibilities include building secure data access controls across accounts, "
            "developing monitoring and compliance reporting for AI/ML systems, and automating "
            "infrastructure provisioning using Terraform. Deploy machine learning models using "
            "AWS SageMaker and configure Snowflake integrations across environments. Create "
            "customized CloudWatch alarms and configure log ingestion pipelines from CloudWatch "
            "to Splunk. "
            + " ".join(
                [
                    "This platform role continues to build, design, automate, monitor, and "
                    "operate cloud infrastructure, APIs, Python tooling, and developer "
                    "productivity workflows across production systems."
                    for _ in range(12)
                ]
            )
            + " Qualifications Minimum of 4 years of related experience. Bachelor's degree "
            "preferred or equivalent experience. The salary range is indicative for roles at "
            "the same level across all US locations. Equal opportunity employer statement."
        ),
    )

    context = _job_description_context(job)

    assert not context.startswith("Qualifications")
    assert "Deploy machine learning models using AWS SageMaker" in context
    assert "automating infrastructure provisioning using Terraform" in context
    assert "CloudWatch to Splunk" in context
    assert "Qualifications Minimum of 4 years" in context
    assert "salary range" not in context.casefold()
    assert "equal opportunity" not in context.casefold()


def test_job_description_context_uses_chunk_ranker_to_drop_boilerplate():
    job = JobDetails(
        job_id="4417171151",
        title="Senior Software Engineer, Engineering Acceleration",
        company="OpenAI",
        description=(
            "About the Role Build engineering acceleration tools for consumer devices. "
            "Responsibilities Design Python services, developer workflows, CI/CD automation, "
            "observability dashboards, and API integrations for hardware engineering teams. "
            "Required Qualifications Experience with Python, cloud infrastructure, distributed "
            "systems, monitoring, and developer productivity. Benefits include medical, dental, "
            "vision, parental leave, wellness benefits, and paid time off. OpenAI Global "
            "Applicant Privacy Policy explains how personal information is processed. We may "
            "use AI tools to support parts of the hiring process."
        ),
    )

    context = _job_description_context(job)

    assert "Build engineering acceleration tools" in context
    assert "developer workflows" in context
    assert "Required Qualifications" in context
    assert "Benefits include" not in context
    assert "Applicant Privacy Policy" not in context
    assert "hiring process" not in context


def test_job_description_context_drops_compensation_chunks_with_qualification_words():
    job = JobDetails(
        job_id="4419879314",
        title="Senior Cloud Engineer",
        company="Capgemini",
        description=(
            "Your Role Develop and maintain Chef cookbooks, recipes, and policies to enforce "
            "Linux OS baseline configurations and compliance. Automate onboarding of Linux "
            "systems into Chef, including bootstrapping and compliance validation. "
            "5-8+ years of hands on experience in Linux systems engineering and OS hardening. "
            "The base compensation range listed for this position reflects the minimum and "
            "maximum target compensation Capgemini may pay for the role at the time of this "
            "posting. These amounts vary based on geographic location, education and "
            "qualifications, certifications, relevant experience and skills, seniority and "
            "performance, market considerations, and internal pay equity. Benefits Capgemini "
            "offers comprehensive medical, dental, vision, retirement, and paid time off."
        ),
    )

    context = _job_description_context(job)

    assert "Develop and maintain Chef cookbooks" in context
    assert "Linux systems engineering and OS hardening" in context
    assert "base compensation range" not in context.casefold()
    assert "internal pay equity" not in context.casefold()
    assert "Benefits Capgemini" not in context


def test_job_description_context_splits_inline_benefits_after_role_content():
    job = JobDetails(
        job_id="4383502230",
        title="Senior Software Engineer, Platform",
        company="Hover",
        description=(
            "About the role Build platform systems for modern AI workloads. Modern AI "
            "workloads place fundamentally different demands on infrastructure than "
            "traditional services do, from LLM inference and agent runtimes to vector stores, "
            "GPU economics, and real-time 3D and computer vision pipelines. You think about "
            "reliability, observability, failure modes, and scalability when designing systems. "
            "Experience collaborating with engineers across teams to build platform "
            "capabilities or improve developer experience. Comfort working across multiple "
            "layers of the infrastructure stack and learning new tools and technologies as "
            "the platform evolves Benefits Compensation - Competitive salary and meaningful "
            "equity in a fast-growing company Healthcare - Comprehensive medical, dental, "
            "and vision coverage for you and dependents Paid Time Off - Unlimited vacation."
        ),
    )

    context = _job_description_context(job)

    assert "Modern AI workloads" in context
    assert "LLM inference and agent runtimes" in context
    assert "improve developer experience" in context
    assert "Benefits Compensation" not in context
    assert "Comprehensive medical" not in context


def test_job_description_context_keeps_linux_datacenter_signals_before_benefits():
    job = JobDetails(
        job_id="4338400238",
        title="Infrastructure Application & Automation Software Engineer",
        company="Hammerspace",
        description=(
            "Hammerspace delivers a Global Data Environment that spans data centers, AWS, "
            "Azure, and Google cloud infrastructure. With origins in Linux, NFS, open "
            "standards, deep file system and data management technology leadership, "
            "Hammerspace connects global users with their data and applications. Be the "
            "go-to Linux admin for networking, storage, virtualization, and distributed "
            "systems. Linux internals muscle: Bonding/VLANs, IP tables, BGP basics, RAID, "
            "LVM, NFS, iSCSI, KVM, Docker, CI/CD pipelines, and chat-ops integrations. "
            "Perks Equity in a storage startup, top-tier health, dental, 401(k), flexible "
            "time off. The anticipated compensation range for this role is $150,000-175,000."
        ),
    )

    context = _job_description_context(job)

    assert "data centers, AWS, Azure" in context
    assert "go-to Linux admin" in context
    assert "CI/CD pipelines" in context
    assert "anticipated compensation range" not in context.casefold()
    assert "401(k)" not in context


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
    assert "linkedin.com/mperkhou" not in text
    assert AI_GENERATION_NOTE in text
    assert "Professional Summary" in text
    assert "Core Technical Skills" in text
    assert "- Languages & Frameworks: Python, Django, LLMs" in text
    assert "- AI Tools: Codex, Oracle Code Assist (OCA), Cline, OpenRouter" in text
    assert "Professional Experience" in text
    assert "Education & Certifications" in text
    assert "Oracle Cloud Infrastructure AI Foundations Associate" in text


def test_render_resume_template_normalizes_generated_scjdir_bullets():
    text = _render_resume_template(
        tailored_scjdir=(
            "Here is the rewritten SCJDiR section tailored to the job description.\n"
            "Oracle | Remote / International Datacenters\n"
            "Senior Technical Lead - Cloud Automation Engineer | Feb 2022 - Present\n"
            "● Platform Component Ownership: Built platform automation APIs.\n"
            "- ● Distributed Observability: Built observability pipelines."
        ),
        sections_plan={"prior_experience": []},
    )

    assert "●" not in text
    assert "Here is the rewritten" not in text
    assert "- Platform Component Ownership: Built platform automation APIs." in text
    assert "- Distributed Observability: Built observability pipelines." in text


def test_core_skills_falls_back_to_missing_template_categories():
    sections = _coerce_core_skill_sections(
        [{"category": "Languages & Frameworks", "skills": ["Python", "LLMs"]}]
    )

    assert sections[0] == ("Languages & Frameworks", ["Python", "LLMs"])
    assert sections[1][0] == "Distributed Systems & Cloud"
    assert "AWS" in sections[1][1]
    assert sections[-1][0] == "AI Tools"
    assert "Codex" in sections[-1][1]
    assert "Oracle Code Assist (OCA)" in sections[-1][1]
    assert "Cline" in sections[-1][1]
    assert "OpenRouter" in sections[-1][1]


def test_core_skills_filters_error_budgets_and_keeps_ai_tools_defaults():
    sections = _coerce_core_skill_sections(
        [
            {
                "category": "Data & Observability",
                "skills": ["Data Pipelines", "Error Budgets", "Error Budget Analysis"],
            },
            {"category": "AI Tools", "skills": ["Codex"]},
        ]
    )
    by_category = dict(sections)

    assert by_category["Data & Observability"] == ["Data Pipelines"]
    assert by_category["AI Tools"][:4] == [
        "Codex",
        "Oracle Code Assist (OCA)",
        "Cline",
        "OpenRouter",
    ]


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
