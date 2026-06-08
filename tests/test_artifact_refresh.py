from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

from linkedin_career_mcp.artifact_refresh import (
    LINKEDIN_PROFILE_LABEL,
    LINKEDIN_PROFILE_URL,
    OLD_LINKEDIN_PROFILE_LABEL,
    OLD_RESUME_CONTACT_LINE,
    _patch_cover_letter_pdf,
    _patch_resume_pdf,
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


def _extract_text(reader: PdfReader) -> str:
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _has_uri(reader: PdfReader, url: str) -> bool:
    for page in reader.pages:
        for annotation_ref in page.get("/Annots") or []:
            annotation = annotation_ref.get_object()
            action = annotation.get("/A")
            if action is not None and action.get("/URI") == url:
                return True
    return False
