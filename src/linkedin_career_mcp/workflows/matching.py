from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from linkedin_career_mcp.application_resume import DEFAULT_MASTER_RESUME_PATH
from linkedin_career_mcp.config import Settings, load_settings
from linkedin_career_mcp.errors import WorkflowError
from linkedin_career_mcp.jod import job_description_context, usable_job_description
from linkedin_career_mcp.llm import (
    build_llm_client,
    build_planner_llm_client,
    workflow_llm_settings_label,
)
from linkedin_career_mcp.models import DatePosted, JobDetails, JobPosting, JobSearchQuery
from linkedin_career_mcp.providers import LinkedInPublicJobsProvider
from linkedin_career_mcp.query_optimizer import (
    QueryOutcome,
    ScoredQuery,
    historical_query_candidates,
    load_query_outcomes,
    rank_search_queries,
    record_query_outcome,
)
from linkedin_career_mcp.services import JobSearchService
from linkedin_career_mcp.webapp import (
    DEFAULT_DATABASE as APPLICATION_DATABASE,
)
from linkedin_career_mcp.webapp import (
    fetch_application_job_ids,
    upsert_application_artifact,
)

DEFAULT_PROFILE_DIR = Path("profile")
DEFAULT_BLACKLIST_PATH = Path(".blacklist")
DEFAULT_OUTPUT_DIR = Path("output")
DEFAULT_MASTER_RESUME_NAME = DEFAULT_MASTER_RESUME_PATH.name
ProgressCallback = Callable[[str], None]

DISALLOWED_EXPERIENCE_LEVELS = {"internship", "entry_level"}
SEARCH_EXPERIENCE_LEVELS = ("associate", "mid_senior", "director", "executive")
DEFAULT_SUPPLEMENTAL_SEARCH_KEYWORDS = (
    "Senior Platform Engineer AI",
    "Cloud Automation Engineer LLMs",
    "Infrastructure Software Engineer agentic AI",
    "DevOps Engineer distributed systems",
)
MIN_SEARCHES_BEFORE_STOP = 4


