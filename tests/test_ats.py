from __future__ import annotations

from pathlib import Path

from reportlab.pdfgen import canvas

from linkedin_career_mcp.ats import _extract_weighted_terms, calculate_ats_proxy_score


def test_calculate_ats_proxy_score_rewards_parseable_matching_resume(tmp_path: Path):
    resume_path = tmp_path / "resume.pdf"
    _write_pdf(
        resume_path,
        """
        Max Perkhounkov
        Iowa City, IA | 641-781-0477 | mperkhounkov1@gmail.com
        linkedin.com/in/maxim-perkhounkov

        Professional Summary
        Senior platform engineer building Python automation, cloud infrastructure,
        distributed systems, REST API integrations, observability, and CI/CD.

        Core Technical Skills
        Python, Terraform, Ansible, Kubernetes, Docker, AWS, Azure, OpenSearch,
        Logstash, Filebeat, React, TypeScript, PostgreSQL, REST APIs, LLMs,
        prompt engineering, OpenRouter.

        Professional Experience
        Oracle - Senior Technical Lead
        Built automation frameworks, infrastructure as code, observability pipelines,
        multi-tenant platform services, and secure API integrations.

        Education & Certifications
        Oracle Cloud Infrastructure certification.
        """,
    )
    job_description = """
    Required experience with Python, Terraform, Kubernetes, cloud infrastructure,
    distributed systems, REST API integrations, observability, CI/CD, security,
    and prompt engineering for LLM-powered automation workflows.
    """

    score = calculate_ats_proxy_score(
        resume_pdf=resume_path.read_bytes(),
        job_description=job_description,
    )

    assert score.overall_score >= 80
    assert score.parsing_score >= 75
    assert score.keyword_match_score >= 80
    assert score.semantic_match_score >= 80
    assert score.formatting_risk == "Low"
    assert "security" in score.missing_high_value_terms


def test_calculate_ats_proxy_score_handles_unparseable_pdf_bytes():
    score = calculate_ats_proxy_score(
        resume_pdf=b"%PDF-1.4 not really a pdf",
        job_description="Required Python and Kubernetes experience.",
    )

    assert score.overall_score < 50
    assert score.parsing_score == 0
    assert score.formatting_risk == "High"
    assert score.missing_high_value_terms


def test_repeated_phrase_terms_ignore_legal_and_footer_boilerplate():
    job_description = """
    Required experience with Kafka, Kubernetes, observability, and developer productivity
    CI/CD tooling. Developer productivity CI/CD work includes internal engineering
    acceleration systems.

    Pursuant to the Los Angeles County Fair Chance Ordinance, we will consider qualified
    applicants. This job posting may describe job duties. The Los Angeles County Fair
    Chance Ordinance language is included in the job posting.
    """

    terms = dict(_extract_weighted_terms(job_description))

    assert "kafka" in terms
    assert "kubernetes" in terms
    assert "developer productivity ci/cd" in terms
    assert "angeles county" not in terms
    assert "fair chance" not in terms
    assert "fair chance ordinance" not in terms
    assert "job posting" not in terms


def test_ats_terms_ignore_negated_or_ordinary_language_false_positives():
    job_description = """
    This isn't a DevOps or SRE role. The Infrastructure team builds the platform under
    Hover's application layer. The rest of engineering is our customer.
    Required experience with Python, Kubernetes, Terraform, and observability.
    """

    terms = dict(_extract_weighted_terms(job_description))

    assert "devops" not in terms
    assert "rest api" not in terms
    assert "python" in terms
    assert "kubernetes" in terms


def test_ats_aliases_match_resume_variants(tmp_path: Path):
    resume_path = tmp_path / "resume.pdf"
    _write_pdf(
        resume_path,
        """
        Professional Summary
        Built scalable cloud-native platforms and RESTful APIs with CI/CD automation.

        Core Technical Skills
        RESTful APIs, Scalability, cloud-native platforms, continuous integration,
        Containerization, Data Pipelines, platform reliability.

        Professional Experience
        Delivered reliable platform services and Dockerized environments.
        """,
    )
    job_description = """
    Required experience with REST API design, scalability, cloud native services,
    CI/CD, containerization, data pipeline work, and reliability.
    """

    score = calculate_ats_proxy_score(
        resume_pdf=resume_path.read_bytes(),
        job_description=job_description,
    )

    assert "rest api" not in score.missing_high_value_terms
    assert "scalability" not in score.missing_high_value_terms
    assert "cloud native" not in score.missing_high_value_terms
    assert "ci/cd" not in score.missing_high_value_terms
    assert "containerization" not in score.missing_high_value_terms
    assert "data pipeline" not in score.missing_high_value_terms
    assert "reliability" not in score.missing_high_value_terms


def test_missing_high_value_terms_do_not_surface_repeated_phrase_noise(tmp_path: Path):
    resume_path = tmp_path / "resume.pdf"
    _write_pdf(
        resume_path,
        """
        Professional Summary
        Built Python automation and observability dashboards.

        Core Technical Skills
        Python, observability.
        """,
    )
    job_description = """
    Required Python and observability experience.
    Monitoring logging data appears in dashboard text. Monitoring logging data appears
    again in a generated description block.
    """

    score = calculate_ats_proxy_score(
        resume_pdf=resume_path.read_bytes(),
        job_description=job_description,
    )

    assert "monitoring logging data" not in score.missing_high_value_terms


def _write_pdf(path: Path, text: str) -> None:
    pdf = canvas.Canvas(str(path))
    text_object = pdf.beginText(40, 760)
    text_object.setFont("Helvetica", 10)
    for line in text.strip().splitlines():
        text_object.textLine(line.strip())
    pdf.drawText(text_object)
    pdf.save()
