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
    stylize_cover_letter_pdf,
    stylize_resume_pdf,
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


def test_stylize_resume_pdf_writes_emerald_copy_without_rewriting_source(
    tmp_path: Path,
) -> None:
    path = tmp_path / "resume-input.pdf"
    pdf = canvas.Canvas(str(path), pagesize=LETTER)
    pdf.setFont("Helvetica", 10)
    case_study_url = "https://example.com/work/ai-enablement"
    project_url = "https://github.com/mperkhou/linkedin-career-mcp"
    y = 740
    lines: list[str] = [
        "Max Perkhounkov",
        "Staff Engineer | AI Enablement & Platform Automation",
        "Professional Summary",
        "Analytical Staff Engineer focused on practical AI enablement.",
        "Core Technical Skills",
        "\u2022 MCP, agentic workflows, Python automation",
        "\u2022 linkedin-career-mcp: Developed a career automation pipeline",
        "\u2022 Case study: AI enablement writeup",
        "Professional Experience",
        "Oracle | Remote",
        "Senior Technical Lead - Cloud Automation Engineer | Feb 2022 - Present",
        "\u2022 Built AI-assisted delivery workflows",
        "Education & Certifications",
        "\u2022 Bachelor of Science in Physics & Mathematics",
        "\u2022 Oracle Cloud Infrastructure AI Foundations Associate | 2026",
        "Personal Projects & Open Source",
        "\u2022 linkedin-career-mcp: Developed an automated career-data pipeline",
        " using a custom MCP server and LLM search planner.",
    ]
    for line in lines:
        pdf.drawString(60, y, line)
        if line == "\u2022 Case study: AI enablement writeup":
            label_prefix = "\u2022 Case study: "
            label = "AI enablement writeup"
            label_x = 60 + pdf.stringWidth(label_prefix, "Helvetica", 10)
            pdf.linkURL(
                case_study_url,
                (label_x, y - 2, label_x + pdf.stringWidth(label, "Helvetica", 10), y + 10),
                relative=0,
            )
        y -= 16
    pdf.linkURL(project_url, (10, 10, 30, 24), relative=0)
    pdf.save()
    original_bytes = path.read_bytes()

    result = stylize_resume_pdf(input_path=path)

    assert result.source_path == path
    assert result.output_path == tmp_path / "resume-input_emerald.pdf"
    assert path.read_bytes() == original_bytes

    reader = PdfReader(result.output_path)
    text = _extract_text(reader)
    assert "Staff Engineer | AI Enablement & Platform Automation" in text
    assert "Analytical Staff Engineer focused on practical AI enablement." in text
    assert "linkedin-career-mcp" in text
    assert "Developed a career automation pipeline" in text
    assert "AI enablement writeup" in text
    assert "Built AI-assisted delivery workflows" in text
    assert "Oracle Cloud Infrastructure AI Foundations Associate | 2026" in text
    assert "Personal Projects & Open Source" in text
    assert "custom MCP server and LLM search planner" in text
    assert "2026 Personal Projects" not in text
    assert _has_uri(reader, case_study_url)
    assert _has_uri(reader, project_url)
    assert _has_emerald_color(reader)


def test_stylize_cover_letter_pdf_writes_emerald_copy_without_rewriting_source(
    tmp_path: Path,
) -> None:
    path = tmp_path / "cover-letter-input.pdf"
    pdf = canvas.Canvas(str(path), pagesize=LETTER)
    project_url = "https://github.com/mperkhou/linkedin-career-mcp"
    y = 740
    lines = [
        "Subject: AI enablement platform automation",
        "",
        "Dear Hiring Manager,",
        "",
        "I build practical AI enablement workflows for enterprise infrastructure.",
        "",
        "1. Building the Connective Tissue",
        "MCP connectivity gives agents the context they need.",
        "\u2022 OCI Automation: Built agentic infrastructure workflows.",
        "\u2022 JIRA Automation: Converted troubleshooting context into stories.",
        "",
        "Sincerely,",
        "Maxim Perkhounkov",
    ]
    for line in lines:
        if line == "Subject: AI enablement platform automation":
            pdf.setFont("Helvetica-Bold", 10)
            pdf.drawString(60, y, line)
            pdf.setFont("Helvetica", 10)
        elif line == "\u2022 OCI Automation: Built agentic infrastructure workflows.":
            bullet = "\u2022 "
            label = "OCI Automation"
            rest = ": Built agentic infrastructure workflows."
            pdf.setFont("Helvetica", 10)
            pdf.drawString(60, y, bullet)
            label_x = 60 + pdf.stringWidth(bullet, "Helvetica", 10)
            pdf.setFont("Helvetica-Bold", 10)
            pdf.drawString(label_x, y, label)
            rest_x = label_x + pdf.stringWidth(label, "Helvetica-Bold", 10)
            pdf.setFont("Helvetica", 10)
            pdf.drawString(rest_x, y, rest)
        elif line == "Maxim Perkhounkov":
            pdf.setFont("Helvetica-Bold", 10)
            pdf.drawString(60, y, line)
            pdf.setFont("Helvetica", 10)
        elif line:
            pdf.setFont("Helvetica", 10)
            pdf.drawString(60, y, line)
        y -= 16
    pdf.drawString(60, y, "Project: linkedin-career-mcp")
    label_x = 60 + pdf.stringWidth("Project: ", "Helvetica", 10)
    pdf.linkURL(
        project_url,
        (
            label_x,
            y - 2,
            label_x + pdf.stringWidth("linkedin-career-mcp", "Helvetica", 10),
            y + 10,
        ),
        relative=0,
    )
    pdf.save()
    original_bytes = path.read_bytes()

    result = stylize_cover_letter_pdf(input_path=path)

    assert result.source_path == path
    assert result.output_path == tmp_path / "cover-letter-input_emerald.pdf"
    assert path.read_bytes() == original_bytes

    reader = PdfReader(result.output_path)
    text = _extract_text(reader)
    assert "Subject: AI enablement platform automation" in text
    assert "MCP connectivity gives agents the context they need." in text
    assert "OCI Automation: Built agentic infrastructure workflows." in text
    assert "Sincerely," in text
    assert _has_uri(reader, project_url)
    assert _has_bold_text(reader, "Subject:")
    assert _has_bold_text(reader, "OCI Automation")
    assert _has_bold_text(reader, "Maxim Perkhounkov")
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


def _has_bold_text(reader: PdfReader, needle: str) -> bool:
    found = False

    def visitor(
        text: str,
        _current_matrix: list[float],
        _text_matrix: list[float],
        font_dictionary: dict[str, object] | None,
        _font_size: float,
    ) -> None:
        nonlocal found
        if needle not in text or font_dictionary is None:
            return
        font_name = str(font_dictionary.get("/BaseFont", ""))
        if "Bold" in font_name:
            found = True

    for page in reader.pages:
        page.extract_text(visitor_text=visitor)
        if found:
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
