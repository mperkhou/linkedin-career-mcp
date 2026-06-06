from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from linkedin_career_mcp.config import Settings, load_settings
from linkedin_career_mcp.providers import LinkedInPublicJobsProvider
from linkedin_career_mcp.services import JobSearchService
from linkedin_career_mcp.tools.jobs import register_job_tools


def create_server(settings: Settings | None = None) -> FastMCP:
    settings = settings or load_settings()
    provider = LinkedInPublicJobsProvider(
        user_agent=settings.user_agent,
        timeout_seconds=settings.timeout_seconds,
    )
    service = JobSearchService(provider=provider, max_results=settings.max_results)

    mcp = FastMCP(
        "LinkedIn Career MCP",
        instructions=(
            "Search public LinkedIn job listings and retrieve public job details. "
            "This server does not authenticate to LinkedIn or submit applications."
        ),
    )
    register_job_tools(mcp, service)
    return mcp
