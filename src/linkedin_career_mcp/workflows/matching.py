from __future__ import annotations

import argparse
import asyncio
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from typing import Any, Literal

from openpyxl import Workbook, load_workbook
from openpyxl.worksheet.worksheet import Worksheet
from pydantic import BaseModel, ConfigDict, Field
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer

from linkedin_career_mcp.api_client import ApiLlmClient
from linkedin_career_mcp.config import Settings, load_settings
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
RESUME_HEADER_NAME = "Max Perkhounkov"
RESUME_HEADER_CONTACT = (
    "Iowa City, IA | 641-781-0477 | mperkhounkov1@gmail.com | linkedin.com/mperkhou"
)
STATIC_PROFESSIONAL_SUMMARY = (
    "Analytical and metrics-driven Senior Platform Software Engineer with over 10 years of "
    "multi-disciplinary experience architecting scalable distributed systems, developer tooling, "
    "and cloud automation frameworks. Proven track record leading enterprise-level integrations, "
    "optimizing platform resilience, and implementing secure API and observability pipelines "
    "across 40,000+ devices. Combines a strong background in advanced mathematics and "
    "algorithmic problem-solving with hands-on expertise in CI/CD, Infrastructure as Code (IaC), "
    "and modern multi-tenant cloud architectures."
)
AI_GENERATION_NOTE = (
    "Note: This resume is custom tailored for every job position using my automated agentic "
    "workflow found at: "
    "[mperkhou/linkedin-career-mcp](https://github.com/mperkhou/linkedin-career-mcp)"
)
RESUME_SECTION_HEADINGS = {
    "Professional Summary",
    "Core Technical Skills",
    "Professional Experience",
    "Education & Certifications",
}
DEFAULT_CORE_TECHNICAL_SKILLS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Languages & Frameworks",
        (
            "Python",
            "Ruby",
            "JavaScript",
            "Node.js",
            "React.js",
            "Go",
            "Bash",
            "PowerShell",
            "Ruby on Rails",
            "Django",
        ),
    ),
    (
        "Distributed Systems & Cloud",
        (
            "AWS",
            "Azure",
            "Oracle Cloud Infrastructure (OCI)",
            "ElasticSearch",
            "OpenSearch",
        ),
    ),
    (
        "Platform & API Engineering",
        (
            "RESTful APIs",
            "Systems Architecture",
            "Microservices",
            "JSON/XML",
            "API Integration",
        ),
    ),
    (
        "Automation & IaC",
        (
            "Chef (Cookbooks/Policies)",
            "Ansible",
            "Terraform",
            "Jenkins",
            "CloudLab CI/CD Pipelines",
        ),
    ),
    (
        "Data & Observability",
        (
            "Filebeat",
            "Logstash",
            "PostgreSQL",
            "MongoDB",
            "SQL",
            "Data Pipelines",
            "Error Budgets",
        ),
    ),
    (
        "Security & Compliance",
        (
            "Secure Coding Practices",
            "Vulnerability Mitigation",
            "Role-Based Access Control (RBAC)",
        ),
    ),
)
DEFAULT_SUPPLEMENTAL_SEARCH_KEYWORDS = (
    "Senior Platform Engineer AI",
    "Cloud Automation Engineer LLMs",
    "Infrastructure Software Engineer agentic AI",
    "DevOps Engineer distributed systems",
)
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
DEFAULT_PRIOR_EXPERIENCE_ENTRIES: tuple[dict[str, object], ...] = (
    {
        "organization": "University of Iowa Hospitals and Clinics",
        "location": "Iowa City, IA",
        "title": "Engineering Support Specialist",
        "dates": "Jan 2020 - May 2021",
        "bullets": (
            "Full-Cycle Software Engineering: Adhered to strict software development lifecycles "
            "to build custom Python and AutoIT automation scripts, streamlining system upgrades "
            "across hundreds of mission-critical platform nodes.",
            "Web Application Development: Collaborated on the structural design and "
            "implementation of a DICOM anonymization server utilizing a modern React.js frontend "
            "interface.",
            "Deep Debugging & Patching: Conducted performance troubleshooting, defect handling, "
            "and remote patch deployments on highly regulated medical platform surfaces.",
        ),
    },
    {
        "organization": "Steindler Orthopedic Clinic",
        "location": "Iowa City, IA",
        "title": "IT Administrator / Systems Engineer",
        "dates": "Mar 2019 - Nov 2019",
        "bullets": (
            "Cloud Migrations & Architecture: Led the engineering lifecycle to modernize 7+ year "
            "old core infrastructure systems, executing legacy virtualization overhauls via "
            "ESX/VMware and migrating services to Azure Cloud.",
            "API & Workflow Integration: Built custom PHP plugins and integrated secure Azure "
            "SharePoint document-control workflows to boost internal process cross-functional "
            "alignment.",
            "Observability Dashboards: Launched an enterprise ticketing and incident-tracking "
            "system, designing centralized health monitoring dashboards and automated analytical "
            "reporting tools.",
        ),
    },
    {
        "organization": "Stamats Communications",
        "location": "Cedar Rapids, IA",
        "title": "Systems Administrator (Contract)",
        "dates": "Apr 2018 - Oct 2018",
        "bullets": (
            "Infrastructure Optimization: Partnered with cross-functional leadership to architect "
            "and execute a multi-million dollar infrastructure upgrade, maximizing capacity and "
            "network availability.",
            "Cloud Ecosystem Deployment: Spearheaded on-premise Exchange migrations to Azure "
            "cloud environments while ensuring strict alignment with enterprise information "
            "security standards.",
        ),
    },
    {
        "organization": "VIDA Diagnostics",
        "location": "Coralville, IA",
        "title": "Systems Engineer",
        "dates": "Mar 2014 - Mar 2018",
        "bullets": (
            "Algorithmic Data Engineering: Wrote highly scalable Python data-transfer scripts "
            "optimizing the ingestion and transit of massive CT imagery cache structures between "
            "Linux environments and SAN/NAS storage arrays.",
            "Framework Refactoring: Rebuilt corporate web platforms entirely from WordPress to a "
            "robust, secure Django framework to improve backend structural integrity.",
        ),
    },
)
DEFAULT_EDUCATION_CERTIFICATIONS = (
    "- Bachelor of Science in Physics & Mathematics | University of Iowa, IA",
    "  - Focus: Graduate-level mathematics, applied statistics, and computer science principles.",
    (
        "  - Leadership: Teaching Assistant (Physics Department), President of the University "
        "Chess Club."
    ),
    "- Oracle Cloud Infrastructure (OCI) Engineer | Certification (August, 2024)",
    "- Oracle Cloud Infrastructure AI Foundations Associate | Certification (May, 2026)",
    "- AlienVault Certified Security Engineer (AVCSE) | Certification",
    "- Advanced Continuing Education (Udemy): Docker & Kubernetes Ecosystems, Microservices "
    "Engineering (Node.js & React), PostgreSQL Database Bootcamp, Object-Oriented Programming "
    "(OOP) & Agile Methodologies.",
)


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


