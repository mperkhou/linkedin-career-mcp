from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pypdf import PdfReader, PdfWriter
from pypdf.annotations import Link
from pypdf.generic import ContentStream, FloatObject, TextStringObject
from reportlab.pdfbase.pdfmetrics import stringWidth

from linkedin_career_mcp.webapp import DEFAULT_DATABASE as RELATIVE_APPLICATION_DATABASE
from linkedin_career_mcp.webapp import connect_database
from linkedin_career_mcp.workflows.matching import (
    AI_GENERATION_NOTE,
    DEFAULT_OUTPUT_DIR,
    LINKEDIN_PROFILE_LABEL,
    LINKEDIN_PROFILE_URL,
    RESUME_HEADER_CONTACT,
    RESUME_HEADER_NAME,
    RESUME_SECTION_HEADINGS,
    _looks_like_employer_line,
    _looks_like_title_line,
    _write_cover_letter_text_pdf,
    _write_text_pdf,
)

OLD_LINKEDIN_PROFILE_LABEL = "linkedin.com/mperkhou"
DEFAULT_APPLICATION_DATABASE = DEFAULT_OUTPUT_DIR / RELATIVE_APPLICATION_DATABASE
COVER_LETTER_LINE_LEADING = 14.5
EMERALD_ACCENT_RGB = (0.341176, 0.729412, 0.52549)
EMERALD_DARK_RGB = (0.015686, 0.470588, 0.341176)
RESUME_CONTACT_PREFIX = (
    "Iowa City, IA | 641-781-0477 | mperkhounkov1@gmail.com | "
)
STYLIZED_RESUME_DEFAULT_SUFFIX = "emerald"
PDF_BULLET_PREFIX_RE = re.compile(
    r"^\s*(?P<marker>[\x7f\u2022\u2023\u2043\u2219\u25aa\u25cf\u25e6]|o)\s+"
)
PROFESSIONAL_EXPERIENCE_DATE_CONTINUATION_RE = re.compile(
    r"(?:[A-Z][a-z]{2}\s+)?\d{4}(?:\s*-\s*(?:Present|[A-Z][a-z]{2}\s+\d{4}|\d{4}))?"
)
MONTH_ABBREVIATIONS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)
OLD_RESUME_CONTACT_LINE = f"{RESUME_CONTACT_PREFIX}{OLD_LINKEDIN_PROFILE_LABEL}"
NEW_RESUME_CONTACT_LINE = f"{RESUME_CONTACT_PREFIX}{LINKEDIN_PROFILE_LABEL}"
OLD_COVER_LETTER_PROJECT_ENDING_LINES = (
    (
        "This project reflects more than interest in AI; it shows hands-on experience applying "
        "LLMs to a"
    ),
    "real workflow, balancing quality with cost, and building practical automation around prompt",
    "engineering, structured context, and repeatable generation.",
)
NEW_COVER_LETTER_PROJECT_ENDING_LINES = (
    "I built this in my own time because I genuinely enjoy automation, AI tooling, and turning",
    "repetitive workflows into reliable systems.",
)
OLD_COVER_LETTER_PROJECT_ENDING_TEXT = " ".join(
    OLD_COVER_LETTER_PROJECT_ENDING_LINES
)
NEW_COVER_LETTER_PROJECT_ENDING_TEXT = " ".join(
    NEW_COVER_LETTER_PROJECT_ENDING_LINES
).strip()


@dataclass(frozen=True)
class StaticArtifactRefreshResult:
    total_jobs: int
    resumes_checked: int
    resumes_updated: int
    cover_letters_checked: int
    cover_letters_updated: int
    database_rows_updated: int
    missing_files: tuple[str, ...]


@dataclass(frozen=True)
class StylizedResumeResult:
    source_path: Path
    output_path: Path
    pages_read: int
    lines_rendered: int


@dataclass(frozen=True)
class StylizedCoverLetterResult:
    source_path: Path
    output_path: Path
    pages_read: int
    paragraphs_rendered: int


@dataclass(frozen=True)
class _TextHit:
    x: float
    y: float
    font_name: str
    font_size: float


@dataclass(frozen=True)
class _LinkLocation:
    x: float
    y: float
    font_name: str
    font_size: float


