from __future__ import annotations

import argparse
import asyncio
import json
import re
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any, Literal

from openpyxl import Workbook, load_workbook
from openpyxl.worksheet.worksheet import Worksheet
from pydantic import BaseModel, ConfigDict, Field
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from linkedin_career_mcp.config import load_settings
from linkedin_career_mcp.errors import LinkedInCareerMcpError, WorkflowError
from linkedin_career_mcp.models import DatePosted, JobDetails, JobSearchQuery
from linkedin_career_mcp.ollama import OllamaClient
from linkedin_career_mcp.providers import LinkedInPublicJobsProvider
from linkedin_career_mcp.services import JobSearchService

DEFAULT_PROFILE_DIR = Path("profile")
DEFAULT_BLACKLIST_PATH = Path(".blacklist")
DEFAULT_OUTPUT_DIR = Path("output")
DEFAULT_SOURCE_RESUME = "MP-RESUME-AGENTIC.pdf"
DEFAULT_CURRENT_JOB_DESCRIPTION = "Senior_Platform_Software_Engineer(IC3).pdf"
TRACKING_WORKBOOK = Path("tracking/read_applications/linkedin_applications.xlsx")
SUPPORTED_TEXT_SUFFIXES = {".csv", ".json", ".md", ".rst", ".text", ".txt"}
SUPPORTED_PROFILE_SUFFIXES = SUPPORTED_TEXT_SUFFIXES | {".docx", ".pdf"}
TRACKING_HEADERS = [
    "job_id",
    "company",
    "job_title",
    "linkedin_url",
    "customized_resume",
    "applied_to",
    "date_applied",
]
DEFAULT_SCJDIR = """
Oracle | Remote / International Datacenters
Senior Technical Lead - Cloud Automation Engineer | Feb 2022 - Present
Platform Component Ownership: Architected and managed the end-to-end multi-tenant architecture
of a global Chef infrastructure orchestrating contracts for 40,000+ managed endpoints across
international datacenters.
Distributed Observability: Built and scaled an enterprise data pipeline utilizing Filebeat agents
on 40,000+ devices routing via Logstash to centralized OpenSearch clusters; analyzed usage, logs,
and error budgets to optimize reliability.
Integration & API Frameworks: Developed a custom Python package and playbooks framework within
Oracle Linux Automation Manager (OLAM) to replace a legacy third-party platform; unified and
automated cross-vendor API integrations for 12,000+ network surfaces.
Infrastructure as Code (IaC): Engineered reusable, highly available Terraform plans, Chef
Cookbooks, and Ansible roles to standardize platform SDKs and services across all enterprise
domains.
CI/CD & Resilience: Eliminated production configuration drift and boosted delivery velocity by
replacing manual workflows with automated Jenkins and CloudLab CI/CD release pipelines.
Developer Tooling Innovation: Spearheaded team-level adoption of AI-assisted engineering tools
(Cline, Codex, Code Assist), developing reliable internal workflows that reduced test-driven
development (TDD) busywork by 80%.
""".strip()


@dataclass(frozen=True)
class ProfileDocument:
    path: Path
    text: str


class TailoredResumeArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    company: str | None
    title: str
    linkedin_url: str | None
    resume_path: str
    artifact_kind: Literal["resume", "recommendations"] = "resume"
    recommendations_path: str | None = None


class MatchingJobsWorkflowResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_files: list[str]
    search_queries: list[JobSearchQuery]
    jobs_found: int
    resumes_created: int
    recommendations_created: int = 0
    tracking_spreadsheet: str
    skipped_blacklisted: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    artifacts: list[TailoredResumeArtifact] = Field(default_factory=list)


