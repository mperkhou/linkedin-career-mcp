from __future__ import annotations

from linkedin_career_mcp.models import JobDetails, JobPosting, JobSearchQuery
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


async def test_search_caps_query_limit():
    service = JobSearchService(provider=FakeProvider(), max_results=3)
    result = await service.search(JobSearchQuery(keywords="python", location="remote", limit=10))

    assert result.query.limit == 3
    assert result.count == 3
    assert len(result.jobs) == 3
