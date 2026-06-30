#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from linkedin_career_mcp.resume_highlighting import (
    DEFAULT_CODEX_COMMAND,
    DEFAULT_CODEX_MODEL,
    DEFAULT_CODEX_TIMEOUT_SECONDS,
    ResumeHighlightError,
    apply_highlight_response,
    build_resume_highlight_prompt,
    collect_highlight_bullets_for_jobs,
    run_codex_highlight,
)
from linkedin_career_mcp.resume_rendering import (
    render_resume_html_from_mapping,
    render_resume_pdf_from_html,
)
from linkedin_career_mcp.webapp import (
    DEFAULT_DATABASE,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_RESUME_TEMPLATE,
    connect_database,
    store_application_resume_first_draft,
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Use a guarded Codex workflow to add selective <strong> highlighting "
            "to stored ARO draft resumes."
        )
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_OUTPUT_DIR / DEFAULT_DATABASE,
    )
    parser.add_argument(
        "--template",
        type=Path,
        default=DEFAULT_RESUME_TEMPLATE,
        help="Resume HTML template used for the re-rendered draft.",
    )
    parser.add_argument(
        "--job-id",
        action="append",
        dest="job_ids",
        help="Only process this job ID. May be passed multiple times.",
    )
    parser.add_argument("--limit", type=int, help="Process at most this many rows.")
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        help="Optionally write prompts, Codex responses, YAML, HTML, and PDF files.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Do not write database updates.")
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop on the first row that cannot be highlighted.",
    )
    parser.add_argument(
        "--codex-command",
        default=os.environ.get("LINKEDIN_CAREER_MCP_CODEX_COMMAND", DEFAULT_CODEX_COMMAND),
        help="Codex CLI command. Defaults to env or 'codex'.",
    )
    parser.add_argument(
        "--codex-model",
        default=os.environ.get("LINKEDIN_CAREER_MCP_CODEX_MODEL", DEFAULT_CODEX_MODEL),
        help="Codex model used for the polish step.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=int(
            os.environ.get(
                "LINKEDIN_CAREER_MCP_CODEX_TIMEOUT_SECONDS",
                DEFAULT_CODEX_TIMEOUT_SECONDS,
            )
        ),
        help="Maximum seconds to wait for each Codex highlighting call.",
    )
    parser.add_argument(
        "--max-strong-spans-per-bullet",
        type=int,
        default=3,
        help="Maximum <strong> spans Codex may add to any one bullet.",
    )
    parser.add_argument(
        "--experience-company",
        help="Only highlight professional-experience jobs whose company contains this text.",
    )
    parser.add_argument(
        "--experience-job-order",
        help="Only highlight the professional-experience job with this ARO order value.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    rows = _load_rows(
        database_path=args.database,
        job_ids=set(args.job_ids or []),
        limit=args.limit,
    )
    print(
        (
            f"Candidates: {len(rows)} (database={args.database}, "
            f"codex_model={args.codex_model})"
        ),
        file=sys.stderr,
        flush=True,
    )

    processed = 0
    failed = 0
    skipped = 0
    for index, row in enumerate(rows, start=1):
        job_id = str(row["job_id"])
        print(f"[{index}/{len(rows)}] Codex highlighting draft resume: {job_id}", file=sys.stderr)
        try:
            outcome = _highlight_row(
                row=row,
                database_path=args.database,
                template_path=args.template,
                artifact_dir=args.artifact_dir,
                dry_run=args.dry_run,
                codex_command=args.codex_command,
                codex_model=args.codex_model,
                timeout_seconds=args.timeout_seconds,
                max_strong_spans_per_bullet=args.max_strong_spans_per_bullet,
                experience_company=args.experience_company,
                experience_job_order=args.experience_job_order,
            )
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"[{job_id}] highlighting failed: {exc}", file=sys.stderr, flush=True)
            if args.fail_fast:
                break
            continue

        if outcome == "skipped":
            skipped += 1
            continue
        processed += 1

    summary = {"processed": processed, "failed": failed, "skipped": skipped}
    print(
        (
            f"Codex highlighted draft resumes: {processed}, "
            f"skipped: {skipped}, failed: {failed}"
        ),
        file=sys.stderr,
        flush=True,
    )
    print(json.dumps(summary, sort_keys=True))
    return 1 if failed else 0


