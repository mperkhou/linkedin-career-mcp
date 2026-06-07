from __future__ import annotations

import httpx
import pytest

from linkedin_career_mcp.errors import JobNotFoundError
from linkedin_career_mcp.providers.linkedin_public import (
    LinkedInPublicJobsProvider,
    _search_params,
    extract_job_id,
)

SEARCH_HTML = """
<li>
  <div class="base-card" data-entity-urn="urn:li:jobPosting:12345">
    <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/senior-python-engineer-at-acme-12345?trk=public_jobs">
      <span class="sr-only">View job</span>
    </a>
    <h3 class="base-search-card__title"> Senior Python Engineer </h3>
    <h4 class="base-search-card__subtitle">
      <a href="https://www.linkedin.com/company/acme?trk=public_jobs"> Acme Corp </a>
    </h4>
    <span class="job-search-card__location"> Chicago, IL </span>
    <time datetime="2026-06-05"> 1 day ago </time>
    <span class="job-search-card__metadata"> Remote </span>
  </div>
</li>
"""


DETAIL_HTML = """
<section>
  <h2 class="top-card-layout__title">Senior Python Engineer</h2>
  <a class="topcard__org-name-link" href="https://www.linkedin.com/company/acme">Acme Corp</a>
  <span class="topcard__flavor topcard__flavor--bullet">Chicago, IL</span>
  <time datetime="2026-06-05">1 day ago</time>
  <div class="show-more-less-html__markup">
    Build practical tools with Python.
  </div>
  <li class="description__job-criteria-item">
    <h3 class="description__job-criteria-subheader">Seniority level</h3>
    <span class="description__job-criteria-text">Mid-Senior level</span>
  </li>
  <li class="description__job-criteria-item">
    <h3 class="description__job-criteria-subheader">Employment type</h3>
    <span class="description__job-criteria-text">Full-time</span>
  </li>
</section>
"""


def test_search_params_map_public_linkedin_filters(sample_query):
    query = sample_query.model_copy(update={"exclude_job_ids": {"12345"}})
    params = _search_params(query)

    assert params["keywords"] == "software engineer"
    assert params["location"] == "Chicago, IL"
    assert params["f_TPR"] == "r604800"
    assert params["f_WT"] == "2"
    assert params["sortBy"] == "DD"
    assert params["start"] == 0
    assert "exclude_job_ids" not in params


@pytest.mark.asyncio
async def test_search_jobs_parses_public_job_cards(sample_query):
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["keywords"] == "software engineer"
        return httpx.Response(200, text=SEARCH_HTML)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = LinkedInPublicJobsProvider(client=client, user_agent="test", timeout_seconds=1)

    jobs = await provider.search_jobs(sample_query)

    assert len(jobs) == 1
    assert jobs[0].job_id == "12345"
    assert jobs[0].title == "Senior Python Engineer"
    assert jobs[0].company == "Acme Corp"
    assert jobs[0].location == "Chicago, IL"
    assert str(jobs[0].job_url) == (
        "https://www.linkedin.com/jobs/view/senior-python-engineer-at-acme-12345"
    )


@pytest.mark.asyncio
async def test_get_job_details_parses_public_detail_page():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/12345")
        return httpx.Response(200, text=DETAIL_HTML)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = LinkedInPublicJobsProvider(client=client, user_agent="test", timeout_seconds=1)

    details = await provider.get_job_details("https://www.linkedin.com/jobs/view/12345/")

    assert details.job_id == "12345"
    assert details.title == "Senior Python Engineer"
    assert details.description == "Build practical tools with Python."
    assert details.seniority_level == "Mid-Senior level"
    assert details.employment_type == "Full-time"


@pytest.mark.asyncio
async def test_get_job_raw_payload_returns_public_detail_html_and_parsed_details():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/12345")
        return httpx.Response(200, text=DETAIL_HTML, headers={"content-type": "text/html"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = LinkedInPublicJobsProvider(client=client, user_agent="test", timeout_seconds=1)

    payload = await provider.get_job_raw_payload("https://www.linkedin.com/jobs/view/12345/")

    assert payload.job_id == "12345"
    assert str(payload.detail_url) == "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/12345"
    assert payload.status_code == 200
    assert payload.content_type == "text/html"
    assert payload.payload_type == "html"
    assert payload.payload_chars == len(DETAIL_HTML)
    assert "show-more-less-html__markup" in payload.payload
    assert payload.parsed.description == "Build practical tools with Python."


@pytest.mark.asyncio
async def test_get_job_details_rejects_unparseable_ids():
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200)))
    provider = LinkedInPublicJobsProvider(client=client, user_agent="test", timeout_seconds=1)

    with pytest.raises(JobNotFoundError):
        await provider.get_job_details("not a linkedin job")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("12345", "12345"),
        ("https://www.linkedin.com/jobs/view/12345/", "12345"),
        (
            "https://www.linkedin.com/jobs/view/software-engineer-new-grad-at-notion-4406118990",
            "4406118990",
        ),
        ("urn:li:jobPosting:67890", "67890"),
        ("https://www.linkedin.com/jobs/search/?currentJobId=24680", "24680"),
    ],
)
def test_extract_job_id(value, expected):
    assert extract_job_id(value) == expected
