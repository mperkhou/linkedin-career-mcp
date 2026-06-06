from __future__ import annotations

import re
from collections.abc import Mapping
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
from bs4 import BeautifulSoup

from linkedin_career_mcp.errors import JobNotFoundError, ProviderError
from linkedin_career_mcp.models import JobDetails, JobPosting, JobSearchQuery

SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
LINKEDIN_JOB_URL = "https://www.linkedin.com/jobs/view/{job_id}"

DATE_POSTED_FILTERS = {
    "past_24_hours": "r86400",
    "past_week": "r604800",
    "past_month": "r2592000",
}
JOB_TYPE_FILTERS = {
    "full_time": "F",
    "part_time": "P",
    "contract": "C",
    "temporary": "T",
    "volunteer": "V",
    "internship": "I",
    "other": "O",
}
WORKPLACE_FILTERS = {
    "on_site": "1",
    "remote": "2",
    "hybrid": "3",
}
EXPERIENCE_FILTERS = {
    "internship": "1",
    "entry_level": "2",
    "associate": "3",
    "mid_senior": "4",
    "director": "5",
    "executive": "6",
}
SORT_FILTERS = {
    "relevance": "R",
    "recent": "DD",
}


class LinkedInPublicJobsProvider:
    name = "linkedin_public"

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        user_agent: str,
        timeout_seconds: float,
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )

    async def search_jobs(self, query: JobSearchQuery) -> list[JobPosting]:
        params = _search_params(query)
        try:
            response = await self._client.get(SEARCH_URL, params=params)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderError(f"LinkedIn public job search failed: {exc}") from exc

        return _parse_search_results(response.text)

    async def get_job_details(self, job_id_or_url: str) -> JobDetails:
        job_id = extract_job_id(job_id_or_url)
        if not job_id:
            raise JobNotFoundError("Provide a LinkedIn job ID or a LinkedIn job URL.")

        try:
            response = await self._client.get(DETAIL_URL.format(job_id=job_id))
            if response.status_code == 404:
                raise JobNotFoundError(f"LinkedIn job {job_id} was not found.")
            response.raise_for_status()
        except JobNotFoundError:
            raise
        except httpx.HTTPError as exc:
            raise ProviderError(f"LinkedIn public job detail lookup failed: {exc}") from exc

        return _parse_job_details(response.text, job_id)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


def _search_params(query: JobSearchQuery) -> dict[str, str | int]:
    params: dict[str, str | int] = {
        "keywords": query.keywords,
        "location": query.location,
        "start": query.page * query.limit,
        "sortBy": SORT_FILTERS[query.sort_by],
    }

    if query.date_posted != "any_time":
        params["f_TPR"] = DATE_POSTED_FILTERS[query.date_posted]
    if query.job_type:
        params["f_JT"] = JOB_TYPE_FILTERS[query.job_type]
    if query.workplace_type:
        params["f_WT"] = WORKPLACE_FILTERS[query.workplace_type]
    if query.experience_level:
        params["f_E"] = EXPERIENCE_FILTERS[query.experience_level]
    if query.distance is not None:
        params["distance"] = query.distance

    return params


def _parse_search_results(html: str) -> list[JobPosting]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("li")
    jobs: list[JobPosting] = []

    for card in cards:
        job_id = _extract_card_job_id(card.attrs)
        title_node = card.select_one(".base-search-card__title")
        company_node = card.select_one(".base-search-card__subtitle")
        location_node = card.select_one(".job-search-card__location")
        link_node = card.select_one("a.base-card__full-link, a[href*='/jobs/view/']")
        date_node = card.select_one("time")
        metadata_node = card.select_one(".job-search-card__metadata")

        href = _clean_url(link_node.get("href")) if link_node else None
        job_id = job_id or extract_job_id(href or "")
        if not job_id:
            continue

        jobs.append(
            JobPosting(
                job_id=job_id,
                title=_text(title_node) or "Unknown title",
                company=_text(company_node),
                location=_text(location_node),
                listed_at=date_node.get("datetime") if date_node else None,
                posted_text=_text(date_node),
                job_url=href or LINKEDIN_JOB_URL.format(job_id=job_id),
                company_url=_clean_url(company_node.get("href")) if company_node else None,
                workplace_type=_text(metadata_node),
            )
        )

    return jobs


def _parse_job_details(html: str, job_id: str) -> JobDetails:
    soup = BeautifulSoup(html, "html.parser")

    title = _text(soup.select_one(".top-card-layout__title, h2")) or "Unknown title"
    company_node = soup.select_one(".topcard__org-name-link, .topcard__flavor")
    location_node = soup.select_one(".topcard__flavor--bullet")
    date_node = soup.select_one("time")
    description_node = soup.select_one(".show-more-less-html__markup")

    criteria = _parse_criteria(soup)

    return JobDetails(
        job_id=job_id,
        title=title,
        company=_text(company_node),
        location=_text(location_node),
        listed_at=date_node.get("datetime") if date_node else None,
        posted_text=_text(date_node),
        job_url=LINKEDIN_JOB_URL.format(job_id=job_id),
        company_url=_clean_url(company_node.get("href")) if company_node else None,
        description=_text(description_node),
        seniority_level=criteria.get("Seniority level"),
        employment_type=criteria.get("Employment type"),
        job_function=criteria.get("Job function"),
        industries=criteria.get("Industries"),
    )


def _parse_criteria(soup: BeautifulSoup) -> dict[str, str]:
    criteria: dict[str, str] = {}
    for item in soup.select(".description__job-criteria-item"):
        label = _text(item.select_one(".description__job-criteria-subheader"))
        value = _text(item.select_one(".description__job-criteria-text"))
        if label and value:
            criteria[label] = value
    return criteria


def extract_job_id(value: str) -> str | None:
    if not value:
        return None

    if value.isdigit():
        return value

    parsed = urlparse(value)
    query = parse_qs(parsed.query)
    for key in ("currentJobId", "jobId"):
        if query.get(key):
            return query[key][0]

    patterns = (
        r"/jobs/view/(\d+)",
        r"jobPosting:(\d+)",
        r"[?&]jk=(\d+)",
    )
    for pattern in patterns:
        match = re.search(pattern, value)
        if match:
            return match.group(1)

    return None


def _extract_card_job_id(attrs: Mapping[str, object]) -> str | None:
    for key in ("data-entity-urn", "data-id", "data-job-id"):
        value = attrs.get(key)
        if isinstance(value, str):
            job_id = extract_job_id(value)
            if job_id:
                return job_id
    return None


def _text(node: object | None) -> str | None:
    if node is None or not hasattr(node, "get_text"):
        return None
    text = node.get_text(" ", strip=True)
    return " ".join(text.split()) or None


def _clean_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url.strip())
    if not parsed.scheme:
        return None
    query = {
        key: value
        for key, value in parse_qs(parsed.query).items()
        if not key.lower().startswith(("trk", "refid"))
    }
    return parsed._replace(query=urlencode(query, doseq=True)).geturl()