def refresh_static_artifacts(
    *,
    database_path: Path = DEFAULT_APPLICATION_DATABASE,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    job_ids: list[str] | None = None,
) -> StaticArtifactRefreshResult:
    normalized_job_ids = tuple(
        sorted({job_id.strip() for job_id in (job_ids or []) if job_id.strip()})
    )
    rows = _fetch_artifact_rows(database_path=database_path, job_ids=normalized_job_ids)
    missing_files: list[str] = []
    resume_updates: dict[str, Path] = {}
    cover_letter_updates: dict[str, Path] = {}
    resumes_checked = 0
    cover_letters_checked = 0

    for row in rows:
        job_id = str(row["job_id"])
        resume_path = _resolve_artifact_path(
            output_dir=output_dir,
            path_text=str(row["source_resume_path"] or ""),
        )
        if resume_path is not None:
            resumes_checked += 1
            if resume_path.exists():
                resume_changed = False
                if _patch_resume_pdf(resume_path):
                    resume_changed = True
                if _patch_resume_style_pdf(resume_path):
                    resume_changed = True
                if resume_changed:
                    resume_updates[job_id] = resume_path
            else:
                missing_files.append(str(resume_path))

        cover_letter_path = _resolve_artifact_path(
            output_dir=output_dir,
            path_text=str(row["source_cover_letter_path"] or ""),
        )
        if cover_letter_path is not None:
            cover_letters_checked += 1
            if cover_letter_path.exists():
                cover_letter_changed = False
                if _patch_cover_letter_pdf(cover_letter_path):
                    cover_letter_changed = True
                if _patch_cover_letter_project_paragraph_pdf(cover_letter_path):
                    cover_letter_changed = True
                if cover_letter_changed:
                    cover_letter_updates[job_id] = cover_letter_path
            else:
                missing_files.append(str(cover_letter_path))

    database_rows_updated = _sync_updated_artifacts(
        database_path=database_path,
        resume_updates=resume_updates,
        cover_letter_updates=cover_letter_updates,
    )
    return StaticArtifactRefreshResult(
        total_jobs=len(rows),
        resumes_checked=resumes_checked,
        resumes_updated=len(resume_updates),
        cover_letters_checked=cover_letters_checked,
        cover_letters_updated=len(cover_letter_updates),
        database_rows_updated=database_rows_updated,
        missing_files=tuple(missing_files),
    )


def _fetch_artifact_rows(
    *,
    database_path: Path,
    job_ids: tuple[str, ...],
) -> list[sqlite3.Row]:
    placeholders = ",".join("?" for _ in job_ids)
    where_clause = f"WHERE job_id IN ({placeholders})" if job_ids else ""
    with connect_database(database_path) as connection:
        rows = connection.execute(
            f"""
            SELECT job_id, source_resume_path, source_cover_letter_path
            FROM applications
            {where_clause}
            ORDER BY company, job_title, job_id
            """,
            job_ids,
        ).fetchall()
    return list(rows)


def _resolve_artifact_path(*, output_dir: Path, path_text: str) -> Path | None:
    if not path_text:
        return None
    path = Path(path_text)
    if path.is_absolute():
        return path
    if path.exists():
        return path
    output_relative = output_dir / path
    if output_relative.exists():
        return output_relative
    return path


def _patch_resume_pdf(path: Path) -> bool:
    reader = PdfReader(path)
    text = _extract_pdf_text(reader)
    if OLD_LINKEDIN_PROFILE_LABEL not in text:
        return _ensure_resume_link_annotation(path=path, reader=reader)

    hit = _find_text_hit(reader.pages[0], OLD_RESUME_CONTACT_LINE)
    writer = PdfWriter(clone_from=reader)
    page = writer.pages[0]
    content = ContentStream(page.get_contents(), writer)
    replaced = _replace_text_in_content(
        content,
        old_text=OLD_RESUME_CONTACT_LINE,
        new_text=NEW_RESUME_CONTACT_LINE,
    )
    if not replaced:
        return False
    page.replace_contents(content)
    if hit is not None and not _page_has_uri(page, LINKEDIN_PROFILE_URL):
        _add_resume_link_annotation(writer=writer, page_number=0, hit=hit)
    _write_pdf(path=path, writer=writer)
    return True


def _ensure_resume_link_annotation(*, path: Path, reader: PdfReader) -> bool:
    if LINKEDIN_PROFILE_LABEL not in _extract_pdf_text(reader):
        return False
    if _page_has_uri(reader.pages[0], LINKEDIN_PROFILE_URL):
        return False
    hit = _find_text_hit(reader.pages[0], NEW_RESUME_CONTACT_LINE)
    if hit is None:
        return False
    writer = PdfWriter(clone_from=reader)
    _add_resume_link_annotation(writer=writer, page_number=0, hit=hit)
    _write_pdf(path=path, writer=writer)
    return True


def _patch_resume_style_pdf(path: Path) -> bool:
    reader = PdfReader(path)
    if _resume_has_emerald_style(reader):
        return False
    resume_text = _resume_text_from_pdf(reader)
    if not resume_text:
        return False
    temp_path = path.with_suffix(".emerald.tmp.pdf")
    _write_text_pdf(text=resume_text, path=temp_path)
    temp_path.replace(path)
    return True


