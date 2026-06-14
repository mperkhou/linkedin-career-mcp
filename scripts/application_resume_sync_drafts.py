#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
import sys
from collections.abc import Sequence
from pathlib import Path

from linkedin_career_mcp.webapp import (
    DEFAULT_DATABASE,
    DEFAULT_OUTPUT_DIR,
    connect_database,
    sync_application_resume_to_draft,
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sync rendered draft resume artifacts from stored ARO YAML without API calls."
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_OUTPUT_DIR / DEFAULT_DATABASE,
    )
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
        print(f"[{index}/{len(rows)}] syncing draft to ARO: {job_id}", file=sys.stderr, flush=True)
        sync_application_resume_to_draft(database_path=args.database, job_id=job_id)
        processed += 1
    print(f"Synced draft resumes: {processed}", file=sys.stderr, flush=True)
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


if __name__ == "__main__":
    raise SystemExit(main())