@dataclass
class _SearchMemory:
    """Tracks which keyword groups returned jobs and which did not, so the LLM can
    refine successive iterations."""

    rewarded_keywords: list[str] = field(default_factory=list)
    penalized_keywords: list[str] = field(default_factory=list)
    attempted_query_keys: set[str] = field(default_factory=set)
    total_searches: int = 0

    def query_key(self, query: JobSearchQuery) -> str:
        wt = query.workplace_type or "any"
        return f"{query.keywords.casefold()}::{query.location.casefold()}::{wt}"

    def register_result(self, query: JobSearchQuery, count: int) -> None:
        self.total_searches += 1
        self.attempted_query_keys.add(self.query_key(query))
        if count > 0:
            self.rewarded_keywords.append(query.keywords)
        else:
            self.penalized_keywords.append(query.keywords)

    @property
    def reward_sample(self) -> str:
        if not self.rewarded_keywords:
            return "No keywords have produced results yet."
        return "\n".join(
            f"- {kw}" for kw in self.rewarded_keywords[-10:]
        )

    @property
    def penalty_sample(self) -> str:
        if not self.penalized_keywords:
            return "None so far."
        return "\n".join(
            f"- {kw}" for kw in self.penalized_keywords[-10:]
        )

    def has_query(self, query: JobSearchQuery) -> bool:
        return self.query_key(query) in self.attempted_query_keys


