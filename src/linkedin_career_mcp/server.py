from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from linkedin_career_mcp.config import Settings, load_settings
from linkedin_career_mcp.llm import build_llm_client, build_planner_llm_client
from linkedin_career_mcp.providers import LinkedInPublicJobsProvider
from linkedin_career_mcp.services import JobSearchService
from linkedin_career_mcp.tools.jobs import register_job_tools
from linkedin_career_mcp.tools.matching import register_matching_tools
from linkedin_career_mcp.workflows.matching import MatchingJobsWorkflow


def create_server(settings: Settings | None = None) -> FastMCP:
    settings = settings or load_settings()
    provider = LinkedInPublicJobsProvider(
        user_agent=settings.user_agent,
        timeout_seconds=settings.timeout_seconds,
    )
    service = JobSearchService(provider=provider, max_results=settings.max_results)
    planner_llm = build_llm_client(settings)
    planner_llm = build_planner_llm_client(settings, planner_llm)
    matching_workflow = MatchingJobsWorkflow(service=service, planner_llm=planner_llm)

    mcp = FastMCP(
        "LinkedIn Career MCP",
        instructions=(
            "Search public LinkedIn job listings, retrieve public job details, and run local "
            "Ollama-assisted matching workflows. "
            "This server does not authenticate to LinkedIn or submit applications."
        ),
    )
    register_job_tools(mcp, service)
    register_matching_tools(mcp, matching_workflow)
    return mcp