def stylize_resume_pdf(
    *,
    input_path: Path,
    output_path: Path | None = None,
    output_suffix: str = STYLIZED_RESUME_DEFAULT_SUFFIX,
) -> StylizedResumeResult:
    source_path = input_path.expanduser()
    if not source_path.is_file():
        raise ValueError(f"Resume PDF was not found: {source_path}")
    if source_path.suffix.lower() != ".pdf":
        raise ValueError(f"Resume stylizer only supports PDF input: {source_path}")

    destination_path = (
        output_path.expanduser()
        if output_path is not None
        else _stylized_resume_output_path(source_path, output_suffix=output_suffix)
    )
    if destination_path == source_path:
        raise ValueError("Refusing to overwrite the input resume; choose a different output path.")

    reader = PdfReader(source_path)
    resume_text = _stylized_resume_text_from_pdf(reader)
    if not resume_text:
        raise ValueError(f"No extractable text was found in resume PDF: {source_path}")

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = destination_path.with_name(f".{destination_path.name}.tmp")
    _write_text_pdf(text=resume_text, path=temp_path)
    temp_path.replace(destination_path)
    return StylizedResumeResult(
        source_path=source_path,
        output_path=destination_path,
        pages_read=len(reader.pages),
        lines_rendered=sum(1 for line in resume_text.splitlines() if line.strip()),
    )


def _stylized_resume_output_path(path: Path, *, output_suffix: str) -> Path:
    suffix = re.sub(r"[^A-Za-z0-9._-]+", "_", output_suffix.strip()).strip("._-")
    suffix = suffix or STYLIZED_RESUME_DEFAULT_SUFFIX
    return path.with_name(f"{path.stem}_{suffix}.pdf")


def _stylized_resume_text_from_pdf(reader: PdfReader) -> str:
    text = _extract_pdf_layout_text(reader)
    lines = _normalize_stylized_resume_pdf_lines(text)
    return "\n".join(lines).strip()


def _extract_pdf_layout_text(reader: PdfReader) -> str:
    page_text: list[str] = []
    for page in reader.pages:
        try:
            text = page.extract_text(extraction_mode="layout") or ""
        except TypeError:
            text = page.extract_text() or ""
        page_text.append(text)
    return "\n".join(page_text)


def _normalize_stylized_resume_pdf_lines(text: str) -> list[str]:
    normalized_lines: list[str] = []
    current_section: str | None = None
    for raw_line in text.splitlines():
        line = _normalize_stylized_resume_pdf_line(raw_line)
        if not line:
            continue
        if line in RESUME_SECTION_HEADINGS:
            current_section = line
            normalized_lines.append(line)
            continue
        if _should_append_resume_continuation(
            raw_line=raw_line,
            line=line,
            previous_line=normalized_lines[-1] if normalized_lines else "",
            current_section=current_section,
        ):
            normalized_lines[-1] = f"{normalized_lines[-1]} {line}"
            continue
        normalized_lines.append(line)
    return normalized_lines


def _normalize_stylized_resume_pdf_line(raw_line: str) -> str:
    line = raw_line.strip()
    if not line:
        return ""
    bullet_match = PDF_BULLET_PREFIX_RE.match(raw_line)
    if bullet_match:
        line = f"- {raw_line[bullet_match.end():]}"
    return _clean_inline_pdf_text(line)


def stylize_cover_letter_pdf(
    *,
    input_path: Path,
    output_path: Path | None = None,
    output_suffix: str = STYLIZED_RESUME_DEFAULT_SUFFIX,
) -> StylizedCoverLetterResult:
    source_path = input_path.expanduser()
    if not source_path.is_file():
        raise ValueError(f"Cover letter PDF was not found: {source_path}")
    if source_path.suffix.lower() != ".pdf":
        raise ValueError(f"Cover letter stylizer only supports PDF input: {source_path}")

    destination_path = (
        output_path.expanduser()
        if output_path is not None
        else _stylized_resume_output_path(source_path, output_suffix=output_suffix)
    )
    if destination_path == source_path:
        raise ValueError(
            "Refusing to overwrite the input cover letter; choose a different output path."
        )

    reader = PdfReader(source_path)
    cover_letter_text = _stylized_cover_letter_text_from_pdf(reader)
    if not cover_letter_text:
        raise ValueError(f"No extractable text was found in cover letter PDF: {source_path}")

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = destination_path.with_name(f".{destination_path.name}.tmp")
    _write_cover_letter_text_pdf(text=cover_letter_text, path=temp_path)
    temp_path.replace(destination_path)
    return StylizedCoverLetterResult(
        source_path=source_path,
        output_path=destination_path,
        pages_read=len(reader.pages),
        paragraphs_rendered=sum(
            1 for paragraph in cover_letter_text.split("\n\n") if paragraph.strip()
        ),
    )