MAX_ITERATIVE_SEARCHES = 1000
MIN_SEARCHES_BEFORE_STOP = 4


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
        blacklist = CompanyBlacklist.from_file(blacklist_path)

        candidates: list[JobDetails] = []
        skipped_blacklisted: list[str] = []
        errors: list[str] = []
        seen_job_ids: set[str] = set()
        search_memory = _SearchMemory()
        all_search_queries: list[JobSearchQuery] = []
        min_searches_before_stop = min(max(max_queries, 1), MIN_SEARCHES_BEFORE_STOP)

        while (
            len(candidates) < max_jobs
            or search_memory.total_searches < min_searches_before_stop
        ) and search_memory.total_searches < MAX_ITERATIVE_SEARCHES:
            search_queries = await self._generate_search_queries(
                profile_context=profile_context,
                location=location,
                date_posted=date_posted,
                limit_per_query=limit_per_query,
                max_queries=max_queries,
                search_memory=search_memory,
            )

            new_query_found = False
            for query in search_queries:
                if search_memory.total_searches >= MAX_ITERATIVE_SEARCHES:
                    break
                if search_memory.has_query(query):
                    continue
                new_query_found = True
                all_search_queries.append(query)
                try:
                    result = await self._service.search(query)
                except LinkedInCareerMcpError as exc:
                    errors.append(f"{query.keywords}: {exc}")
                    search_memory.register_result(query, 0)
                    continue
                search_memory.register_result(query, len(result.jobs))
                for posting in result.jobs:
                    if len(candidates) >= max_jobs:
                        break
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
                if (
                    len(candidates) >= max_jobs
                    and search_memory.total_searches >= min_searches_before_stop
                ):
                    break

            if not new_query_found or search_memory.total_searches == 0:
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
            search_queries=all_search_queries,
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
        search_memory: _SearchMemory | None = None,
    ) -> list[JobSearchQuery]:
        plan = await self._ollama.generate_json(
            _search_query_prompt(
                profile_context=_limit_context(profile_context, max_chars=8_000),
                location=location,
                date_posted=date_posted,
                limit_per_query=limit_per_query,
                max_queries=max_queries,
                search_memory=search_memory,
            )
        )
        raw_queries = plan.get("queries")
        if raw_queries is None and "keywords" in plan:
            raw_queries = [plan]
        if not isinstance(raw_queries, list):
            raw_queries = []

        base_queries: list[JobSearchQuery] = []
        for value in raw_queries:
            if not isinstance(value, dict):
                continue
            try:
                base_queries.append(
                    _coerce_search_query(
                        value,
                        location=location,
                        date_posted=date_posted,
                        limit_per_query=limit_per_query,
                    )
                )
            except WorkflowError:
                continue

        supplemented_queries = _supplement_search_queries(
            base_queries,
            location=location,
            date_posted=date_posted,
            limit_per_query=limit_per_query,
        )
        if not supplemented_queries:
            raise WorkflowError("The LLM did not return usable LinkedIn search queries.")
        return _expand_remote_and_hybrid_queries(
            supplemented_queries,
            max_queries=max_queries,
        )

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
            raise WorkflowError(f"The LLM returned an empty SCJDiR rewrite for job {job.job_id}.")
        sections_plan = await self._ollama.generate_json(
            _resume_sections_prompt(
                source_resume=source_resume,
                current_job_description=current_job_description,
                tailored_scjdir=tailored_scjdir,
                job=job,
            )
        )
        return _render_resume_template(
            tailored_scjdir=tailored_scjdir,
            sections_plan=sections_plan,
        )

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
            raise WorkflowError(f"The LLM returned empty recommendations for job {job.job_id}.")
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
    body = ParagraphStyle(
        "ResumeBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8.8,
        leading=10.6,
        spaceAfter=2,
    )
    bullet = ParagraphStyle(
        "ResumeBullet",
        parent=body,
        leftIndent=0.32 * inch,
        firstLineIndent=-0.18 * inch,
        bulletIndent=0.03 * inch,
        spaceAfter=1,
    )
    nested_bullet = ParagraphStyle(
        "ResumeNestedBullet",
        parent=body,
        leftIndent=0.72 * inch,
        firstLineIndent=-0.14 * inch,
        bulletIndent=0.46 * inch,
        spaceAfter=1,
    )
    heading = ParagraphStyle(
        "ResumeHeading",
        parent=body,
        fontName="Helvetica",
        fontSize=12,
        leading=14,
        spaceBefore=9,
        spaceAfter=7,
        textColor=colors.black,
    )
    employer_style = ParagraphStyle(
        "ResumeEmployer",
        parent=body,
        fontName="Helvetica-Bold",
        fontSize=9.5,
        leading=11.4,
        spaceBefore=9,
        spaceAfter=5,
    )
    title_style = ParagraphStyle(
        "ResumeTitle",
        parent=body,
        fontName="Helvetica-Bold",
        fontSize=8.6,
        leading=10.3,
        spaceAfter=8,
    )
    name_style = ParagraphStyle(
        "ResumeName",
        parent=body,
        fontName="Helvetica",
        fontSize=11,
        leading=13,
        alignment=0,
        spaceAfter=6,
    )
    contact_style = ParagraphStyle(
        "ResumeContact",
        parent=body,
        fontName="Helvetica-Bold",
        fontSize=7.2,
        leading=8.6,
        alignment=0,
        textColor=colors.black,
        spaceAfter=8,
    )
    note_style = ParagraphStyle(
        "ResumeNote",
        parent=body,
        fontName="Helvetica",
        fontSize=8,
        leading=9.6,
        textColor=colors.black,
    )

    story: list[Any] = []
    story.append(_resume_rule())
    story.append(Spacer(1, 13))

    current_section: str | None = None
    previous_line_blank = False
    for line_number, raw_line in enumerate(_clean_resume_text(text).splitlines()):
        raw_line = _strip_markdown_emphasis(raw_line.rstrip())
        line = raw_line.strip()
        is_nested_bullet = raw_line.startswith("  - ")
        if not line:
            if not previous_line_blank:
                story.append(Spacer(1, 5))
            previous_line_blank = True
            continue
        previous_line_blank = False

        if line in RESUME_SECTION_HEADINGS:
            if line in {"Professional Experience", "Education & Certifications"}:
                story.append(Spacer(1, 5))
                story.append(_resume_rule())
                story.append(Spacer(1, 8))
            current_section = line
            story.append(Paragraph(_paragraph_markup(line), heading))
        elif line_number == 0:
            story.append(Paragraph(_paragraph_markup(line), name_style))
        elif line_number == 1:
            story.append(Paragraph(_paragraph_markup(line), contact_style))
        elif line.startswith("Note:"):
            story.append(Paragraph(_paragraph_markup(line), note_style))
        elif current_section == "Professional Experience" and _looks_like_employer_line(line):
            story.append(Paragraph(_paragraph_markup(line), employer_style))
        elif current_section == "Professional Experience" and _looks_like_title_line(line):
            story.append(Paragraph(_title_markup(line), title_style))
        elif is_nested_bullet:
            story.append(
                Paragraph(
                    _nested_bullet_markup(raw_line[4:].strip()),
                    nested_bullet,
                    bulletText="o",
                )
            )
        elif line.startswith("- "):
            story.append(Paragraph(_bullet_markup(line[2:]), bullet, bulletText="\u2022"))
        elif _looks_like_heading(line):
            story.append(Paragraph(_paragraph_markup(line), heading))
        else:
            story.append(Paragraph(_paragraph_markup(line), body))

    if not story:
        story.append(Paragraph("Resume content was empty.", body))

    document = SimpleDocTemplate(
        str(path),
        pagesize=LETTER,
        rightMargin=54,
        leftMargin=54,
        topMargin=58,
        bottomMargin=52,
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
        raise WorkflowError("The LLM returned a search query without keywords.")
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


def _supplement_search_queries(
    queries: list[JobSearchQuery],
    *,
    location: str,
    date_posted: DatePosted,
    limit_per_query: int,
) -> list[JobSearchQuery]:
    max_limit = min(max(limit_per_query, 1), 100)
    supplements = [
        JobSearchQuery(
            keywords=keywords,
            location=location,
            date_posted=date_posted,
            job_type="full_time",
            workplace_type="remote",
            experience_level="mid_senior",
            sort_by="recent",
            limit=max_limit,
            page=0,
        )
        for keywords in DEFAULT_SUPPLEMENTAL_SEARCH_KEYWORDS
    ]

    ordered: list[JobSearchQuery] = []
    seen_keywords: set[str] = set()
    for query in [*queries[:1], *supplements, *queries[1:]]:
        key = query.keywords.casefold().strip()
        if not key or key in seen_keywords:
            continue
        seen_keywords.add(key)
        ordered.append(query)
    return ordered


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
    search_memory: _SearchMemory | None = None,
) -> str:
    feedback_section = ""
    if search_memory and search_memory.total_searches > 0:
        feedback_section = f"""
Search feedback from previous iterations (up to 10 per category):

Keyword strings that returned jobs (reward these — they work):
{search_memory.reward_sample}

Keyword strings that returned zero jobs (avoid these patterns):
{search_memory.penalty_sample}

Use this feedback to generate fresh, non-duplicate keyword combinations.
Prefer short, general keyword strings (2-4 words) over long, specific ones.
Include role titles like "Platform Engineer", "DevOps Engineer", "Software Engineer",
combined with domain terms like "infrastructure", "automation", "cloud", "distributed systems",
"AI", "agentic AI", and "LLMs" when supported by the profile.
"""

    return f"""
You generate LinkedIn public job search parameters from a candidate profile.
Return only valid JSON. Do not include commentary.
{feedback_section}
Rules:
- Generate up to {max_queries} keyword-focused query objects.
- Use combinations of role titles, seniority, domain keywords, and core skills.
- The workflow will force remote and hybrid LinkedIn workplace filters.
- Prefer concise keyword strings that LinkedIn search can use directly.
- Include AI, agentic AI, and LLM keyword variants when they overlap with the candidate profile.
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


def _resume_sections_prompt(
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
        max_chars=6_000,
    )
    default_skills = "\n".join(
        f"- {category}: {', '.join(skills)}"
        for category, skills in DEFAULT_CORE_TECHNICAL_SKILLS
    )
    default_prior_experience = _render_prior_experience_text(DEFAULT_PRIOR_EXPERIENCE_ENTRIES)
    return f"""