class CompanyBlacklist:
    def __init__(self, patterns: list[str]) -> None:
        self._patterns = [pattern.strip() for pattern in patterns if pattern.strip()]

    @classmethod
    def from_file(cls, path: Path) -> CompanyBlacklist:
        if not path.exists():
            return cls([])
        patterns: list[str] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            value = line.strip()
            if not value or value.startswith("#"):
                continue
            patterns.append(value)
        return cls(patterns)

    def matches(self, company: str | None) -> bool:
        if not company:
            return False
        company_value = company.casefold()
        return any(_glob_matches(company_value, pattern.casefold()) for pattern in self._patterns)


class MatchingJobsWorkflow:
    def __init__(self, *, service: JobSearchService, ollama: Any) -> None:
        self._service = service
        self._ollama = ollama

    async def run(
        self,
        *,
        profile_dir: Path = DEFAULT_PROFILE_DIR,
        blacklist_path: Path = DEFAULT_BLACKLIST_PATH,
        output_dir: Path = DEFAULT_OUTPUT_DIR,
        source_resume_name: str = DEFAULT_SOURCE_RESUME,
        current_job_description_name: str = DEFAULT_CURRENT_JOB_DESCRIPTION,
        location: str = "United States",
        date_posted: DatePosted = "past_week",
        limit_per_query: int = 10,
        max_queries: int = 6,
        max_jobs: int = 10,
    ) -> MatchingJobsWorkflowResult:
        profile_documents = load_profile_documents(profile_dir)
        profile_context = format_profile_context(profile_documents)
        source_resume = _find_source_resume(profile_documents, source_resume_name)
        current_job_description = _find_source_resume(
            profile_documents,
            current_job_description_name,
        )
        search_queries = await self._generate_search_queries(
            profile_context=profile_context,
            location=location,
            date_posted=date_posted,
            limit_per_query=limit_per_query,
            max_queries=max_queries,
        )
        blacklist = CompanyBlacklist.from_file(blacklist_path)

        candidates: list[JobDetails] = []
        skipped_blacklisted: list[str] = []
        errors: list[str] = []
        seen_job_ids: set[str] = set()

        for query in search_queries:
            try:
                result = await self._service.search(query)
            except LinkedInCareerMcpError as exc:
                errors.append(f"{query.keywords}: {exc}")
                continue
            for posting in result.jobs:
                if posting.job_id in seen_job_ids:
                    continue
                seen_job_ids.add(posting.job_id)
                if blacklist.matches(posting.company):
                    skipped_blacklisted.append(_job_label(posting.company, posting.title))
                    continue
                try:
                    details = await self._service.get_details(
                        str(posting.job_url or posting.job_id),
                    )
                except LinkedInCareerMcpError as exc:
                    errors.append(f"{posting.job_id}: {exc}")
                    details = JobDetails(**posting.model_dump())
                if blacklist.matches(details.company):
                    skipped_blacklisted.append(_job_label(details.company, details.title))
                    continue
                candidates.append(details)
                if len(candidates) >= max_jobs:
                    break
            if len(candidates) >= max_jobs:
                break

        artifacts: list[TailoredResumeArtifact] = []
        tracking_path = output_dir / TRACKING_WORKBOOK
        for job in candidates:
            try:
                resume_text = await self._generate_resume_text(
                    source_resume=source_resume,
                    current_job_description=current_job_description,
                    job=job,
                )
                artifact_kind: Literal["resume", "recommendations"] = "resume"
                recommendations_path: Path | None = None
                if _looks_like_recommendations(resume_text):
                    artifact_kind = "recommendations"
                    recommendations_text = await self._generate_recommendations_text(
                        source_resume=source_resume,
                        current_job_description=current_job_description,
                        job=job,
                        draft_text=resume_text,
                    )
                    resume_path = write_resume_recommendations_pdf(
                        recommendations_text=recommendations_text,
                        output_dir=output_dir,
                        job=job,
                    )
                    recommendations_path = resume_path
                else:
                    resume_path = write_resume_pdf(
                        resume_text=resume_text,
                        output_dir=output_dir,
                        job=job,
                    )
                append_tracking_row(tracking_path=tracking_path, job=job, resume_path=resume_path)
            except LinkedInCareerMcpError as exc:
                errors.append(f"{job.job_id}: {exc}")
                continue
            artifacts.append(
                TailoredResumeArtifact(
                    job_id=job.job_id,
                    company=job.company,
                    title=job.title,
                    linkedin_url=str(job.job_url) if job.job_url else None,
                    resume_path=str(resume_path),
                    artifact_kind=artifact_kind,
                    recommendations_path=(
                        str(recommendations_path) if recommendations_path else None
                    ),
                )
            )

        return MatchingJobsWorkflowResult(
            profile_files=[str(document.path) for document in profile_documents],
            search_queries=search_queries,
            jobs_found=len(candidates),
            resumes_created=sum(1 for artifact in artifacts if artifact.artifact_kind == "resume"),
            recommendations_created=sum(
                1 for artifact in artifacts if artifact.artifact_kind == "recommendations"
            ),
            tracking_spreadsheet=str(tracking_path),
            skipped_blacklisted=skipped_blacklisted,
            errors=errors,
            artifacts=artifacts,
        )

    async def _generate_search_queries(
        self,
        *,
        profile_context: str,
        location: str,
        date_posted: DatePosted,
        limit_per_query: int,
        max_queries: int,
    ) -> list[JobSearchQuery]:
        plan = await self._ollama.generate_json(
            _search_query_prompt(
                profile_context=_limit_context(profile_context, max_chars=8_000),
                location=location,
                date_posted=date_posted,
                limit_per_query=limit_per_query,
                max_queries=max_queries,
            )
        )
        raw_queries = plan.get("queries")
        if raw_queries is None and "keywords" in plan:
            raw_queries = [plan]
        if not isinstance(raw_queries, list) or not raw_queries:
            raise WorkflowError("Ollama did not return any LinkedIn search queries.")

        base_queries = [
            _coerce_search_query(
                value,
                location=location,
                date_posted=date_posted,
                limit_per_query=limit_per_query,
            )
            for value in raw_queries
            if isinstance(value, dict)
        ]
        if not base_queries:
            raise WorkflowError("Ollama search queries were not usable.")
        return _expand_remote_and_hybrid_queries(base_queries, max_queries=max_queries)

    async def _generate_resume_text(
        self,
        *,
        source_resume: ProfileDocument | None,
        current_job_description: ProfileDocument | None,
        job: JobDetails,
    ) -> str:
        if source_resume is None:
            raise WorkflowError(f"Source resume file was not found: {DEFAULT_SOURCE_RESUME}")
        tailored_scjdir = await self._ollama.generate_text(
            _scjdir_prompt(
                source_resume=source_resume,
                current_job_description=current_job_description,
                job=job,
            )
        )
        if not tailored_scjdir:
            raise WorkflowError(f"Ollama returned an empty SCJDiR rewrite for job {job.job_id}.")
        text = await self._ollama.generate_text(
            _resume_prompt(
                source_resume=source_resume,
                current_job_description=current_job_description,
                tailored_scjdir=tailored_scjdir,
                job=job,
            )
        )
        if not text:
            raise WorkflowError(f"Ollama returned an empty resume for job {job.job_id}.")
        return text

    async def _generate_recommendations_text(
        self,
        *,
        source_resume: ProfileDocument | None,
        current_job_description: ProfileDocument | None,
        job: JobDetails,
        draft_text: str,
    ) -> str:
        text = await self._ollama.generate_text(
            _recommendations_prompt(
                source_resume=source_resume,
                current_job_description=current_job_description,
                job=job,
                draft_text=draft_text,
            )
        )
        if not text:
            raise WorkflowError(f"Ollama returned empty recommendations for job {job.job_id}.")
        return text


