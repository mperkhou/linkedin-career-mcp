from __future__ import annotations

import math
import re
import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from linkedin_career_mcp.models import DatePosted, JobSearchQuery

DEFAULT_EXPLORATION_RATE = 0.20
QUERY_OUTCOMES_TABLE = "search_query_outcomes"
DISALLOWED_REUSED_EXPERIENCE_LEVELS = {"internship", "entry_level"}

STOPWORDS = {
    "and",
    "are",
    "for",
    "from",
    "jobs",
    "level",
    "role",
    "senior",
    "software",
    "the",
    "with",
}


@dataclass(frozen=True)
class StoredQueryOutcome:
    keywords: str
    location: str
    date_posted: str
    workplace_type: str | None
    experience_level: str | None
    job_type: str | None
    sort_by: str
    limit: int
    profile_match: float
    query_score: float
    results_returned: int
    fresh_jobs_accepted: int
    skipped_existing: int
    skipped_blacklisted: int
    skipped_workplace_type: int
    skipped_experience_level: int
    resumes_generated: int
    average_ats_score: float | None

    @property
    def query(self) -> JobSearchQuery:
        return JobSearchQuery(
            keywords=self.keywords,
            location=self.location,
            date_posted=self.date_posted,  # type: ignore[arg-type]
            job_type=self.job_type,  # type: ignore[arg-type]
            workplace_type=self.workplace_type,  # type: ignore[arg-type]
            experience_level=self.experience_level,  # type: ignore[arg-type]
            sort_by=self.sort_by,  # type: ignore[arg-type]
            limit=self.limit,
        )


@dataclass(frozen=True)
class QueryOutcome:
    query: JobSearchQuery
    profile_match: float
    query_score: float
    results_returned: int
    fresh_jobs_accepted: int
    skipped_existing: int = 0
    skipped_blacklisted: int = 0
    skipped_workplace_type: int = 0
    skipped_experience_level: int = 0
    resumes_generated: int = 0
    average_ats_score: float | None = None
    artifact_mode: str = "all"


@dataclass(frozen=True)
class QueryPerformanceEstimate:
    history_count: int
    expected_fresh_results: float
    historical_acceptance_rate: float
    historical_ats_score: float
    duplicate_or_skip_rate: float


@dataclass(frozen=True)
class ScoredQuery:
    query: JobSearchQuery
    score: float
    profile_match: float
    performance: QueryPerformanceEstimate
    selection_reason: Literal["exploit", "explore"] = "exploit"