You produce structured resume section edits for one job opening.
Return only valid JSON. Do not return markdown fences, commentary, advice, or a full resume.

The application will render the final resume from a local template. You only control:
1. core_technical_skills
2. prior_experience

Do not include the header, professional summary, AI generation note, Oracle current role, or
education/certifications in the JSON response. Those sections are static or generated separately.

Hard requirements:
- Preserve the six Core Technical Skills categories exactly.
- Add or remove individual skills only when supported by the source resume, CJD, or tailored SCJDiR.
- Prefer skills that overlap with the JOD, including AI, agentic AI, and LLM terms only
  when factual.
- Preserve all prior employers, locations, titles, dates, and the original bullet count per job.
- For prior experience, make only minor keyword swaps or wording changes that remain factual.
- Do not invent employers, dates, credentials, projects, tools, metrics, or responsibilities.

Return this exact JSON shape:
{{
  "core_technical_skills": [
    {{"category": "Languages & Frameworks", "skills": ["Python", "Django"]}}
  ],
  "prior_experience": [
    {{
      "organization": "University of Iowa Hospitals and Clinics",
      "bullets": ["Full-Cycle Software Engineering: ..."]
    }}
  ]
}}

Tailored Oracle current-role SCJDiR, already generated separately:
{tailored_scjdir}

