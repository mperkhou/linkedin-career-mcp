from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook
from pypdf import PdfReader

from linkedin_career_mcp.models import JobDetails, JobPosting, JobSearchQuery, JobSearchResult
from linkedin_career_mcp.webapp import (
    DEFAULT_DATABASE,
    connect_database,
    fetch_existing_resume_job_ids,
    upsert_application_artifact,
)
from linkedin_career_mcp.workflows.matching import (
    DEFAULT_SUPPLEMENTAL_SEARCH_KEYWORDS,
    CompanyBlacklist,
    MatchingJobsWorkflow,
    _expand_remote_and_hybrid_queries,
    _supplement_search_queries,
)


class FakeOllama:
    def __init__(self) -> None:
        self.text_prompts: list[str] = []
        self.json_prompts: list[str] = []

    async def generate_json(self, prompt: str) -> dict[str, object]:
        self.json_prompts.append(prompt)
        if "core_technical_skills" in prompt:
            return {
                "core_technical_skills": [
                    {
                        "category": "Languages & Frameworks",
                        "skills": ["Python", "JavaScript", "Node.js", "React.js"],
                    },
                    {
                        "category": "Distributed Systems & Cloud",
                        "skills": ["AWS", "Azure", "OpenSearch"],
                    },
                    {
                        "category": "Platform & API Engineering",
                        "skills": ["RESTful APIs", "Systems Architecture", "Microservices"],
                    },
                    {
                        "category": "Automation & IaC",
                        "skills": ["Terraform", "Ansible", "Jenkins"],
                    },
                    {
                        "category": "Data & Observability",
                        "skills": ["Data Pipelines", "Observability Dashboards"],
                    },
                    {
                        "category": "Security & Compliance",
                        "skills": ["Secure Coding Practices", "RBAC"],
                    },
                    {
                        "category": "AI Tools",
                        "skills": ["Codex", "Oracle Code Assist (OCA)", "Cline", "OpenRouter"],
                    },
                ],
                "prior_experience": [],
            }
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
        self.text_prompts.append(prompt)
        return (
            "**Oracle | Remote / International Datacenters**\n"
            "**Senior Technical Lead - Cloud Automation Engineer | Feb 2022 - Present**\n"
            "- **Platform Component Ownership:** Built agentic AI systems and MCP tools."
        )


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


class ExistingThenNewJobService:
    def __init__(self) -> None:
        self.queries: list[JobSearchQuery] = []
        self.detail_requests: list[str] = []

    async def search(self, query: JobSearchQuery) -> JobSearchResult:
        self.queries.append(query)
        if len(self.queries) == 1:
            jobs = [
                JobPosting(
                    job_id="111",
                    title="Existing Engineer",
                    company="Existing Co",
                    job_url="https://www.linkedin.com/jobs/view/111",
                )
            ]
        else:
            jobs = [
                JobPosting(
                    job_id="333",
                    title="Fresh Platform Engineer",
                    company="Fresh Co",
                    job_url="https://www.linkedin.com/jobs/view/333",
                )
            ]
        return JobSearchResult(query=query, count=len(jobs), jobs=jobs, provider="fake")

    async def get_details(self, job_id_or_url: str) -> JobDetails:
        self.detail_requests.append(job_id_or_url)
        job_id = job_id_or_url.rstrip("/").rsplit("/", 1)[-1]
        return JobDetails(
            job_id=job_id,
            title="Fresh Platform Engineer",
            company="Fresh Co",
            job_url=f"https://www.linkedin.com/jobs/view/{job_id}",
            description="Fresh role that should count toward max_jobs.",
        )


def test_company_blacklist_matches_globs_case_insensitively(tmp_path: Path):
    blacklist_path = tmp_path / ".blacklist"
    blacklist_path.write_text("# comment\nRaytheon*\n", encoding="utf-8")

    blacklist = CompanyBlacklist.from_file(blacklist_path)

    assert blacklist.matches("Raytheon Technologies")
    assert blacklist.matches("raytheon")
    assert not blacklist.matches("Acme AI")


def test_search_queries_are_supplemented_with_trending_keyword_fallbacks():
    model_query = JobSearchQuery(
        keywords="Senior Platform Engineer AWS Azure Terraform",
        location="United States",
        date_posted="past_month",
        job_type="full_time",
        workplace_type="remote",
        experience_level="mid_senior",
        sort_by="recent",
        limit=5,
    )

    supplemented = _supplement_search_queries(
        [model_query],
        location="United States",
        date_posted="past_month",
        limit_per_query=5,
    )
    expanded = _expand_remote_and_hybrid_queries(supplemented, max_queries=8)

    keywords = [query.keywords for query in expanded]
    assert keywords[:2] == [model_query.keywords, model_query.keywords]
    assert DEFAULT_SUPPLEMENTAL_SEARCH_KEYWORDS[0] in keywords
    assert any("AI" in keyword or "LLM" in keyword or "agentic" in keyword for keyword in keywords)
    assert {query.workplace_type for query in expanded[:2]} == {"remote", "hybrid"}


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
    resume_text = "\n".join(page.extract_text() or "" for page in PdfReader(resume_path).pages)
    assert "Max Perkhounkov" in resume_text
    assert "custom tailored for every job position" in resume_text
    assert "Education & Certifications" in resume_text
    assert "Oracle Cloud Infrastructure AI Foundations Associate" in resume_text
    assert "AI Tools" in resume_text
    assert "OpenRouter" in resume_text
    assert "Error Budgets" not in resume_text
    assert "**" not in resume_text

    database_path = output_dir / DEFAULT_DATABASE
    with connect_database(database_path) as connection:
        row = connection.execute(
            """
            SELECT job_description, prompt_job_description
            FROM applications
            WHERE job_id = ?
            """,
            ("111",),
        ).fetchone()
    assert row["job_description"] == "Build local AI workflows and MCP integrations."
    assert row["prompt_job_description"] == "Build local AI workflows and MCP integrations."

    workbook_path = output_dir / "tracking/read_applications/linkedin_applications.xlsx"
    assert workbook_path.exists()
    workbook = load_workbook(workbook_path)
    sheet = workbook.active
    assert sheet.cell(row=2, column=1).value == "111"
    assert sheet.cell(row=2, column=4).hyperlink.target == "https://www.linkedin.com/jobs/view/111"
    assert sheet.cell(row=2, column=6).value == "No"
    assert sheet.cell(row=2, column=7).value is None