def load_query_outcomes(database_path: Path, *, limit: int = 500) -> list[StoredQueryOutcome]:
    _ensure_query_outcomes_table(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            f"""
            SELECT keywords, location, date_posted, workplace_type, experience_level,
                   job_type, sort_by, limit_value, profile_match, query_score,
                   results_returned, fresh_jobs_accepted, skipped_existing,
                   skipped_blacklisted, skipped_workplace_type, skipped_experience_level,
                   resumes_generated, average_ats_score
            FROM {QUERY_OUTCOMES_TABLE}
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        StoredQueryOutcome(
            keywords=str(row["keywords"] or ""),
            location=str(row["location"] or ""),
            date_posted=str(row["date_posted"] or "any_time"),
            workplace_type=row["workplace_type"],
            experience_level=row["experience_level"],
            job_type=row["job_type"],
            sort_by=str(row["sort_by"] or "recent"),
            limit=int(row["limit_value"] or 10),
            profile_match=float(row["profile_match"] or 0.0),
            query_score=float(row["query_score"] or 0.0),
            results_returned=int(row["results_returned"] or 0),
            fresh_jobs_accepted=int(row["fresh_jobs_accepted"] or 0),
            skipped_existing=int(row["skipped_existing"] or 0),
            skipped_blacklisted=int(row["skipped_blacklisted"] or 0),
            skipped_workplace_type=int(row["skipped_workplace_type"] or 0),
            skipped_experience_level=int(row["skipped_experience_level"] or 0),
            resumes_generated=int(row["resumes_generated"] or 0),
            average_ats_score=(
                float(row["average_ats_score"])
                if row["average_ats_score"] is not None
                else None
            ),
        )
        for row in rows
    ]


def record_query_outcome(database_path: Path, outcome: QueryOutcome) -> None:
    _ensure_query_outcomes_table(database_path)
    now = datetime.now(UTC).isoformat(timespec="seconds")
    query = outcome.query
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            f"""
            INSERT INTO {QUERY_OUTCOMES_TABLE} (
                created_at, keywords, location, date_posted, workplace_type,
                experience_level, job_type, sort_by, limit_value, page,
                profile_match, query_score, results_returned, fresh_jobs_accepted,
                skipped_existing, skipped_blacklisted, skipped_workplace_type,
                skipped_experience_level, resumes_generated, average_ats_score,
                artifact_mode
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now,
                query.keywords,
                query.location,
                query.date_posted,
                query.workplace_type,
                query.experience_level,
                query.job_type,
                query.sort_by,
                query.limit,
                query.page,
                _clamp_unit(outcome.profile_match),
                _clamp_unit(outcome.query_score),
                max(0, outcome.results_returned),
                max(0, outcome.fresh_jobs_accepted),
                max(0, outcome.skipped_existing),
                max(0, outcome.skipped_blacklisted),
                max(0, outcome.skipped_workplace_type),
                max(0, outcome.skipped_experience_level),
                max(0, outcome.resumes_generated),
                outcome.average_ats_score,
                outcome.artifact_mode,
            ),
        )
        connection.commit()


def historical_query_candidates(
    history: Sequence[StoredQueryOutcome],
    *,
    location: str,
    date_posted: DatePosted,
    limit_per_query: int,
    max_candidates: int = 8,
) -> list[JobSearchQuery]:
    grouped: dict[str, dict[str, object]] = {}
    for outcome in history:
        key = _normalize_keywords(outcome.keywords)
        if not key:
            continue
        group = grouped.setdefault(
            key,
            {
                "keywords": outcome.keywords,
                "accepted": 0,
                "resumes": 0,
                "score": 0.0,
                "count": 0,
                "experience_level": outcome.experience_level,
                "job_type": outcome.job_type or "full_time",
            },
        )
        group["accepted"] = int(group["accepted"]) + outcome.fresh_jobs_accepted
        group["resumes"] = int(group["resumes"]) + outcome.resumes_generated
        group["score"] = float(group["score"]) + outcome.query_score
        group["count"] = int(group["count"]) + 1
        if (
            (
                not group["experience_level"]
                or str(group["experience_level"]) in DISALLOWED_REUSED_EXPERIENCE_LEVELS
            )
            and outcome.experience_level
            and outcome.experience_level not in DISALLOWED_REUSED_EXPERIENCE_LEVELS
        ):
            group["experience_level"] = outcome.experience_level

    ranked = sorted(
        grouped.values(),
        key=lambda item: (
            -int(item["accepted"]),
            -int(item["resumes"]),
            -(float(item["score"]) / max(int(item["count"]), 1)),
            str(item["keywords"]).casefold(),
        ),
    )
    candidates: list[JobSearchQuery] = []
    max_limit = min(max(limit_per_query, 1), 100)
    for item in ranked:
        if int(item["accepted"]) <= 0 and int(item["resumes"]) <= 0:
            continue
        experience_level = str(item["experience_level"] or "")
        if experience_level in DISALLOWED_REUSED_EXPERIENCE_LEVELS:
            experience_level = ""
        candidates.append(
            JobSearchQuery(
                keywords=str(item["keywords"]),
                location=location,
                date_posted=date_posted,
                job_type=str(item["job_type"] or "full_time"),  # type: ignore[arg-type]
                workplace_type="remote",
                experience_level=experience_level or None,  # type: ignore[arg-type]
                sort_by="recent",
                limit=max_limit,
            )
        )
        if len(candidates) >= max_candidates:
            break
    return candidates


