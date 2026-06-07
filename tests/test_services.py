from __future__ import annotations

from linkedin_career_mcp.models import JobDetails, JobPosting, JobRawPayload, JobSearchQuery
from linkedin_career_mcp.services import JobSearchService


class FakeProvider:
    name = "fake"

    async def search_jobs(self, query: JobSearchQuery) -> list[JobPosting]:
        return [
            JobPosting(job_id=str(index), title=f"Job {index}")
            for index in range(query.limit + 2)
        ]

    async def get_job_details(self, job_id_or_url: str) -> JobDetails:
        return JobDetails(job_id=job_id_or_url, title="A job")

    async def get_job_raw_payload(self, job_id_or_url: str) -> JobRawPayload:
        parsed = JobDetails(job_id=job_id_or_url, title="A job")
        return JobRawPayload(
            job_id=job_id_or_url,
            detail_url=f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id_or_url}",
            status_code=200,
            content_type="text/html",
            payload_chars=13,
            payload="<p>A job</p>",
            parsed=parsed,
        )


async def test_search_caps_query_limit():
    service = JobSearchService(provider=FakeProvider(), max_results=3)
    result = await service.search(JobSearchQuery(keywords="python", location="remote", limit=10))

    assert result.query.limit == 3
    assert result.count == 3
    assert len(result.jobs) == 3


async def test_search_filters_excluded_job_ids_before_counting_results():
    service = JobSearchService(provider=FakeProvider(), max_results=10)
    result = await service.search(
        JobSearchQuery(
            keywords="python",
            location="remote",
            limit=5,
            exclude_job_ids={"0", "2"},
        )
    )

    assert [job.job_id for job in result.jobs] == ["1", "3", "4", "5", "6"]
    assert result.count == 5


async def test_get_raw_payload_returns_provider_payload():
    service = JobSearchService(provider=FakeProvider(), max_results=3)

    payload = await service.get_raw_payload("12345")

    assert payload.job_id == "12345"
    assert payload.payload == "<p>A job</p>"
    assert payload.parsed.title == "A job"