def load_profile_documents(profile_dir: Path) -> list[ProfileDocument]:
    if not profile_dir.exists():
        raise WorkflowError(f"Profile directory does not exist: {profile_dir}")
    documents: list[ProfileDocument] = []
    for path in sorted(profile_dir.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        if path.suffix.lower() not in SUPPORTED_PROFILE_SUFFIXES:
            continue
        text = _read_profile_file(path)
        if text.strip():
            documents.append(ProfileDocument(path=path, text=text.strip()))
    if not documents:
        supported = ", ".join(sorted(SUPPORTED_PROFILE_SUFFIXES))
        raise WorkflowError(f"No supported profile files found in {profile_dir} ({supported}).")
    return documents


def format_profile_context(documents: list[ProfileDocument], *, max_chars: int = 120_000) -> str:
    sections: list[str] = []
    remaining = max_chars
    for document in documents:
        if remaining <= 0:
            break
        text = document.text[:remaining]
        sections.append(f"--- {document.path.name} ---\n{text}")
        remaining -= len(text)
    return "\n\n".join(sections)


def _limit_context(text: str, *, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit("\n", 1)[0]


def write_resume_pdf(*, resume_text: str, output_dir: Path, job: JobDetails) -> Path:
    company_dir = _path_part(job.company or "unknown_company")
    title_part = _path_part(job.title, lower=True)
    job_dir = _path_part(f"{job.job_id}_{job.title}", lower=True)
    resume_path = output_dir / "resumes" / company_dir / job_dir / f"mp_resume_{title_part}.pdf"
    _write_text_pdf(text=resume_text, path=resume_path)
    return resume_path


def write_resume_recommendations_pdf(
    *,
    recommendations_text: str,
    output_dir: Path,
    job: JobDetails,
) -> Path:
    company_dir = _path_part(job.company or "unknown_company")
    title_part = _path_part(job.title, lower=True)
    job_dir = _path_part(f"{job.job_id}_{job.title}", lower=True)
    recommendations_path = (
        output_dir
        / "resumes"
        / company_dir
        / job_dir
        / f"mp_resume_{title_part}-recommends.pdf"
    )
    _write_text_pdf(text=recommendations_text, path=recommendations_path)
    return recommendations_path


def _write_text_pdf(*, text: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    styles = getSampleStyleSheet()
    body = styles["BodyText"]
    body.fontName = "Helvetica"
    body.fontSize = 10
    body.leading = 13
    heading = styles["Heading2"]
    heading.fontName = "Helvetica-Bold"

    story: list[Any] = []
    for raw_line in _clean_resume_text(text).splitlines():
        line = raw_line.strip()
        if not line:
            story.append(Spacer(1, 8))
        elif _looks_like_heading(line):
            story.append(Paragraph(escape(line), heading))
        else:
            story.append(Paragraph(escape(line), body))

    if not story:
        story.append(Paragraph("Resume content was empty.", body))

    document = SimpleDocTemplate(
        str(path),
        pagesize=LETTER,
        rightMargin=42,
        leftMargin=42,
        topMargin=42,
        bottomMargin=42,
    )
    document.build(story)


def append_tracking_row(*, tracking_path: Path, job: JobDetails, resume_path: Path) -> None:
    tracking_path.parent.mkdir(parents=True, exist_ok=True)
    workbook: Workbook
    if tracking_path.exists():
        workbook = load_workbook(tracking_path)
        sheet = workbook.active
        _ensure_tracking_headers(sheet)
    else:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Applications"
        sheet.append(TRACKING_HEADERS)
        sheet.freeze_panes = "A2"
        _size_tracking_columns(sheet)

    row = sheet.max_row + 1
    job_url = str(job.job_url) if job.job_url else ""
    relative_resume = str(resume_path)
    values = [
        job.job_id,
        job.company or "",
        job.title,
        job_url,
        relative_resume,
        "No",
        "",
    ]
    for column, value in enumerate(values, start=1):
        sheet.cell(row=row, column=column, value=value)

    if job_url:
        link_cell = sheet.cell(row=row, column=4)
        link_cell.hyperlink = job_url
        link_cell.style = "Hyperlink"

    resume_cell = sheet.cell(row=row, column=5)
    resume_cell.hyperlink = resume_path.resolve().as_uri()
    resume_cell.style = "Hyperlink"

    workbook.save(tracking_path)


def _read_profile_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in SUPPORTED_TEXT_SUFFIXES:
        return path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(path)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if suffix == ".docx":
        from docx import Document

        document = Document(path)
        return "\n".join(paragraph.text for paragraph in document.paragraphs)
    return ""


def _find_source_resume(
    documents: list[ProfileDocument],
    source_resume_name: str,
) -> ProfileDocument | None:
    for document in documents:
        if document.path.name == source_resume_name:
            return document
    return None


def _job_description_context(job: JobDetails, *, max_chars: int = 4_000) -> str:
    return _limit_context(
        job.description or "No public job description was available.",
        max_chars=max_chars,
    )


def _coerce_search_query(
    value: dict[str, Any],
    *,
    location: str,
    date_posted: DatePosted,
    limit_per_query: int,
) -> JobSearchQuery:
    max_limit = min(max(limit_per_query, 1), 100)
    data = {
        "keywords": str(value.get("keywords") or "").strip(),
        "location": str(value.get("location") or location).strip() or location,
        "date_posted": value.get("date_posted") or date_posted,
        "job_type": value.get("job_type"),
        "workplace_type": value.get("workplace_type"),
        "experience_level": value.get("experience_level"),
        "sort_by": value.get("sort_by") or "recent",
        "distance": value.get("distance"),
        "limit": min(max(int(value.get("limit") or max_limit), 1), max_limit),
        "page": max(int(value.get("page") or 0), 0),
    }
    if not data["keywords"]:
        raise WorkflowError("Ollama returned a search query without keywords.")
    try:
        return JobSearchQuery(**data)
    except ValueError:
        data["date_posted"] = date_posted
        data["job_type"] = None
        data["workplace_type"] = None
        data["experience_level"] = None
        data["sort_by"] = "recent"
        data["distance"] = None
        return JobSearchQuery(**data)


def _expand_remote_and_hybrid_queries(
    queries: list[JobSearchQuery],
    *,
    max_queries: int,
) -> list[JobSearchQuery]:
    expanded: list[JobSearchQuery] = []
    seen: set[tuple[str, str, str]] = set()
    for query in queries:
        for workplace_type in ("remote", "hybrid"):
            next_query = query.model_copy(update={"workplace_type": workplace_type})
            key = (
                next_query.keywords.casefold(),
                next_query.location.casefold(),
                workplace_type,
            )
            if key in seen:
                continue
            seen.add(key)
            expanded.append(next_query)
            if len(expanded) >= max_queries:
                return expanded
    return expanded


def _search_query_prompt(
    *,
    profile_context: str,
    location: str,
    date_posted: DatePosted,
    limit_per_query: int,
    max_queries: int,
) -> str:
    return f"""
You generate LinkedIn public job search parameters from a candidate profile.
Return only valid JSON. Do not include commentary.

Rules:
- Generate up to {max_queries} keyword-focused query objects.
- Use combinations of role titles, seniority, domain keywords, and core skills.
- The workflow will force remote and hybrid LinkedIn workplace filters.
- Prefer concise keyword strings that LinkedIn search can use directly.
- Do not invent facts about the candidate.

Each query object must use this schema:
{{
  "keywords": "string",
  "location": "{location}",
  "date_posted": "{date_posted}",
  "job_type": "full_time",
  "workplace_type": "remote",
  "experience_level": "mid_senior",
  "sort_by": "recent",
  "limit": {limit_per_query},
  "page": 0
}}

Allowed values:
- date_posted: any_time, past_24_hours, past_week, past_month
- job_type: full_time, part_time, contract, temporary, volunteer, internship, other
- workplace_type: remote, hybrid
- experience_level: internship, entry_level, associate, mid_senior, director, executive
- sort_by: relevance, recent

Candidate profile files:
{profile_context}
""".strip()


def _scjdir_prompt(
    *,
    source_resume: ProfileDocument | None,
    current_job_description: ProfileDocument | None,
    job: JobDetails,
) -> str:
    source_resume_text = _limit_context(
        source_resume.text if source_resume else "",
        max_chars=12_000,
    )
    cjd_text = _limit_context(
        current_job_description.text if current_job_description else "No CJD was available.",
        max_chars=8_000,
    )
    return f"""
You are rewriting only the candidate's current-role resume section, called SCJDiR.
Return only the replacement SCJDiR block. Do not return advice, notes, markdown fences,
JSON, analysis, or instructions.

Rules:
- Keep the employer, location, title, and dates factual.
- Use the CJD only as supporting context for the current Oracle role.
- Use the job opening description only to choose emphasis and language.
- Make small, factual wording changes around the margins.
- Preserve the approximate length and bullet count of the original SCJDiR.
- Do not invent products, dates, employers, certifications, tools, metrics, or responsibilities.
- Prefer resume bullets, not recommendations.

Original SCJDiR:
{DEFAULT_SCJDIR}

Current resume text:
{source_resume_text}

Current job description (CJD):
{cjd_text}

Job opening description (JOD):
Title: {job.title}
Company: {job.company or "Unknown"}
Location: {job.location or "Unknown"}
LinkedIn job ID: {job.job_id}
Description:
{_job_description_context(job)}
""".strip()


def _resume_prompt(
    *,
    source_resume: ProfileDocument | None,
    current_job_description: ProfileDocument | None,
    tailored_scjdir: str,
    job: JobDetails,
) -> str:
    source_resume_text = _limit_context(
        source_resume.text if source_resume else "",
        max_chars=18_000,
    )
    cjd_hint = _limit_context(
        current_job_description.text if current_job_description else "No CJD was available.",
        max_chars=4_000,
    )
    return f"""
You are producing the final tailored resume text for one job opening.
Return only the finished resume text. Do not return advice, recommendations, commentary,
markdown fences, JSON, or implementation instructions.

Hard requirements:
- Start from the source resume below. Preserve its factual content and overall structure.
- Replace the current Oracle role section with the tailored SCJDiR below.
- Make only minor wording or keyword-emphasis changes outside the Oracle section.
- Use the CJD only to support factual rephrasing of the current Oracle role.
- Use the JOD only to choose emphasis and terminology.
- Do not invent employers, dates, credentials, projects, tools, metrics, or responsibilities.
- Do not add a "recommendations", "suggestions", "notes", or "changes made" section.
- The output must read as a resume from the candidate's point of view.
- Include the candidate's name/contact header if it appears in the source resume.

Tailored SCJDiR to insert:
{tailored_scjdir}

Source resume:
{source_resume_text}

CJD context:
{cjd_hint}

JOD:
Title: {job.title}
Company: {job.company or "Unknown"}
Description:
{_job_description_context(job)}
""".strip()


def _recommendations_prompt(
    *,
    source_resume: ProfileDocument | None,
    current_job_description: ProfileDocument | None,
    job: JobDetails,
    draft_text: str,
) -> str:
    source_resume_text = _limit_context(
        source_resume.text if source_resume else "",
        max_chars=14_000,
    )
    cjd_text = _limit_context(
        current_job_description.text if current_job_description else "No CJD was available.",
        max_chars=6_000,
    )
    return f"""
The prior generation did not produce a usable resume. Produce focused implementation
recommendations that another model or Codex skill can apply to the source resume.

Return only concise recommendations. Do not write a full resume.

Required format:
1. SCJDiR replacement: provide the exact replacement Oracle current-role section.
2. Other minor resume edits: list only small keyword or wording changes outside SCJDiR.
3. Do-not-change constraints: list factual details that must remain unchanged.

Source resume:
{source_resume_text}

CJD:
{cjd_text}

JOD:
Title: {job.title}
Company: {job.company or "Unknown"}
Description:
{_job_description_context(job)}

Unusable draft text:
{_limit_context(draft_text, max_chars=6_000)}
""".strip()


def _glob_matches(value: str, pattern: str) -> bool:
    regex = "^" + re.escape(pattern).replace(r"\*", ".*").replace(r"\?", ".") + "$"
    return re.match(regex, value) is not None


def _job_label(company: str | None, title: str | None) -> str:
    return f"{company or 'Unknown company'} - {title or 'Unknown title'}"


def _path_part(value: str, *, lower: bool = False) -> str:
    value = value.lower() if lower else value
    value = re.sub(r"[^A-Za-z0-9._ -]+", "", value)
    value = re.sub(r"[\s/]+", "_", value.strip())
    value = value.strip("._-")
    return value[:120] or "unknown"


def _clean_resume_text(text: str) -> str:
    text = re.sub(r"```(?:\w+)?", "", text)
    return text.replace("```", "").strip()


def _looks_like_recommendations(text: str) -> bool:
    normalized = text.casefold()
    recommendation_markers = (
        "recommendation",
        "recommendations",
        "suggestion",
        "suggestions",
        "here are",
        "you should",
        "i recommend",
        "changes to make",
        "proposed changes",
    )
    has_marker = any(marker in normalized for marker in recommendation_markers)
    has_resume_anchor = "professional summary" in normalized or "oracle" in normalized
    return has_marker and not has_resume_anchor


def _looks_like_heading(line: str) -> bool:
    if len(line) > 80:
        return False
    letters = [char for char in line if char.isalpha()]
    return bool(letters) and sum(char.isupper() for char in letters) / len(letters) > 0.75


def _ensure_tracking_headers(sheet: Worksheet) -> None:
    existing = [
        sheet.cell(row=1, column=column).value
        for column in range(1, len(TRACKING_HEADERS) + 1)
    ]
    if existing == TRACKING_HEADERS:
        return
    if sheet.max_row == 1 and all(value is None for value in existing):
        for column, header in enumerate(TRACKING_HEADERS, start=1):
            sheet.cell(row=1, column=column, value=header)
        _size_tracking_columns(sheet)
        return
    raise WorkflowError(f"Tracking workbook has unexpected headers: {sheet.title}")


def _size_tracking_columns(sheet: Worksheet) -> None:
    widths = [16, 24, 36, 60, 70, 14, 16]
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[chr(64 + index)].width = width


async def run_from_cli(args: argparse.Namespace) -> MatchingJobsWorkflowResult:
    settings = load_settings()
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
    workflow = MatchingJobsWorkflow(service=service, ollama=ollama)
    try:
        return await workflow.run(
            profile_dir=Path(args.profile_dir),
            blacklist_path=Path(args.blacklist_path),
            output_dir=Path(args.output_dir),
            source_resume_name=args.source_resume_name,
            current_job_description_name=args.current_job_description_name,
            location=args.location,
            date_posted=args.date_posted,
            limit_per_query=args.limit_per_query,
            max_queries=args.max_queries,
            max_jobs=args.max_jobs,
        )
    finally:
        await provider.aclose()
        await ollama.aclose()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Find matching LinkedIn jobs and tailor resumes.")
    parser.add_argument("--profile-dir", default=str(DEFAULT_PROFILE_DIR))
    parser.add_argument("--blacklist-path", default=str(DEFAULT_BLACKLIST_PATH))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--source-resume-name", default=DEFAULT_SOURCE_RESUME)
    parser.add_argument("--current-job-description-name", default=DEFAULT_CURRENT_JOB_DESCRIPTION)
    parser.add_argument("--location", default="United States")
    parser.add_argument(
        "--date-posted",
        default="past_week",
        choices=["any_time", "past_24_hours", "past_week", "past_month"],
    )
    parser.add_argument("--limit-per-query", type=int, default=10)
    parser.add_argument("--max-queries", type=int, default=6)
    parser.add_argument("--max-jobs", type=int, default=10)
    return parser


def main() -> None:
    parser = build_arg_parser()
    result = asyncio.run(run_from_cli(parser.parse_args()))
    print(json.dumps(result.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    main()
