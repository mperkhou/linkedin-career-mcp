from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, replace
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
    DEFAULT_RESUME_VARIANT,
    SECOND_PASS_RESUME_VARIANT,
    backfill_application_resume_v1_variants,
    connect_database,
    fetch_active_resume_refinement_job_ids,
    fetch_resume_variant_comparisons,
    store_application_resume_variant,
)

SECOND_PASS_RESUME_REFINEMENT_AUDIT_SCHEMA_VERSION = "second_pass_resume_refinement_audit.v1"
DEFAULT_AUDIT_DIR = DEFAULT_OUTPUT_DIR / "resume_refinement_audits"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run second-pass resume refinement for stored ARO drafts."
    )
    parser.add_argument(
        "--job-id",
        action="append",
        help="Stored application job ID to refine. May be passed multiple times.",
    )
    parser.add_argument(
        "--all-active",
        action="store_true",
        help="Run against every non-archived application row with a stored ARO.",
    )
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
        help=(
            "Deprecated. Second-pass audit data is now stored in SQLite resume variants."
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Deprecated compatibility flag. The workflow stores v2; automatic "
            "resume selection uses manual, then v2, then v1 precedence."
        ),
    )
    parser.add_argument(
        "--api-model",
        help="Override the configured API model for the second-pass critique call.",
    )
    parser.add_argument(
        "--api-timeout-seconds",
        type=float,
        help="Override the configured API timeout for the second-pass critique call.",
    )
    parser.add_argument(
        "--api-retries",
        type=int,
        default=1,
        help="Number of timeout retries for the second-pass critique call.",
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
    job_ids = _selected_job_ids(
        database_path=args.database,
        job_ids=args.job_id,
        all_active=args.all_active,
    )
    backfilled_v1_count = backfill_application_resume_v1_variants(args.database)
    settings = load_settings()
    if args.api_timeout_seconds is not None:
        settings = replace(
            settings,
            llm_api_timeout_seconds=max(1.0, args.api_timeout_seconds),
            ollama_timeout_seconds=max(1.0, args.api_timeout_seconds),
        )
    llm = build_llm_client(settings, api_model=args.api_model)
    audits: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    try:
        for index, job_id in enumerate(job_ids, start=1):
            print(
                f"[{index}/{len(job_ids)}] running second-pass refinement for {job_id}",
                file=sys.stderr,
                flush=True,
            )
            try:
                audit = await run_second_pass_refinement_for_job(
                    database_path=args.database,
                    job_id=job_id,
                    master_resume_path=args.master_resume,
                    template_path=args.template,
                    artifact_dir=args.artifact_dir,
                    apply=args.apply,
                    llm=llm,
                    generation_timeout_seconds=args.api_timeout_seconds,
                    generation_retry_count=args.api_retries,
                    external_critique_text=external_critique_text,
                )
                audits.append(audit)
                print(
                    f"[{index}/{len(job_ids)}] stored v2 for {job_id} "
                    f"accepted={len(audit['validation']['accepted_change_ids'])} "
                    f"rejected={len(audit['validation']['rejected_changes'])}",
                    file=sys.stderr,
                    flush=True,
                )
            except Exception as exc:
                errors.append({"job_id": job_id, "error": str(exc)})
                print(
                    f"[{index}/{len(job_ids)}] failed {job_id}: {exc}",
                    file=sys.stderr,
                    flush=True,
                )
    finally:
        await llm.aclose()

    comparisons = fetch_resume_variant_comparisons(
        database_path=args.database,
        job_ids=job_ids,
    )
    print(
        json.dumps(
            {
                "requested_job_ids": job_ids,
                "processed": len(audits),
                "failed": len(errors),
                "errors": errors,
                "backfilled_v1_variants": backfilled_v1_count,
                "stored_variant": SECOND_PASS_RESUME_VARIANT,
                "selected_variant_changed": any(
                    bool(audit.get("selected_variant_changed")) for audit in audits
                ),
                "comparisons": comparisons,
                "jobs": [
                    {
                        "job_id": audit["job"]["job_id"],
                        "accepted": len(audit["validation"]["accepted_change_ids"]),
                        "rejected": len(audit["validation"]["rejected_changes"]),
                        "external_suggestions": len(
                            (audit.get("external_critique") or {}).get("suggestions", [])
                        ),
                    }
                    for audit in audits
                ],
            },
            sort_keys=True,
        )
    )
    return 1 if errors else 0


async def run_second_pass_refinement_for_job(
    *,
    database_path: Path,
    job_id: str,
    master_resume_path: Path,
    template_path: Path,
    artifact_dir: Path | None = None,
    apply: bool = False,
    llm: Any,
    generation_timeout_seconds: float | None = None,
    generation_retry_count: int = 0,
    external_critique_text: str | None = None,
) -> dict[str, Any]:
    row = _load_row(database_path=database_path, job_id=job_id)
    selected_variant_before = str(
        row["selected_resume_variant"] or DEFAULT_RESUME_VARIANT
    )
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
    critique_response = await _generate_text_with_timeout(
        llm=llm,
        prompt=critique_prompt,
        timeout_seconds=generation_timeout_seconds,
        retry_count=generation_retry_count,
    )
    critique = parse_second_pass_resume_critique_response(critique_response)
    patch_result = validate_and_apply_second_pass_resume_patches(
        application_resume=application_resume,
        critique=critique,
        evidence_packet=evidence_packet,
    )

    updated_yaml = yaml.safe_dump(
        patch_result.updated_resume,
        sort_keys=False,
        allow_unicode=False,
    )
    updated_resume_html = render_resume_html_from_mapping(
        resume=patch_result.updated_resume,
        template_path=template_path,
    )
    updated_resume_pdf = await asyncio.to_thread(
        render_resume_pdf_from_html,
        updated_resume_html,
    )
    updated_ats_diagnostics = calculate_ats_diagnostics(
        resume_pdf=updated_resume_pdf,
        job_description=job_description,
    )
    validation_payload = {
        **patch_result.validation.model_dump(),
        "is_valid": patch_result.validation.is_valid,
    }
    external_critique_payload = (
        external_critique_report.model_dump()
        if external_critique_report is not None
        else None
    )
    model_metadata = _llm_model_metadata(llm)
    store_application_resume_variant(
        database_path=database_path,
        job_id=job_id,
        variant_key=SECOND_PASS_RESUME_VARIANT,
        variant_label="Refined v2",
        source="second_pass",
        parent_variant_key=DEFAULT_RESUME_VARIANT,
        application_resume_object=updated_yaml,
        resume_html=updated_resume_html,
        resume_pdf=updated_resume_pdf,
        ats_score=updated_ats_diagnostics.score,
        ats_diagnostics=asdict(updated_ats_diagnostics),
        evidence_packet=evidence_packet.model_dump(),
        external_critique=external_critique_payload,
        critique_prompt=critique_prompt,
        critique_response=critique_response,
        critique=critique.model_dump(),
        validation=validation_payload,
        model_metadata=model_metadata,
    )

    audit = {
        "schema_version": SECOND_PASS_RESUME_REFINEMENT_AUDIT_SCHEMA_VERSION,
        "job": {
            "job_id": job_id,
            "company": str(row["company"] or ""),
            "job_title": str(row["job_title"] or ""),
        },
        "apply_requested": apply,
        "applied": False,
        "applied_change_ids": [],
        "stored_variant": SECOND_PASS_RESUME_VARIANT,
        "selected_variant_changed": False,
        "ats_diagnostics": asdict(ats_diagnostics),
        "updated_ats_diagnostics": asdict(updated_ats_diagnostics),
        "evidence_packet": evidence_packet.model_dump(),
        "external_critique": external_critique_payload,
        "critique_prompt": critique_prompt,
        "critique_response": critique_response,
        "critique": critique.model_dump(),
        "validation": validation_payload,
        "model_metadata": model_metadata,
    }
    comparison = fetch_resume_variant_comparisons(
        database_path=database_path,
        job_ids=[job_id],
    )
    audit["comparison"] = comparison[0] if comparison else None
    selected_variant_after = (
        str(audit["comparison"]["selected_resume_variant"])
        if audit["comparison"] is not None
        else selected_variant_before
    )
    audit["selected_variant_changed"] = (
        selected_variant_after != selected_variant_before
    )
    return audit


def _selected_job_ids(
    *,
    database_path: Path,
    job_ids: Sequence[str] | None,
    all_active: bool,
) -> list[str]:
    selected = [str(job_id).strip() for job_id in job_ids or [] if str(job_id).strip()]
    if all_active:
        active_ids = fetch_active_resume_refinement_job_ids(database_path)
        return [*selected, *[job_id for job_id in active_ids if job_id not in selected]]
    if selected:
        return selected
    raise SystemExit("Pass --job-id at least once or use --all-active.")


def _llm_model_metadata(llm: Any) -> dict[str, str | None]:
    return {
        "client": type(llm).__name__,
        "model": getattr(llm, "model", None),
    }


async def _generate_text_with_timeout(
    *,
    llm: Any,
    prompt: str,
    timeout_seconds: float | None,
    retry_count: int = 0,
) -> str:
    attempts = max(1, retry_count + 1)
    for attempt in range(1, attempts + 1):
        try:
            if timeout_seconds is None:
                return await llm.generate_text(prompt)
            return await asyncio.wait_for(
                llm.generate_text(prompt),
                timeout=max(1.0, timeout_seconds),
            )
        except TimeoutError as exc:
            if attempt < attempts:
                print(
                    (
                        "Second-pass critique timed out; retrying "
                        f"(attempt {attempt + 1}/{attempts})"
                    ),
                    file=sys.stderr,
                    flush=True,
                )
                continue
            timeout_value = (
                f"{timeout_seconds:g}" if timeout_seconds is not None else "unknown"
            )
            raise TimeoutError(
                f"Second-pass critique timed out after {timeout_value} seconds."
            ) from exc
    raise AssertionError("unreachable retry loop exit")


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
                   application_resume_object, resume_content, selected_resume_variant
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


def main(argv: Sequence[str] | None = None) -> None:
    raise SystemExit(asyncio.run(main_async(argv)))


if __name__ == "__main__":
    main()
