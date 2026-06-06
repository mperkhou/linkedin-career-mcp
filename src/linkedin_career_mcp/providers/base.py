from __future__ import annotations

from abc import ABC, abstractmethod

from linkedin_career_mcp.models import JobDetails, JobPosting, JobSearchQuery


class JobProvider(ABC):
    name: str

    @abstractmethod
    async def search_jobs(self, query: JobSearchQuery) -> list[JobPosting]:
        """Return normalized job postings for the supplied query."""

    @abstractmethod
    async def get_job_details(self, job_id_or_url: str) -> JobDetails:
        """Return a normalized job detail record."""