def rank_search_queries(
    queries: Sequence[JobSearchQuery],
    *,
    profile_context: str,
    history: Sequence[StoredQueryOutcome],
    max_queries: int,
    exploration_rate: float = DEFAULT_EXPLORATION_RATE,
) -> list[ScoredQuery]:
    if max_queries <= 0:
        return []
    unique_queries = _dedupe_queries(queries)
    scored = [
        _score_query(query=query, profile_context=profile_context, history=history)
        for query in unique_queries
    ]
    scored.sort(
        key=lambda item: (
            -item.score,
            -item.profile_match,
            item.query.keywords.casefold(),
            item.query.workplace_type or "",
        )
    )
    if len(scored) <= max_queries:
        return scored

    explore_count = 0
    if max_queries > 1:
        explore_count = min(
            math.ceil(max_queries * max(0.0, min(exploration_rate, 1.0))),
            max_queries - 1,
        )
    exploit_count = max_queries - explore_count
    exploit = scored[:exploit_count]
    selected_keys = {_query_key(item.query) for item in exploit}
    exploration_pool = [
        item for item in scored[exploit_count:] if _query_key(item.query) not in selected_keys
    ]
    exploration_pool.sort(
        key=lambda item: (
            item.performance.history_count,
            -item.profile_match,
            -item.score,
            item.query.keywords.casefold(),
        )
    )
    explore = [
        ScoredQuery(
            query=item.query,
            score=item.score,
            profile_match=item.profile_match,
            performance=item.performance,
            selection_reason="explore",
        )
        for item in exploration_pool[:explore_count]
    ]
    return [*exploit, *explore]


def query_profile_match(query: JobSearchQuery, profile_context: str) -> float:
    query_tokens = _tokens(query.keywords)
    if not query_tokens:
        return 0.0
    profile_tokens = _tokens(profile_context)
    if not profile_tokens:
        return 0.25
    overlap = len(query_tokens & profile_tokens) / len(query_tokens)
    return _clamp_unit(overlap)


def _score_query(
    *,
    query: JobSearchQuery,
    profile_context: str,
    history: Sequence[StoredQueryOutcome],
) -> ScoredQuery:
    profile_match = query_profile_match(query, profile_context)
    performance = _estimate_performance(query=query, history=history)
    score = _clamp_unit(
        0.35 * profile_match
        + 0.25 * performance.expected_fresh_results
        + 0.20 * performance.historical_acceptance_rate
        + 0.15 * performance.historical_ats_score
        - 0.05 * performance.duplicate_or_skip_rate
    )
    return ScoredQuery(
        query=query,
        score=score,
        profile_match=profile_match,
        performance=performance,
    )


