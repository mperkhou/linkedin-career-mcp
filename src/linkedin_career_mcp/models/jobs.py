from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

DatePosted = Literal["any_time", "past_24_hours", "past_week", "past_month"]
JobType = Literal[
    "full_time",
    "part_time",
    "contract",
    "temporary",
    "volunteer",
    "internship",
    "other",
]
WorkplaceType = Literal["on_site", "remote", "hybrid"]
ExperienceLevel = Literal[
    "internship",
    "entry_level",
    "associate",
    "mid_senior",
    "director",
    "executive",
]
SortBy = Literal["relevance", "recent"]


class JobSearchQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keywords: str = Field(min_length=1, description="Job title or keywords to search for.")
    location: str = Field(min_length=1, description="Location to search in.")
    date_posted: DatePosted = "any_time"
    job_type: JobType | None = None
    workplace_type: WorkplaceType | None = None
    experience_level: ExperienceLevel | None = None
    sort_by: SortBy = "recent"
    distance: int | None = Field(default=None, ge=0, le=100)
    limit: int = Field(default=10, ge=1, le=100)
    page: int = Field(default=0, ge=0)
    exclude_job_ids: set[str] = Field(
        default_factory=set,
        description="LinkedIn job IDs to filter out of returned search results.",
    )


class JobPosting(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    title: str
    company: str | None = None
    location: str | None = None
    listed_at: str | None = None
    posted_text: str | None = None
    job_url: HttpUrl | None = None
    company_url: HttpUrl | None = None
    workplace_type: str | None = None
    source: str = "linkedin_public"


class JobSearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: JobSearchQuery
    count: int
    jobs: list[JobPosting]
    provider: str = "linkedin_public"


class JobDetails(JobPosting):
    description: str | None = None
    seniority_level: str | None = None
    employment_type: str | None = None
    job_function: str | None = None
    industries: str | None = None


class JobRawPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    detail_url: HttpUrl
    status_code: int
    content_type: str | None = None
    payload_type: str = "html"
    payload_chars: int
    payload: str
    parsed: JobDetails