def _stylized_cover_letter_text_from_pdf(reader: PdfReader) -> str:
    text = _extract_pdf_layout_text(reader)
    paragraphs = _normalize_stylized_cover_letter_pdf_paragraphs(text)
    return "\n\n".join(paragraphs).strip()


def _normalize_stylized_cover_letter_pdf_paragraphs(text: str) -> list[str]:
    paragraphs: list[str] = []
    current_lines: list[str] = []
    current_is_bullet = False

    def flush_current() -> None:
        nonlocal current_is_bullet
        if current_lines:
            paragraphs.append(" ".join(current_lines).strip())
            current_lines.clear()
        current_is_bullet = False

    for raw_line in text.splitlines():
        line = _clean_inline_pdf_text(raw_line)
        if not line:
            flush_current()
            continue

        bullet_match = PDF_BULLET_PREFIX_RE.match(raw_line)
        if bullet_match:
            flush_current()
            current_lines.append(f"\u2022 {_clean_inline_pdf_text(raw_line[bullet_match.end():])}")
            current_is_bullet = True
            continue

        if _looks_like_numbered_cover_letter_heading(line):
            flush_current()
            paragraphs.append(line)
            continue

        current_lines.append(line)

    flush_current()
    return paragraphs


def _looks_like_numbered_cover_letter_heading(line: str) -> bool:
    return bool(re.fullmatch(r"\d+\.\s+\S.+", line))


def _resume_has_emerald_style(reader: PdfReader) -> bool:
    emerald_colors = {EMERALD_ACCENT_RGB, EMERALD_DARK_RGB}
    for page in reader.pages:
        content = ContentStream(page.get_contents(), reader)
        for operands, operator in content.operations:
            if operator not in (b"rg", b"RG") or len(operands) < 3:
                continue
            color = tuple(round(float(value), 6) for value in operands[:3])
            if color in emerald_colors:
                return True
    return False


def _resume_text_from_pdf(reader: PdfReader) -> str:
    text = _extract_pdf_text(reader)
    lines = _normalize_resume_pdf_lines(text)
    return "\n".join(lines).strip()


def _normalize_resume_pdf_lines(text: str) -> list[str]:
    normalized_lines: list[str] = []
    current_section: str | None = None
    for raw_line in text.splitlines():
        line = _normalize_resume_pdf_line(raw_line)
        if not line:
            continue
        if line == RESUME_HEADER_NAME and not normalized_lines:
            normalized_lines.append(RESUME_HEADER_NAME)
            continue
        if line.startswith(RESUME_CONTACT_PREFIX):
            line = RESUME_HEADER_CONTACT
        elif line.startswith("Note: This resume is custom tailored"):
            line = AI_GENERATION_NOTE

        if line in RESUME_SECTION_HEADINGS:
            current_section = line
            normalized_lines.append(line)
            continue
        if _should_append_resume_continuation(
            raw_line=raw_line,
            line=line,
            previous_line=normalized_lines[-1] if normalized_lines else "",
            current_section=current_section,
        ):
            normalized_lines[-1] = f"{normalized_lines[-1]} {line}"
            continue
        normalized_lines.append(line)
    return normalized_lines


def _normalize_resume_pdf_line(raw_line: str) -> str:
    line = raw_line.strip()
    if not line:
        return ""
    if line.startswith("\x7f"):
        return f"- {_clean_inline_pdf_text(line[1:])}"
    if line.startswith("o "):
        return f"  - {_clean_inline_pdf_text(line[2:])}"
    return _clean_inline_pdf_text(line)


def _clean_inline_pdf_text(text: str) -> str:
    text = text.replace("\x7f", " ")
    return " ".join(text.split())


def _should_append_resume_continuation(
    *,
    raw_line: str,
    line: str,
    previous_line: str,
    current_section: str | None,
) -> bool:
    if not previous_line:
        return False
    if line in RESUME_SECTION_HEADINGS or line.startswith(("Note:", "- ", "  - ")):
        return False
    if previous_line in RESUME_SECTION_HEADINGS:
        return False
    if previous_line in {RESUME_HEADER_NAME, RESUME_HEADER_CONTACT}:
        return False
    if current_section == "Professional Experience" and (
        _looks_like_employer_line(line) or _looks_like_title_line(line)
    ):
        return False
    if raw_line[:1].isspace():
        return True
    if previous_line.startswith(("- ", "  - ")):
        return True
    if current_section == "Professional Experience" and _looks_like_date_continuation(
        previous_line=previous_line,
        line=line,
    ):
        return True
    return current_section == "Professional Summary" and not line.startswith("Note:")


