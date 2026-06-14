from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import yaml

from linkedin_career_mcp.models import JobDetails, JobPosting, JobSearchResult
from linkedin_career_mcp.webapp import connect_database
from linkedin_career_mcp.workflows.matching import MatchingJobsWorkflow


class FakePlanner:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.prompts: list[str] = []

    async def generate_json(self, prompt: str) -> dict[str, Any]:
        self.prompts.append(prompt)
        return self.response

    async def aclose(self) -> None:
        return None


class FakeService:
    def __init__(self) -> None:
        self.searches: list[Any] = []
        self.details_by_job_id: dict[str, JobDetails] = {}

    async def search(self, query) -> JobSearchResult:
        self.searches.append(query)
        jobs = [
            JobPosting(
                job_id=job_id,
                title=details.title,
                company=details.company,
                location=details.location,
                listed_at=details.listed_at,
                job_url=details.job_url,
                workplace_type=details.workplace_type,
            )
            for job_id, details in self.details_by_job_id.items()
        ]
        return JobSearchResult(query=query, count=len(jobs), jobs=jobs)

    async def get_details(self, job_id_or_url: str) -> JobDetails:
        for details in self.details_by_job_id.values():
            if job_id_or_url in {details.job_id, str(details.job_url)}:
                return details
        raise AssertionError(f"unexpected details lookup: {job_id_or_url}")


