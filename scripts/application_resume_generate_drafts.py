#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from linkedin_career_mcp.application_resume import (
    CORE_SKILLS_PROMPT_JOD_MAX_CHARS,
    DEFAULT_JOD_LLM_API_MODEL,
    DEFAULT_MASTER_RESUME_PATH,
    apply_core_skill_jod_matches,
    attach_job_opening_description_object,
    build_core_skills_jod_match_prompt,
    build_experience_job_bullet_rewrite_prompt,
    build_jod_requirements_target_prompt,
    create_job_opening_description_object,
    experience_jobs_for_jod_bullet_rewrite,
    initialize_application_resume_object,
    oracle_job_for_jod_bullet_rewrite,
    replace_experience_job_bullets_from_text_response,
)
from linkedin_career_mcp.config import load_settings
from linkedin_career_mcp.jod import usable_job_description
from linkedin_career_mcp.llm import build_llm_client
from linkedin_career_mcp.resume_rendering import (
    render_resume_html_from_mapping,
    render_resume_pdf_from_html,
)
from linkedin_career_mcp.webapp import (
    DEFAULT_DATABASE,
    DEFAULT_OUTPUT_DIR,
    connect_database,
    store_application_resume_first_draft,
)

DEFAULT_TEMPLATE = Path("templates/resume/master_resume.html.j2")


@dataclass(frozen=True)
class Candidate:
    job_id: str
    company: str
    job_title: str
    trimmed_jod: str


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate first-draft ARO resume artifacts from stored trimmed JODs."
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_OUTPUT_DIR / DEFAULT_DATABASE,
    )
    parser.add_argument("--master-resume", type=Path, default=DEFAULT_MASTER_RESUME_PATH)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument(
        "--job-id",
        action="append",
        dest="job_ids",
        help="Only process this job ID. May be passed multiple times.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Process at most this many candidates after filtering.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild rows even when an application_resume_object already exists.",
    )
    parser.add_argument(
        "--api-model",
        help=(
            "OpenRouter model used for Core Technical Skills matching. "
            "Defaults to --jod-model."
        ),
    )
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        help="Optionally write ARO YAML, HTML, PDF, prompts, and LLM responses here.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List candidate rows without calling the LLM or updating SQLite.",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop on the first failed row instead of continuing.",
    )
    parser.add_argument("--max-jod-chars", type=int, default=CORE_SKILLS_PROMPT_JOD_MAX_CHARS)
    parser.add_argument(
        "--jod-model",
        default=DEFAULT_JOD_LLM_API_MODEL,
        help="OpenRouter model used for JOD targets and experience bullet rewrites.",
    )
    return parser


