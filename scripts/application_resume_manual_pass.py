#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from linkedin_career_mcp.codex_cli import (
    DEFAULT_CODEX_COMMAND,
    DEFAULT_CODEX_TIMEOUT_SECONDS,
)
from linkedin_career_mcp.resume_manual_pass import (
    DEFAULT_CODEX_MODEL,
    DEFAULT_CODEX_REASONING_EFFORT,
    run_manual_resume_pass_for_job,
)
from linkedin_career_mcp.resume_manual_profiles import (
    DEFAULT_MANUAL_PASS_PROFILE,
    ResolvedManualPassConfig,
    parse_manual_pass_profile_key,
    resolve_manual_pass_config,
)
from linkedin_career_mcp.webapp import (
    DEFAULT_DATABASE,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_RESUME_TEMPLATE,
)

MANUAL_PASS_PROFILE_ENV = "LINKEDIN_CAREER_MCP_MANUAL_PASS_PROFILE"
MANUAL_PASS_CODEX_MODEL_ENV = "LINKEDIN_CAREER_MCP_MANUAL_PASS_CODEX_MODEL"
MANUAL_PASS_CODEX_REASONING_EFFORT_ENV = (
    "LINKEDIN_CAREER_MCP_MANUAL_PASS_CODEX_REASONING_EFFORT"
)
LEGACY_CODEX_MODEL_ENV = "LINKEDIN_CAREER_MCP_CODEX_MODEL"
LEGACY_CODEX_REASONING_EFFORT_ENV = "LINKEDIN_CAREER_MCP_CODEX_REASONING_EFFORT"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Codex manual resume passthrough and store manual variants."
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_OUTPUT_DIR / DEFAULT_DATABASE,
    )
    parser.add_argument(
        "--master-resume",
        type=Path,
        default=Path("profile/MASTER-RESUME.yml"),
    )
    parser.add_argument(
        "--master-resume-text",
        type=Path,
        default=Path("profile/MP-MASTER-RESUME.txt"),
    )
    parser.add_argument(
        "--template",
        type=Path,
        default=DEFAULT_RESUME_TEMPLATE,
    )
    parser.add_argument(
        "--job-id",
        action="append",
        dest="job_ids",
        required=True,
        help="Application job ID. May be passed multiple times.",
    )
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        help="Optionally write the input bundle, prompt, response, and rendered artifacts.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Do not write SQLite.")
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop on the first failed job.",
    )
    parser.add_argument(
        "--codex-command",
        default=os.environ.get("LINKEDIN_CAREER_MCP_CODEX_COMMAND", DEFAULT_CODEX_COMMAND),
        help="Codex CLI command. Defaults to env or 'codex'.",
    )
    parser.add_argument(
        "--manual-pass-profile",
        type=parse_manual_pass_profile_key,
        help=(
            "Allowlisted manual-pass profile. Defaults to "
            f"{MANUAL_PASS_PROFILE_ENV} or {DEFAULT_MANUAL_PASS_PROFILE.value}."
        ),
    )
    parser.add_argument(
        "--codex-model",
        help=(
            "Manual-pass model override. Defaults to workflow env, deprecated shared "
            f"env, or the selected profile ({DEFAULT_CODEX_MODEL} for regular)."
        ),
    )
    parser.add_argument(
        "--codex-reasoning-effort",
        help=(
            "Manual-pass reasoning override. Defaults to workflow env, deprecated "
            f"shared env, or the selected profile ({DEFAULT_CODEX_REASONING_EFFORT} "
            "for regular). Pass an empty value to inherit Codex configuration."
        ),
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
        help="Maximum seconds to wait for each Codex manual pass.",
    )
    parser.add_argument(
        "--retry-count",
        type=int,
        default=int(os.environ.get("LINKEDIN_CAREER_MCP_CODEX_RETRIES", "1")),
        help="Number of timeout retries for each Codex manual pass.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        codex_config = _resolve_codex_config(args)
    except ValueError as exc:
        parser.error(str(exc))
    job_ids = _selected_job_ids(args.job_ids)
    processed = 0
    failed = 0
    results: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
    print(
        (
            f"Codex manual pass candidates: {len(job_ids)} "
            f"(database={args.database}, profile={codex_config.profile.key.value}, "
            f"codex_model={codex_config.model or 'inherit'}, "
            f"codex_reasoning_effort={codex_config.reasoning_effort or 'inherit'})"
        ),
        file=sys.stderr,
        flush=True,
    )

    for index, job_id in enumerate(job_ids, start=1):
        print(f"[{index}/{len(job_ids)}] Codex manual pass: {job_id}", file=sys.stderr)
        try:
            result = run_manual_resume_pass_for_job(
                database_path=args.database,
                job_id=job_id,
                master_resume_path=args.master_resume,
                master_resume_text_path=args.master_resume_text,
                template_path=args.template,
                codex_command=args.codex_command,
                manual_pass_profile=codex_config.profile.key,
                codex_model=codex_config.model,
                codex_reasoning_effort=codex_config.reasoning_effort,
                timeout_seconds=args.timeout_seconds,
                retry_count=args.retry_count,
                artifact_dir=args.artifact_dir,
                dry_run=args.dry_run,
            )
        except Exception as exc:  # noqa: BLE001
            failed += 1
            errors.append({"job_id": job_id, "error": str(exc)})
            print(f"[{job_id}] manual pass failed: {exc}", file=sys.stderr, flush=True)
            if args.fail_fast:
                break
            continue
        processed += 1
        results.append(result)
        print(
            (
                f"[{job_id}] stored manual variant "
                f"ats={result['ats_score']} unsupported={len(result['unsupported_terms'])}"
            ),
            file=sys.stderr,
            flush=True,
        )

    summary = {
        "processed": processed,
        "failed": failed,
        "errors": errors,
        "results": results,
        "stored_variant": "manual",
        "selected_variant_changed": False,
    }
    print(
        f"Codex manual pass variants: {processed}, failed: {failed}",
        file=sys.stderr,
        flush=True,
    )
    print(json.dumps(summary, sort_keys=True))
    return 1 if failed else 0


def _resolve_codex_config(args: argparse.Namespace) -> ResolvedManualPassConfig:
    profile = args.manual_pass_profile
    if profile is None:
        profile = os.environ.get(MANUAL_PASS_PROFILE_ENV, DEFAULT_MANUAL_PASS_PROFILE.value)
    return resolve_manual_pass_config(
        profile=profile,
        workflow_model_override=_cli_or_environment(
            args.codex_model,
            MANUAL_PASS_CODEX_MODEL_ENV,
        ),
        workflow_reasoning_effort_override=_cli_or_environment(
            args.codex_reasoning_effort,
            MANUAL_PASS_CODEX_REASONING_EFFORT_ENV,
        ),
        legacy_model_override=os.environ.get(LEGACY_CODEX_MODEL_ENV),
        legacy_reasoning_effort_override=os.environ.get(
            LEGACY_CODEX_REASONING_EFFORT_ENV
        ),
    )


def _cli_or_environment(cli_value: str | None, environment_name: str) -> str | None:
    if cli_value is not None:
        return cli_value
    return os.environ.get(environment_name)


def _selected_job_ids(values: Sequence[str]) -> list[str]:
    job_ids: list[str] = []
    seen: set[str] = set()
    for value in values:
        job_id = str(value or "").strip()
        if not job_id or job_id in seen:
            continue
        seen.add(job_id)
        job_ids.append(job_id)
    return job_ids


if __name__ == "__main__":
    raise SystemExit(main())