def _looks_like_date_continuation(*, previous_line: str, line: str) -> bool:
    normalized_line = line.replace("\u2013", "-").replace("\u2014", "-")
    if not PROFESSIONAL_EXPERIENCE_DATE_CONTINUATION_RE.fullmatch(normalized_line):
        return False
    return previous_line.endswith(MONTH_ABBREVIATIONS) or previous_line.endswith(
        ("-", "\u2013", "\u2014")
    )


def _patch_cover_letter_pdf(path: Path) -> bool:
    reader = PdfReader(path)
    text = _extract_pdf_text(reader)
    if LINKEDIN_PROFILE_LABEL in text:
        return _ensure_cover_letter_link_annotation(path=path, reader=reader)

    writer = PdfWriter(clone_from=reader)
    for page_number, page in enumerate(writer.pages):
        content = ContentStream(page.get_contents(), writer)
        link_location = _insert_cover_letter_link(content)
        if link_location is None:
            continue
        page.replace_contents(content)
        if not _page_has_uri(page, LINKEDIN_PROFILE_URL):
            _add_link_annotation(
                writer=writer,
                page_number=page_number,
                location=link_location,
                font_label=LINKEDIN_PROFILE_LABEL,
            )
        _write_pdf(path=path, writer=writer)
        return True
    return False


def _patch_cover_letter_project_paragraph_pdf(path: Path) -> bool:
    reader = PdfReader(path)
    text = _normalize_pdf_text(_extract_pdf_text(reader))
    if OLD_COVER_LETTER_PROJECT_ENDING_TEXT not in text:
        return False
    if NEW_COVER_LETTER_PROJECT_ENDING_TEXT in text:
        return False

    writer = PdfWriter(clone_from=reader)
    for page in writer.pages:
        content = ContentStream(page.get_contents(), writer)
        extra_line_count = _replace_cover_letter_project_ending(content)
        if extra_line_count is None:
            continue
        page.replace_contents(content)
        if extra_line_count > 0:
            _shift_uri_annotations(
                page=page,
                url=LINKEDIN_PROFILE_URL,
                y_delta=-(COVER_LETTER_LINE_LEADING * extra_line_count),
            )
        _write_pdf(path=path, writer=writer)
        return True
    return False


def _ensure_cover_letter_link_annotation(*, path: Path, reader: PdfReader) -> bool:
    for page_number, page in enumerate(reader.pages):
        hit = _find_text_hit(page, LINKEDIN_PROFILE_LABEL)
        if hit is None:
            continue
        if _page_has_uri(page, LINKEDIN_PROFILE_URL):
            return False
        writer = PdfWriter(clone_from=reader)
        _add_link_annotation(
            writer=writer,
            page_number=page_number,
            location=_LinkLocation(
                x=hit.x,
                y=hit.y,
                font_name=hit.font_name,
                font_size=hit.font_size,
            ),
            font_label=LINKEDIN_PROFILE_LABEL,
        )
        _write_pdf(path=path, writer=writer)
        return True
    return False


def _extract_pdf_text(reader: PdfReader) -> str:
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _normalize_pdf_text(text: str) -> str:
    return " ".join(text.split())


def _find_text_hit(page: Any, needle: str) -> _TextHit | None:
    hits: list[_TextHit] = []

    def visitor(
        text: str,
        current_matrix: list[float],
        text_matrix: list[float],
        font_dictionary: dict[str, Any] | None,
        font_size: float,
    ) -> None:
        if needle not in text:
            return
        font_name = "Helvetica"
        if font_dictionary is not None:
            base_font = str(font_dictionary.get("/BaseFont", "")).lstrip("/")
            if base_font:
                font_name = base_font
        hits.append(
            _TextHit(
                x=float(current_matrix[4]) + float(text_matrix[4]),
                y=float(current_matrix[5]) + float(text_matrix[5]),
                font_name=font_name,
                font_size=float(font_size),
            )
        )

    page.extract_text(visitor_text=visitor)
    return hits[0] if hits else None


def _replace_text_in_content(
    content: ContentStream,
    *,
    old_text: str,
    new_text: str,
) -> bool:
    changed = False
    for operands, operator in content.operations:
        if operator in (b"Tj", b"'", b'"'):
            for index, operand in enumerate(operands):
                if isinstance(operand, str) and old_text in operand:
                    operands[index] = TextStringObject(operand.replace(old_text, new_text))
                    changed = True
        elif operator == b"TJ" and operands:
            for index, item in enumerate(operands[0]):
                if isinstance(item, str) and old_text in item:
                    operands[0][index] = TextStringObject(item.replace(old_text, new_text))
                    changed = True
    return changed