def _highlight_row(
    *,
    row: sqlite3.Row,
    database_path: Path,
    template_path: Path,
    artifact_dir: Path | None,
    dry_run: bool,
    codex_command: str,
    codex_model: str,
    timeout_seconds: int,
    max_strong_spans_per_bullet: int,
    experience_company: str | None,
    experience_job_order: str | None,
) -> str:
    job_id = str(row["job_id"])
    application_resume = _yaml_mapping(row["application_resume_object"])
    bullets = collect_highlight_bullets_for_jobs(
        application_resume,
        experience_company=experience_company,
        experience_job_order=experience_job_order,
    )
    if not bullets:
        print(f"[{job_id}] skipped: no rendered professional-experience bullets", file=sys.stderr)
        return "skipped"

    prompt = build_resume_highlight_prompt(
        application_resume,
        job_id=job_id,
        company=str(row["company"] or ""),
        job_title=str(row["job_title"] or ""),
        experience_company=experience_company,
        experience_job_order=experience_job_order,
        max_strong_spans_per_bullet=max_strong_spans_per_bullet,
    )
    _write_artifact(
        artifact_dir=artifact_dir,
        job_id=job_id,
        suffix="highlight_prompt.txt",
        content=prompt,
    )
    response = run_codex_highlight(
        prompt,
        project_root=_project_root(),
        codex_command=codex_command,
        codex_model=codex_model,
        timeout_seconds=timeout_seconds,
    )
    _write_artifact(
        artifact_dir=artifact_dir,
        job_id=job_id,
        suffix="highlight_response.json",
        content=f"{response}\n",
    )

    updated_resume, stats = apply_highlight_response(
        application_resume,
        response,
        experience_company=experience_company,
        experience_job_order=experience_job_order,
        max_strong_spans_per_bullet=max_strong_spans_per_bullet,
    )
    aro_yaml = yaml.safe_dump(updated_resume, sort_keys=False, allow_unicode=False)
    resume_html = render_resume_html_from_mapping(
        resume=updated_resume,
        template_path=template_path,
    )
    resume_pdf = render_resume_pdf_from_html(resume_html)

    safe_job_id = _safe_filename(job_id)
    html_path: Path | None = None
    pdf_path: Path | None = None
    if artifact_dir is not None:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        aro_path = artifact_dir / f"{safe_job_id}_highlighted.yml"
        html_path = artifact_dir / f"{safe_job_id}_highlighted.html"
        pdf_path = artifact_dir / f"{safe_job_id}_highlighted.pdf"
        aro_path.write_text(aro_yaml, encoding="utf-8")
        html_path.write_text(resume_html, encoding="utf-8")
        pdf_path.write_bytes(resume_pdf)

    if not dry_run:
        store_application_resume_first_draft(
            database_path=database_path,
            job_id=job_id,
            application_resume_object=aro_yaml,
            resume_html=resume_html,
            resume_pdf=resume_pdf,
            resume_html_path=html_path,
            resume_pdf_path=pdf_path,
        )

    print(
        (
            f"[{job_id}] highlighted {stats.bullet_count} bullets with "
            f"{stats.strong_span_count} strong spans"
        ),
        file=sys.stderr,
        flush=True,
    )
    return "processed"


def _load_rows(
    *,
    database_path: Path,
    job_ids: set[str],
    limit: int | None,
) -> list[sqlite3.Row]:
    with connect_database(database_path) as connection:
        rows = connection.execute(
            """
            SELECT job_id, company, job_title, application_resume_object
            FROM applications
            WHERE COALESCE(NULLIF(application_resume_object, ''), '') != ''
            ORDER BY rowid
            """
        ).fetchall()

    filtered: list[sqlite3.Row] = []
    for row in rows:
        job_id = str(row["job_id"])
        if job_ids and job_id not in job_ids:
            continue
        filtered.append(row)
        if limit is not None and len(filtered) >= max(limit, 0):
            break
    return filtered


def _yaml_mapping(value: object) -> Mapping[str, Any]:
    try:
        payload = yaml.safe_load(str(value or "")) or {}
    except yaml.YAMLError as exc:
        raise ResumeHighlightError(f"Application resume object is not valid YAML: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise ResumeHighlightError("Application resume object must be a YAML mapping.")
    return payload


def _write_artifact(
    *,
    artifact_dir: Path | None,
    job_id: str,
    suffix: str,
    content: str,
) -> None:
    if artifact_dir is None:
        return
    artifact_dir.mkdir(parents=True, exist_ok=True)
    path = artifact_dir / f"{_safe_filename(job_id)}_{suffix}"
    path.write_text(content, encoding="utf-8")


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _safe_filename(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)


if __name__ == "__main__":
    raise SystemExit(main())
