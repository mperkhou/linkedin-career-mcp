from __future__ import annotations

from pathlib import Path
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from linkedin_career_mcp.errors import LinkedInCareerMcpError
from linkedin_career_mcp.models import DatePosted
from linkedin_career_mcp.workflows.matching import (
    DEFAULT_BLACKLIST_PATH,
    DEFAULT_MASTER_RESUME_NAME,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_PROFILE_DIR,
    MatchingJobsWorkflow,
)


def register_matching_tools(mcp: FastMCP, workflow: MatchingJobsWorkflow) -> None:
    @mcp.tool()
    async def find_matching_linkedin_jobs(
        profile_dir: Annotated[
            str,
            Field(description="Directory containing resume and profile/job-description files."),
        ] = str(DEFAULT_PROFILE_DIR),
        blacklist_path: Annotated[
            str,
            Field(description="Company blacklist file with gitignore-style glob patterns."),
        ] = str(DEFAULT_BLACKLIST_PATH),
        output_dir: Annotated[
            str,
            Field(description="Directory containing the local SQLite tracking database."),
        ] = str(DEFAULT_OUTPUT_DIR),
        master_resume_name: Annotated[
            str,
            Field(description="Master resume YAML file used for search planning."),
        ] = DEFAULT_MASTER_RESUME_NAME,
        location: Annotated[
            str,
            Field(
                description="LinkedIn search location. Defaults to a broad remote-friendly search.",
            ),
        ] = "United States",
        date_posted: Annotated[DatePosted, Field(description="Posting age filter.")] = "past_week",
        limit_per_query: Annotated[
            int,
            Field(ge=1, le=100, description="LinkedIn results requested per generated query."),
        ] = 10,
        max_queries: Annotated[
            int,
            Field(ge=1, le=20, description="Maximum total generated LinkedIn searches."),
        ] = 6,
        max_jobs: Annotated[
            int,
            Field(ge=1, le=50, description="Maximum jobs to seed into the database."),
        ] = 10,
    ) -> dict[str, object]:
        """Find remote or hybrid matching LinkedIn jobs and seed application/JOD rows."""

        try:
            result = await workflow.run(
                profile_dir=Path(profile_dir),
                blacklist_path=Path(blacklist_path),
                output_dir=Path(output_dir),
                master_resume_name=master_resume_name,
                location=location,
                date_posted=date_posted,
                limit_per_query=limit_per_query,
                max_queries=max_queries,
                max_jobs=max_jobs,
            )
        except LinkedInCareerMcpError as exc:
            return {"error": str(exc)}
        return result.model_dump(mode="json")