Base Core Technical Skills:
{default_skills}

Base prior experience section:
{default_prior_experience}

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


def _render_resume_template(
    *,
    tailored_scjdir: str,
    sections_plan: Mapping[str, Any],
) -> str:
    core_skills = _coerce_core_skill_sections(sections_plan.get("core_technical_skills"))
    prior_experience = _coerce_prior_experience_entries(sections_plan.get("prior_experience"))
    scjdir_lines = _resume_block_lines(tailored_scjdir)
    if not scjdir_lines or _looks_like_recommendations("\n".join(scjdir_lines)):
        scjdir_lines = _resume_block_lines(DEFAULT_SCJDIR)

    lines: list[str] = [
        RESUME_HEADER_NAME,
        RESUME_HEADER_CONTACT,
        "",
        "Professional Summary",
        STATIC_PROFESSIONAL_SUMMARY,
        "",
        AI_GENERATION_NOTE,
        "",
        "Core Technical Skills",
    ]
    lines.extend(_render_core_skills_lines(core_skills))
    lines.extend(["", "Professional Experience"])
    lines.extend(scjdir_lines)
    lines.append("")
    lines.extend(_render_prior_experience_lines(prior_experience))
    lines.extend(["", "Education & Certifications"])
    lines.extend(DEFAULT_EDUCATION_CERTIFICATIONS)
    return "\n".join(lines).strip()


