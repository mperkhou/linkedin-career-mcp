from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

from linkedin_career_mcp.artifact_refresh import (
    LINKEDIN_PROFILE_LABEL,
    LINKEDIN_PROFILE_URL,
    NEW_COVER_LETTER_PROJECT_ENDING_TEXT,
    OLD_COVER_LETTER_PROJECT_ENDING_TEXT,
    OLD_LINKEDIN_PROFILE_LABEL,
    OLD_RESUME_CONTACT_LINE,
    _patch_cover_letter_pdf,
    _patch_cover_letter_project_paragraph_pdf,
    _patch_resume_pdf,
    _patch_resume_style_pdf,
)
from linkedin_career_mcp.workflows.matching import _write_cover_letter_text_pdf


def test_patch_resume_pdf_replaces_static_linkedin_contact(tmp_path: Path) -> None:
    path = tmp_path / "resume.pdf"
    pdf = canvas.Canvas(str(path), pagesize=LETTER)
    pdf.setFont("Helvetica-Bold", 7.2)
    pdf.drawString(60, 682.25, OLD_RESUME_CONTACT_LINE)
    pdf.save()

    assert _patch_resume_pdf(path) is True

    reader = PdfReader(path)
    text = _extract_text(reader)
    assert OLD_LINKEDIN_PROFILE_LABEL not in text
    assert LINKEDIN_PROFILE_LABEL in text
    assert _has_uri(reader, LINKEDIN_PROFILE_URL)


def test_patch_resume_style_pdf_rerenders_old_style_resume(tmp_path: Path) -> None:
    path = tmp_path / "resume-old-style.pdf"
    pdf = canvas.Canvas(str(path), pagesize=LETTER)
    pdf.setFont("Helvetica", 10)
    y = 740
    lines = [
        "Max Perkhounkov",
        (
            "Iowa City, IA | 641-781-0477 | mperkhounkov1@gmail.com | "
            "linkedin.com/in/maxim-perkhounkov"
        ),
        "Professional Summary",
        "Analytical platform engineer focused on automation.",
        (
            "Note: This resume is custom tailored for every job position using my automated "
            "agentic workflow found at: mperkhou/linkedin-career-mcp"
        ),
        "Core Technical Skills",
        "\x7f Languages & Frameworks: Python, Go",
        "Professional Experience",
        "Oracle | Remote / International Datacenters",
        "Senior Technical Lead - Cloud Automation Engineer | Feb 2022 - Present",
        "\x7f Platform Component Ownership: Built multi-tenant automation",
        " systems for managed endpoints.",
        "Education & Certifications",
        "\x7f Bachelor of Science in Physics & Mathematics | University of Iowa, IA",
    ]
    for line in lines:
        pdf.drawString(60, y, line)
        y -= 16
    pdf.save()

    assert _patch_resume_style_pdf(path) is True

    reader = PdfReader(path)
    text = _extract_text(reader)
    assert "Platform Component Ownership: Built multi-tenant automation systems" in text
    assert _has_uri(reader, LINKEDIN_PROFILE_URL)
    assert _has_uri(reader, "https://github.com/mperkhou/linkedin-career-mcp")
    assert _has_emerald_color(reader)


def test_patch_cover_letter_pdf_adds_signature_link(tmp_path: Path) -> None:
    path = tmp_path / "cover-letter.pdf"
    _write_cover_letter_text_pdf(
        text=(
            "June 8, 2026\n\n"
            "Dear Hiring Manager,\n\n"
            "Please accept my application.\n\n"
            "Sincerely,\n"
            "Maxim Perkhounkov"
        ),
        path=path,
    )

    assert _patch_cover_letter_pdf(path) is True

    reader = PdfReader(path)
    text = _extract_text(reader)
    assert "Sincerely,\nMaxim Perkhounkov\nlinkedin.com/in/maxim-perkhounkov" in text
    assert _has_uri(reader, LINKEDIN_PROFILE_URL)


