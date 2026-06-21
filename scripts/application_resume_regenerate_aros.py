#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

from linkedin_career_mcp.application_resume import (
    DEFAULT_MASTER_RESUME_PATH,
    apply_core_skill_jod_matches,
    initialize_application_resume_object,
)
from linkedin_career_mcp.webapp import (
    DEFAULT_DATABASE,
    DEFAULT_OUTPUT_DIR,
    connect_database,
    store_application_resume_object,
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Regenerate stored ARO YAML from the latest master resume without API calls."
        )
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_OUTPUT_DIR / DEFAULT_DATABASE,
    )
    parser.add_argument("--master-resume", type=Path, default=DEFAULT_MASTER_RESUME_PATH)
    parser.add_argument(
        "--job-id",
        action="append",
        dest="job_ids",
        help="Only process this job ID. May be passed multiple times.",
    )
    parser.add_argument("--limit", type=int, help="Process at most this many rows.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    rows = _load_rows(
        database_path=args.database,
        job_ids=set(args.job_ids or []),
        limit=args.limit,
    )
    print(
        f"Candidates: {len(rows)} (database={args.database}, api_calls=0)",
        file=sys.stderr,
        flush=True,
    )
    processed = 0
    for index, row in enumerate(rows, start=1):
        job_id = str(row["job_id"])
        print(f"[{index}/{len(rows)}] regenerating ARO: {job_id}", file=sys.stderr, flush=True)
        existing_response = _core_skill_response_from_existing_aro(
            row["application_resume_object"]
        )
        fresh_aro = initialize_application_resume_object(args.master_resume)
        matched_aro = apply_core_skill_jod_matches(
            application_resume=fresh_aro,
            core_skill_response=existing_response,
        )
        store_application_resume_object(
            database_path=args.database,
            job_id=job_id,
            application_resume_object=yaml.safe_dump(
                matched_aro,
                sort_keys=False,
                allow_unicode=False,
            ),
        )
        processed += 1
    print(f"Regenerated ARO objects: {processed}", file=sys.stderr, flush=True)
    print(processed)
    return 0


def _load_rows(
    *,
    database_path: Path,
    job_ids: set[str],
    limit: int | None,
) -> list[sqlite3.Row]:
    with connect_database(database_path) as connection:
        rows = connection.execute(
            """
            SELECT job_id, application_resume_object
            FROM applications
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


def _core_skill_response_from_existing_aro(value: Any) -> dict[str, list[dict[str, Any]]]:
    parsed = _yaml_mapping(value)
    core_skills = parsed.get("core_technical_skills")
    buckets = core_skills.get("bullet_points") if isinstance(core_skills, dict) else []
    items: list[dict[str, Any]] = []
    if isinstance(buckets, list):
        for bucket in buckets:
            if not isinstance(bucket, dict):
                continue
            category = str(bucket.get("category") or "").strip()
            if not category:
                continue
            items.append(
                {
                    "category": category,
                    "jod_matched_items": _string_list(bucket.get("jod_matched_items")),
                }
            )
    return {"core_technical_skills": items}


def _yaml_mapping(value: Any) -> dict[str, Any]:
    text = str(value or "").strip()
    if not text:
        return {}
    parsed = yaml.safe_load(text)
    return parsed if isinstance(parsed, dict) else {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


if __name__ == "__main__":
    raise SystemExit(main())
