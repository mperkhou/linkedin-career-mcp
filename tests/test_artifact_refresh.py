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
)
from linkedin_career_mcp.workflows.matching import (
    _looks_like_employer_line,
    _looks_like_title_line,
    _write_cover_letter_text_pdf,
)


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


def test_full_month_job_title_line_is_not_rendered_as_employer_heading() -> None:
    line = (
        "Steindler Orthopedic Clinic | Systems Engineer / IT Administrator | "
        "March 2019 - Nov 2019"
    )

    assert _looks_like_title_line(line) is True
    assert _looks_like_employer_line(line) is False


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