class SeededApplication(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    company: str | None
    title: str
    linkedin_url: str | None
    prompt_job_description_chars: int


class MatchingJobsWorkflowResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    master_resume_path: str
    database_path: str
    search_queries: list[JobSearchQuery]
    jobs_found: int
    jobs_seeded: int
    skipped_blacklisted: list[str] = Field(default_factory=list)
    skipped_existing: list[str] = Field(default_factory=list)
    skipped_workplace_type: list[str] = Field(default_factory=list)
    skipped_experience_level: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    seeded_applications: list[SeededApplication] = Field(default_factory=list)


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
    rewarded_keywords: list[str] = field(default_factory=list)
    penalized_keywords: list[str] = field(default_factory=list)
    attempted_query_keys: set[str] = field(default_factory=set)
    total_searches: int = 0

    def query_key(self, query: JobSearchQuery) -> str:
        workplace_type = query.workplace_type or "any"
        return f"{query.keywords.casefold()}::{query.location.casefold()}::{workplace_type}"

    def register_result(self, query: JobSearchQuery, count: int) -> None:
        self.total_searches += 1
        self.attempted_query_keys.add(self.query_key(query))
        if count > 0:
            self.rewarded_keywords.append(query.keywords)
        else:
            self.penalized_keywords.append(query.keywords)

    def has_query(self, query: JobSearchQuery) -> bool:
        return self.query_key(query) in self.attempted_query_keys

    @property
    def reward_sample(self) -> str:
        if not self.rewarded_keywords:
            return "No keywords have produced results yet."
        return "\n".join(f"- {keyword}" for keyword in self.rewarded_keywords[-10:])

    @property
    def penalty_sample(self) -> str:
        if not self.penalized_keywords:
            return "None so far."
        return "\n".join(f"- {keyword}" for keyword in self.penalized_keywords[-10:])


@dataclass
class _QueryRunOutcome:
    scored_query: ScoredQuery
    results_returned: int = 0
    fresh_jobs_accepted: int = 0
    skipped_existing: int = 0
    skipped_blacklisted: int = 0
    skipped_workplace_type: int = 0
    skipped_experience_level: int = 0

    @property
    def query(self) -> JobSearchQuery:
        return self.scored_query.query

    def to_query_outcome(self) -> QueryOutcome:
        return QueryOutcome(
            query=self.query,
            profile_match=self.scored_query.profile_match,
            query_score=self.scored_query.score,
            results_returned=self.results_returned,
            fresh_jobs_accepted=self.fresh_jobs_accepted,
            skipped_existing=self.skipped_existing,
            skipped_blacklisted=self.skipped_blacklisted,
            skipped_workplace_type=self.skipped_workplace_type,
            skipped_experience_level=self.skipped_experience_level,
            resumes_generated=0,
            average_ats_score=None,
            artifact_mode="application-seed",
        )


class MatchingJobsWorkflow:
    def __init__(
        self,
        *,
        service: JobSearchService,
        planner_llm: Any,
    ) -> None:
        self._service = service
        self._planner_llm = planner_llm

    async def run(
        self,
        *,
        profile_dir: Path = DEFAULT_PROFILE_DIR,
        blacklist_path: Path = DEFAULT_BLACKLIST_PATH,
        output_dir: Path = DEFAULT_OUTPUT_DIR,
        master_resume_name: str = DEFAULT_MASTER_RESUME_NAME,
        location: str = "United States",
        date_posted: DatePosted = "past_week",
        limit_per_query: int = 10,
        max_queries: int = 6,
        max_jobs: int = 10,
        progress_callback: ProgressCallback | None = None,
    ) -> MatchingJobsWorkflowResult:
        database_path = output_dir / APPLICATION_DATABASE
        master_resume_path = profile_dir / master_resume_name
        profile_context = _master_resume_search_context(master_resume_path)
        blacklist = CompanyBlacklist.from_file(blacklist_path)
        existing_job_ids = fetch_application_job_ids(database_path)
        query_history = load_query_outcomes(database_path)
        search_memory = _SearchMemory()

        seeded: list[SeededApplication] = []
        skipped_blacklisted: list[str] = []
        skipped_existing: list[str] = []
        skipped_workplace_type: list[str] = []
        skipped_experience_level: list[str] = []
        errors: list[str] = []
        query_run_outcomes: list[_QueryRunOutcome] = []
        all_search_queries: list[JobSearchQuery] = []
        seen_job_ids: set[str] = set()
        jobs_found = 0
        min_searches_before_stop = min(max(max_queries, 1), MIN_SEARCHES_BEFORE_STOP)

        while len(seeded) < max_jobs or search_memory.total_searches < min_searches_before_stop:
            planned_queries = await _planned_search_queries(
                planner_llm=self._planner_llm,
                profile_context=profile_context,
                location=location,
                date_posted=date_posted,
                limit_per_query=limit_per_query,
                max_queries=max_queries,
                search_memory=search_memory,
            )
            historical_queries = historical_query_candidates(
                query_history,
                location=location,
                date_posted=date_posted,
                limit_per_query=limit_per_query,
            )
            ranked_queries = rank_search_queries(
                [*planned_queries, *historical_queries],
                profile_context=profile_context,
                history=query_history,
                max_queries=max_queries,
            )
            ranked_queries = [
                query for query in ranked_queries if not search_memory.has_query(query.query)
            ]
            if not ranked_queries:
                break

            for scored_query in ranked_queries:
                outcome = _QueryRunOutcome(scored_query=scored_query)
                query_run_outcomes.append(outcome)
                all_search_queries.append(scored_query.query)
                _progress(
                    progress_callback,
                    f"Searching LinkedIn: {scored_query.query.keywords}",
                )
                result = await self._service.search(scored_query.query)
                jobs_found += result.count
                outcome.results_returned = result.count
                search_memory.register_result(scored_query.query, result.count)
                for posting in result.jobs:
                    if len(seeded) >= max_jobs:
                        break
                    if posting.job_id in seen_job_ids:
                        continue
                    seen_job_ids.add(posting.job_id)
                    if posting.job_id in existing_job_ids:
                        outcome.skipped_existing += 1
                        skipped_existing.append(_candidate_label(posting))
                        continue
                    try:
                        details = await self._fetch_details(posting)
                    except Exception as exc:
                        errors.append(f"{posting.job_id}: {exc}")
                        continue
                    if blacklist.matches(details.company):
                        outcome.skipped_blacklisted += 1
                        skipped_blacklisted.append(_candidate_label(details))
                        continue
                    if not _is_remote_or_hybrid_job(details, scored_query.query):
                        outcome.skipped_workplace_type += 1
                        skipped_workplace_type.append(_candidate_label(details))
                        continue
                    if _is_disallowed_experience_level(details):
                        outcome.skipped_experience_level += 1
                        skipped_experience_level.append(_candidate_label(details))
                        continue
                    raw_description = usable_job_description(details.description)
                    if raw_description is None:
                        errors.append(f"{details.job_id}: no usable public job description")
                        continue

                    details = details.model_copy(update={"description": raw_description})
                    prompt_description = job_description_context(details)
                    upsert_application_artifact(
                        database_path=database_path,
                        job_id=details.job_id,
                        company=details.company or "",
                        job_title=details.title or "Unknown title",
                        linkedin_url=str(details.job_url or ""),
                        resume_path=None,
                        cover_letter_path=None,
                        job_description=raw_description,
                        prompt_job_description=prompt_description,
                        date_posted=_job_date_posted(details),
                        experience_level=details.seniority_level,
                    )
                    existing_job_ids.add(details.job_id)
                    outcome.fresh_jobs_accepted += 1
                    seeded.append(
                        SeededApplication(
                            job_id=details.job_id,
                            company=details.company,
                            title=details.title,
                            linkedin_url=str(details.job_url) if details.job_url else None,
                            prompt_job_description_chars=len(prompt_description),
                        )
                    )
                    _progress(
                        progress_callback,
                        f"Seeded application row: {details.job_id} {details.company or ''}",
                    )

                if (
                    len(seeded) >= max_jobs
                    and search_memory.total_searches >= min_searches_before_stop
                ):
                    break

            if not ranked_queries:
                break

        for outcome in query_run_outcomes:
            record_query_outcome(database_path, outcome.to_query_outcome())

        return MatchingJobsWorkflowResult(
            master_resume_path=str(master_resume_path),
            database_path=str(database_path),
            search_queries=all_search_queries,
            jobs_found=jobs_found,
            jobs_seeded=len(seeded),
            skipped_blacklisted=skipped_blacklisted,
            skipped_existing=skipped_existing,
            skipped_workplace_type=skipped_workplace_type,
            skipped_experience_level=skipped_experience_level,
            errors=errors,
            seeded_applications=seeded,
        )

    async def _fetch_details(self, posting: JobPosting) -> JobDetails:
        lookup = str(posting.job_url or posting.job_id)
        details = await self._service.get_details(lookup)
        return details.model_copy(
            update={
                "job_id": details.job_id or posting.job_id,
                "title": details.title if details.title != "Unknown title" else posting.title,
                "company": details.company or posting.company,
                "location": details.location or posting.location,
                "listed_at": details.listed_at or posting.listed_at,
                "posted_text": details.posted_text or posting.posted_text,
                "job_url": details.job_url or posting.job_url,
                "company_url": details.company_url or posting.company_url,
                "workplace_type": details.workplace_type or posting.workplace_type,
                "source": details.source or posting.source,
            },
        )


async def _planned_search_queries(
    *,
    planner_llm: Any,
    profile_context: str,
    location: str,
    date_posted: DatePosted,
    limit_per_query: int,
    max_queries: int,
    search_memory: _SearchMemory,
) -> list[JobSearchQuery]:
    prompt = _search_query_prompt(
        profile_context=profile_context,
        location=location,
        date_posted=date_posted,
        limit_per_query=limit_per_query,
        max_queries=max_queries,
        search_memory=search_memory,
    )
    try:
        response = await planner_llm.generate_json(prompt)
    except Exception:
        response = {}
    raw_queries = response.get("queries") if isinstance(response, dict) else response
    queries: list[JobSearchQuery] = []
    if isinstance(raw_queries, list):
        for item in raw_queries:
            if not isinstance(item, dict):
                continue
            try:
                queries.append(
                    _coerce_search_query(
                        item,
                        location=location,
                        date_posted=date_posted,
                        limit_per_query=limit_per_query,
                    )
                )
            except WorkflowError:
                continue
    queries = _supplement_search_queries(
        queries,
        location=location,
        date_posted=date_posted,
        limit_per_query=limit_per_query,
    )
    return _expand_remote_and_hybrid_queries(queries, max_queries=max_queries)


def _master_resume_search_context(master_resume_path: Path) -> str:
    if not master_resume_path.exists():
        raise WorkflowError(f"Master resume YAML was not found: {master_resume_path}")
    parsed = yaml.safe_load(master_resume_path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise WorkflowError(f"Master resume YAML is not a mapping: {master_resume_path}")
    sections: list[str] = []
    summary = parsed.get("professional_summary")
    if isinstance(summary, dict):
        text = str(summary.get("text") or "").strip()
        if text:
            sections.append(f"Professional Summary:\n{text}")

    core_skills = parsed.get("core_technical_skills")
    skill_lines: list[str] = []
    buckets = core_skills.get("bullet_points") if isinstance(core_skills, dict) else []
    if isinstance(buckets, list):
        for bucket in buckets:
            if not isinstance(bucket, dict):
                continue
            category = str(bucket.get("category") or "").strip()
            items = bucket.get("items")
            terms: list[str] = []
            if isinstance(items, dict):
                terms.extend(_string_list(items.get("primary")))
                terms.extend(_string_list(items.get("additional")))
            if category and terms:
                skill_lines.append(f"- {category}: {', '.join(_dedupe_preserve_order(terms))}")
    if skill_lines:
        sections.append("Core Technical Skills:\n" + "\n".join(skill_lines))

    experience = parsed.get("professional_experience")
    jobs = experience.get("jobs") if isinstance(experience, dict) else []
    bullet_lines: list[str] = []
    if isinstance(jobs, list):
        for job in jobs:
            if not isinstance(job, dict):
                continue
            title = str(job.get("title") or "").strip()
            company = str(job.get("company") or "").strip()
            bullets = job.get("bullet_points")
            if title or company:
                bullet_lines.append(f"{company} {title}".strip())
            if isinstance(bullets, list):
                for bullet in bullets[:8]:
                    if isinstance(bullet, dict):
                        text = str(bullet.get("text") or "").strip()
                    else:
                        text = str(bullet or "").strip()
                    if text:
                        bullet_lines.append(f"- {text}")
    if bullet_lines:
        sections.append("Experience Evidence:\n" + "\n".join(bullet_lines[:80]))
    return "\n\n".join(sections)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


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
        "experience_level": _coerce_search_experience_level(value.get("experience_level")),
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


def _coerce_search_experience_level(value: Any) -> str | None:
    normalized = _normalize_experience_level(value)
    if not normalized or normalized in DISALLOWED_EXPERIENCE_LEVELS:
        return None
    return normalized


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
    search_memory: _SearchMemory,
) -> str:
    feedback_section = ""
    if search_memory.total_searches > 0:
        feedback_section = f"""
Search feedback from previous iterations:

Keyword strings that returned jobs:
{search_memory.reward_sample}

Keyword strings that returned zero jobs:
{search_memory.penalty_sample}

Use this feedback to generate fresh, non-duplicate keyword combinations.
Prefer short, general keyword strings over long, specific ones.
"""

    return f"""
You generate LinkedIn public job search parameters from a candidate's master resume object.
Return only valid JSON. Do not include commentary.
{feedback_section}
Rules:
- Generate up to {max_queries} keyword-focused query objects.
- Use combinations of role titles, seniority, domain keywords, and core skills.
- The workflow will force remote and hybrid LinkedIn workplace filters.
- Do not use internship or entry_level experience filters.
- Prefer concise keyword strings LinkedIn search can use directly.
- Include AI, agentic AI, and LLM keyword variants when they overlap with the profile.
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
- experience_level: {", ".join(SEARCH_EXPERIENCE_LEVELS)}
- sort_by: relevance, recent

Master resume object summary:
{profile_context}
""".strip()


def _is_remote_or_hybrid_job(job: JobDetails, query: JobSearchQuery) -> bool:
    workplace_context = " ".join(
        value for value in (job.workplace_type, job.location) if value
    ).casefold()
    compact_context = re.sub(r"[\s-]+", "", workplace_context)
    if "onsite" in compact_context:
        return False
    if "remote" in workplace_context or "hybrid" in workplace_context:
        return True
    return query.workplace_type in {"remote", "hybrid"}


def _is_disallowed_experience_level(job: JobDetails) -> bool:
    normalized = _normalize_experience_level(job.seniority_level)
    return normalized in DISALLOWED_EXPERIENCE_LEVELS


def _normalize_experience_level(value: Any) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(value or "").casefold()).strip("_")
    if normalized in {"intern", "internship"}:
        return "internship"
    if normalized in {"entry", "entry_level", "entrylevel"}:
        return "entry_level"
    if normalized.startswith("entry_level"):
        return "entry_level"
    return normalized


