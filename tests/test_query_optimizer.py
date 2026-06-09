from __future__ import annotations

from pathlib import Path

from linkedin_career_mcp.models import JobSearchQuery
from linkedin_career_mcp.query_optimizer import (
    QueryOutcome,
    historical_query_candidates,
    load_query_outcomes,
    rank_search_queries,
    record_query_outcome,
)


def test_record_and_load_query_outcomes(tmp_path: Path) -> None:
    database_path = tmp_path / "tracking/applications.sqlite3"
    query = JobSearchQuery(
        keywords="platform automation engineer",
        location="United States",
        date_posted="past_week",
        job_type="full_time",
        workplace_type="remote",
        experience_level="mid_senior",
        limit=10,
    )

    record_query_outcome(
        database_path,
        QueryOutcome(
            query=query,
            profile_match=0.92,
            query_score=0.81,
            results_returned=8,
            fresh_jobs_accepted=3,
            skipped_existing=2,
            skipped_blacklisted=1,
            resumes_generated=2,
            average_ats_score=87.5,
        ),
    )

    outcomes = load_query_outcomes(database_path)

    assert len(outcomes) == 1
    assert outcomes[0].keywords == "platform automation engineer"
    assert outcomes[0].fresh_jobs_accepted == 3
    assert outcomes[0].average_ats_score == 87.5
    assert outcomes[0].query.experience_level == "mid_senior"


def test_rank_search_queries_balances_profile_fit_history_and_exploration(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "tracking/applications.sqlite3"
    strong_query = JobSearchQuery(
        keywords="platform automation engineer",
        location="United States",
        date_posted="past_week",
        workplace_type="remote",
        experience_level="mid_senior",
        limit=10,
    )
    unrelated_query = JobSearchQuery(
        keywords="sales manager",
        location="United States",
        date_posted="past_week",
        workplace_type="remote",
        experience_level="mid_senior",
        limit=10,
    )
    exploration_query = JobSearchQuery(
        keywords="agentic ai platform engineer",
        location="United States",
        date_posted="past_week",
        workplace_type="hybrid",
        experience_level="mid_senior",
        limit=10,
    )
    record_query_outcome(
        database_path,
        QueryOutcome(
            query=strong_query,
            profile_match=1.0,
            query_score=0.8,
            results_returned=6,
            fresh_jobs_accepted=3,
            resumes_generated=2,
            average_ats_score=92,
        ),
    )
    record_query_outcome(
        database_path,
        QueryOutcome(
            query=unrelated_query,
            profile_match=0.0,
            query_score=0.2,
            results_returned=12,
            fresh_jobs_accepted=1,
            skipped_existing=8,
            average_ats_score=50,
        ),
    )
    history = load_query_outcomes(database_path)

    ranked = rank_search_queries(
        [unrelated_query, exploration_query, strong_query],
        profile_context=(
            "Python platform automation distributed systems agentic AI OpenSearch"
        ),
        history=history,
        max_queries=2,
    )

    assert {item.query.keywords for item in ranked} == {
        "platform automation engineer",
        "agentic ai platform engineer",
    }
    assert {item.selection_reason for item in ranked} == {"exploit", "explore"}


def test_historical_query_candidates_reuse_successful_keywords(tmp_path: Path) -> None:
    database_path = tmp_path / "tracking/applications.sqlite3"
    record_query_outcome(
        database_path,
        QueryOutcome(
            query=JobSearchQuery(
                keywords="cloud automation engineer",
                location="United States",
                date_posted="past_month",
                workplace_type="remote",
                experience_level="associate",
                limit=10,
            ),
            profile_match=0.8,
            query_score=0.75,
            results_returned=9,
            fresh_jobs_accepted=4,
            resumes_generated=2,
        ),
    )
    record_query_outcome(
        database_path,
        QueryOutcome(
            query=JobSearchQuery(
                keywords="ai platform engineer",
                location="United States",
                date_posted="past_month",
                workplace_type="remote",
                experience_level="entry_level",
                limit=10,
            ),
            profile_match=0.7,
            query_score=0.7,
            results_returned=5,
            fresh_jobs_accepted=2,
            resumes_generated=1,
        ),
    )

    candidates = historical_query_candidates(
        load_query_outcomes(database_path),
        location="United States",
        date_posted="past_week",
        limit_per_query=5,
    )

    assert len(candidates) == 2
    assert [candidate.keywords for candidate in candidates] == [
        "cloud automation engineer",
        "ai platform engineer",
    ]
    assert candidates[0].date_posted == "past_week"
    assert candidates[0].limit == 5
    assert candidates[0].experience_level == "associate"
    assert candidates[1].experience_level is None
