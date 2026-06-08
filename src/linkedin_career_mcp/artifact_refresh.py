from __future__ import annotations

import argparse
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
    DEFAULT_OUTPUT_DIR,
    LINKEDIN_PROFILE_LABEL,
    LINKEDIN_PROFILE_URL,
)

OLD_LINKEDIN_PROFILE_LABEL = "linkedin.com/mperkhou"
DEFAULT_APPLICATION_DATABASE = DEFAULT_OUTPUT_DIR / RELATIVE_APPLICATION_DATABASE
RESUME_CONTACT_PREFIX = (
    "Iowa City, IA | 641-781-0477 | mperkhounkov1@gmail.com | "
)
OLD_RESUME_CONTACT_LINE = f"{RESUME_CONTACT_PREFIX}{OLD_LINKEDIN_PROFILE_LABEL}"
NEW_RESUME_CONTACT_LINE = f"{RESUME_CONTACT_PREFIX}{LINKEDIN_PROFILE_LABEL}"


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
                if _patch_resume_pdf(resume_path):
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
                if _patch_cover_letter_pdf(cover_letter_path):
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
            "Patch static resume and cover-letter profile-link text in existing PDF "
            "artifacts without calling LinkedIn or any LLM API."
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


def _parse_job_ids(values: list[str]) -> list[str]:
    job_ids: list[str] = []
    for value in values:
        job_ids.extend(
            part.strip()
            for part in value.split(",")
            if part.strip() and part.strip().lower() != "all"
        )
    return sorted(set(job_ids))
