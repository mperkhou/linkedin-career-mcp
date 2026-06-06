from __future__ import annotations

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from linkedin_career_mcp.errors import LinkedInCareerMcpError
from linkedin_career_mcp.models import (
    DatePosted,
    ExperienceLevel,
    JobSearchQuery,
    JobType,
    SortBy,
    WorkplaceType,
)
from linkedin_career_mcp.services import JobSearchService


def register_job_tools(mcp: FastMCP, service: JobSearchService) -> None:
    @mcp.tool()
    async def search_linkedin_jobs(
        keywords: Annotated[str, Field(description="Job title or keywords to search for.")],
        location: Annotated[str, Field(description="Location to search in.")],
        date_posted: Annotated[
            DatePosted,
            Field(description="Posting age filter."),
        ] = "any_time",
        job_type: Annotated[
            JobType | None,
            Field(description="Employment type filter."),
        ] = None,
        workplace_type: Annotated[
            WorkplaceType | None,
            Field(description="On-site, remote, or hybrid filter."),
        ] = None,
        experience_level: Annotated[
            ExperienceLevel | None,
            Field(description="Experience level filter."),
        ] = None,
        sort_by: Annotated[SortBy, Field(description="Sort order.")] = "recent",
        distance: Annotated[
            int | None,
            Field(ge=0, le=100, description="Distance in miles from the requested location."),
        ] = None,
        limit: Annotated[int, Field(ge=1, le=100, description="Number of jobs to return.")] = 10,
        page: Annotated[int, Field(ge=0, description="Zero-based page number.")] = 0,
        exclude_job_ids: Annotated[
            list[str] | None,
            Field(description="LinkedIn job IDs to filter out of returned search results."),
        ] = None,
    ) -> dict[str, object]:
        """Search public LinkedIn job openings."""

        query = JobSearchQuery(
            keywords=keywords,
            location=location,
            date_posted=date_posted,
            job_type=job_type,
            workplace_type=workplace_type,
            experience_level=experience_level,
            sort_by=sort_by,
            distance=distance,
            limit=limit,
            page=page,
            exclude_job_ids=set(exclude_job_ids or []),
        )
        try:
            result = await service.search(query)
        except LinkedInCareerMcpError as exc:
            return {"error": str(exc)}
        return result.model_dump(mode="json")

    @mcp.tool()
    async def get_linkedin_job_details(
        job_id_or_url: Annotated[
            str,
            Field(description="LinkedIn job ID or public LinkedIn job URL."),
        ],
    ) -> dict[str, object]:
        """Fetch public details for a LinkedIn job."""

        try:
            details = await service.get_details(job_id_or_url)
        except LinkedInCareerMcpError as exc:
            return {"error": str(exc)}
        return details.model_dump(mode="json")
