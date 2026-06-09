from __future__ import annotations

from pathlib import Path

from reportlab.pdfgen import canvas

from linkedin_career_mcp.ats import calculate_ats_proxy_score


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


def _write_pdf(path: Path, text: str) -> None:
    pdf = canvas.Canvas(str(path))
    text_object = pdf.beginText(40, 760)
    text_object.setFont("Helvetica", 10)
    for line in text.strip().splitlines():
        text_object.textLine(line.strip())
    pdf.drawText(text_object)
    pdf.save()
