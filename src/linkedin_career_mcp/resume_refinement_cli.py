from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from linkedin_career_mcp.application_resume import DEFAULT_MASTER_RESUME_PATH
from linkedin_career_mcp.ats import calculate_ats_diagnostics
from linkedin_career_mcp.config import load_settings
from linkedin_career_mcp.jod import usable_job_description
from linkedin_career_mcp.llm import build_llm_client
from linkedin_career_mcp.resume_refinement import (
    build_resume_critique_evidence_packet,
    build_second_pass_resume_critique_prompt,
    classify_external_resume_critique,
    parse_second_pass_resume_critique_response,
    validate_and_apply_second_pass_resume_patches,
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
    save_application_resume_edit,
)

SECOND_PASS_RESUME_REFINEMENT_AUDIT_SCHEMA_VERSION = "second_pass_resume_refinement_audit.v1"
DEFAULT_AUDIT_DIR = DEFAULT_OUTPUT_DIR / "resume_refinement_audits"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run second-pass resume refinement for one stored ARO."
    )
    parser.add_argument("--job-id", required=True, help="Stored application job ID to refine.")
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_OUTPUT_DIR / DEFAULT_DATABASE,
    )
    parser.add_argument("--master-resume", type=Path, default=DEFAULT_MASTER_RESUME_PATH)
    parser.add_argument("--template", type=Path, default=DEFAULT_RESUME_TEMPLATE)
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=DEFAULT_AUDIT_DIR,
        help="Directory where the JSON audit artifact is written.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply accepted patches to SQLite and re-render the stored resume artifacts.",
    )
    parser.add_argument(
        "--api-model",
        help="Override the configured API model for the second-pass critique call.",
    )
    parser.add_argument(
        "--external-critique-file",
        type=Path,
        help="Optional pasted external critique text file to classify before refinement.",
    )
    parser.add_argument(
        "--external-critique-text",
        help="Optional pasted external critique text to classify before refinement.",
    )
    return parser