def _replace_cover_letter_project_ending(content: ContentStream) -> int | None:
    if not _content_has_text_lines(content, OLD_COVER_LETTER_PROJECT_ENDING_LINES):
        return None

    new_operations: list[tuple[list[Any], bytes]] = []
    replacement_index = 0
    extra_line_count = max(
        len(NEW_COVER_LETTER_PROJECT_ENDING_LINES)
        - len(OLD_COVER_LETTER_PROJECT_ENDING_LINES),
        0,
    )
    shift_following_content = False

    for operands, operator in content.operations:
        if shift_following_content and operator == b"cm" and len(operands) >= 6:
            operands[5] = FloatObject(
                float(operands[5]) - (COVER_LETTER_LINE_LEADING * extra_line_count)
            )

        new_operations.append((operands, operator))
        replacement_index, finished_replacement = _replace_project_line_operand(
            operands=operands,
            operator=operator,
            replacement_index=replacement_index,
        )
        if finished_replacement and extra_line_count:
            for extra_line in NEW_COVER_LETTER_PROJECT_ENDING_LINES[
                len(OLD_COVER_LETTER_PROJECT_ENDING_LINES) :
            ]:
                new_operations.extend(
                    [
                        ([], b"T*"),
                        ([TextStringObject(extra_line)], b"Tj"),
                    ]
                )
            shift_following_content = True

    if replacement_index != len(OLD_COVER_LETTER_PROJECT_ENDING_LINES):
        return None
    content.operations = new_operations
    return extra_line_count


def _content_has_text_lines(content: ContentStream, lines: tuple[str, ...]) -> bool:
    remaining = list(lines)
    for operands, operator in content.operations:
        text_values = _text_values_for_operator(operands=operands, operator=operator)
        for text_value in text_values:
            if remaining and text_value == remaining[0]:
                remaining.pop(0)
    return not remaining


def _replace_project_line_operand(
    *,
    operands: list[Any],
    operator: bytes,
    replacement_index: int,
) -> tuple[int, bool]:
    inserted_final_line = False
    if operator in (b"Tj", b"'", b'"'):
        for index, operand in enumerate(operands):
            if not isinstance(operand, str):
                continue
            replacement_index, replacement, inserted_line = _replacement_project_text_value(
                text_value=operand,
                replacement_index=replacement_index,
            )
            if replacement is not None:
                operands[index] = TextStringObject(replacement)
            inserted_final_line = inserted_final_line or inserted_line
    elif operator == b"TJ" and operands:
        for index, item in enumerate(operands[0]):
            if not isinstance(item, str):
                continue
            replacement_index, replacement, inserted_line = _replacement_project_text_value(
                text_value=item,
                replacement_index=replacement_index,
            )
            if replacement is not None:
                operands[0][index] = TextStringObject(replacement)
            inserted_final_line = inserted_final_line or inserted_line
    return replacement_index, inserted_final_line


def _replacement_project_text_value(
    *,
    text_value: str,
    replacement_index: int,
) -> tuple[int, str | None, bool]:
    if replacement_index >= len(OLD_COVER_LETTER_PROJECT_ENDING_LINES):
        return replacement_index, None, False
    if text_value != OLD_COVER_LETTER_PROJECT_ENDING_LINES[replacement_index]:
        return replacement_index, None, False
    replacement = (
        NEW_COVER_LETTER_PROJECT_ENDING_LINES[replacement_index]
        if replacement_index < len(NEW_COVER_LETTER_PROJECT_ENDING_LINES)
        else ""
    )
    replacement_index += 1
    finished_replacement = replacement_index == len(OLD_COVER_LETTER_PROJECT_ENDING_LINES)
    return replacement_index, replacement, finished_replacement


def _text_values_for_operator(*, operands: list[Any], operator: bytes) -> list[str]:
    if operator in (b"Tj", b"'", b'"'):
        return [operand for operand in operands if isinstance(operand, str)]
    if operator == b"TJ" and operands:
        return [item for item in operands[0] if isinstance(item, str)]
    return []