async def test_matching_workflow_skips_existing_database_jobs_without_counting_them(
    tmp_path: Path,
):
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    (profile_dir / "MP-RESUME-AGENTIC.txt").write_text(
        "Resume: built MCP servers and local LLM workflows.",
        encoding="utf-8",
    )
    blacklist_path = tmp_path / ".blacklist"
    blacklist_path.write_text("", encoding="utf-8")
    output_dir = tmp_path / "output"
    existing_resume = output_dir / "resumes/Existing_Co/111_existing_engineer/resume.pdf"
    existing_resume.parent.mkdir(parents=True)
    existing_resume.write_bytes(b"%PDF-1.4 existing")
    database_path = output_dir / DEFAULT_DATABASE
    upsert_application_artifact(
        database_path=database_path,
        job_id="111",
        company="Existing Co",
        job_title="Existing Engineer",
        linkedin_url="https://www.linkedin.com/jobs/view/111",
        resume_path=existing_resume,
    )
    service = ExistingThenNewJobService()
    workflow = MatchingJobsWorkflow(service=service, ollama=FakeOllama())

    result = await workflow.run(
        profile_dir=profile_dir,
        blacklist_path=blacklist_path,
        output_dir=output_dir,
        source_resume_name="MP-RESUME-AGENTIC.txt",
        limit_per_query=5,
        max_queries=2,
        max_jobs=1,
    )

    assert len(service.queries) == 2
    assert "111" in service.queries[0].exclude_job_ids
    assert service.detail_requests == ["https://www.linkedin.com/jobs/view/333"]
    assert result.jobs_found == 1
    assert result.artifacts[0].job_id == "333"
    assert "Existing Co - Existing Engineer" in result.skipped_existing
    assert fetch_existing_resume_job_ids(database_path) == {"111", "333"}


async def test_regenerate_resumes_uses_database_jobs_and_fetches_missing_descriptions(
    tmp_path: Path,
):
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    (profile_dir / "MP-RESUME-AGENTIC.txt").write_text(
        "Resume: built MCP servers and local LLM workflows.",
        encoding="utf-8",
    )
    output_dir = tmp_path / "output"
    database_path = output_dir / DEFAULT_DATABASE
    stored_resume = output_dir / "resumes/Existing_Co/111_existing_engineer/resume.pdf"
    stored_resume.parent.mkdir(parents=True)
    stored_resume.write_bytes(b"%PDF-1.4 existing")
    missing_description_resume = output_dir / "resumes/Fresh_Co/333_fresh_platform/resume.pdf"
    missing_description_resume.parent.mkdir(parents=True)
    missing_description_resume.write_bytes(b"%PDF-1.4 existing")
    upsert_application_artifact(
        database_path=database_path,
        job_id="111",
        company="Existing Co",
        job_title="Existing Engineer",
        linkedin_url="https://www.linkedin.com/jobs/view/111",
        resume_path=stored_resume,
        job_description="Raw stored JOD with company boilerplate.",
        prompt_job_description="Stored prompt JOD with AI Experience.",
    )
    upsert_application_artifact(
        database_path=database_path,
        job_id="333",
        company="Fresh Co",
        job_title="Fresh Platform Engineer",
        linkedin_url="https://www.linkedin.com/jobs/view/333",
        resume_path=missing_description_resume,
    )
    service = ExistingThenNewJobService()
    ollama = FakeOllama()
    workflow = MatchingJobsWorkflow(service=service, ollama=ollama)

    result = await workflow.regenerate_resumes(
        profile_dir=profile_dir,
        output_dir=output_dir,
        source_resume_name="MP-RESUME-AGENTIC.txt",
        job_ids=["111", "333"],
        linkedin_delay_seconds=0,
    )

    assert result.jobs_found == 2
    assert result.resumes_created == 2
    assert [artifact.job_id for artifact in result.artifacts] == ["111", "333"]
    assert service.detail_requests == ["https://www.linkedin.com/jobs/view/333"]
    assert any("Stored prompt JOD with AI Experience." in prompt for prompt in ollama.text_prompts)
    with connect_database(database_path) as connection:
        rows = connection.execute(
            """
            SELECT job_id, job_description, prompt_job_description
            FROM applications
            ORDER BY job_id
            """
        ).fetchall()
    row_by_job_id = {row["job_id"]: row for row in rows}
    assert row_by_job_id["111"]["job_description"] == "Raw stored JOD with company boilerplate."
    assert row_by_job_id["111"]["prompt_job_description"] == "Stored prompt JOD with AI Experience."
    assert row_by_job_id["333"]["job_description"] == (
        "Fresh role that should count toward max_jobs."
    )
    assert row_by_job_id["333"]["prompt_job_description"] == (
        "Fresh role that should count toward max_jobs."
    )