def _estimate_performance(
    *,
    query: JobSearchQuery,
    history: Sequence[StoredQueryOutcome],
) -> QueryPerformanceEstimate:
    weighted: list[tuple[StoredQueryOutcome, float]] = []
    for outcome in history:
        similarity = _query_similarity(query, outcome.query)
        if similarity >= 0.20:
            weighted.append((outcome, similarity))
    if not weighted:
        return QueryPerformanceEstimate(
            history_count=0,
            expected_fresh_results=0.50,
            historical_acceptance_rate=0.50,
            historical_ats_score=0.50,
            duplicate_or_skip_rate=0.0,
        )

    total_weight = sum(weight for _, weight in weighted)

    def average(values: Iterable[tuple[float, float]]) -> float:
        return sum(value * weight for value, weight in values) / max(total_weight, 0.0001)

    expected_fresh_results = average(
        (
            (
                min(outcome.fresh_jobs_accepted / max(query.limit, 1), 1.0),
                weight,
            )
            for outcome, weight in weighted
        )
    )
    historical_acceptance_rate = average(
        (
            (
                outcome.fresh_jobs_accepted / max(outcome.results_returned, 1),
                weight,
            )
            for outcome, weight in weighted
        )
    )
    historical_ats_score = average(
        (
            (
                (outcome.average_ats_score / 100)
                if outcome.average_ats_score is not None
                else 0.50,
                weight,
            )
            for outcome, weight in weighted
        )
    )
    duplicate_or_skip_rate = average(
        (
            (
                (
                    outcome.skipped_existing
                    + outcome.skipped_blacklisted
                    + outcome.skipped_workplace_type
                    + outcome.skipped_experience_level
                )
                / max(outcome.results_returned, 1),
                weight,
            )
            for outcome, weight in weighted
        )
    )
    return QueryPerformanceEstimate(
        history_count=len(weighted),
        expected_fresh_results=_clamp_unit(expected_fresh_results),
        historical_acceptance_rate=_clamp_unit(historical_acceptance_rate),
        historical_ats_score=_clamp_unit(historical_ats_score),
        duplicate_or_skip_rate=_clamp_unit(duplicate_or_skip_rate),
    )


def _query_similarity(query: JobSearchQuery, previous: JobSearchQuery) -> float:
    query_tokens = _tokens(query.keywords)
    previous_tokens = _tokens(previous.keywords)
    token_similarity = (
        len(query_tokens & previous_tokens) / len(query_tokens | previous_tokens)
        if query_tokens and previous_tokens
        else 0.0
    )
    score = token_similarity * 0.70
    if query.workplace_type and query.workplace_type == previous.workplace_type:
        score += 0.10
    if query.experience_level == previous.experience_level:
        score += 0.08
    if query.date_posted == previous.date_posted:
        score += 0.07
    if query.job_type == previous.job_type:
        score += 0.05
    return _clamp_unit(score)


def _ensure_query_outcomes_table(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {QUERY_OUTCOMES_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                keywords TEXT NOT NULL,
                location TEXT NOT NULL,
                date_posted TEXT NOT NULL,
                workplace_type TEXT,
                experience_level TEXT,
                job_type TEXT,
                sort_by TEXT NOT NULL,
                limit_value INTEGER NOT NULL,
                page INTEGER NOT NULL,
                profile_match REAL NOT NULL,
                query_score REAL NOT NULL,
                results_returned INTEGER NOT NULL,
                fresh_jobs_accepted INTEGER NOT NULL,
                skipped_existing INTEGER NOT NULL DEFAULT 0,
                skipped_blacklisted INTEGER NOT NULL DEFAULT 0,
                skipped_workplace_type INTEGER NOT NULL DEFAULT 0,
                skipped_experience_level INTEGER NOT NULL DEFAULT 0,
                resumes_generated INTEGER NOT NULL DEFAULT 0,
                average_ats_score REAL,
                artifact_mode TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT ''
            )
            """
        )
        connection.execute(
            f"""
            CREATE INDEX IF NOT EXISTS search_query_outcomes_keywords_idx
            ON {QUERY_OUTCOMES_TABLE}(keywords, location, workplace_type)
            """
        )
        connection.commit()


def _dedupe_queries(queries: Sequence[JobSearchQuery]) -> list[JobSearchQuery]:
    deduped: list[JobSearchQuery] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for query in queries:
        key = _query_key(query)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(query)
    return deduped


def _query_key(query: JobSearchQuery) -> tuple[str, str, str, str, str]:
    return (
        _normalize_keywords(query.keywords),
        query.location.casefold().strip(),
        str(query.date_posted),
        query.workplace_type or "",
        query.experience_level or "",
    )


def _normalize_keywords(value: str) -> str:
    return " ".join(value.casefold().split())


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9+#./-]*", value.casefold())
        if token not in STOPWORDS and len(token) >= 2
    }


def _clamp_unit(value: float) -> float:
    return max(0.0, min(1.0, value))
