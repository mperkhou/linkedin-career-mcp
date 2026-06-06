from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook

from linkedin_career_mcp.models import JobDetails, JobPosting, JobSearchQuery, JobSearchResult
from linkedin_career_mcp.workflows.matching import CompanyBlacklist, MatchingJobsWorkflow


class FakeOllama:
    async def generate_json(self, prompt: str) -> dict[str, object]:
        return {
            "queries": [
                {
                    "keywords": "agentic ai platform engineer",
                    "location": "United States",
                    "date_posted": "past_week",
                    "job_type": "full_time",
                    "sort_by": "recent",
                    "limit": 5,
                }
            ]
        }

    async def generate_text(self, prompt: str) -> str:
        return "MORGAN PERKHOU\n\nEXPERIENCE\nBuilt agentic AI systems and MCP tools."


class FakeJobService:
    def __init__(self) -> None:
        self.queries: list[JobSearchQuery] = []

    async def search(self, query: JobSearchQuery) -> JobSearchResult:
        self.queries.append(query)
        return JobSearchResult(
            query=query,
            count=2,
            jobs=[
                JobPosting(
                    job_id="111",
                    title="Agentic AI Engineer",
                    company="Acme AI",
                    job_url="https://www.linkedin.com/jobs/view/111",
                ),
                JobPosting(
                    job_id="222",
                    title="Defense AI Engineer",
                    company="Raytheon Technologies",
                    job_url="https://www.linkedin.com/jobs/view/222",
                ),
            ],
            provider="fake",
        )

    async def get_details(self, job_id_or_url: str) -> JobDetails:
        job_id = job_id_or_url.rstrip("/").rsplit("/", 1)[-1]
        if job_id == "222":
            return JobDetails(
                job_id="222",
                title="Defense AI Engineer",
                company="Raytheon Technologies",
                job_url="https://www.linkedin.com/jobs/view/222",
                description="Defense AI role.",
            )
        return JobDetails(
            job_id="111",
            title="Agentic AI Engineer",
            company="Acme AI",
            job_url="https://www.linkedin.com/jobs/view/111",
            description="Build local AI workflows and MCP integrations.",
        )


def test_company_blacklist_matches_globs_case_insensitively(tmp_path: Path):
    blacklist_path = tmp_path / ".blacklist"
    blacklist_path.write_text("# comment\nRaytheon*\n", encoding="utf-8")

    blacklist = CompanyBlacklist.from_file(blacklist_path)

    assert blacklist.matches("Raytheon Technologies")
    assert blacklist.matches("raytheon")
    assert not blacklist.matches("Acme AI")


async def test_matching_workflow_writes_resume_and_tracking(tmp_path: Path):
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    (profile_dir / "MP-RESUME-AGENTIC.txt").write_text(
        "Resume: built MCP servers and local LLM workflows.",
        encoding="utf-8",
    )
    blacklist_path = tmp_path / ".blacklist"
    blacklist_path.write_text("Raytheon*\n", encoding="utf-8")
    output_dir = tmp_path / "output"
    service = FakeJobService()
    workflow = MatchingJobsWorkflow(service=service, ollama=FakeOllama())

    result = await workflow.run(
        profile_dir=profile_dir,
        blacklist_path=blacklist_path,
        output_dir=output_dir,
        source_resume_name="MP-RESUME-AGENTIC.txt",
        limit_per_query=5,
        max_queries=2,
        max_jobs=5,
    )

    assert {query.workplace_type for query in service.queries} == {"remote", "hybrid"}
    assert result.resumes_created == 1
    assert result.artifacts[0].company == "Acme AI"
    assert "Raytheon Technologies - Defense AI Engineer" in result.skipped_blacklisted

    resume_path = Path(result.artifacts[0].resume_path)
    assert resume_path.exists()
    assert resume_path.name == "mp_resume_agentic_ai_engineer.pdf"

    workbook_path = output_dir / "tracking/read_applications/linkedin_applications.xlsx"
    assert workbook_path.exists()
    workbook = load_workbook(workbook_path)
    sheet = workbook.active
    assert sheet.cell(row=2, column=1).value == "111"
    assert sheet.cell(row=2, column=4).hyperlink.target == "https://www.linkedin.com/jobs/view/111"
    assert sheet.cell(row=2, column=6).value == "No"
    assert sheet.cell(row=2, column=7).value is None