def _coerce_core_skill_sections(raw_value: Any) -> list[tuple[str, list[str]]]:
    default_sections = [
        (category, list(skills)) for category, skills in DEFAULT_CORE_TECHNICAL_SKILLS
    ]
    if not isinstance(raw_value, list):
        return default_sections

    by_category: dict[str, list[str]] = {}
    for item in raw_value:
        category = ""
        skills_value: Any = None
        if isinstance(item, Mapping):
            category = str(item.get("category") or item.get("name") or "").strip()
            skills_value = item.get("skills") or item.get("items")
        elif isinstance(item, str) and ":" in item:
            category, skills_value = item.split(":", 1)
        skills = _coerce_skill_items(skills_value)
        if category and skills:
            by_category[_normalize_label(category)] = skills

    sections: list[tuple[str, list[str]]] = []
    for category, default_skills in default_sections:
        skills = by_category.get(_normalize_label(category), default_skills)
        sections.append((category, _dedupe_preserve_order(skills)[:12] or default_skills))
    return sections


def _coerce_skill_items(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_items = re.split(r",|;|\n", value)
    elif isinstance(value, list):
        raw_items = [str(item) for item in value]
    else:
        return []
    return [
        _clean_inline_text(item).removeprefix("- ").strip()
        for item in raw_items
        if _clean_inline_text(item).removeprefix("- ").strip()
    ]


def _coerce_prior_experience_entries(raw_value: Any) -> list[dict[str, object]]:
    default_entries = [
        {
            "organization": entry["organization"],
            "location": entry["location"],
            "title": entry["title"],
            "dates": entry["dates"],
            "bullets": list(entry["bullets"]),
        }
        for entry in DEFAULT_PRIOR_EXPERIENCE_ENTRIES
    ]
    if not isinstance(raw_value, list):
        return default_entries

    raw_by_org: dict[str, Mapping[str, Any]] = {}
    for item in raw_value:
        if not isinstance(item, Mapping):
            continue
        organization = str(item.get("organization") or item.get("company") or "").strip()
        if organization:
            raw_by_org[_normalize_label(organization)] = item

    entries: list[dict[str, object]] = []
    for default_entry in default_entries:
        raw_entry = raw_by_org.get(_normalize_label(str(default_entry["organization"])))
        if raw_entry is None:
            entries.append(default_entry)
            continue

        default_bullets = list(default_entry["bullets"])
        model_bullets = _coerce_bullet_items(raw_entry.get("bullets"))
        bullet_count = len(default_bullets)
        if not model_bullets:
            bullets = default_bullets
        else:
            bullets = [
                model_bullets[index] if index < len(model_bullets) else default_bullets[index]
                for index in range(bullet_count)
            ]
        entries.append({**default_entry, "bullets": bullets})
    return entries


def _coerce_bullet_items(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_items = [line for line in value.splitlines() if line.strip()]
    elif isinstance(value, list):
        raw_items = [str(item) for item in value]
    else:
        return []
    return [
        _clean_inline_text(item).removeprefix("- ").strip()
        for item in raw_items
        if _clean_inline_text(item).removeprefix("- ").strip()
    ]


def _render_core_skills_lines(sections: list[tuple[str, list[str]]]) -> list[str]:
    return [f"- {category}: {', '.join(skills)}" for category, skills in sections]


def _render_prior_experience_lines(entries: list[dict[str, object]]) -> list[str]:
    lines: list[str] = []
    for index, entry in enumerate(entries):
        if index:
            lines.append("")
        lines.append(f"{entry['organization']} | {entry['location']}")
        lines.append(f"{entry['title']} | {entry['dates']}")
        lines.extend(f"- {bullet}" for bullet in entry["bullets"])
    return lines


def _render_prior_experience_text(entries: tuple[dict[str, object], ...]) -> str:
    return "\n".join(_render_prior_experience_lines(list(entries)))


def _resume_block_lines(text: str) -> list[str]:
    lines = []
    for raw_line in _clean_resume_text(text).splitlines():
        line = _clean_inline_text(raw_line)
        if not line or line in RESUME_SECTION_HEADINGS:
            continue
        if len(lines) >= 2 and not line.startswith("- ") and ":" in line:
            line = f"- {line}"
        lines.append(line)
    return lines


def _clean_inline_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\u2022", "-")).strip()


def _normalize_label(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.casefold())


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


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


def _paragraph_markup(line: str) -> str:
    parts: list[str] = []
    cursor = 0
    for match in re.finditer(r"\[([^\]]+)\]\((https?://[^)]+)\)", line):
        parts.append(escape(line[cursor : match.start()]))
        label = escape(match.group(1))
        url = escape(match.group(2), quote=True)
        parts.append(f'<a href="{url}" color="blue">{label}</a>')
        cursor = match.end()
    parts.append(escape(line[cursor:]))
    return "".join(parts)


def _bullet_markup(line: str) -> str:
    line = _strip_markdown_emphasis(line)
    if ":" in line:
        label, rest = line.split(":", 1)
        if 2 <= len(label) <= 60:
            return f"<b>{_paragraph_markup(label)}:</b>{_paragraph_markup(rest)}"
    if "|" in line:
        label, rest = line.split("|", 1)
        if 2 <= len(label) <= 80:
            return f"<b>{_paragraph_markup(label.strip())}</b> |{_paragraph_markup(rest)}"
    return _paragraph_markup(line)


def _nested_bullet_markup(line: str) -> str:
    line = _strip_markdown_emphasis(line)
    if ":" in line:
        label, rest = line.split(":", 1)
        if 2 <= len(label) <= 60:
            return f"<i>{_paragraph_markup(label)}:</i>{_paragraph_markup(rest)}"
    return _paragraph_markup(line)


def _title_markup(line: str) -> str:
    line = _strip_markdown_emphasis(line)
    if "|" not in line:
        return _paragraph_markup(line)
    title, dates = line.split("|", 1)
    return f"<b>{_paragraph_markup(title.strip())}</b> | <i>{_paragraph_markup(dates.strip())}</i>"


def _strip_markdown_emphasis(text: str) -> str:
    return re.sub(r"(?<!\*)\*\*(.+?)\*\*(?!\*)", r"\1", text)


def _resume_rule() -> HRFlowable:
    return HRFlowable(
        width="100%",
        thickness=0.55,
        color=colors.HexColor("#6B7280"),
        spaceBefore=0,
        spaceAfter=0,
    )


def _looks_like_employer_line(line: str) -> bool:
    if line.startswith("- ") or " | " not in line:
        return False
    return not any(date in line for date in ("Jan ", "Feb ", "Mar ", "Apr ", "May ", "Jun "))


def _looks_like_title_line(line: str) -> bool:
    if line.startswith("- ") or " | " not in line:
        return False
    return any(
        marker in line
        for marker in (
            "Present",
            "Jan ",
            "Feb ",
            "Mar ",
            "Apr ",
            "May ",
            "Jun ",
            "Jul ",
            "Aug ",
            "Sep ",
            "Oct ",
            "Nov ",
            "Dec ",
        )
    )


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


def _build_llm_client(settings: Settings) -> ApiLlmClient | OllamaClient:
    """Build the LLM client based on the configured provider.

    Defaults to the external API (OpenRouter / DeepSeek). Local Ollama is
    only used when explicitly requested with LINKEDIN_CAREER_MCP_LLM_PROVIDER=ollama.
    """
    provider = settings.llm_provider.casefold().strip()
    if provider == "ollama":
        return OllamaClient(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            timeout_seconds=settings.ollama_timeout_seconds,
        )
    if provider != "api":
        raise WorkflowError(
            "Unsupported LLM provider. Set LINKEDIN_CAREER_MCP_LLM_PROVIDER to 'api' "
            "or 'ollama'."
        )
    if not settings.llm_api_key:
        raise WorkflowError(
            "LINKEDIN_CAREER_MCP_LLM_API_KEY is required when "
            "LINKEDIN_CAREER_MCP_LLM_PROVIDER=api."
        )
    return ApiLlmClient(
        base_url=settings.llm_api_base_url,
        model=settings.llm_api_model,
        api_key=settings.llm_api_key,
        timeout_seconds=settings.llm_api_timeout_seconds,
    )


async def run_from_cli(args: argparse.Namespace) -> MatchingJobsWorkflowResult:
    settings = load_settings()
    provider = LinkedInPublicJobsProvider(
        user_agent=settings.user_agent,
        timeout_seconds=settings.timeout_seconds,
    )
    service = JobSearchService(provider=provider, max_results=settings.max_results)
    llm = _build_llm_client(settings)
    workflow = MatchingJobsWorkflow(service=service, ollama=llm)
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
        await llm.aclose()


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
