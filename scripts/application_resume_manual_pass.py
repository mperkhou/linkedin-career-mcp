#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from linkedin_career_mcp.resume_highlighting import (
    DEFAULT_CODEX_COMMAND,
    DEFAULT_CODEX_MODEL,
    DEFAULT_CODEX_REASONING_EFFORT,
    DEFAULT_CODEX_TIMEOUT_SECONDS,
)
from linkedin_career_mcp.resume_manual_pass import run_manual_resume_pass_for_job
from linkedin_career_mcp.webapp import (
    DEFAULT_DATABASE,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_RESUME_TEMPLATE,
)


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
        "--codex-model",
        default=os.environ.get("LINKEDIN_CAREER_MCP_CODEX_MODEL", DEFAULT_CODEX_MODEL),
        help="Codex model used for the manual pass.",
    )
    parser.add_argument(
        "--codex-reasoning-effort",
        default=os.environ.get(
            "LINKEDIN_CAREER_MCP_CODEX_REASONING_EFFORT",
            DEFAULT_CODEX_REASONING_EFFORT,
        ),
        help="Codex reasoning effort for the manual pass. Pass an empty value to inherit config.",
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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    job_ids = _selected_job_ids(args.job_ids)
    processed = 0
    failed = 0
    results: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
    print(
        (
            f"Codex manual pass candidates: {len(job_ids)} "
            f"(database={args.database}, codex_model={args.codex_model}, "
            f"codex_reasoning_effort={args.codex_reasoning_effort or 'inherit'})"
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
                codex_model=args.codex_model,
                codex_reasoning_effort=args.codex_reasoning_effort,
                timeout_seconds=args.timeout_seconds,
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