def test_patch_cover_letter_pdf_adds_signature_link_on_later_page(
    tmp_path: Path,
) -> None:
    path = tmp_path / "cover-letter-long.pdf"
    body = "\n\n".join(
        [
            (
                "This generated paragraph keeps the cover letter flowing long enough "
                "to push the signature block onto a later page while preserving the "
                "same static signature text."
            )
            for _ in range(18)
        ]
    )
    _write_cover_letter_text_pdf(
        text=(
            "June 8, 2026\n\n"
            "Dear Hiring Manager,\n\n"
            f"{body}\n\n"
            "Sincerely,\n"
            "Maxim Perkhounkov"
        ),
        path=path,
    )

    assert len(PdfReader(path).pages) > 1
    assert _patch_cover_letter_pdf(path) is True

    reader = PdfReader(path)
    text = _extract_text(reader)
    assert "Sincerely,\nMaxim Perkhounkov\nlinkedin.com/in/maxim-perkhounkov" in text
    assert _has_uri(reader, LINKEDIN_PROFILE_URL)


def test_patch_cover_letter_pdf_replaces_project_paragraph_ending(
    tmp_path: Path,
) -> None:
    path = tmp_path / "cover-letter-project.pdf"
    old_project_paragraph = (
        "I also want to highlight the automation project "
        "([mperkhou/linkedin-career-mcp](https://github.com/mperkhou/linkedin-career-mcp)) "
        "used to generate the resume and cover letter submitted with this application. I built "
        "a custom agentic workflow that searches public LinkedIn job postings, compares each "
        "Job Opening Description against my resume and current role context, and generates "
        "tailored resume artifacts through cost-conscious API calls to OpenRouter and DeepSeek. "
        "I developed the project using multiple AI-assisted engineering tools, including Codex, "
        "Cline with DeepSeek, and GitHub Copilot, while actively managing prompt structure, "
        "context windows, token usage, model selection, and output validation. "
        f"{OLD_COVER_LETTER_PROJECT_ENDING_TEXT}"
    )
    _write_cover_letter_text_pdf(
        text=(
            "June 8, 2026\n\n"
            "Dear Hiring Manager,\n\n"
            f"{old_project_paragraph}\n\n"
            "Please find my resume attached for your consideration.\n\n"
            "Sincerely,\n"
            "Maxim Perkhounkov\n"
            f"[{LINKEDIN_PROFILE_LABEL}]({LINKEDIN_PROFILE_URL})"
        ),
        path=path,
    )

    assert _patch_cover_letter_project_paragraph_pdf(path) is True

    reader = PdfReader(path)
    text = _normalize_text(_extract_text(reader))
    assert OLD_COVER_LETTER_PROJECT_ENDING_TEXT not in text
    assert NEW_COVER_LETTER_PROJECT_ENDING_TEXT in text
    assert _has_uri(reader, LINKEDIN_PROFILE_URL)


def _extract_text(reader: PdfReader) -> str:
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _normalize_text(text: str) -> str:
    return " ".join(text.split())


def _has_uri(reader: PdfReader, url: str) -> bool:
    for page in reader.pages:
        for annotation_ref in page.get("/Annots") or []:
            annotation = annotation_ref.get_object()
            action = annotation.get("/A")
            if action is not None and action.get("/URI") == url:
                return True
    return False


def _has_emerald_color(reader: PdfReader) -> bool:
    expected_colors = {
        (0.341176, 0.729412, 0.52549),
        (0.015686, 0.470588, 0.341176),
    }
    for page in reader.pages:
        content = page.get_contents()
        if content is None:
            continue
        for operands, operator in content.operations:
            if operator not in (b"rg", b"RG") or len(operands) < 3:
                continue
            color = tuple(round(float(value), 6) for value in operands[:3])
            if color in expected_colors:
                return True
    return False
