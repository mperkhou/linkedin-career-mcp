from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from linkedin_career_mcp.config import Settings, load_settings
from linkedin_career_mcp.ollama import OllamaClient
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
    ollama = OllamaClient(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
        timeout_seconds=settings.ollama_timeout_seconds,
    )
    matching_workflow = MatchingJobsWorkflow(service=service, ollama=ollama)

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
