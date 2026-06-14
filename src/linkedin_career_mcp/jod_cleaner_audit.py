from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean, median
from typing import Any

from linkedin_career_mcp.ats import calculate_ats_proxy_score
from linkedin_career_mcp.jod import job_description_context, usable_job_description
from linkedin_career_mcp.models import JobDetails

DEFAULT_DATABASE_PATH = Path("output/tracking/applications.sqlite3")
BOILERPLATE_PATTERNS = {
    "compensation": re.compile(
        r"\b(compensation|salary range|base salary|pay range|estimated annual pay|"
        r"estimated annual salary)\b",
        re.IGNORECASE,
    ),
    "benefits": re.compile(
        r"\b(benefits|perks|health and wellness|401\(k\)|parental leave|"
        r"medical, dental|vision coverage|paid time off)\b",
        re.IGNORECASE,
    ),
    "equal_opportunity": re.compile(
        r"\b(equal opportunity|eeo|affirmative action|reasonable accommodation)\b",
        re.IGNORECASE,
    ),
    "privacy": re.compile(
        r"\b(privacy policy|applicant notice|applicant privacy|personal information)\b",
        re.IGNORECASE,
    ),
    "application_process": re.compile(
        r"\b(application process|interview process|hiring process|recruiter will share|"
        r"we may use ai tools|we may use artificial intelligence)\b",
        re.IGNORECASE,
    ),
}
RISKY_START_RE = re.compile(
    r"^\s*(required qualifications|minimum qualifications|basic qualifications|"
    r"qualifications|requirements)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class JobDescriptionAudit:
    job_id: str
    company: str
    title: str
    raw_length: int
    stored_length: int
    cleaned_length: int
    changed: bool
    cleaned_flags: tuple[str, ...]
    risky_start: bool


def audit_tracker_database(
    database_path: Path = DEFAULT_DATABASE_PATH,
    *,
    apply: bool = False,
    create_backup: bool = True,
    recalculate_ats: bool = True,
    sample_limit: int = 10,
) -> dict[str, Any]:
    rows = _load_rows(database_path)
    audits: list[JobDescriptionAudit] = []
    cleaned_by_job_id: dict[str, str] = {}
    resume_content_by_job_id: dict[str, bytes | None] = {}

    for row in rows:
        raw_description = usable_job_description(row["job_description"])
        if not raw_description:
            continue
        cleaned = _clean_prompt_job_description(row, raw_description)
        stored = usable_job_description(row["prompt_job_description"]) or ""
        audit = JobDescriptionAudit(
            job_id=str(row["job_id"]),
            company=str(row["company"] or ""),
            title=str(row["job_title"] or ""),
            raw_length=len(raw_description),
            stored_length=len(stored),
            cleaned_length=len(cleaned),
            changed=stored != cleaned,
            cleaned_flags=tuple(_boilerplate_flags(cleaned)),
            risky_start=bool(RISKY_START_RE.search(cleaned)),
        )
        audits.append(audit)
        cleaned_by_job_id[audit.job_id] = cleaned
        resume_content_by_job_id[audit.job_id] = row["resume_content"]

    changed = [audit for audit in audits if audit.changed]
    flagged = [audit for audit in audits if audit.cleaned_flags]
    applied = 0
    backup_path: str | None = None
    ats_recalculated = 0

    if apply and changed:
        if create_backup:
            backup_path = _backup_database(database_path)
        applied, ats_recalculated = _apply_backfill(
            database_path=database_path,
            changed=changed,
            cleaned_by_job_id=cleaned_by_job_id,
            resume_content_by_job_id=resume_content_by_job_id,
            recalculate_ats=recalculate_ats,
        )

    return {
        "database_path": str(database_path),
        "mode": "apply" if apply else "dry-run",
        "backup_path": backup_path,
        "total_rows": len(rows),
        "usable_raw_jod_rows": len(audits),
        "no_usable_jod_rows": len(rows) - len(audits),
        "changed_rows": len(changed),
        "applied_rows": applied,
        "ats_recalculated_rows": ats_recalculated,
        "lengths": {
            "raw": _length_summary(audit.raw_length for audit in audits),
            "stored_prompt": _length_summary(audit.stored_length for audit in audits),
            "cleaned_prompt": _length_summary(audit.cleaned_length for audit in audits),
        },
        "retention": {
            "stored_average": _safe_average(
                audit.stored_length / audit.raw_length for audit in audits
            ),
            "cleaned_average": _safe_average(
                audit.cleaned_length / audit.raw_length for audit in audits
            ),
            "stored_median": _safe_median(
                audit.stored_length / audit.raw_length for audit in audits
            ),
            "cleaned_median": _safe_median(
                audit.cleaned_length / audit.raw_length for audit in audits
            ),
        },
        "risky_starts": sum(audit.risky_start for audit in audits),
        "boilerplate_counts": _boilerplate_counts(audits),
        "sample_changed_rows": [asdict(audit) for audit in changed[:sample_limit]],
        "sample_remaining_flags": [asdict(audit) for audit in flagged[:sample_limit]],
    }


def _load_rows(database_path: Path) -> list[sqlite3.Row]:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        return list(
            connection.execute(
                """
                SELECT job_id, company, job_title, job_description, prompt_job_description,
                       resume_content
                FROM applications
                ORDER BY company COLLATE NOCASE, job_title COLLATE NOCASE, job_id
                """
            )
        )
    finally:
        connection.close()


def _clean_prompt_job_description(row: sqlite3.Row, raw_description: str) -> str:
    job = JobDetails(
        job_id=str(row["job_id"]),
        title=str(row["job_title"] or "Unknown title"),
        company=str(row["company"] or "") or None,
        description=raw_description,
    )
    return job_description_context(job)


def _apply_backfill(
    *,
    database_path: Path,
    changed: list[JobDescriptionAudit],
    cleaned_by_job_id: dict[str, str],
    resume_content_by_job_id: dict[str, bytes | None],
    recalculate_ats: bool,
) -> tuple[int, int]:
    connection = sqlite3.connect(database_path)
    try:
        applied = 0
        ats_recalculated = 0
        now = datetime.now(UTC).isoformat(timespec="seconds")
        with connection:
            for audit in changed:
                cleaned = cleaned_by_job_id[audit.job_id]
                score_values: tuple[Any, ...] | None = None
                resume_content = resume_content_by_job_id.get(audit.job_id)
                if recalculate_ats and resume_content:
                    score = calculate_ats_proxy_score(
                        resume_pdf=resume_content,
                        job_description=cleaned,
                    )
                    score_values = (
                        score.overall_score,
                        score.parsing_score,
                        score.keyword_match_score,
                        score.semantic_match_score,
                        score.formatting_risk,
                        ", ".join(score.missing_high_value_terms),
                        now,
                    )
                    ats_recalculated += 1

                if score_values is None:
                    connection.execute(
                        """
                        UPDATE applications
                        SET prompt_job_description = ?,
                            updated_at = ?
                        WHERE job_id = ?
                        """,
                        (cleaned, now, audit.job_id),
                    )
                else:
                    connection.execute(
                        """
                        UPDATE applications
                        SET prompt_job_description = ?,
                            ats_score = ?,
                            ats_parsing_score = ?,
                            ats_keyword_score = ?,
                            ats_semantic_score = ?,
                            ats_formatting_risk = ?,
                            ats_missing_terms = ?,
                            ats_updated_at = ?,
                            updated_at = ?
                        WHERE job_id = ?
                        """,
                        (cleaned, *score_values, now, audit.job_id),
                    )
                applied += 1
        return applied, ats_recalculated
    finally:
        connection.close()


def _backup_database(database_path: Path) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_path = database_path.with_name(
        f"{database_path.stem}.pre-jod-backfill-{timestamp}.sqlite3"
    )
    shutil.copy2(database_path, backup_path)
    return str(backup_path)


def _boilerplate_flags(text: str) -> list[str]:
    return [name for name, pattern in BOILERPLATE_PATTERNS.items() if pattern.search(text)]


def _boilerplate_counts(audits: list[JobDescriptionAudit]) -> dict[str, int]:
    return {
        name: sum(name in audit.cleaned_flags for audit in audits)
        for name in BOILERPLATE_PATTERNS
    }


def _length_summary(values: Any) -> dict[str, float | int]:
    lengths = list(values)
    if not lengths:
        return {"min": 0, "median": 0, "mean": 0, "max": 0}
    return {
        "min": min(lengths),
        "median": round(median(lengths), 1),
        "mean": round(mean(lengths), 1),
        "max": max(lengths),
    }


def _safe_average(values: Any) -> float:
    collected = list(values)
    return round(mean(collected), 3) if collected else 0.0


def _safe_median(values: Any) -> float:
    collected = list(values)
    return round(median(collected), 3) if collected else 0.0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit and optionally backfill cleaned prompt JODs in the tracker DB.",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
        help="SQLite tracker database path.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write cleaned prompt_job_description values back to the database.",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Do not create a timestamped database backup before applying.",
    )
    parser.add_argument(
        "--skip-ats",
        action="store_true",
        help="Do not recalculate ATS scores when applying.",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=10,
        help="Number of changed/flagged sample rows to include in the JSON output.",
    )
    args = parser.parse_args()

    result = audit_tracker_database(
        database_path=args.database,
        apply=args.apply,
        create_backup=not args.no_backup,
        recalculate_ats=not args.skip_ats,
        sample_limit=args.sample_limit,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