def _insert_cover_letter_link(content: ContentStream) -> _LinkLocation | None:
    new_operations: list[tuple[list[Any], bytes]] = []
    current_cm = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
    current_tm = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
    current_leading = 12.0
    current_font_name = "Helvetica"
    current_font_size = 10.5
    line_moves = 0
    pending_link_location: _LinkLocation | None = None
    inserted_location: _LinkLocation | None = None

    for operands, operator in content.operations:
        new_operations.append((operands, operator))

        if operator == b"cm" and len(operands) >= 6:
            current_cm = [float(value) for value in operands[:6]]
        elif operator == b"BT":
            line_moves = 0
        elif operator == b"Tm" and len(operands) >= 6:
            current_tm = [float(value) for value in operands[:6]]
            line_moves = 0
        elif operator == b"TL" and operands:
            current_leading = float(operands[0])
        elif operator == b"Tf" and len(operands) >= 2:
            current_font_name = _font_name_from_operand(operands[0])
            current_font_size = float(operands[1])
        elif operator == b"T*":
            line_moves += 1
            if pending_link_location is not None:
                new_operations.extend(
                    [
                        ([FloatObject(0), FloatObject(0), FloatObject(1)], b"rg"),
                        ([TextStringObject(LINKEDIN_PROFILE_LABEL)], b"Tj"),
                        ([], b"T*"),
                    ]
                )
                inserted_location = pending_link_location
                pending_link_location = None
        elif _operator_has_text(operator, operands, "Maxim Perkhounkov"):
            link_line_moves = line_moves + 1
            pending_link_location = _LinkLocation(
                x=current_cm[4] + current_tm[4],
                y=current_cm[5] + current_tm[5] - (link_line_moves * current_leading),
                font_name=current_font_name,
                font_size=current_font_size,
            )

    if inserted_location is not None:
        content.operations = new_operations
    return inserted_location


def _operator_has_text(operator: bytes, operands: list[Any], needle: str) -> bool:
    if operator in (b"Tj", b"'", b'"'):
        return any(isinstance(operand, str) and needle in operand for operand in operands)
    if operator == b"TJ" and operands:
        return any(isinstance(item, str) and needle in item for item in operands[0])
    return False


def _font_name_from_operand(operand: Any) -> str:
    value = str(operand).lstrip("/")
    if value == "F2":
        return "Helvetica-Bold"
    return "Helvetica"


def _add_resume_link_annotation(
    *,
    writer: PdfWriter,
    page_number: int,
    hit: _TextHit,
) -> None:
    link_x = hit.x + stringWidth(RESUME_CONTACT_PREFIX, hit.font_name, hit.font_size)
    location = _LinkLocation(
        x=link_x,
        y=hit.y,
        font_name=hit.font_name,
        font_size=hit.font_size,
    )
    _add_link_annotation(
        writer=writer,
        page_number=page_number,
        location=location,
        font_label=LINKEDIN_PROFILE_LABEL,
    )


def _add_link_annotation(
    *,
    writer: PdfWriter,
    page_number: int,
    location: _LinkLocation,
    font_label: str,
) -> None:
    width = stringWidth(font_label, location.font_name, location.font_size)
    writer.add_annotation(
        page_number,
        Link(
            rect=(
                location.x,
                location.y - 2,
                location.x + width,
                location.y + location.font_size + 2,
            ),
            url=LINKEDIN_PROFILE_URL,
        ),
    )


def _page_has_uri(page: Any, url: str) -> bool:
    for annotation_ref in page.get("/Annots") or []:
        annotation = annotation_ref.get_object()
        action = annotation.get("/A")
        if action is not None and action.get("/URI") == url:
            return True
    return False


def _shift_uri_annotations(*, page: Any, url: str, y_delta: float) -> None:
    for annotation_ref in page.get("/Annots") or []:
        annotation = annotation_ref.get_object()
        action = annotation.get("/A")
        if action is None or action.get("/URI") != url:
            continue
        rectangle = annotation.get("/Rect")
        if rectangle is None or len(rectangle) < 4:
            continue
        rectangle[1] = FloatObject(float(rectangle[1]) + y_delta)
        rectangle[3] = FloatObject(float(rectangle[3]) + y_delta)


def _write_pdf(*, path: Path, writer: PdfWriter) -> None:
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    with temp_path.open("wb") as handle:
        writer.write(handle)
    temp_path.replace(path)