def test_matching_workflow_seeds_trimmed_jods_into_database(tmp_path: Path):
    profile_dir = tmp_path / "profile"
    output_dir = tmp_path / "output"
    profile_dir.mkdir()
    (profile_dir / "MASTER-RESUME.yml").write_text(
        yaml.safe_dump(
            {
                "professional_summary": {
                    "text": "Senior platform engineer focused on automation and AI tooling."
                },
                "core_technical_skills": {
                    "bullet_points": [
                        {
                            "category": "Automation & IaC",
                            "items": {
                                "primary": ["Python", "Terraform"],
                                "additional": ["Jenkins"],
                            },
                        }
                    ]
                },
                "professional_experience": {
                    "jobs": [
                        {
                            "company": "Oracle",
                            "title": "Senior Platform Software Engineer",
                            "bullet_points": [
                                {
                                    "text": (
                                        "Built Python automation and Terraform pipelines for "
                                        "platform reliability."
                                    )
                                }
                            ],
                        }
                    ]
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    planner = FakePlanner(
        {
            "queries": [
                {
                    "keywords": "Platform Engineer AI",
                    "location": "United States",
                    "date_posted": "past_week",
                    "job_type": "full_time",
                    "workplace_type": "remote",
                    "experience_level": "mid_senior",
                    "sort_by": "recent",
                    "limit": 2,
                    "page": 0,
                }
            ]
        }
    )
    service = FakeService()
    service.details_by_job_id["111"] = JobDetails(
        job_id="111",
        title="Staff Platform Engineer",
        company="Example Co",
        location="Remote",
        listed_at="2026-06-14",
        job_url="https://www.linkedin.com/jobs/view/111",
        workplace_type="Remote",
        seniority_level="Mid-Senior level",
        description=(
            "About the Role\n"
            "Build platform automation, Python APIs, and Terraform workflows.\n\n"
            "Benefits\n"
            "Medical, dental, vision, and 401(k)."
        ),
    )

    workflow = MatchingJobsWorkflow(
        service=service,  # type: ignore[arg-type]
        planner_llm=planner,
    )

    result = _run(
        workflow.run(
            profile_dir=profile_dir,
            output_dir=output_dir,
            max_queries=2,
            limit_per_query=2,
            max_jobs=1,
        )
    )

    assert result.jobs_seeded == 1
    assert result.seeded_applications[0].job_id == "111"
    assert planner.prompts
    assert "Master resume object summary" in planner.prompts[0]
    assert service.searches

    database_path = output_dir / "tracking/applications.sqlite3"
    with connect_database(database_path) as connection:
        row = connection.execute(
            """
            SELECT company, job_title, job_description, prompt_job_description,
                   date_posted, experience_level
            FROM applications
            WHERE job_id = '111'
            """
        ).fetchone()
    assert row["company"] == "Example Co"
    assert row["job_title"] == "Staff Platform Engineer"
    assert "Medical, dental" in row["job_description"]
    assert "Python APIs" in row["prompt_job_description"]
    assert "Medical, dental" not in row["prompt_job_description"]
    assert row["date_posted"] == "2026-06-14"
    assert row["experience_level"] == "Mid-Senior level"

    with sqlite3.connect(database_path) as connection:
        outcome_count = connection.execute(
            "SELECT COUNT(*) FROM search_query_outcomes"
        ).fetchone()[0]
    assert outcome_count >= 1


def test_matching_workflow_skips_existing_blacklisted_onsite_and_entry_level_jobs(
    tmp_path: Path,
):
    profile_dir = tmp_path / "profile"
    output_dir = tmp_path / "output"
    profile_dir.mkdir()
    (profile_dir / "MASTER-RESUME.yml").write_text(
        "professional_summary:\n  text: Platform automation engineer.\n",
        encoding="utf-8",
    )
    blacklist_path = tmp_path / ".blacklist"
    blacklist_path.write_text("Blocked*\n", encoding="utf-8")
    database_path = output_dir / "tracking/applications.sqlite3"
    with connect_database(database_path):
        pass
    with connect_database(database_path) as connection:
        connection.execute(
            """
            INSERT INTO applications (
                job_id, company, job_title, linkedin_url, resume_filename,
                source_resume_path, applied_to, imported_at, updated_at
            )
            VALUES ('existing', 'Old Co', 'Engineer', '', '', '', 'No', 'now', 'now')
            """
        )
        connection.commit()

    planner = FakePlanner({"queries": []})
    service = FakeService()
    service.details_by_job_id = {
        "existing": JobDetails(
            job_id="existing",
            title="Existing Engineer",
            company="Old Co",
            location="Remote",
            job_url="https://www.linkedin.com/jobs/view/existing",
            workplace_type="Remote",
            seniority_level="Mid-Senior level",
            description="Responsibilities Build Python automation.",
        ),
        "blocked": JobDetails(
            job_id="blocked",
            title="Platform Engineer",
            company="Blocked Labs",
            location="Remote",
            job_url="https://www.linkedin.com/jobs/view/blocked",
            workplace_type="Remote",
            seniority_level="Mid-Senior level",
            description="Responsibilities Build Python automation.",
        ),
        "onsite": JobDetails(
            job_id="onsite",
            title="Platform Engineer",
            company="Onsite Co",
            location="On-site",
            job_url="https://www.linkedin.com/jobs/view/onsite",
            workplace_type="On-site",
            seniority_level="Mid-Senior level",
            description="Responsibilities Build Python automation.",
        ),
        "entry": JobDetails(
            job_id="entry",
            title="Platform Engineer",
            company="Entry Co",
            location="Remote",
            job_url="https://www.linkedin.com/jobs/view/entry",
            workplace_type="Remote",
            seniority_level="Entry level",
            description="Responsibilities Build Python automation.",
        ),
    }

    workflow = MatchingJobsWorkflow(
        service=service,  # type: ignore[arg-type]
        planner_llm=planner,
    )
    result = _run(
        workflow.run(
            profile_dir=profile_dir,
            blacklist_path=blacklist_path,
            output_dir=output_dir,
            max_queries=1,
            max_jobs=1,
        )
    )

    assert result.jobs_seeded == 0
    assert result.skipped_existing
    assert result.skipped_blacklisted
    assert result.skipped_workplace_type
    assert result.skipped_experience_level


def _run(awaitable):
    import asyncio

    return asyncio.run(awaitable)