async def main_async(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    candidates = load_candidates(
        database_path=args.database,
        job_ids=set(args.job_ids or []),
        force=args.force,
        limit=args.limit,
    )
    print(
        f"Candidates: {len(candidates)} "
        f"(database={args.database}, force={args.force}, dry_run={args.dry_run})",
        file=sys.stderr,
        flush=True,
    )
    if args.dry_run:
        for candidate in candidates:
            print(
                f"{candidate.job_id}\t{candidate.company}\t{candidate.job_title}\t"
                f"jod_chars={len(candidate.trimmed_jod)}"
            )
        return 0
    if not candidates:
        print(json.dumps({"processed": 0, "failed": 0}, sort_keys=True))
        return 0

    settings = load_settings()
    if settings.llm_provider.casefold().strip() != "api":
        raise RuntimeError("JOD-target resume generation requires the API/OpenRouter LLM provider.")
    core_skill_model = args.api_model or args.jod_model
    llm = build_llm_client(settings, api_model=core_skill_model)
    jod_llm = build_llm_client(settings, api_model=args.jod_model)
    model = getattr(llm, "model", core_skill_model)
    print(f"LLM: {settings.llm_provider}:{model}", file=sys.stderr, flush=True)
    jod_model = getattr(jod_llm, "model", args.jod_model)
    print(
        f"JOD LLM: {settings.llm_provider}:{jod_model}",
        file=sys.stderr,
        flush=True,
    )

    processed = 0
    failures: list[dict[str, str]] = []
    try:
        for index, candidate in enumerate(candidates, start=1):
            print(
                f"[{index}/{len(candidates)}] {candidate.job_id} "
                f"{candidate.company} - {candidate.job_title}",
                file=sys.stderr,
                flush=True,
            )
            try:
                await backport_candidate(
                    candidate,
                    database_path=args.database,
                    master_resume_path=args.master_resume,
                    template_path=args.template,
                    llm=llm,
                    jod_llm=jod_llm,
                    jod_model=args.jod_model,
                    artifact_dir=args.artifact_dir,
                    max_jod_chars=args.max_jod_chars,
                )
            except Exception as exc:
                failures.append({"job_id": candidate.job_id, "error": str(exc)})
                print(
                    f"  failed: {candidate.job_id}: {exc}",
                    file=sys.stderr,
                    flush=True,
                )
                if args.fail_fast:
                    raise
            else:
                processed += 1
                print(f"  stored: {candidate.job_id}", file=sys.stderr, flush=True)
    finally:
        await llm.aclose()
        await jod_llm.aclose()

    print(
        json.dumps(
            {
                "processed": processed,
                "failed": len(failures),
                "failures": failures,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 1 if failures else 0


def load_candidates(
    *,
    database_path: Path,
    job_ids: set[str],
    force: bool,
    limit: int | None,
) -> list[Candidate]:
    with connect_database(database_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT job_id, company, job_title, prompt_job_description, job_description,
                   application_resume_object
            FROM applications
            ORDER BY rowid
            """
        ).fetchall()

    candidates: list[Candidate] = []
    for row in rows:
        job_id = str(row["job_id"])
        if job_ids and job_id not in job_ids:
            continue
        if not force and _has_text(row["application_resume_object"]):
            continue
        trimmed_jod = (
            usable_job_description(row["prompt_job_description"])
            or usable_job_description(row["job_description"])
        )
        if not trimmed_jod:
            continue
        candidates.append(
            Candidate(
                job_id=job_id,
                company=str(row["company"] or ""),
                job_title=str(row["job_title"] or ""),
                trimmed_jod=trimmed_jod,
            )
        )
        if limit is not None and len(candidates) >= max(limit, 0):
            break
    return candidates


async def backport_candidate(
    candidate: Candidate,
    *,
    database_path: Path,
    master_resume_path: Path,
    template_path: Path,
    llm: Any,
    jod_llm: Any,
    jod_model: str,
    artifact_dir: Path | None,
    max_jod_chars: int,
) -> None:
    aro = initialize_application_resume_object(master_resume_path)
    prompt = build_core_skills_jod_match_prompt(
        application_resume=aro,
        trimmed_job_description=candidate.trimmed_jod,
        max_jod_chars=max_jod_chars,
    )
    response = await llm.generate_json(prompt)
    first_draft_aro = apply_core_skill_jod_matches(
        application_resume=aro,
        core_skill_response=response,
    )
    jod_artifacts: list[tuple[str, str]] = []

    jod_prompt = build_jod_requirements_target_prompt(
        trimmed_job_description=candidate.trimmed_jod,
        max_jod_chars=max_jod_chars,
    )
    jod_response = await jod_llm.generate_json(jod_prompt)
    jod_object = create_job_opening_description_object(
        trimmed_job_description=candidate.trimmed_jod,
        requirements_response=jod_response,
        model=jod_model,
    )
    first_draft_aro = attach_job_opening_description_object(
        application_resume=first_draft_aro,
        job_opening_description=jod_object,
    )
    jod_artifacts.extend(
        [
            ("jod_targets_prompt.txt", f"{jod_prompt}\n"),
            (
                "jod_targets_response.json",
                f"{json.dumps(jod_response, indent=2, sort_keys=True)}\n",
            ),
        ]
    )

    oracle_job = oracle_job_for_jod_bullet_rewrite(first_draft_aro)
    oracle_prompt = build_experience_job_bullet_rewrite_prompt(
        job_opening_description=jod_object,
        job=oracle_job,
    )
    oracle_response = await jod_llm.generate_text(oracle_prompt)
    first_draft_aro = replace_experience_job_bullets_from_text_response(
        application_resume=first_draft_aro,
        job_order=oracle_job.get("order"),
        bullet_response=oracle_response,
    )
    jod_artifacts.extend(
        [
            ("job_1_rewrite_prompt.txt", f"{oracle_prompt}\n"),
            ("job_1_rewrite_response.txt", f"{oracle_response}\n"),
        ]
    )

    for job in experience_jobs_for_jod_bullet_rewrite(first_draft_aro):
        job_order = job.get("order")
        rewrite_prompt = build_experience_job_bullet_rewrite_prompt(
            job_opening_description=jod_object,
            job=job,
        )
        rewrite_response = await jod_llm.generate_text(rewrite_prompt)
        first_draft_aro = replace_experience_job_bullets_from_text_response(
            application_resume=first_draft_aro,
            job_order=job_order,
            bullet_response=rewrite_response,
        )
        safe_job_order = _safe_filename(str(job_order or "unknown"))
        jod_artifacts.extend(
            [
                (f"job_{safe_job_order}_rewrite_prompt.txt", f"{rewrite_prompt}\n"),
                (f"job_{safe_job_order}_rewrite_response.txt", f"{rewrite_response}\n"),
            ]
        )

    aro_yaml = yaml.safe_dump(first_draft_aro, sort_keys=False, allow_unicode=False)
    resume_html = render_resume_html_from_mapping(
        resume=first_draft_aro,
        template_path=template_path,
    )
    resume_pdf = await asyncio.to_thread(render_resume_pdf_from_html, resume_html)

    aro_path: Path | None = None
    html_path: Path | None = None
    pdf_path: Path | None = None
    if artifact_dir is not None:
        safe_job_id = _safe_filename(candidate.job_id)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        prompt_path = artifact_dir / f"{safe_job_id}_prompt.txt"
        response_path = artifact_dir / f"{safe_job_id}_response.json"
        aro_path = artifact_dir / f"{safe_job_id}_first_draft.yml"
        html_path = artifact_dir / f"{safe_job_id}_first_draft.html"
        pdf_path = artifact_dir / f"{safe_job_id}_first_draft.pdf"
        prompt_path.write_text(f"{prompt}\n", encoding="utf-8")
        response_path.write_text(
            f"{json.dumps(response, indent=2, sort_keys=True)}\n",
            encoding="utf-8",
        )
        for suffix, content in jod_artifacts:
            (artifact_dir / f"{safe_job_id}_{suffix}").write_text(content, encoding="utf-8")
        aro_path.write_text(aro_yaml, encoding="utf-8")
        html_path.write_text(resume_html, encoding="utf-8")
        pdf_path.write_bytes(resume_pdf)

    store_application_resume_first_draft(
        database_path=database_path,
        job_id=candidate.job_id,
        application_resume_object=aro_yaml,
        resume_html=resume_html,
        resume_pdf=resume_pdf,
        resume_html_path=html_path,
        resume_pdf_path=pdf_path,
    )


def _has_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _safe_filename(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)


def main(argv: Sequence[str] | None = None) -> None:
    raise SystemExit(asyncio.run(main_async(argv)))


if __name__ == "__main__":
    main()
