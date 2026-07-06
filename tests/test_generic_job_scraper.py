from __future__ import annotations

import html as html_module
import json

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


def test_extract_generic_job_details_infers_greenhouse_company_from_page_title():
    description = (
        "LTS is seeking a principal platform engineer to build AI-native platform "
        "systems on commercial AWS, design distributed services, improve observability, "
        "and operate high-leverage production workflows with a small senior team."
    )
    html = f"""
    <html>
      <head>
        <title>Job Application for Principal Platform Engineer at LTS</title>
        <meta property="og:title" content="Principal Platform Engineer">
      </head>
      <body>
        <main>
          <h1>Principal Platform Engineer</h1>
          <p>{description}</p>
        </main>
      </body>
    </html>
    """

    details = extract_generic_job_details_from_html(
        html=html,
        url="https://job-boards.greenhouse.io/lts/jobs/4284753009",
    )

    assert details.title == "Principal Platform Engineer"
    assert details.company == "LTS"
    assert "commercial AWS" in details.description


def test_extract_generic_job_details_reads_dayforce_next_data():
    description = (
        "<h1>About the Opportunity</h1>"
        "<p>Build a scalable AI platform for developing, deploying, and maintaining "
        "LLM applications, autonomous agents, RAG pipelines, vector databases, and "
        "multimodal systems in a secure cloud environment.</p>"
    )
    payload = {
        "props": {
            "pageProps": {
                "dehydratedState": {
                    "queries": [
                        {
                            "state": {
                                "data": {
                                    "candidateCorrespondenceClientName": "Dayforce",
                                }
                            }
                        }
                    ]
                },
                "jobData": {
                    "jobPostingId": 98352,
                    "jobTitle": "AI Platform Developer, Sr.",
                    "postingStartTimestampUTC": "2026-06-23T05:00:00+00:00",
                    "postingLocations": [
                        {
                            "formattedAddress": "United States",
                            "isoCountryCode": "US",
                        }
                    ],
                    "jobPostingContent": {
                        "jobDescription": description,
                    },
                },
            }
        }
    }
    html = f"""
    <html>
      <head>
        <title>Job Details | Dayforce Jobs</title>
      </head>
      <body>
        <main>Job Details | Dayforce Jobs Sign In</main>
        <script id="__NEXT_DATA__" type="application/json">
          {json.dumps(payload)}
        </script>
      </body>
    </html>
    """

    details = extract_generic_job_details_from_html(
        html=html,
        url="https://jobs.dayforcehcm.com/en-US/mydayforce/alljobs/jobs/98352",
    )

    assert details.job_id == generic_job_id(
        "https://jobs.dayforcehcm.com/en-US/mydayforce/alljobs/jobs/98352"
    )
    assert details.title == "AI Platform Developer, Sr."
    assert details.company == "Dayforce"
    assert details.location == "United States"
    assert details.listed_at == "2026-06-23"
    assert "autonomous agents" in details.description
    assert "Job Details | Dayforce Jobs Sign In" not in details.description


def test_extract_generic_job_details_reads_workatastartup_inertia_data():
    description = (
        "<p>Emergent builds autonomous coding agents that generate, test, debug, "
        "and deploy production applications from plain-language intent.</p>"
        "<p>Own distributed systems, agent runtime infrastructure, observability, "
        "fault tolerance, validation, and correctness for millions of applications.</p>"
    )
    payload = {
        "component": "jobs/public/pages/JobDetailPage",
        "props": {
            "job": {
                "id": 97648,
                "title": "Staff Engineer ",
                "location": "Bangalore",
                "jobType": "Full-time",
                "minExperience": "8+ years",
                "descriptionHtml": description,
            },
            "company": {
                "name": "Emergent",
                "industry": "Consumer",
                "url": "https://emergent.sh",
            },
        },
    }
    data_page = html_module.escape(json.dumps(payload), quote=True)
    html = f"""
    <html>
      <head>
        <title>Staff Engineer at Emergent | Y Combinator's Work at a Startup</title>
      </head>
      <body>
        <div id="app" data-page="{data_page}"></div>
      </body>
    </html>
    """

    details = extract_generic_job_details_from_html(
        html=html,
        url="https://www.workatastartup.com/jobs/97648",
    )

    assert details.title == "Staff Engineer"
    assert details.company == "Emergent"
    assert str(details.company_url).rstrip("/") == "https://emergent.sh"
    assert details.location == "Bangalore"
    assert details.employment_type == "Full-time"
    assert details.seniority_level == "8+ years"
    assert details.industries == "Consumer"
    assert "agent runtime infrastructure" in details.description


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
