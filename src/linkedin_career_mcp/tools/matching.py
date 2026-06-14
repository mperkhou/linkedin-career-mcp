from __future__ import annotations

from pathlib import Path
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from linkedin_career_mcp.errors import LinkedInCareerMcpError
from linkedin_career_mcp.models import DatePosted
from linkedin_career_mcp.workflows.matching import (
    DEFAULT_BLACKLIST_PATH,
    DEFAULT_CURRENT_JOB_DESCRIPTION,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_PROFILE_DIR,
    DEFAULT_SOURCE_RESUME,
    ArtifactMode,
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
            Field(description="Directory where tailored resumes and tracking files are written."),
        ] = str(DEFAULT_OUTPUT_DIR),
        source_resume_name: Annotated[
            str,
            Field(description="Profile resume file to use as the primary tailoring source."),
        ] = DEFAULT_SOURCE_RESUME,
        current_job_description_name: Annotated[
            str,
            Field(description="Current job description file used as context for SCJDiR tailoring."),
        ] = DEFAULT_CURRENT_JOB_DESCRIPTION,
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
            Field(ge=1, le=50, description="Maximum jobs to prepare artifacts for."),
        ] = 10,
        artifact_mode: Annotated[
            ArtifactMode,
            Field(
                description=(
                    "Artifact generation mode. Use resumes-only while cover letters are manual."
                ),
            ),
        ] = "resumes-only",
    ) -> dict[str, object]:
        """Find remote or hybrid matching LinkedIn jobs and prepare application PDFs."""

        try:
            result = await workflow.run(
                profile_dir=Path(profile_dir),
                blacklist_path=Path(blacklist_path),
                output_dir=Path(output_dir),
                source_resume_name=source_resume_name,
                current_job_description_name=current_job_description_name,
                location=location,
                date_posted=date_posted,
                limit_per_query=limit_per_query,
                max_queries=max_queries,
                max_jobs=max_jobs,
                artifact_mode=artifact_mode,
            )
        except LinkedInCareerMcpError as exc:
            return {"error": str(exc)}
        return result.model_dump(mode="json")
