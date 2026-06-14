from __future__ import annotations

import pytest

from linkedin_career_mcp.errors import ProviderError
from linkedin_career_mcp.generic_job_scraper import (
    extract_generic_job_details_from_html,
    generic_job_id,
    normalize_job_url,
)


def test_extract_generic_job_details_prefers_schema_org_jobposting():
    description = (
        "Build reliable Python services, own API design, mentor engineers, and operate "
        "production systems with strong observability and incident response practices."
    )
    html = f"""
    <html>
      <head>
        <script type="application/ld+json">
          {{
            "@context": "https://schema.org",
            "@type": "JobPosting",
            "title": "Senior Platform Engineer",
            "datePosted": "2026-06-14",
            "description": "<p>{description}</p>",
            "employmentType": ["FULL_TIME"],
            "jobLocationType": "TELECOMMUTE",
            "occupationalCategory": "Software Engineering",
            "industry": "Cloud Infrastructure",
            "hiringOrganization": {{
              "@type": "Organization",
              "name": "Example Systems",
              "sameAs": "https://example.com"
            }},
            "jobLocation": {{
              "@type": "Place",
              "address": {{
                "@type": "PostalAddress",
                "addressLocality": "Chicago",
                "addressRegion": "IL",
                "addressCountry": "US"
              }}
            }}
          }}
        </script>
      </head>
      <body><main>Fallback text that should not win.</main></body>
    </html>
    """

    details = extract_generic_job_details_from_html(
        html=html,
        url="https://jobs.example.com/platform-engineer?utm_source=newsletter#apply",
    )

    assert details.job_id == generic_job_id("https://jobs.example.com/platform-engineer")
    assert details.title == "Senior Platform Engineer"
    assert details.company == "Example Systems"
    assert details.location == "Chicago, IL, US"
    assert details.listed_at == "2026-06-14"
    assert details.workplace_type == "TELECOMMUTE"
    assert details.employment_type == "FULL_TIME"
    assert details.job_function == "Software Engineering"
    assert details.industries == "Cloud Infrastructure"
    assert details.description == description


def test_extract_generic_job_details_falls_back_to_main_text():
    description = (
        "We need a staff engineer to design distributed systems, improve deployment "
        "automation, build secure APIs, lead incident response, and partner closely "
        "with product teams on platform reliability work."
    )
    html = f"""
    <html>
      <head>
        <title>Staff Software Engineer - Acme Careers</title>
        <meta property="og:title" content="Staff Software Engineer">
        <meta property="og:site_name" content="Acme Careers">
      </head>
      <body>
        <nav>Navigation</nav>
        <main>
          <h1>Staff Software Engineer</h1>
          <p>{description}</p>
        </main>
      </body>
    </html>
    """

    details = extract_generic_job_details_from_html(
        html=html,
        url="https://careers.acme.test/jobs/staff-software-engineer",
    )

    assert details.job_id == generic_job_id(
        "https://careers.acme.test/jobs/staff-software-engineer"
    )
    assert details.title == "Staff Software Engineer"
    assert details.company == "Acme Careers"
    assert "deployment automation" in details.description


def test_extract_generic_job_details_rejects_pages_without_usable_description():
    with pytest.raises(ProviderError, match="No usable job description"):
        extract_generic_job_details_from_html(
            html="<html><body><main>Too short.</main></body></html>",
            url="https://example.com/jobs/short",
        )


def test_normalize_job_url_strips_common_tracking_noise():
    assert normalize_job_url(
        "HTTPS://Jobs.Example.com/path/?utm_source=x&job=123&trk=public#apply"
    ) == "https://jobs.example.com/path?job=123"