def _job_date_posted(job: JobDetails) -> str | None:
    return _posted_date_value(job.listed_at) or _posted_date_value(job.posted_text)


def _posted_date_value(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    date_match = re.match(r"^\d{4}-\d{2}-\d{2}", text)
    if date_match:
        return date_match.group(0)
    return text


def _candidate_label(job: JobDetails | JobPosting) -> str:
    company = f"{job.company} - " if job.company else ""
    return f"{job.job_id}: {company}{job.title}"


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


def _progress(callback: ProgressCallback | None, message: str) -> None:
    if callback is not None:
        callback(message)


def _stderr_progress(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


async def run_from_cli(
    args: argparse.Namespace,
    *,
    settings: Settings | None = None,
    progress_callback: ProgressCallback | None = None,
) -> MatchingJobsWorkflowResult:
    settings = settings or load_settings()
    provider = LinkedInPublicJobsProvider(
        user_agent=settings.user_agent,
        timeout_seconds=settings.timeout_seconds,
    )
    service = JobSearchService(provider=provider, max_results=settings.max_results)
    planner_llm = build_llm_client(settings)
    if settings.llm_provider.casefold().strip() == "api":
        planner_llm = build_planner_llm_client(settings, planner_llm)
    workflow = MatchingJobsWorkflow(service=service, planner_llm=planner_llm)
    try:
        return await workflow.run(
            profile_dir=Path(args.profile_dir),
            blacklist_path=Path(args.blacklist_path),
            output_dir=Path(args.output_dir),
            master_resume_name=args.master_resume_name,
            location=args.location,
            date_posted=args.date_posted,
            limit_per_query=args.limit_per_query,
            max_queries=args.max_queries,
            max_jobs=args.max_jobs,
            progress_callback=progress_callback or _stderr_progress,
        )
    finally:
        await provider.aclose()
        await planner_llm.aclose()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Search public LinkedIn jobs and seed application rows with trimmed JODs."
    )
    parser.add_argument("--profile-dir", default=str(DEFAULT_PROFILE_DIR))
    parser.add_argument("--blacklist-path", default=str(DEFAULT_BLACKLIST_PATH))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--master-resume-name", default=DEFAULT_MASTER_RESUME_NAME)
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
    args = parser.parse_args()
    settings = load_settings()
    print(f"LLM: {workflow_llm_settings_label(settings)}", file=sys.stderr, flush=True)
    result = asyncio.run(run_from_cli(args, settings=settings))
    print(json.dumps(result.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    main()
