from __future__ import annotations

from linkedin_career_mcp.models import JobDetails, JobSearchQuery, JobSearchResult
from linkedin_career_mcp.providers.base import JobProvider


class JobSearchService:
    def __init__(self, *, provider: JobProvider, max_results: int) -> None:
        self._provider = provider
        self._max_results = max(1, max_results)

    async def search(self, query: JobSearchQuery) -> JobSearchResult:
        capped_query = query.model_copy(update={"limit": min(query.limit, self._max_results)})
        jobs = await self._provider.search_jobs(capped_query)
        if capped_query.exclude_job_ids:
            jobs = [job for job in jobs if job.job_id not in capped_query.exclude_job_ids]
        jobs = jobs[: capped_query.limit]
        return JobSearchResult(
            query=capped_query,
            count=len(jobs),
            jobs=jobs,
            provider=self._provider.name,
        )

    async def get_details(self, job_id_or_url: str) -> JobDetails:
        return await self._provider.get_job_details(job_id_or_url)