async def main_async(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    external_critique_text = _external_critique_text(
        inline_text=args.external_critique_text,
        file_path=args.external_critique_file,
    )
    settings = load_settings()
    llm = build_llm_client(settings, api_model=args.api_model)
    try:
        audit = await run_second_pass_refinement_for_job(
            database_path=args.database,
            job_id=args.job_id,
            master_resume_path=args.master_resume,
            template_path=args.template,
            artifact_dir=args.artifact_dir,
            apply=args.apply,
            llm=llm,
            external_critique_text=external_critique_text,
        )
    finally:
        await llm.aclose()

    print(
        json.dumps(
            {
                "job_id": args.job_id,
                "audit_path": audit["audit_path"],
                "accepted": len(audit["validation"]["accepted_change_ids"]),
                "rejected": len(audit["validation"]["rejected_changes"]),
                "applied": audit["applied"],
                "external_suggestions": len(
                    (audit.get("external_critique") or {}).get("suggestions", [])
                ),
            },
            sort_keys=True,
        )
    )
    return 0


async def run_second_pass_refinement_for_job(
    *,
    database_path: Path,
    job_id: str,
    master_resume_path: Path,
    template_path: Path,
    artifact_dir: Path,
    apply: bool,
    llm: Any,
    external_critique_text: str | None = None,
) -> dict[str, Any]:
    row = _load_row(database_path=database_path, job_id=job_id)
    application_resume = _yaml_mapping(row["application_resume_object"], label="ARO")
    master_resume = _yaml_mapping(master_resume_path.read_text(encoding="utf-8"), label="MRO")
    job_description = _row_job_description(row)
    resume_pdf = _row_resume_pdf(
        row,
        application_resume=application_resume,
        template_path=template_path,
    )

    ats_diagnostics = calculate_ats_diagnostics(
        resume_pdf=resume_pdf,
        job_description=job_description,
    )
    evidence_packet = build_resume_critique_evidence_packet(
        application_resume=application_resume,
        master_resume=master_resume,
        ats_diagnostics=ats_diagnostics,
    )
    external_critique_report = (
        classify_external_resume_critique(
            external_critique_text=external_critique_text,
            evidence_packet=evidence_packet,
        )
        if external_critique_text
        else None
    )
    critique_prompt = build_second_pass_resume_critique_prompt(
        job_id=job_id,
        company=str(row["company"] or ""),
        job_title=str(row["job_title"] or ""),
        application_resume=application_resume,
        master_resume=master_resume,
        ats_diagnostics=ats_diagnostics,
        external_critique_suggestions=(
            external_critique_report.supported_suggestions
            if external_critique_report is not None
            else None
        ),
    )
    critique_response = await llm.generate_text(critique_prompt)
    critique = parse_second_pass_resume_critique_response(critique_response)
    patch_result = validate_and_apply_second_pass_resume_patches(
        application_resume=application_resume,
        critique=critique,
        evidence_packet=evidence_packet,
    )

    applied_change_ids: list[str] = []
    if apply and patch_result.validation.accepted_change_ids:
        updated_yaml = yaml.safe_dump(
            patch_result.updated_resume,
            sort_keys=False,
            allow_unicode=False,
        )
        save_application_resume_edit(
            database_path=database_path,
            job_id=job_id,
            application_resume_object=updated_yaml,
            template_path=template_path,
        )
        applied_change_ids = patch_result.validation.accepted_change_ids

    audit = {
        "schema_version": SECOND_PASS_RESUME_REFINEMENT_AUDIT_SCHEMA_VERSION,
        "job": {
            "job_id": job_id,
            "company": str(row["company"] or ""),
            "job_title": str(row["job_title"] or ""),
        },
        "apply_requested": apply,
        "applied": bool(applied_change_ids),
        "applied_change_ids": applied_change_ids,
        "ats_diagnostics": asdict(ats_diagnostics),
        "evidence_packet": evidence_packet.model_dump(),
        "external_critique": (
            external_critique_report.model_dump()
            if external_critique_report is not None
            else None
        ),
        "critique_prompt": critique_prompt,
        "critique_response": critique_response,
        "critique": critique.model_dump(),
        "validation": {
            **patch_result.validation.model_dump(),
            "is_valid": patch_result.validation.is_valid,
        },
    }
    audit_path = _audit_artifact_path(
        artifact_dir=artifact_dir,
        job_id=job_id,
    )
    audit["audit_path"] = str(audit_path)
    audit_path.write_text(f"{json.dumps(audit, indent=2, sort_keys=True)}\n", encoding="utf-8")
    return audit


def _external_critique_text(
    *,
    inline_text: str | None,
    file_path: Path | None,
) -> str | None:
    parts: list[str] = []
    if file_path is not None:
        parts.append(file_path.read_text(encoding="utf-8"))
    if inline_text:
        parts.append(inline_text)
    text = "\n".join(part.strip() for part in parts if part.strip()).strip()
    return text or None


def _load_row(*, database_path: Path, job_id: str) -> sqlite3.Row:
    with connect_database(database_path) as connection:
        row = connection.execute(
            """
            SELECT job_id, company, job_title, prompt_job_description, job_description,
                   application_resume_object, resume_content
            FROM applications
            WHERE job_id = ?
            """,
            (job_id,),
        ).fetchone()
    if row is None:
        raise ValueError(f"Application row was not found for job_id={job_id}.")
    if not str(row["application_resume_object"] or "").strip():
        raise ValueError(f"Application row has no stored ARO for job_id={job_id}.")
    return row


def _row_job_description(row: sqlite3.Row) -> str:
    job_description = (
        usable_job_description(row["prompt_job_description"])
        or usable_job_description(row["job_description"])
    )
    if not job_description:
        raise ValueError("Application row has no usable JOD text.")
    return job_description


def _row_resume_pdf(
    row: sqlite3.Row,
    *,
    application_resume: Mapping[str, Any],
    template_path: Path,
) -> bytes:
    resume_content = row["resume_content"]
    if isinstance(resume_content, bytes) and resume_content:
        return resume_content
    resume_html = render_resume_html_from_mapping(
        resume=application_resume,
        template_path=template_path,
    )
    return render_resume_pdf_from_html(resume_html)


def _yaml_mapping(value: object, *, label: str) -> dict[str, Any]:
    try:
        parsed = yaml.safe_load(str(value or "")) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"{label} is not valid YAML: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{label} must be a YAML mapping.")
    return parsed


def _audit_artifact_path(
    *,
    artifact_dir: Path,
    job_id: str,
) -> Path:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    return artifact_dir / f"{_safe_filename(job_id)}_second_pass_refinement_audit.json"


def _safe_filename(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)


def main(argv: Sequence[str] | None = None) -> None:
    raise SystemExit(asyncio.run(main_async(argv)))


if __name__ == "__main__":
    main()