def _sync_updated_artifacts(
    *,
    database_path: Path,
    resume_updates: dict[str, Path],
    cover_letter_updates: dict[str, Path],
) -> int:
    updated_job_ids = sorted(set(resume_updates) | set(cover_letter_updates))
    if not updated_job_ids:
        return 0
    now = datetime.now(UTC).isoformat(timespec="seconds")
    with connect_database(database_path) as connection:
        for job_id in updated_job_ids:
            resume_path = resume_updates.get(job_id)
            if resume_path is not None:
                connection.execute(
                    """
                    UPDATE applications
                    SET resume_filename = ?,
                        resume_content = ?,
                        resume_mime_type = 'application/pdf',
                        source_resume_path = ?,
                        updated_at = ?
                    WHERE job_id = ?
                    """,
                    (
                        resume_path.name,
                        resume_path.read_bytes(),
                        str(resume_path),
                        now,
                        job_id,
                    ),
                )
            cover_letter_path = cover_letter_updates.get(job_id)
            if cover_letter_path is not None:
                connection.execute(
                    """
                    UPDATE applications
                    SET cover_letter_filename = ?,
                        cover_letter_content = ?,
                        cover_letter_mime_type = 'application/pdf',
                        source_cover_letter_path = ?,
                        updated_at = ?
                    WHERE job_id = ?
                    """,
                    (
                        cover_letter_path.name,
                        cover_letter_path.read_bytes(),
                        str(cover_letter_path),
                        now,
                        job_id,
                    ),
                )
        connection.commit()
    return len(updated_job_ids)


def refresh_static_artifacts_main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Patch static resume and cover-letter text in existing PDF artifacts "
            "without calling LinkedIn or any LLM API."
        )
    )
    parser.add_argument(
        "job_ids",
        nargs="*",
        help="Optional job ID or comma-separated job ID list to patch.",
    )
    parser.add_argument(
        "--database-path",
        type=Path,
        default=DEFAULT_APPLICATION_DATABASE,
        help=f"Application database path. Defaults to {DEFAULT_APPLICATION_DATABASE}.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory. Defaults to {DEFAULT_OUTPUT_DIR}.",
    )
    args = parser.parse_args()
    job_ids = _parse_job_ids(args.job_ids)
    result = refresh_static_artifacts(
        database_path=args.database_path,
        output_dir=args.output_dir,
        job_ids=job_ids,
    )
    print(
        "Static artifacts refreshed: "
        f"{result.resumes_updated}/{result.resumes_checked} resumes, "
        f"{result.cover_letters_updated}/{result.cover_letters_checked} cover letters, "
        f"{result.database_rows_updated} database rows updated.",
        file=sys.stderr,
    )
    if result.missing_files:
        print("Missing artifact files:", file=sys.stderr)
        for path in result.missing_files:
            print(f"- {path}", file=sys.stderr)


def stylize_resume_main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Render an existing resume PDF with the emerald resume style. "
            "The input PDF is left untouched and the output is written beside it by default."
        )
    )
    parser.add_argument("input_path", type=Path, help="Resume PDF to restyle.")
    parser.add_argument(
        "--output-path",
        type=Path,
        default=None,
        help="Optional output PDF path. Defaults to INPUT_STEM_emerald.pdf in the input directory.",
    )
    parser.add_argument(
        "--suffix",
        default=STYLIZED_RESUME_DEFAULT_SUFFIX,
        help="Filename suffix used when --output-path is omitted. Defaults to emerald.",
    )
    args = parser.parse_args()

    try:
        result = stylize_resume_pdf(
            input_path=args.input_path,
            output_path=args.output_path,
            output_suffix=args.suffix,
        )
    except ValueError as exc:
        parser.exit(status=1, message=f"error: {exc}\n")

    print(
        "Resume stylized: "
        f"{result.pages_read} page(s), {result.lines_rendered} rendered line(s).",
        file=sys.stderr,
    )
    print(result.output_path)


def stylize_cover_letter_main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Render an existing cover letter PDF with the emerald cover-letter style. "
            "The input PDF is left untouched and the output is written beside it by default."
        )
    )
    parser.add_argument("input_path", type=Path, help="Cover letter PDF to restyle.")
    parser.add_argument(
        "--output-path",
        type=Path,
        default=None,
        help="Optional output PDF path. Defaults to INPUT_STEM_emerald.pdf in the input directory.",
    )
    parser.add_argument(
        "--suffix",
        default=STYLIZED_RESUME_DEFAULT_SUFFIX,
        help="Filename suffix used when --output-path is omitted. Defaults to emerald.",
    )
    args = parser.parse_args()

    try:
        result = stylize_cover_letter_pdf(
            input_path=args.input_path,
            output_path=args.output_path,
            output_suffix=args.suffix,
        )
    except ValueError as exc:
        parser.exit(status=1, message=f"error: {exc}\n")

    print(
        "Cover letter stylized: "
        f"{result.pages_read} page(s), {result.paragraphs_rendered} rendered paragraph(s).",
        file=sys.stderr,
    )
    print(result.output_path)


def _parse_job_ids(values: list[str]) -> list[str]:
    job_ids: list[str] = []
    for value in values:
        job_ids.extend(
            part.strip()
            for part in value.split(",")
            if part.strip() and part.strip().lower() != "all"
        )
    return sorted(set(job_ids))
