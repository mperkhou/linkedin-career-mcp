import os
import sqlite3
import threading
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import pytest
import yaml
from bs4 import BeautifulSoup
from reportlab.pdfgen import canvas

from linkedin_career_mcp import webapp
from linkedin_career_mcp.models import JobDetails
from linkedin_career_mcp.webapp import create_app

MANUAL_PASS_PROFILE_CHOICES = [
    ("economy", "Economy — Terra / High"),
    ("regular", "Regular — Sol / High (Recommended)"),
    ("premium", "Premium — Sol / X-High"),
]


def _assert_manual_pass_profile_select(select) -> None:
    assert select is not None
    assert select["name"] == "manual_pass_profile"
    assert select.has_attr("disabled")
    options = select.find_all("option")
    assert [
        (option["value"], option.get_text(" ", strip=True)) for option in options
    ] == MANUAL_PASS_PROFILE_CHOICES
    selected = [option["value"] for option in options if option.has_attr("selected")]
    assert selected == ["regular"]


def test_connect_database_migrates_job_description_columns(tmp_path: Path):
    database_path = tmp_path / "applications.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE applications (
                job_id TEXT PRIMARY KEY,
                company TEXT NOT NULL,
                job_title TEXT NOT NULL,
                linkedin_url TEXT NOT NULL,
                resume_filename TEXT NOT NULL,
                resume_content BLOB,
                resume_mime_type TEXT NOT NULL DEFAULT 'application/pdf',
                source_resume_path TEXT NOT NULL,
                applied_to TEXT NOT NULL DEFAULT 'No',
                date_applied TEXT,
                notes TEXT NOT NULL DEFAULT '',
                imported_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO applications (
                job_id, company, job_title, linkedin_url, resume_filename,
                source_resume_path, applied_to, imported_at, updated_at
            )
            VALUES (
                '123', 'Example Co', 'Senior Engineer',
                'https://www.linkedin.com/jobs/view/123', 'resume.pdf',
                '', 'No',
                '2026-06-08T10:00:00+00:00',
                '2026-06-08T10:00:00+00:00'
            )
            """
        )
        connection.commit()

    with webapp.connect_database(database_path) as connection:
        rows = connection.execute("PRAGMA table_info(applications)").fetchall()

    columns = {row["name"] for row in rows}
    assert "job_description" in columns
    assert "prompt_job_description" in columns
    assert "archived_at" in columns
    assert "application_resume_object" in columns
    assert "application_resume_updated_at" in columns
    assert "application_resume_backup_object" in columns
    assert "application_resume_backup_created_at" in columns
    assert "resume_html_filename" in columns
    assert "resume_html_content" in columns
    assert "resume_html_mime_type" in columns
    assert "source_resume_html_path" in columns
    assert "resume_html_updated_at" in columns
    assert "resume_updated_at" in columns
    assert "cover_letter_object" in columns
    assert "cover_letter_object_updated_at" in columns
    assert "cover_letter_filename" in columns
    assert "cover_letter_content" in columns
    assert "source_cover_letter_path" in columns
    assert "cover_letter_updated_at" in columns
    assert "date_matched" in columns
    assert "date_posted" in columns
    assert "experience_level" in columns
    assert "ats_score" in columns
    assert "ats_parsing_score" in columns
    assert "ats_keyword_score" in columns
    assert "ats_semantic_score" in columns
    assert "ats_formatting_risk" in columns
    assert "ats_missing_terms" in columns
    assert "selected_resume_variant" in columns
    assert "resume_variant_selection_mode" in columns
    with webapp.connect_database(database_path) as connection:
        variant_table = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name = 'application_resume_variants'
            """
        ).fetchone()
    assert variant_table is not None
    with webapp.connect_database(database_path) as connection:
        row = connection.execute(
            """
            SELECT date_matched, date_posted, archived_at, selected_resume_variant,
                   resume_variant_selection_mode
            FROM applications
            WHERE job_id = '123'
            """
        ).fetchone()
    assert row["date_matched"] == "2026-06-08T10:00:00+00:00"
    assert row["date_posted"] is None
    assert row["archived_at"] is None
    assert row["selected_resume_variant"] == "v1"
    assert row["resume_variant_selection_mode"] == "auto"


def test_index_shows_database_backed_actions_and_links(tmp_path: Path, monkeypatch):
    output_dir = tmp_path / "output"
    database_path = output_dir / "tracking/applications.sqlite3"
    resume_pdf = _pdf_bytes(
        """
        Max Perkhounkov
        Professional Summary
        Core Technical Skills
        Python AWS APIs observability
        Professional Experience
        Built Python APIs on AWS with observability.
        Education
        Certifications
        """
    )
    webapp.upsert_application_artifact(
        database_path=database_path,
        job_id="123",
        company="Example Co",
        job_title="Senior Engineer",
        linkedin_url="https://www.linkedin.com/jobs/view/123",
        resume_path=None,
        cover_letter_path=None,
        job_description="Full parsed JOD with mission boilerplate and role requirements.",
        prompt_job_description="Clean prompt JOD with role requirements.",
        date_posted="2026-06-07T12:00:00Z",
        experience_level="Mid-Senior level",
    )
    webapp.store_application_resume_first_draft(
        database_path=database_path,
        job_id="123",
        application_resume_object="schema_version: test\n",
        resume_html="<html><body><h1>First Draft Resume</h1></body></html>",
        resume_pdf=resume_pdf,
    )
    with webapp.connect_database(database_path) as connection:
        connection.execute(
            """
            UPDATE applications
            SET notes = 'Manual second pass 2026-07-01: refreshed artifacts.'
            WHERE job_id = '123'
            """
        )
        connection.commit()
    with webapp.connect_database(database_path) as connection:
        score_row = connection.execute(
            """
            SELECT ats_score, ats_parsing_score, ats_keyword_score,
                   ats_semantic_score, ats_formatting_risk, ats_missing_terms,
                   experience_level, resume_updated_at, cover_letter_updated_at
            FROM applications
            WHERE job_id = '123'
            """
        ).fetchone()
    assert score_row["ats_score"] is not None
    assert score_row["ats_formatting_risk"] in {"Low", "Medium", "High"}
    assert score_row["ats_missing_terms"] is not None
    assert score_row["experience_level"] == "Mid-Senior level"
    assert score_row["resume_updated_at"] is not None
    assert score_row["cover_letter_updated_at"] is None

    app = create_app(database_path=database_path, output_dir=output_dir)
    client = app.test_client()

    index = client.get("/")
    assert index.status_code == 200
    html = index.data.decode()
    assert b"/descriptions/123" in index.data
    assert b"Compare descriptions" in index.data
    assert b'href="https://www.linkedin.com/jobs/view/123"' in index.data
    assert b'href="/linkedin/123"' not in index.data
    assert b"Cover Letter" in index.data
    assert b"/cover-letters/123/edit" in index.data
    assert 'action="/resumes/123/copy-to-downloads"' in html
    assert 'action="/cover-letters/123/copy-to-downloads"' not in html
    assert 'id="actions-form"' in html
    assert 'action="/actions/run"' in html
    assert 'id="archive-filter"' in html
    assert 'id="archive-selected"' in html
    assert 'id="unarchive-selected"' not in html
    assert 'formaction="/applications/archive"' in html
    assert 'formaction="/applications/delete"' in html
    assert 'form="bulk-applications-form"' in html
    assert "Archive selected" in html
    assert b"Active: 1" in index.data
    assert b"Archived: 0" in index.data
    assert 'id="add-application"' in html
    assert "Add" in html
    assert html.index('id="delete-selected"') < html.index('id="add-application"')
    assert html.index('id="add-application"') < html.index('class="actions-menu"')
    assert 'window.open(' in html
    assert '"/applications/add"' in html
    assert 'id="action-sync"' not in html
    assert "#action-sync" not in html
    assert "actionSync" not in html
    assert "Sync from output" not in html
    assert "Regenerate ARO Objects" in html
    assert "Regenerate Draft v1 Only" in html
    assert "Run v1 + v2 Resume Workflow" in html
    assert "Run v1 + v2 + Codex Manual Pass" in html
    assert "Run v2 Refinement" in html
    assert "Codex Highlight Selected Resume" in html
    assert "Codex Manual Pass Variant" in html
    assert "Run Codex highlighting after draft generation" in html
    assert "Sync Draft to ARO" in html
    assert 'name="regenerate_mode" value="aro_objects"' in html
    assert 'name="regenerate_mode" value="draft_resumes"' in html
    assert 'name="regenerate_mode" value="resume_variants"' in html
    assert 'value="resume_variants_manual_pass"' in html
    assert 'name="regenerate_mode" value="refine_drafts"' in html
    assert 'name="regenerate_mode" value="highlight_drafts"' in html
    assert 'name="regenerate_mode" value="manual_pass"' in html
    assert 'name="highlight_with_codex" value="1"' in html
    assert '"manual_pass",' in html
    assert 'name="regenerate_mode" value="sync_draft_to_aro"' in html
    assert "ARO/Resume Sync" in html
    assert "Cover letters" not in html
    assert "Regenerate docs" not in html
    assert 'id="action-status"' in html
    assert 'id="action-status-progress-fill"' in html
    assert 'id="action-status-toggle"' in html
    assert 'id="action-status-close"' in html
    assert 'fetch("/actions/status"' in html
    assert 'class="same-page-download"' not in html
    assert "downloadInCurrentPage" not in html
    assert "samePageDownloads.forEach" not in html
    assert 'href="/resumes/123/download"' not in html
    assert 'href="/cover-letters/123/download"' not in html
    assert b"N/A" in index.data
    assert b"Rejected" in index.data
    assert b"Accepted for interview" in index.data
    assert b"<th>Posted</th>" in index.data
    assert b"<th>Experience</th>" in index.data
    assert b"<th>ARO/Resume Sync</th>" in index.data
    soup = BeautifulSoup(html, "html.parser")
    manual_profile_control = soup.select_one(
        "#actions-manual-pass-profile-control"
    )
    assert manual_profile_control is not None
    assert manual_profile_control.has_attr("hidden")
    _assert_manual_pass_profile_select(
        manual_profile_control.select_one("select[name='manual_pass_profile']")
    )
    assert len(
        soup.select(
            'input[type="radio"][name="regenerate_mode"]'
            '[value="resume_variants_manual_pass"]'
        )
    ) == 1
    assert not soup.select(
        'input[type="radio"][name="regenerate_mode"][checked]'
    )
    assert (
        soup.select_one(
            'input[name="regenerate_mode"][value="resume_variants_manual_pass"]'
        )
        .find_next("span")
        .get_text(" ", strip=True)
        == "Run v1 + v2 + Codex Manual Pass"
    )
    headers = [
        header.get_text(" ", strip=True).replace(" ↑↓", "")
        for header in soup.select("thead th")
    ]
    assert headers[7:12] == [
        "Job Links",
        "Resume",
        "ARO/Resume Sync",
        "Cover Letter",
        "Application",
    ]
    first_row = soup.select_one("tbody tr")
    assert first_row is not None
    cells = first_row.find_all("td", recursive=False)
    assert "Job URL" in cells[7].get_text(" ", strip=True)
    assert "Compare descriptions" in cells[7].get_text(" ", strip=True)
    assert "Resume" in cells[8].get_text(" ", strip=True)
    assert cells[9].select_one(".sync-status") is not None
    assert "Edit" in cells[10].get_text(" ", strip=True)

    def cell_link(cell, label: str):
        return next(
            (
                link
                for link in cell.find_all("a")
                if link.get_text(" ", strip=True) == label
            ),
            None,
        )

    job_url_link = cell_link(cells[7], "Job URL")
    compare_link = cell_link(cells[7], "Compare descriptions")
    resume_link = cell_link(cells[8], "Resume")
    resume_html_link = cell_link(cells[8], "HTML")
    resume_edit_link = cell_link(cells[8], "Edit")
    resume_review_link = cell_link(cells[8], "Review")
    cover_letter_edit_link = cell_link(cells[10], "Edit")
    assert job_url_link is not None
    assert job_url_link.get("target") == "_blank"
    assert compare_link is not None
    assert compare_link.get("target") is None
    assert resume_link is not None
    assert resume_link.get("target") == "_blank"
    assert resume_html_link is not None
    assert resume_html_link.get("target") == "_blank"
    assert resume_edit_link is not None
    assert resume_edit_link.get("target") is None
    assert resume_review_link is not None
    assert resume_review_link.get("target") is None
    assert cover_letter_edit_link is not None
    assert cover_letter_edit_link.get("target") is None
    badge_texts = [
        badge.get_text(" ", strip=True)
        for badge in cells[2].select(".variant-badge")
    ]
    assert badge_texts == ["Draft v1", "Manual pass"]
    manual_badge = cells[2].select_one(".variant-badge.is-manual")
    assert manual_badge is not None
    assert manual_badge.get_text(" ", strip=True) == "Manual pass"
    assert manual_badge["title"] == "Selected resume variant"
    assert b"Mid-Senior level" in index.data
    assert b'id="company-sort"' in index.data
    assert b'id="matched-sort"' in index.data
    assert b'id="ats-sort"' in index.data
    assert b'id="resume-sort"' in index.data
    assert b'id="cover-letter-sort"' in index.data
    assert b'data-company-sort="Example Co"' in index.data
    assert b'data-matched-sort=' in index.data
    assert b"data-ats-sort=" in index.data
    assert b"data-resume-sort=" in index.data
    assert b'data-cover-letter-sort=""' in index.data
    assert b"First Draft Resume" not in index.data
    assert b"ATS proxy score:" in index.data
    assert b"Keyword match:" in index.data
    assert b"Formatting risk:" in index.data
    assert b"Missing/high-value terms:" in index.data
    assert b"2026-06-07" in index.data

    filtered_index = client.get(
        "/?status=Accepted+for+interview&q=Example&sort=ats&direction=desc"
    )
    filtered_html = filtered_index.data.decode()
    assert 'value="Example"' in filtered_html
    assert (
        'value="/?status=Accepted+for+interview&amp;q=Example&amp;sort=ats&amp;direction=desc"'
        in filtered_html
    )
    assert 'const initialSort = "ats";' in filtered_html
    assert 'const initialDirection = "desc";' in filtered_html
    assert "preserve-state-link" in filtered_html
    assert "return-to-state" in filtered_html

    archived_filtered_index = client.get(
        "/?archive=archived&q=Example&sort=ats&direction=desc"
    )
    archived_filtered_html = archived_filtered_index.data.decode()
    assert (
        'value="/?archive=archived&amp;q=Example&amp;sort=ats&amp;direction=desc"'
        in archived_filtered_html
    )
    assert 'value="archived" selected' in archived_filtered_html

    artifact_sorted_index = client.get("/?sort=resume&direction=desc")
    artifact_sorted_html = artifact_sorted_index.data.decode()
    assert 'const initialSort = "resume";' in artifact_sorted_html
    assert 'const initialDirection = "desc";' in artifact_sorted_html

    cover_sorted_index = client.get("/?sort=cover_letter&direction=asc")
    cover_sorted_html = cover_sorted_index.data.decode()
    assert 'const initialSort = "cover_letter";' in cover_sorted_html
    assert 'const initialDirection = "asc";' in cover_sorted_html

    descriptions = client.get("/descriptions/123")
    assert descriptions.status_code == 200
    assert b"Edit Job Descriptions" in descriptions.data
    assert b"Parsed Job Description" in descriptions.data
    assert b"Prompt Job Description" in descriptions.data
    assert b"Removed By Trimming" in descriptions.data
    assert b"Description Diff" in descriptions.data
    assert b'name="job_description"' in descriptions.data
    assert b'name="prompt_job_description"' in descriptions.data
    assert b"Full parsed JOD with mission boilerplate and role requirements." in descriptions.data
    assert b"Clean prompt JOD with role requirements." in descriptions.data

    descriptions_save = client.post(
        "/descriptions/123",
        data={
            "job_description": "Full edited JOD with Java, auth, and platform work.",
            "prompt_job_description": "Prompt edited JOD with Java and auth.",
            "return_to": "/?sort=ats&direction=desc",
        },
    )
    assert descriptions_save.status_code == 302
    assert descriptions_save.headers["Location"] == (
        "/descriptions/123?return_to=%2F%3Fsort%3Dats%26direction%3Ddesc"
    )
    with webapp.connect_database(database_path) as connection:
        description_row = connection.execute(
            """
            SELECT job_description, prompt_job_description, ats_updated_at
            FROM applications
            WHERE job_id = '123'
            """
        ).fetchone()
    assert (
        description_row["job_description"]
        == "Full edited JOD with Java, auth, and platform work."
    )
    assert description_row["prompt_job_description"] == "Prompt edited JOD with Java and auth."
    assert description_row["ats_updated_at"] is not None

    edited_descriptions = client.get("/descriptions/123")
    assert b"Full edited JOD with Java, auth, and platform work." in edited_descriptions.data
    assert b"Prompt edited JOD with Java and auth." in edited_descriptions.data

    db_resume = client.get("/resumes/123")
    assert db_resume.status_code == 200
    assert db_resume.data == resume_pdf

    resume_download = client.get("/resumes/123/download")
    assert resume_download.status_code == 200
    assert resume_download.data == resume_pdf
    assert "attachment" in resume_download.headers["Content-Disposition"]

    assert client.get("/cover-letters/123").status_code == 404
    assert client.get("/cover-letters/123/download").status_code == 404

    downloads_dir = tmp_path / "Downloads"
    downloads_dir.mkdir()
    downloaded_resume = downloads_dir / "mp_resume_senior_engineer.pdf"
    unrelated_pdf = downloads_dir / "other_resume.pdf"
    monkeypatch.setenv("HOME", str(tmp_path))

    resume_copy = client.post("/resumes/123/copy-to-downloads")
    assert resume_copy.status_code == 302
    assert downloaded_resume.read_bytes() == resume_pdf

    copy_index = client.get("/")
    assert b"Copied resume to ~/Downloads/mp_resume_senior_engineer.pdf." in copy_index.data

    unrelated_pdf.write_bytes(b"other")

    yes_response = client.post(
        "/applications/123",
        data={"applied_to": "Yes", "date_applied": "2026-06-08", "notes": ""},
    )
    assert yes_response.status_code == 302
    assert not downloaded_resume.exists()
    assert unrelated_pdf.exists()

    update_response = client.post(
        "/applications/123",
        data={"applied_to": "N/A", "date_applied": "", "notes": "Skip this one"},
    )
    assert update_response.status_code == 302
    refreshed_index = client.get("/")
    assert b'N/A: 1' in refreshed_index.data
    not_applicable_row = BeautifulSoup(
        refreshed_index.data.decode(),
        "html.parser",
    ).select_one('tbody tr[data-status="N/A"]')
    assert not_applicable_row is not None
    assert "is-not-applicable" in not_applicable_row.get("class", [])

    interview_response = client.post(
        "/applications/123",
        data={
            "applied_to": "Accepted for interview",
            "date_applied": "",
            "notes": "Recruiter screen scheduled",
            "return_to": "/?status=Accepted+for+interview&q=Example&sort=ats&direction=desc",
        },
    )
    assert interview_response.status_code == 302
    assert interview_response.headers["Location"] == (
        "/?status=Accepted+for+interview&q=Example&sort=ats&direction=desc"
    )
    interview_index = client.get("/")
    assert b"Interview: 1" in interview_index.data
    assert b'data-status="Accepted for interview"' in interview_index.data
    interview_row = BeautifulSoup(
        interview_index.data.decode(),
        "html.parser",
    ).select_one('tbody tr[data-status="Accepted for interview"]')
    assert interview_row is not None
    assert "is-interview" in interview_row.get("class", [])

    rejected_response = client.post(
        "/applications/123",
        data={"applied_to": "Rejected", "date_applied": "", "notes": "Closed out"},
    )
    assert rejected_response.status_code == 302
    rejected_index = client.get("/")
    assert b"Rejected: 1" in rejected_index.data
    assert b'data-status="Rejected"' in rejected_index.data

    assert client.get(
        "/output/resumes/Example_Co/123_senior_engineer/mp_resume_senior_engineer.pdf"
    ).status_code == 404

    opened_urls: list[str] = []
    monkeypatch.setattr(webapp, "_open_url_in_chromium", opened_urls.append)
    linkedin_response = client.get(
        "/linkedin/123",
        query_string={"return_to": "/?status=Rejected&sort=company&direction=asc"},
    )
    assert linkedin_response.status_code == 302
    assert linkedin_response.headers["Location"] == (
        "/?status=Rejected&sort=company&direction=asc"
    )
    assert opened_urls == ["https://www.linkedin.com/jobs/view/123"]

    archive_response = client.post(
        "/applications/archive",
        data={
            "job_id": "123",
            "return_to": "/?status=Rejected&archive=all&sort=company&direction=asc",
        },
    )
    assert archive_response.status_code == 302
    assert archive_response.headers["Location"] == (
        "/?status=Rejected&archive=all&sort=company&direction=asc"
    )
    with webapp.connect_database(database_path) as connection:
        archived_row = connection.execute(
            """
            SELECT archived_at, resume_content, job_description, prompt_job_description
            FROM applications
            WHERE job_id = '123'
            """
        ).fetchone()
    assert archived_row["archived_at"] is not None
    assert archived_row["resume_content"] == resume_pdf
    assert archived_row["job_description"] == (
        "Full edited JOD with Java, auth, and platform work."
    )
    assert archived_row["prompt_job_description"] == "Prompt edited JOD with Java and auth."

    active_index = client.get("/")
    assert b"Archived 1 application rows." in active_index.data
    assert b"Active: 0" in active_index.data
    assert b"Archived: 1" in active_index.data
    assert b"Example Co" not in active_index.data
    assert client.get("/resumes/123").data == resume_pdf

    archived_index = client.get("/?archive=archived")
    archived_html = archived_index.data.decode()
    assert b"Example Co" in archived_index.data
    assert 'id="unarchive-selected"' in archived_html
    assert 'id="archive-selected"' not in archived_html
    assert 'formaction="/applications/unarchive"' in archived_html
    assert 'value="archived" selected' in archived_html

    all_index = client.get("/?archive=all")
    all_html = all_index.data.decode()
    assert b"Example Co" in all_index.data
    assert 'id="archive-selected"' in all_html
    assert 'id="unarchive-selected"' in all_html

    restore_response = client.post(
        "/applications/unarchive",
        data={"job_id": "123", "return_to": "/?archive=archived"},
    )
    assert restore_response.status_code == 302
    assert restore_response.headers["Location"] == "/?archive=archived"
    with webapp.connect_database(database_path) as connection:
        restored_row = connection.execute(
            "SELECT archived_at, resume_content FROM applications WHERE job_id = '123'"
        ).fetchone()
    assert restored_row["archived_at"] is None
    assert restored_row["resume_content"] == resume_pdf

    restored_index = client.get("/")
    assert b"Restored 1 application rows." in restored_index.data
    assert b"Active: 1" in restored_index.data
    assert b"Archived: 0" in restored_index.data
    assert b"Example Co" in restored_index.data

    response = client.post("/applications/delete", data={"job_id": "123"})
    assert response.status_code == 302
    assert client.get("/resumes/123").status_code == 404
    assert client.get("/cover-letters/123").status_code == 404


def test_description_diff_reports_removed_text_without_wrapping_noise():
    parsed_description = (
        "Intro text we keep. This boilerplate should be removed. "
        "Role requires Python automation."
    )
    prompt_description = "Intro text we keep.\nRole requires Python automation."

    removed_text = webapp._description_removed_text(  # noqa: SLF001
        parsed_description,
        prompt_description,
    )
    diff_rows = webapp._description_diff_rows(  # noqa: SLF001
        parsed_description,
        prompt_description,
    )

    assert removed_text == "This boilerplate should be removed."
    assert len(diff_rows) == 1
    assert diff_rows[0].status == "delete"
    assert diff_rows[0].left_text == "This boilerplate should be removed."
    assert diff_rows[0].right_text == ""
    assert "Intro text we keep." not in removed_text
    assert "Role requires Python automation." not in removed_text


def test_regenerate_make_command_maps_modes_to_make_targets():
    assert webapp._regenerate_make_command(  # noqa: SLF001
        regenerate_mode="aro_objects",
        job_ids=["url-123"],
    ) == [
        "make",
        "regenerate-aro-objects",
        "JOB_IDS=url-123",
    ]
    assert webapp._regenerate_make_command(  # noqa: SLF001
        regenerate_mode="draft_resumes",
        job_ids=["url-123"],
    ) == [
        "make",
        "regenerate-draft-resumes",
        "JOB_IDS=url-123",
        "FIRST_DRAFT_FORCE=1",
    ]
    assert webapp._regenerate_make_command(  # noqa: SLF001
        regenerate_mode="resume_variants",
        job_ids=["url-123"],
    ) == [
        "make",
        "regenerate-resumes",
        "JOB_IDS=url-123",
        "FIRST_DRAFT_FORCE=1",
    ]
    assert webapp._regenerate_make_command(  # noqa: SLF001
        regenerate_mode="refine_drafts",
        job_ids=["url-123"],
    ) == ["make", "refine-draft-resumes", "JOB_IDS=url-123"]
    assert webapp._regenerate_make_command(  # noqa: SLF001
        regenerate_mode="sync_draft_to_aro",
        job_ids=["url-123"],
    ) == ["make", "sync-draft-to-aro", "JOB_IDS=url-123"]
    assert webapp._regenerate_make_command(  # noqa: SLF001
        regenerate_mode="highlight_drafts",
        job_ids=["url-123"],
    ) == ["make", "highlight-draft-resumes", "JOB_IDS=url-123"]
    assert webapp._regenerate_make_command(  # noqa: SLF001
        regenerate_mode="manual_pass",
        job_ids=["url-123"],
    ) == [
        "make",
        "manual-pass-resumes",
        "JOB_IDS=url-123",
        "MANUAL_PASS_PROFILE=regular",
    ]
    assert webapp._regenerate_make_command(  # noqa: SLF001
        regenerate_mode="manual_pass",
        job_ids=["url-123"],
        manual_pass_profile="economy",
    ) == [
        "make",
        "manual-pass-resumes",
        "JOB_IDS=url-123",
        "MANUAL_PASS_PROFILE=economy",
    ]
    assert webapp._regenerate_make_command(  # noqa: SLF001
        regenerate_mode="manual_pass",
        job_ids=["url-123"],
        manual_pass_profile="premium",
    ) == [
        "make",
        "manual-pass-resumes",
        "JOB_IDS=url-123",
        "MANUAL_PASS_PROFILE=premium",
    ]
    assert webapp._regenerate_make_command(  # noqa: SLF001
        regenerate_mode="refine_drafts",
        job_ids=["url-123"],
        manual_pass_profile="premium",
    ) == ["make", "refine-draft-resumes", "JOB_IDS=url-123"]
    assert webapp._highlight_make_command(job_ids=["url-123"]) == [  # noqa: SLF001
        "make",
        "highlight-draft-resumes",
        "JOB_IDS=url-123",
    ]
    assert webapp._highlight_make_command(  # noqa: SLF001
        job_ids=["url-123"],
        variant_key="v2",
    ) == [
        "make",
        "highlight-draft-resumes",
        "JOB_IDS=url-123",
        "HIGHLIGHT_RESUME_VARIANT=v2",
    ]
    with pytest.raises(ValueError, match="Unsupported regeneration mode"):
        webapp._regenerate_make_command(  # noqa: SLF001
            regenerate_mode="resumes",
            job_ids=["123"],
        )
    with pytest.raises(ValueError, match="Unsupported regeneration mode"):
        webapp._regenerate_make_command(  # noqa: SLF001
            regenerate_mode="first_draft_resumes",
            job_ids=["123"],
        )
    with pytest.raises(ValueError, match="invalid manual-pass profile"):
        webapp._regenerate_make_command(  # noqa: SLF001
            regenerate_mode="manual_pass",
            job_ids=["123"],
            manual_pass_profile="gpt-5.6-sol",
        )


def test_seed_make_command_and_output_parsing():
    assert webapp._seed_make_command(  # noqa: SLF001
        max_jobs=5,
        date_posted="past_week",
    ) == [
        "make",
        "seed-jobs",
        "MAX_JOBS=5",
        "DATE_POSTED=past_week",
    ]
    with pytest.raises(ValueError, match="at least 1"):
        webapp._seed_make_command(max_jobs=0, date_posted="past_week")  # noqa: SLF001
    with pytest.raises(ValueError, match="Unsupported seed date posted filter"):
        webapp._seed_make_command(max_jobs=5, date_posted="yesterday")  # noqa: SLF001

    output = """
    LLM: planner=z-ai/glm-5.2
    {
      "jobs_seeded": 2,
      "seeded_applications": [
        {"job_id": "4436138555", "company": "Intuitive"},
        {"job_id": "4432384894", "company": "Matlen Silver"},
        {"job_id": "4436138555", "company": "Duplicate"}
      ]
    }
    """

    assert webapp._extract_seeded_job_ids(output) == [  # noqa: SLF001
        "4436138555",
        "4432384894",
    ]
    assert webapp._extract_seeded_job_ids("no json here") == []  # noqa: SLF001


def test_application_status_row_class_maps_shaded_statuses():
    assert webapp._application_status_row_class("Yes") == "is-applied"  # noqa: SLF001
    assert (  # noqa: SLF001
        webapp._application_status_row_class("Accepted for interview")
        == "is-interview"
    )
    assert webapp._application_status_row_class("N/A") == "is-not-applicable"  # noqa: SLF001
    assert webapp._application_status_row_class("Rejected") == ""  # noqa: SLF001


def test_store_application_resume_first_draft_updates_tracker_row(tmp_path: Path):
    database_path = tmp_path / "applications.sqlite3"
    webapp.upsert_application_artifact(
        database_path=database_path,
        job_id="123",
        company="Example Co",
        job_title="Senior Engineer",
        linkedin_url="https://www.linkedin.com/jobs/view/123",
        resume_path=None,
        job_description="Requires Python, AWS, APIs, and observability.",
        prompt_job_description="Requires Python, AWS, APIs, and observability.",
    )
    resume_pdf = _pdf_bytes(
        """
        Max Perkhounkov
        Professional Summary
        Core Technical Skills
        Python AWS APIs observability
        Professional Experience
        Built Python APIs on AWS with observability.
        Education
        Certifications
        """
    )

    webapp.store_application_resume_first_draft(
        database_path=database_path,
        job_id="123",
        application_resume_object="schema_version: test\n",
        resume_html="<html><body><h1>First Draft Resume</h1></body></html>",
        resume_pdf=resume_pdf,
    )

    with webapp.connect_database(database_path) as connection:
        row = connection.execute(
            """
            SELECT application_resume_object, resume_html_filename, resume_html_content,
                   resume_html_mime_type, resume_filename, resume_content,
                   source_resume_path, ats_score, ats_missing_terms,
                   selected_resume_variant
            FROM applications
            WHERE job_id = '123'
            """
        ).fetchone()
        v1_variant = connection.execute(
            """
            SELECT application_resume_object, resume_html_filename, resume_html_content,
                   resume_filename, resume_content, ats_score
            FROM application_resume_variants
            WHERE job_id = '123' AND variant_key = 'v1'
            """
        ).fetchone()
    assert row["application_resume_object"] == "schema_version: test\n"
    assert row["resume_html_filename"] == "mp_resume_senior_engineer.html"
    assert row["resume_html_content"] == "<html><body><h1>First Draft Resume</h1></body></html>"
    assert row["resume_html_mime_type"] == "text/html; charset=utf-8"
    assert row["resume_filename"] == "mp_resume_senior_engineer.pdf"
    assert row["resume_content"] == resume_pdf
    assert row["source_resume_path"] == ""
    assert row["ats_score"] is not None
    assert row["ats_missing_terms"] is not None
    assert row["selected_resume_variant"] == "v1"
    assert v1_variant["application_resume_object"] == row["application_resume_object"]
    assert v1_variant["resume_html_filename"] == row["resume_html_filename"]
    assert v1_variant["resume_html_content"] == row["resume_html_content"]
    assert v1_variant["resume_filename"] == row["resume_filename"]
    assert v1_variant["resume_content"] == row["resume_content"]
    assert v1_variant["ats_score"] == row["ats_score"]

    app = create_app(database_path=database_path, output_dir=tmp_path / "output")
    client = app.test_client()
    html_response = client.get("/resume-html/123")
    assert html_response.status_code == 200
    assert b"First Draft Resume" in html_response.data
    assert html_response.mimetype == "text/html"
    index = client.get("/")
    assert b'href="/resume-html/123"' in index.data


def test_resume_variant_review_selects_v2_and_v1_reversibly(tmp_path: Path):
    database_path = tmp_path / "applications.sqlite3"
    webapp.upsert_application_artifact(
        database_path=database_path,
        job_id="123",
        company="Example Co",
        job_title="Senior Engineer",
        linkedin_url="https://www.linkedin.com/jobs/view/123",
        resume_path=None,
        job_description="Requires Python, AWS, APIs, and observability.",
        prompt_job_description="Requires Python, AWS, APIs, and observability.",
    )
    v1_pdf = _pdf_bytes("Draft v1 Python AWS APIs")
    v2_pdf = _pdf_bytes("Refined v2 Python AWS APIs observability")
    webapp.store_application_resume_first_draft(
        database_path=database_path,
        job_id="123",
        application_resume_object="schema_version: test\nsummary: Draft v1\n",
        resume_html="<html><body><h1>Draft v1</h1></body></html>",
        resume_pdf=v1_pdf,
    )
    webapp.store_application_resume_variant(
        database_path=database_path,
        job_id="123",
        variant_key="v2",
        variant_label="Refined v2",
        source="second_pass",
        parent_variant_key="v1",
        application_resume_object="schema_version: test\nsummary: Refined v2\n",
        resume_html="<html><body><h1>Refined v2</h1></body></html>",
        resume_pdf=v2_pdf,
        validation={
            "accepted_change_ids": ["summary-1"],
            "rejected_changes": [
                {
                    "change_id": "skills-1",
                    "issues": [
                        {
                            "reason": "unsupported_target",
                            "message": "Skill was not backed by evidence.",
                        }
                    ],
                }
            ],
            "is_valid": False,
        },
        critique={
            "proposed_changes": [
                {
                    "change_id": "summary-1",
                    "rationale": "Tightens the platform summary.",
                    "unsupported_claims": [],
                },
                {
                    "change_id": "skills-1",
                    "rationale": "Adds a tool term.",
                    "unsupported_claims": ["Kubernetes"],
                },
            ],
        },
        model_metadata={"model": "z-ai/glm-5.2"},
    )
    webapp.store_application_resume_variant(
        database_path=database_path,
        job_id="123",
        variant_key="manual",
        variant_label="Manual pass",
        source="manual_pass",
        parent_variant_key="v2",
        application_resume_object="schema_version: test\nsummary: Manual pass\n",
        resume_html="<html><body><h1>Manual pass</h1></body></html>",
        resume_pdf=v2_pdf,
        validation={
            "accepted_change_ids": ["summary-1"],
            "rejected_changes": [
                {
                    "change_id": "skills-1",
                    "issues": [
                        {
                            "reason": "unsupported_target",
                            "message": "Skill was not backed by evidence.",
                        }
                    ],
                }
            ],
            "is_valid": False,
        },
        critique={
            "proposed_changes": [
                {
                    "change_id": "summary-1",
                    "rationale": "Tightens the platform summary.",
                    "unsupported_claims": [],
                },
                {
                    "change_id": "skills-1",
                    "rationale": "Adds a tool term.",
                    "unsupported_claims": ["Kubernetes"],
                },
            ],
        },
        model_metadata={"model": "z-ai/glm-5.2"},
    )

    app = create_app(database_path=database_path, output_dir=tmp_path / "output")
    client = app.test_client()

    index_html = client.get("/").data.decode()
    index_soup = BeautifulSoup(index_html, "html.parser")
    index_badges = [
        badge.get_text(" ", strip=True)
        for badge in index_soup.select(".job .variant-badge")
    ]
    assert index_badges == ["Draft v1", "Refined v2", "Manual pass"]
    manual_badge = index_soup.select_one(".job .variant-badge.is-manual")
    assert manual_badge is not None
    assert manual_badge["title"] == "Selected resume variant"
    assert 'href="/resumes/123/variants"' in index_html
    assert "Review" in index_html

    review = client.get("/resumes/123/variants?return_to=%2F%3Fsort%3Dresume")
    assert review.status_code == 200
    review_html = review.data.decode()
    assert "Resume Variants" in review_html
    assert "Draft v1" in review_html
    assert "Refined v2" in review_html
    assert "Manual pass" in review_html
    assert "Selected" in review_html
    assert "Use v2 draft" in review_html
    assert 'href="/resumes/123/variants/v1"' in review_html
    assert 'href="/resume-html/123/variants/v2"' in review_html
    assert "z-ai/glm-5.2" in review_html
    assert "summary-1" in review_html
    assert "skills-1" in review_html
    assert "unsupported_target" in review_html
    assert "Kubernetes" in review_html
    assert review_html.count("summary-1") == 1
    assert review_html.count("skills-1") == 1
    assert review_html.count("unsupported_target") == 1
    assert review_html.count("Kubernetes") == 1
    assert "-summary: Draft v1" in review_html
    assert "+summary: Refined v2" in review_html

    v2_pdf_response = client.get("/resumes/123/variants/v2")
    assert v2_pdf_response.status_code == 200
    assert v2_pdf_response.data == v2_pdf
    v2_html_response = client.get("/resume-html/123/variants/v2")
    assert v2_html_response.status_code == 200
    assert b"Refined v2" in v2_html_response.data

    use_v2 = client.post(
        "/resumes/123/variants/v2/use",
        data={"return_to": "/?sort=resume"},
    )
    assert use_v2.status_code == 302
    assert use_v2.headers["Location"] == (
        "/resumes/123/variants?return_to=%2F%3Fsort%3Dresume"
    )
    with webapp.connect_database(database_path) as connection:
        row = connection.execute(
            """
            SELECT selected_resume_variant, application_resume_object, resume_content,
                   resume_html_content, resume_variant_selection_mode
            FROM applications
            WHERE job_id = '123'
            """
        ).fetchone()
    assert row["selected_resume_variant"] == "v2"
    assert row["resume_variant_selection_mode"] == "manual"
    assert "summary: Refined v2" in row["application_resume_object"]
    assert row["resume_content"] == v2_pdf
    assert "Refined v2" in row["resume_html_content"]
    assert client.get("/resumes/123").data == v2_pdf
    assert b"Refined v2" in client.get("/resume-html/123").data
    assert "Refined v2" in client.get("/").data.decode()

    use_v1 = client.post(
        "/resumes/123/variants/v1/use",
        data={"return_to": "/?sort=resume"},
    )
    assert use_v1.status_code == 302
    with webapp.connect_database(database_path) as connection:
        reverted = connection.execute(
            """
            SELECT selected_resume_variant, application_resume_object, resume_content,
                   resume_html_content, resume_variant_selection_mode
            FROM applications
            WHERE job_id = '123'
            """
        ).fetchone()
    assert reverted["selected_resume_variant"] == "v1"
    assert reverted["resume_variant_selection_mode"] == "manual"
    assert "summary: Draft v1" in reverted["application_resume_object"]
    assert reverted["resume_content"] == v1_pdf
    assert "Draft v1" in reverted["resume_html_content"]


def test_connect_database_backfills_v1_resume_variant_for_existing_aro(tmp_path: Path):
    database_path = tmp_path / "applications.sqlite3"
    webapp.upsert_application_artifact(
        database_path=database_path,
        job_id="123",
        company="Example Co",
        job_title="Senior Engineer",
        linkedin_url="https://www.linkedin.com/jobs/view/123",
        resume_path=None,
        job_description="Requires Python, AWS, APIs, and observability.",
        prompt_job_description="Requires Python, AWS, APIs, and observability.",
    )
    webapp.store_application_resume_first_draft(
        database_path=database_path,
        job_id="123",
        application_resume_object="schema_version: test\n",
        resume_html="<html><body><h1>First Draft Resume</h1></body></html>",
        resume_pdf=_pdf_bytes("Python AWS APIs observability"),
    )
    with sqlite3.connect(database_path) as connection:
        connection.execute("DROP TABLE application_resume_variants")
        connection.commit()

    with webapp.connect_database(database_path) as connection:
        variant = connection.execute(
            """
            SELECT variant_key, application_resume_object, resume_html_content,
                   resume_content, ats_score
            FROM application_resume_variants
            WHERE job_id = '123' AND variant_key = 'v1'
            """
        ).fetchone()

    assert variant is not None
    assert variant["application_resume_object"] == "schema_version: test\n"
    assert "First Draft Resume" in variant["resume_html_content"]
    assert variant["resume_content"] is not None
    assert variant["ats_score"] is not None


def test_connect_database_backfills_legacy_manual_resume_variant(tmp_path: Path):
    database_path = tmp_path / "applications.sqlite3"
    webapp.upsert_application_artifact(
        database_path=database_path,
        job_id="123",
        company="Example Co",
        job_title="Senior Engineer",
        linkedin_url="https://www.linkedin.com/jobs/view/123",
        resume_path=None,
        job_description="Requires Python, AWS, APIs, and observability.",
        prompt_job_description="Requires Python, AWS, APIs, and observability.",
    )
    webapp.store_application_resume_first_draft(
        database_path=database_path,
        job_id="123",
        application_resume_object="schema_version: test\nsummary: Draft v1\n",
        resume_html="<html><body><h1>Draft v1</h1></body></html>",
        resume_pdf=_pdf_bytes("Draft v1 Python AWS APIs observability"),
    )
    manual_pdf = _pdf_bytes("Manual pass Python AWS APIs observability")
    with webapp.connect_database(database_path) as connection:
        connection.execute(
            """
            UPDATE applications
            SET application_resume_object = ?,
                application_resume_updated_at = '2026-07-01T10:00:00+00:00',
                resume_html_filename = 'manual.html',
                resume_html_content = ?,
                resume_html_updated_at = '2026-07-01T10:00:00+00:00',
                resume_filename = 'manual.pdf',
                resume_content = ?,
                resume_updated_at = '2026-07-01T10:00:00+00:00',
                ats_score = 88,
                ats_parsing_score = 100,
                ats_keyword_score = 84,
                ats_semantic_score = 72,
                ats_formatting_risk = 'Low',
                ats_missing_terms = '',
                notes = 'Manual second pass 2026-07-01: refreshed artifacts.',
                selected_resume_variant = 'v1'
            WHERE job_id = '123'
            """,
            (
                "schema_version: test\nsummary: Manual pass\n",
                "<html><body><h1>Manual pass</h1></body></html>",
                manual_pdf,
            ),
        )
        connection.execute(
            """
            DELETE FROM application_resume_variants
            WHERE job_id = '123' AND variant_key = 'manual'
            """
        )
        connection.commit()

    with webapp.connect_database(database_path) as connection:
        row = connection.execute(
            """
            SELECT selected_resume_variant, resume_variant_selection_mode
            FROM applications
            WHERE job_id = '123'
            """
        ).fetchone()
        manual_variant = connection.execute(
            """
            SELECT variant_key, variant_label, source, parent_variant_key,
                   application_resume_object, resume_html_content, resume_content,
                   ats_score
            FROM application_resume_variants
            WHERE job_id = '123' AND variant_key = 'manual'
            """
        ).fetchone()

    assert row["selected_resume_variant"] == "manual"
    assert row["resume_variant_selection_mode"] == "auto"
    assert manual_variant is not None
    assert manual_variant["variant_label"] == "Manual pass"
    assert manual_variant["source"] == "legacy_manual_pass"
    assert manual_variant["parent_variant_key"] == "v1"
    assert "summary: Manual pass" in manual_variant["application_resume_object"]
    assert "Manual pass" in manual_variant["resume_html_content"]
    assert manual_variant["resume_content"] == manual_pdf
    assert manual_variant["ats_score"] == 88

    app = create_app(database_path=database_path, output_dir=tmp_path / "output")
    review_html = app.test_client().get("/resumes/123/variants").data.decode()
    assert "Manual pass" in review_html
    assert 'href="/resumes/123/variants/manual"' in review_html


def test_application_seed_update_preserves_first_draft_resume_when_aro_exists(
    tmp_path: Path,
):
    database_path = tmp_path / "applications.sqlite3"
    webapp.upsert_application_artifact(
        database_path=database_path,
        job_id="123",
        company="Example Co",
        job_title="Senior Engineer",
        linkedin_url="https://www.linkedin.com/jobs/view/123",
        resume_path=None,
        job_description="Requires Python, AWS, APIs, and observability.",
        prompt_job_description="Requires Python, AWS, APIs, and observability.",
    )
    first_draft_pdf = _pdf_bytes(
        """
        Max Perkhounkov
        Core Technical Skills
        Python AWS APIs observability
        Professional Experience
        Built Python APIs on AWS with observability.
        """
    )
    first_draft_path = tmp_path / "first_draft.pdf"
    first_draft_path.write_bytes(first_draft_pdf)
    webapp.store_application_resume_first_draft(
        database_path=database_path,
        job_id="123",
        application_resume_object="schema_version: test\n",
        resume_html="<html><body><h1>First Draft Resume</h1></body></html>",
        resume_pdf=first_draft_pdf,
        resume_pdf_path=first_draft_path,
    )
    with webapp.connect_database(database_path) as connection:
        first_draft_row = connection.execute(
            """
            SELECT resume_filename, resume_content, source_resume_path,
                   resume_updated_at, ats_score, ats_updated_at
            FROM applications
            WHERE job_id = '123'
            """
        ).fetchone()

    legacy_resume_path = tmp_path / "external_resume.pdf"
    legacy_resume_path.write_bytes(_pdf_bytes("Legacy Java resume"))
    legacy_updated_at = datetime(2026, 6, 9, 15, 30, tzinfo=UTC)
    os.utime(
        legacy_resume_path,
        (legacy_updated_at.timestamp(), legacy_updated_at.timestamp()),
    )
    webapp.upsert_application_artifact(
        database_path=database_path,
        job_id="123",
        company="Example Co",
        job_title="Senior Engineer",
        linkedin_url="https://www.linkedin.com/jobs/view/123",
        resume_path=legacy_resume_path,
        job_description="Requires Java and legacy systems.",
        prompt_job_description="Requires Java and legacy systems.",
    )

    with webapp.connect_database(database_path) as connection:
        row = connection.execute(
            """
            SELECT resume_filename, resume_content, source_resume_path,
                   resume_updated_at, ats_score, ats_updated_at
            FROM applications
            WHERE job_id = '123'
            """
        ).fetchone()
    assert row["resume_filename"] == first_draft_row["resume_filename"]
    assert row["resume_content"] == first_draft_row["resume_content"]
    assert row["source_resume_path"] == str(first_draft_path)
    assert row["resume_updated_at"] == first_draft_row["resume_updated_at"]
    assert row["ats_score"] == first_draft_row["ats_score"]
    assert row["ats_updated_at"] == first_draft_row["ats_updated_at"]


def test_resume_editor_saves_rerenders_rescores_and_reverts(tmp_path: Path, monkeypatch):
    database_path = tmp_path / "applications.sqlite3"
    webapp.upsert_application_artifact(
        database_path=database_path,
        job_id="123",
        company="Example Co",
        job_title="Senior Engineer",
        linkedin_url="https://www.linkedin.com/jobs/view/123",
        resume_path=None,
        job_description="Requires Python, AWS, APIs, and authentication.",
        prompt_job_description="Requires Python, AWS, APIs, and authentication.",
    )
    original_aro = _sample_application_resume_yaml(
        paragraph="Original summary for platform APIs.",
        bullet="Original platform API bullet.",
    )
    webapp.store_application_resume_first_draft(
        database_path=database_path,
        job_id="123",
        application_resume_object=original_aro,
        resume_html="<html><body><h1>Original</h1></body></html>",
        resume_pdf=_pdf_bytes("Original Python AWS APIs"),
    )

    monkeypatch.setattr(
        webapp,
        "render_resume_pdf_from_html",
        lambda html: _pdf_bytes(f"Rendered {html}"),
    )

    app = create_app(database_path=database_path, output_dir=tmp_path / "output")
    client = app.test_client()
    index = client.get("/")
    assert b"/resumes/123/edit" in index.data

    edit_response = client.get("/resumes/123/edit?return_to=%2F%3Fsort%3Dresume")
    assert edit_response.status_code == 200
    edit_html = edit_response.data.decode()
    assert 'data-rich-command="bold"' in edit_html
    assert 'data-rich-command="italic"' in edit_html
    assert 'data-rich-target="header_line_2"' in edit_html
    assert 'data-rich-target="summary_paragraph"' in edit_html
    form_data = _edit_form_data(edit_html)
    form_data["header_line_2"] = "<b>Staff Platform Engineer</b>"
    form_data["summary_paragraph"] = (
        "Edited summary with <b>authentication</b> <i>APIs</i>."
        "<script>bad()</script>"
    )
    form_data["job_0_bullet_0_text"] = "Edited <b>authentication</b> API bullet."

    save_response = client.post("/resumes/123/edit", data=form_data)
    assert save_response.status_code == 302
    with webapp.connect_database(database_path) as connection:
        edited_row = connection.execute(
            """
            SELECT application_resume_object, application_resume_backup_object,
                   resume_html_content, resume_content, source_resume_path,
                   ats_score
            FROM applications
            WHERE job_id = '123'
            """
        ).fetchone()
    assert "<b>Staff Platform Engineer</b>" in edited_row["application_resume_object"]
    edited_aro = yaml.safe_load(edited_row["application_resume_object"])
    edited_skill_items = edited_aro["core_technical_skills"]["bullet_points"][0]["items"]
    assert edited_skill_items["primary"] == ["Python", "AWS"]
    assert edited_skill_items["additional"] == ["authentication", "Java"]
    assert "line_3_applicant_info_text" in edited_row["application_resume_object"]
    assert "line_2_applicant_info_text" not in edited_row["application_resume_object"]
    assert "Edited summary with <b>authentication</b> <i>APIs</i>." in edited_row[
        "application_resume_object"
    ]
    assert "<script>" not in edited_row["application_resume_object"]
    assert "Edited <b>authentication</b> API bullet." in edited_row[
        "application_resume_object"
    ]
    assert "Original platform API bullet." in edited_row[
        "application_resume_backup_object"
    ]
    assert '<p class="resume-headline"><b>Staff Platform Engineer</b></p>' in edited_row[
        "resume_html_content"
    ]
    assert "<strong>Platform Engineering:</strong> Python, AWS, authentication" in edited_row[
        "resume_html_content"
    ]
    assert "Edited <b>authentication</b> API bullet." in edited_row["resume_html_content"]
    assert edited_row["resume_content"] is not None
    assert edited_row["source_resume_path"] == ""
    assert edited_row["ats_score"] is not None

    revert_response = client.post(
        "/resumes/123/edit/revert",
        data={"return_to": "/?sort=resume"},
    )
    assert revert_response.status_code == 302
    with webapp.connect_database(database_path) as connection:
        reverted_row = connection.execute(
            """
            SELECT application_resume_object, application_resume_backup_object,
                   resume_html_content, ats_score
            FROM applications
            WHERE job_id = '123'
            """
        ).fetchone()
    assert "Original platform API bullet." in reverted_row["application_resume_object"]
    assert "Edited <b>authentication</b> API bullet." in reverted_row[
        "application_resume_backup_object"
    ]
    assert "Original platform API bullet." in reverted_row["resume_html_content"]
    assert reverted_row["ats_score"] is not None


def test_resume_editor_preserves_skill_inventory_when_skill_fields_are_missing():
    resume = yaml.safe_load(
        _sample_application_resume_yaml(
            paragraph="Original summary for platform APIs.",
            bullet="Original platform API bullet.",
        )
    )
    form = {
        "header_name": "Max Perkhounkov",
        "header_line_2": "Senior Platform Software Engineer",
        "header_info": "max@example.com",
        "header_contact_items": "max@example.com",
        "summary_render": "1",
        "summary_header_text": "Professional Summary",
        "summary_paragraph": "Original summary for platform APIs.",
        "summary_note": "",
        "skills_render": "1",
        "skills_header_text": "Core Technical Skills",
        "skill_0_primary": "",
        "skill_0_additional": "",
        "skill_0_jod_matched": "",
        "experience_render": "1",
        "experience_header_text": "Professional Experience",
    }

    updated = webapp._apply_resume_editor_form(resume, form)  # noqa: SLF001

    skill_bucket = updated["core_technical_skills"]["bullet_points"][0]
    assert skill_bucket["category"] == "Platform Engineering"
    assert skill_bucket["items"]["primary"] == ["Python", "AWS"]
    assert skill_bucket["items"]["additional"] == ["authentication", "Java"]
    assert skill_bucket["jod_matched_items"] == ["authentication"]


def test_aro_resume_sync_status_and_edit_warning(tmp_path: Path, monkeypatch):
    database_path = tmp_path / "applications.sqlite3"
    webapp.upsert_application_artifact(
        database_path=database_path,
        job_id="123",
        company="Example Co",
        job_title="Senior Engineer",
        linkedin_url="https://www.linkedin.com/jobs/view/123",
        resume_path=None,
        job_description="Requires Python, AWS, APIs, and authentication.",
        prompt_job_description="Requires Python, AWS, APIs, and authentication.",
    )
    original_aro = _sample_application_resume_yaml(
        paragraph="Original summary for platform APIs.",
        bullet="Original platform API bullet.",
    )
    webapp.store_application_resume_first_draft(
        database_path=database_path,
        job_id="123",
        application_resume_object=original_aro,
        resume_html="<html><body><p>Original summary for platform APIs.</p></body></html>",
        resume_pdf=_pdf_bytes("Original Python AWS APIs"),
    )
    updated_aro = _sample_application_resume_yaml(
        paragraph="Updated ARO summary for authentication APIs.",
        bullet="Updated ARO authentication API bullet.",
    )
    webapp.store_application_resume_object(
        database_path=database_path,
        job_id="123",
        application_resume_object=updated_aro,
    )
    with webapp.connect_database(database_path) as connection:
        connection.execute(
            """
            UPDATE applications
            SET application_resume_updated_at = '2000-01-01T00:00:02+00:00',
                resume_updated_at = '2000-01-01T00:00:01+00:00',
                resume_html_updated_at = '2000-01-01T00:00:01+00:00'
            WHERE job_id = '123'
            """
        )
        connection.commit()

    monkeypatch.setattr(
        webapp,
        "render_resume_pdf_from_html",
        lambda html: _pdf_bytes(f"Rendered {html}"),
    )

    app = create_app(database_path=database_path, output_dir=tmp_path / "output")
    client = app.test_client()
    index_html = client.get("/").data.decode()
    assert "ARO/Resume Sync" in index_html
    sync_badge = BeautifulSoup(index_html, "html.parser").find("span", class_="sync-status")
    assert sync_badge is not None
    assert sync_badge.text.strip() == "No"
    assert "is-stale" in sync_badge.get("class", [])

    edit_html = client.get("/resumes/123/edit").data.decode()
    assert "ARO and draft resume are out of sync." in edit_html
    assert 'action="/resumes/123/sync"' in edit_html

    sync_response = client.post("/resumes/123/sync", data={"return_to": "/"})
    assert sync_response.status_code == 302
    with webapp.connect_database(database_path) as connection:
        row = connection.execute(
            """
            SELECT application_resume_updated_at, resume_html_content, resume_content
            FROM applications
            WHERE job_id = '123'
            """
        ).fetchone()
    assert row["application_resume_updated_at"] == "2000-01-01T00:00:02+00:00"
    assert "Updated ARO summary for authentication APIs." in row["resume_html_content"]
    assert row["resume_content"] is not None
    assert webapp._fetch_application(database_path, "123")["aro_resume_sync_status"] == "Yes"  # noqa: SLF001


def test_cover_letter_editor_saves_clo_and_pdf(tmp_path: Path, monkeypatch):
    database_path = tmp_path / "applications.sqlite3"
    webapp.upsert_application_artifact(
        database_path=database_path,
        job_id="123",
        company="Example Co",
        job_title="Senior Engineer",
        linkedin_url="https://www.linkedin.com/jobs/view/123",
        resume_path=None,
        job_description="Requires Python, AWS, APIs, and authentication.",
        prompt_job_description="Requires Python, AWS, APIs, and authentication.",
    )

    app = create_app(database_path=database_path, output_dir=tmp_path / "output")
    client = app.test_client()

    edit_response = client.get("/cover-letters/123/edit?return_to=%2F%3Fq%3DExample")
    assert edit_response.status_code == 200
    edit_html = edit_response.data.decode()
    assert "Edit Cover Letter" in edit_html
    assert 'contenteditable="true"' in edit_html
    assert 'data-command="bold"' in edit_html
    assert 'data-command="italic"' in edit_html

    save_response = client.post(
        "/cover-letters/123/edit",
        data={
            "return_to": "/?q=Example",
            "body_html": (
                "<p>Dear <strong>Hiring Team</strong>,</p>"
                "<script>alert('nope')</script>"
                "<p><em>I am excited</em> about authentication systems.</p>"
            ),
        },
    )
    assert save_response.status_code == 302
    with webapp.connect_database(database_path) as connection:
        row = connection.execute(
            """
            SELECT cover_letter_object, cover_letter_filename, cover_letter_content,
                   source_cover_letter_path, cover_letter_updated_at
            FROM applications
            WHERE job_id = '123'
            """
        ).fetchone()
    assert row["cover_letter_object"] is not None
    assert "<script>" not in row["cover_letter_object"]
    assert "<b>Hiring Team</b>" in row["cover_letter_object"]
    assert "<i>I am excited</i>" in row["cover_letter_object"]
    assert row["cover_letter_filename"] == "mp_cover_letter_senior_engineer.pdf"
    assert bytes(row["cover_letter_content"]).startswith(b"%PDF")
    assert row["source_cover_letter_path"] == ""
    assert row["cover_letter_updated_at"] is not None

    pdf_response = client.get("/cover-letters/123")
    assert pdf_response.status_code == 200
    assert pdf_response.data.startswith(b"%PDF")
    download_response = client.get("/cover-letters/123/download")
    assert download_response.status_code == 200
    assert "attachment" in download_response.headers["Content-Disposition"]

    index = client.get("/")
    assert b"/cover-letters/123/edit" in index.data
    assert b"/cover-letters/123" in index.data
    assert b"Download" in index.data

    downloads_dir = tmp_path / "Downloads"
    downloads_dir.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    copy_response = client.post("/cover-letters/123/copy-to-downloads")
    assert copy_response.status_code == 302
    assert (downloads_dir / "mp_cover_letter_senior_engineer.pdf").read_bytes().startswith(
        b"%PDF"
    )


def test_cover_letter_pdf_renderer_fits_lts_length_manual_letter_on_one_page():
    from pypdf import PdfReader

    body_html = (
        "<p><b>Cover Letter: Principal Platform Engineer at LTS</b></p>"
        "<p><b>To the LTS Engineering Team,</b></p>"
        "<p>I am writing to express my interest in the Principal Platform Engineer role at "
        "LTS. The mission you describe, building agents that can read, translate, and "
        "modernize a consequential legacy system with real users and executive backing, "
        "lands very close to the direction of my current platform work at Oracle. I tend "
        "to operate as a force multiplier: building the connective tissue between AI tools "
        "and production-adjacent enterprise systems so models can help with real operational "
        "work without blurring ownership, auditability, or safety.</p>"
        "<p>At Oracle, on the Platform Development and Automation Frameworks team, my work "
        "sits at the intersection of cloud automation, observability, legacy modernization, "
        "and AI-native engineering. The strongest match with LTS is not simply that I use "
        "AI heavily; it is that I have had to make AI-assisted work repeatable enough for "
        "serious infrastructure environments.</p>"
        "<p><b>Agentic orchestration and MCP:</b> I built an OLAM MCP server and associated "
        "Codex skills that turned ad hoc AI investigation into repeatable platform tooling. "
        "The architecture uses stable tool contracts, read/write separation, explicit "
        "cluster routing, admin-only control-plane guardrails, secret-bearing argument "
        "rejection, redacted logs, source-control discipline, and Ruff/unit-test validation. "
        "That gave Codex a governed way to inspect schedules, classify job outcomes, analyze "
        "inventory coverage, and produce operational reports against OLAM/AWX.</p>"
        "<p><b>Production modernization and platform ownership:</b> I helped execute the "
        "migration from self-hosted ELK to OCI Search Service/OpenSearch, automating "
        "migration steps, validating document counts, deduplicating data, and preserving "
        "observability usefulness while the backend changed. I also helped replace fragile "
        "CMDB dependencies with OCI function/API front-end pieces, managed PostgreSQL "
        "monitoring, OCI metrics and alarms, notification routing, and service-backed asset "
        "data. In ONDA, I built and hardened Python utility paths for sanitized SCM-backed "
        "configuration backups, encrypted secret handling, restore metadata, and "
        "vendor-extensible data collection across an 11,000+ network-device fleet.</p>"
        "<p><b>Security, compliance, and restricted-environment thinking:</b> My experience "
        "includes OLAM-native RBAC boundaries, per-cluster token providers, least-privilege "
        "operating patterns, human approval workflows, dry-run validation, and careful "
        "separation between read and write actions. Earlier healthcare roles add a practical "
        "compliance base: DICOM anonymization, regulated clinical platform support, "
        "HIPAA-driven infrastructure modernization, incident and change management, disaster "
        "recovery, and audit-facing security work. I have not treated compliance as "
        "paperwork after the fact; I have translated it into concrete system behavior.</p>"
        "<p><b>Developer experience and operational responsibility:</b> I have owned "
        "production on-call responsibilities across OLAM, OpenSearch, Chef, Logstash/Filebeat, "
        "and monitoring systems. Much of my work has been turning failure modes into clearer "
        "alerts, dashboards, runbooks, remediation guides, CI/CD paths, and handoffs that "
        "other engineers can trust. That is the part of platform engineering I enjoy most: "
        "making the paved road real enough that the team moves faster without hiding risk.</p>"
        "<p>I understand LTS is building on commercial AWS and will need clean "
        "infrastructure-as-code, identity abstraction, observability, portability, and "
        "deployment paths that can survive movement into regulated or restricted "
        "environments. My recent production experience has been OCI-heavy, but the "
        "architectural problems are the ones I have been working through every day: tenancy "
        "boundaries, managed services, platform observability, secret handling, controlled "
        "automation, compliance-aware design, and agents that remain accountable to human "
        "operators.</p>"
        "<p>I have attached my Principal Platform Engineer resume with more detail on the "
        "Oracle platform work, the MCP/Codex tooling, and the regulated healthcare "
        "infrastructure experience. I would welcome the chance to discuss how I can help own "
        "the architectural shape of the LTS platform and make the AI-native workflow safe, "
        "inspectable, and durable from the start.</p>"
        "<p>Best regards,</p>"
        "<p>Max Perkhounkov</p>"
    )

    pdf_bytes = webapp.render_cover_letter_pdf_from_clo_html(body_html)

    assert pdf_bytes.startswith(b"%PDF")
    assert len(PdfReader(BytesIO(pdf_bytes)).pages) == 1


def test_actions_run_starts_background_regeneration(tmp_path: Path):
    with webapp._ACTION_RUN_LOCK:  # noqa: SLF001
        webapp._ACTION_RUNS.clear()  # noqa: SLF001

    calls = []
    completed = threading.Event()

    def runner(**kwargs):
        calls.append(kwargs)
        webapp._append_background_action_message(  # noqa: SLF001
            kwargs["run_id"],
            "processing job 123",
        )
        webapp._finish_background_action_run(  # noqa: SLF001
            kwargs["run_id"],
            status="completed",
            return_code=0,
        )
        completed.set()

    output_dir = tmp_path / "output"
    database_path = output_dir / "tracking/applications.sqlite3"
    app = create_app(
        database_path=database_path,
        output_dir=output_dir,
        background_action_runner=runner,
    )
    client = app.test_client()

    response = client.post(
        "/actions/run",
        data={
            "regenerate_mode": "draft_resumes",
            "job_id": ["123", "123", "456"],
            "return_to": "/?q=Example",
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/?q=Example"
    assert completed.wait(timeout=2)
    assert calls
    assert "sync_requested" not in calls[0]
    assert calls[0]["regenerate_mode"] == "draft_resumes"
    assert calls[0]["highlight_with_codex"] is False
    assert calls[0]["job_ids"] == ["123", "456"]

    status = client.get("/actions/status").get_json()
    assert status is not None
    assert status["runs"][0]["status"] == "completed"
    assert status["runs"][0]["return_code"] == 0
    assert status["runs"][0]["title"] == "regenerate draft v1 only for 2 job(s)"
    assert any("processing job 123" in message for message in status["runs"][0]["messages"])


def test_actions_run_can_chain_codex_highlighting_after_draft_generation(tmp_path: Path):
    with webapp._ACTION_RUN_LOCK:  # noqa: SLF001
        webapp._ACTION_RUNS.clear()  # noqa: SLF001

    calls = []
    completed = threading.Event()

    def runner(**kwargs):
        calls.append(kwargs)
        webapp._finish_background_action_run(  # noqa: SLF001
            kwargs["run_id"],
            status="completed",
            return_code=0,
        )
        completed.set()

    output_dir = tmp_path / "output"
    database_path = output_dir / "tracking/applications.sqlite3"
    app = create_app(
        database_path=database_path,
        output_dir=output_dir,
        background_action_runner=runner,
    )
    client = app.test_client()

    response = client.post(
        "/actions/run",
        data={
            "regenerate_mode": "draft_resumes",
            "highlight_with_codex": "1",
            "job_id": ["url-123"],
        },
    )

    assert response.status_code == 302
    assert completed.wait(timeout=2)
    assert calls[0]["regenerate_mode"] == "draft_resumes"
    assert calls[0]["highlight_with_codex"] is True

    status = client.get("/actions/status").get_json()
    assert status is not None
    assert status["runs"][0]["title"] == (
        "regenerate draft v1 only for 1 job(s) + "
        "Codex highlight selected resume for 1 job(s)"
    )


def test_actions_run_can_chain_codex_highlighting_after_v2_generation(tmp_path: Path):
    with webapp._ACTION_RUN_LOCK:  # noqa: SLF001
        webapp._ACTION_RUNS.clear()  # noqa: SLF001

    calls = []
    completed = threading.Event()

    def runner(**kwargs):
        calls.append(kwargs)
        webapp._finish_background_action_run(  # noqa: SLF001
            kwargs["run_id"],
            status="completed",
            return_code=0,
        )
        completed.set()

    output_dir = tmp_path / "output"
    database_path = output_dir / "tracking/applications.sqlite3"
    app = create_app(
        database_path=database_path,
        output_dir=output_dir,
        background_action_runner=runner,
    )
    client = app.test_client()

    response = client.post(
        "/actions/run",
        data={
            "regenerate_mode": "resume_variants",
            "highlight_with_codex": "1",
            "job_id": ["url-123"],
        },
    )

    assert response.status_code == 302
    assert completed.wait(timeout=2)
    assert calls[0]["regenerate_mode"] == "resume_variants"
    assert calls[0]["highlight_with_codex"] is True
    assert calls[0]["run_manual"] is False

    status = client.get("/actions/status").get_json()
    assert status is not None
    assert status["runs"][0]["title"] == (
        "run v1 and v2 resume workflow for 1 job(s) + "
        "Codex highlight selected resume for 1 job(s)"
    )


def test_actions_run_can_chain_v2_manual_pass_and_highlighting(tmp_path: Path):
    with webapp._ACTION_RUN_LOCK:  # noqa: SLF001
        webapp._ACTION_RUNS.clear()  # noqa: SLF001

    calls = []
    completed = threading.Event()

    def runner(**kwargs):
        calls.append(kwargs)
        webapp._finish_background_action_run(  # noqa: SLF001
            kwargs["run_id"],
            status="completed",
            return_code=0,
        )
        completed.set()

    output_dir = tmp_path / "output"
    database_path = output_dir / "tracking/applications.sqlite3"
    app = create_app(
        database_path=database_path,
        output_dir=output_dir,
        background_action_runner=runner,
    )
    client = app.test_client()

    response = client.post(
        "/actions/run",
        data={
            "regenerate_mode": "resume_variants_manual_pass",
            "highlight_with_codex": "1",
            "job_id": ["url-123"],
        },
    )

    assert response.status_code == 302
    assert completed.wait(timeout=2)
    assert calls[0]["regenerate_mode"] == "resume_variants"
    assert calls[0]["highlight_with_codex"] is True
    assert calls[0]["run_manual"] is True
    assert calls[0]["manual_pass_profile"].value == "regular"

    status = client.get("/actions/status").get_json()
    assert status is not None
    assert status["runs"][0]["title"] == (
        "run v1 and v2 resume workflow for 1 job(s) + "
        "Codex manual pass resume (regular) for 1 job(s) + "
        "Codex highlight selected resume for 1 job(s)"
    )


def test_actions_run_can_start_v2_refinement(tmp_path: Path):
    with webapp._ACTION_RUN_LOCK:  # noqa: SLF001
        webapp._ACTION_RUNS.clear()  # noqa: SLF001

    calls = []
    completed = threading.Event()

    def runner(**kwargs):
        calls.append(kwargs)
        webapp._finish_background_action_run(  # noqa: SLF001
            kwargs["run_id"],
            status="completed",
            return_code=0,
        )
        completed.set()

    output_dir = tmp_path / "output"
    database_path = output_dir / "tracking/applications.sqlite3"
    app = create_app(
        database_path=database_path,
        output_dir=output_dir,
        background_action_runner=runner,
    )
    client = app.test_client()

    response = client.post(
        "/actions/run",
        data={
            "regenerate_mode": "refine_drafts",
            "job_id": ["url-123"],
        },
    )

    assert response.status_code == 302
    assert completed.wait(timeout=2)
    assert calls[0]["regenerate_mode"] == "refine_drafts"
    assert calls[0]["highlight_with_codex"] is False

    status = client.get("/actions/status").get_json()
    assert status is not None
    assert status["runs"][0]["title"] == "run v2 resume refinement for 1 job(s)"


def test_actions_run_can_start_codex_manual_pass_variant(tmp_path: Path):
    with webapp._ACTION_RUN_LOCK:  # noqa: SLF001
        webapp._ACTION_RUNS.clear()  # noqa: SLF001

    calls = []
    completed = threading.Event()

    def runner(**kwargs):
        calls.append(kwargs)
        webapp._finish_background_action_run(  # noqa: SLF001
            kwargs["run_id"],
            status="completed",
            return_code=0,
        )
        completed.set()

    output_dir = tmp_path / "output"
    database_path = output_dir / "tracking/applications.sqlite3"
    app = create_app(
        database_path=database_path,
        output_dir=output_dir,
        background_action_runner=runner,
    )
    client = app.test_client()

    response = client.post(
        "/actions/run",
        data={
            "regenerate_mode": "manual_pass",
            "job_id": ["url-123"],
        },
    )

    assert response.status_code == 302
    assert completed.wait(timeout=2)
    assert calls[0]["regenerate_mode"] == "manual_pass"
    assert calls[0]["highlight_with_codex"] is False
    assert calls[0]["manual_pass_profile"].value == "regular"

    status = client.get("/actions/status").get_json()
    assert status is not None
    assert status["runs"][0]["title"] == (
        "Codex manual pass resume (regular) for 1 job(s)"
    )


def test_actions_run_can_chain_codex_highlighting_after_manual_pass(tmp_path: Path):
    with webapp._ACTION_RUN_LOCK:  # noqa: SLF001
        webapp._ACTION_RUNS.clear()  # noqa: SLF001

    calls = []
    completed = threading.Event()

    def runner(**kwargs):
        calls.append(kwargs)
        webapp._finish_background_action_run(  # noqa: SLF001
            kwargs["run_id"],
            status="completed",
            return_code=0,
        )
        completed.set()

    output_dir = tmp_path / "output"
    database_path = output_dir / "tracking/applications.sqlite3"
    app = create_app(
        database_path=database_path,
        output_dir=output_dir,
        background_action_runner=runner,
    )
    client = app.test_client()

    response = client.post(
        "/actions/run",
        data={
            "regenerate_mode": "manual_pass",
            "highlight_with_codex": "1",
            "job_id": ["url-123"],
        },
    )

    assert response.status_code == 302
    assert completed.wait(timeout=2)
    assert calls[0]["regenerate_mode"] == "manual_pass"
    assert calls[0]["highlight_with_codex"] is True
    assert calls[0]["run_manual"] is False

    status = client.get("/actions/status").get_json()
    assert status is not None
    assert status["runs"][0]["title"] == (
        "Codex manual pass resume (regular) for 1 job(s) + "
        "Codex highlight selected resume for 1 job(s)"
    )


@pytest.mark.parametrize(
    ("submitted_profile", "expected_profile"),
    [
        (None, "regular"),
        ("economy", "economy"),
        ("regular", "regular"),
        ("premium", "premium"),
    ],
)
def test_actions_manual_pass_profile_allowlist_and_default(
    tmp_path: Path,
    submitted_profile: str | None,
    expected_profile: str,
):
    with webapp._ACTION_RUN_LOCK:  # noqa: SLF001
        webapp._ACTION_RUNS.clear()  # noqa: SLF001

    calls = []
    completed = threading.Event()

    def runner(**kwargs):
        calls.append(kwargs)
        webapp._finish_background_action_run(  # noqa: SLF001
            kwargs["run_id"],
            status="completed",
            return_code=0,
        )
        completed.set()

    output_dir = tmp_path / "output"
    app = create_app(
        database_path=output_dir / "tracking/applications.sqlite3",
        output_dir=output_dir,
        background_action_runner=runner,
    )
    data = {
        "regenerate_mode": "manual_pass",
        "job_id": "url-123",
    }
    if submitted_profile is not None:
        data["manual_pass_profile"] = submitted_profile

    response = app.test_client().post("/actions/run", data=data)

    assert response.status_code == 302
    assert completed.wait(timeout=2)
    assert calls[0]["manual_pass_profile"].value == expected_profile
    assert f"({expected_profile})" in webapp.background_action_snapshots()[0]["title"]


@pytest.mark.parametrize(
    ("path", "data"),
    [
        (
            "/actions/run",
            {
                "regenerate_mode": "manual_pass",
                "job_id": "url-123",
            },
        ),
        (
            "/applications/add/seed",
            {
                "max_jobs": "2",
                "run_v1": "1",
                "run_v2": "1",
                "run_manual": "1",
            },
        ),
        (
            "/applications/add/linkedin",
            {
                "linkedin_url": "https://www.linkedin.com/jobs/view/12345/",
                "run_v2": "1",
                "run_manual": "1",
            },
        ),
        (
            "/applications/add/other",
            {
                "other_url": "https://jobs.example.com/platform-engineer",
                "run_v2": "1",
                "run_manual": "1",
            },
        ),
    ],
)
def test_manual_workflows_reject_invalid_profile_before_background_start(
    tmp_path: Path,
    path: str,
    data: dict[str, str],
):
    with webapp._ACTION_RUN_LOCK:  # noqa: SLF001
        webapp._ACTION_RUNS.clear()  # noqa: SLF001

    calls = []
    output_dir = tmp_path / "output"
    app = create_app(
        database_path=output_dir / "tracking/applications.sqlite3",
        output_dir=output_dir,
        background_action_runner=lambda **kwargs: calls.append(kwargs),
    )
    request_data = {**data, "manual_pass_profile": "gpt-5.6-sol"}
    client = app.test_client()

    response = client.post(path, data=request_data)

    assert response.status_code == 302
    assert calls == []
    assert webapp.background_action_snapshots() == []
    page = client.get(response.headers["Location"])
    assert b"invalid manual-pass profile" in page.data


@pytest.mark.parametrize(
    ("mode", "profile", "highlight", "expected_commands"),
    [
        (
            "manual_pass",
            "premium",
            False,
            [
                [
                    "make",
                    "manual-pass-resumes",
                    "JOB_IDS=url-123",
                    "MANUAL_PASS_PROFILE=premium",
                ],
            ],
        ),
        (
            "resume_variants_manual_pass",
            "economy",
            True,
            [
                [
                    "make",
                    "regenerate-resumes",
                    "JOB_IDS=url-123",
                    "FIRST_DRAFT_FORCE=1",
                ],
                [
                    "make",
                    "manual-pass-resumes",
                    "JOB_IDS=url-123",
                    "MANUAL_PASS_PROFILE=economy",
                ],
                [
                    "make",
                    "highlight-draft-resumes",
                    "JOB_IDS=url-123",
                    "HIGHLIGHT_RESUME_VARIANT=manual",
                ],
            ],
        ),
    ],
)
def test_actions_manual_profiles_reach_exact_workflow_commands(
    tmp_path: Path,
    monkeypatch,
    mode: str,
    profile: str,
    highlight: bool,
    expected_commands: list[list[str]],
):
    with webapp._ACTION_RUN_LOCK:  # noqa: SLF001
        webapp._ACTION_RUNS.clear()  # noqa: SLF001

    commands: list[list[str]] = []
    completed = threading.Event()

    def fake_run_make_command(**kwargs):
        commands.append(kwargs["command"])
        return ""

    def runner(**kwargs):
        webapp._run_background_action(**kwargs)  # noqa: SLF001
        completed.set()

    monkeypatch.setattr(webapp, "_run_make_command", fake_run_make_command)
    output_dir = tmp_path / "output"
    app = create_app(
        database_path=output_dir / "tracking/applications.sqlite3",
        output_dir=output_dir,
        background_action_runner=runner,
    )
    data = {
        "regenerate_mode": mode,
        "manual_pass_profile": profile,
        "job_id": "url-123",
    }
    if highlight:
        data["highlight_with_codex"] = "1"

    response = app.test_client().post("/actions/run", data=data)

    assert response.status_code == 302
    assert completed.wait(timeout=2)
    assert commands == expected_commands


def test_concurrent_manual_profiles_do_not_bleed_commands_or_environment(
    monkeypatch,
):
    with webapp._ACTION_RUN_LOCK:  # noqa: SLF001
        webapp._ACTION_RUNS.clear()  # noqa: SLF001

    monkeypatch.setenv("MANUAL_PASS_PROFILE", "process-wide-sentinel")
    commands_by_run: dict[str, list[list[str]]] = {}
    commands_lock = threading.Lock()
    barrier = threading.Barrier(2)
    completed = {
        "economy": threading.Event(),
        "premium": threading.Event(),
    }

    def fake_run_make_command(**kwargs):
        with commands_lock:
            commands_by_run.setdefault(kwargs["run_id"], []).append(kwargs["command"])
        return ""

    def runner(**kwargs):
        profile = kwargs["manual_pass_profile"].value
        barrier.wait(timeout=2)
        webapp._run_background_action(**kwargs)  # noqa: SLF001
        completed[profile].set()

    monkeypatch.setattr(webapp, "_run_make_command", fake_run_make_command)

    economy_run = webapp.start_background_action(
        regenerate_mode="manual_pass",
        job_ids=["economy-job"],
        manual_pass_profile="economy",
        runner=runner,
    )
    premium_run = webapp.start_background_action(
        regenerate_mode="manual_pass",
        job_ids=["premium-job"],
        manual_pass_profile="premium",
        runner=runner,
    )

    assert completed["economy"].wait(timeout=2)
    assert completed["premium"].wait(timeout=2)
    assert commands_by_run[economy_run.run_id] == [
        [
            "make",
            "manual-pass-resumes",
            "JOB_IDS=economy-job",
            "MANUAL_PASS_PROFILE=economy",
        ]
    ]
    assert commands_by_run[premium_run.run_id] == [
        [
            "make",
            "manual-pass-resumes",
            "JOB_IDS=premium-job",
            "MANUAL_PASS_PROFILE=premium",
        ]
    ]
    assert "premium" not in " ".join(commands_by_run[economy_run.run_id][0])
    assert "economy" not in " ".join(commands_by_run[premium_run.run_id][0])
    assert os.environ["MANUAL_PASS_PROFILE"] == "process-wide-sentinel"


def test_manual_profile_is_attached_only_to_manual_workflow_stage(monkeypatch):
    with webapp._ACTION_RUN_LOCK:  # noqa: SLF001
        webapp._ACTION_RUNS.clear()  # noqa: SLF001

    regenerate_calls: list[dict[str, object]] = []

    def fake_regenerate_action(**kwargs):
        regenerate_calls.append(kwargs)

    monkeypatch.setattr(webapp, "_run_regenerate_action", fake_regenerate_action)
    run = webapp._create_background_action_run(title="profile isolation")  # noqa: SLF001

    webapp._run_background_action(  # noqa: SLF001
        run_id=run.run_id,
        regenerate_mode="resume_variants",
        job_ids=["url-123"],
        run_manual=True,
        manual_pass_profile=webapp.ManualPassProfileKey.PREMIUM,
    )

    assert regenerate_calls[0] == {
        "run_id": run.run_id,
        "regenerate_mode": "resume_variants",
        "job_ids": ["url-123"],
    }
    assert regenerate_calls[1] == {
        "run_id": run.run_id,
        "regenerate_mode": "manual_pass",
        "job_ids": ["url-123"],
        "manual_pass_profile": webapp.ManualPassProfileKey.PREMIUM,
    }


def test_background_action_runs_only_requested_new_workflow(
    tmp_path: Path,
    monkeypatch,
):
    with webapp._ACTION_RUN_LOCK:  # noqa: SLF001
        webapp._ACTION_RUNS.clear()  # noqa: SLF001

    calls: list[tuple[str, str]] = []
    highlight_calls: list[dict[str, object]] = []

    def fake_regenerate_action(**kwargs):
        calls.append(("regenerate", kwargs["regenerate_mode"]))

    def fake_highlight_action(**kwargs):
        calls.append(("highlight", " ".join(kwargs["job_ids"])))
        highlight_calls.append(kwargs)

    monkeypatch.setattr(webapp, "_run_regenerate_action", fake_regenerate_action)
    monkeypatch.setattr(webapp, "_run_highlight_action", fake_highlight_action)

    run = webapp._create_background_action_run(title="generate first draft")  # noqa: SLF001
    webapp._run_background_action(  # noqa: SLF001
        run_id=run.run_id,
        regenerate_mode="draft_resumes",
        job_ids=["url-123"],
    )

    assert calls == [("regenerate", "draft_resumes")]
    status = webapp.background_action_snapshots()[0]
    assert status["status"] == "completed"

    calls.clear()
    run = webapp._create_background_action_run(title="generate first draft")  # noqa: SLF001
    webapp._run_background_action(  # noqa: SLF001
        run_id=run.run_id,
        regenerate_mode="draft_resumes",
        job_ids=["url-123"],
        highlight_with_codex=True,
    )

    assert calls == [("regenerate", "draft_resumes"), ("highlight", "url-123")]
    assert highlight_calls[-1].get("variant_key") is None

    calls.clear()
    run = webapp._create_background_action_run(title="generate draft and v2")  # noqa: SLF001
    webapp._run_background_action(  # noqa: SLF001
        run_id=run.run_id,
        regenerate_mode="resume_variants",
        job_ids=["url-123"],
    )

    assert calls == [("regenerate", "resume_variants")]

    calls.clear()
    run = webapp._create_background_action_run(  # noqa: SLF001
        title="generate draft, v2, and highlight"
    )
    webapp._run_background_action(  # noqa: SLF001
        run_id=run.run_id,
        regenerate_mode="resume_variants",
        job_ids=["url-123"],
        highlight_with_codex=True,
    )

    assert calls == [("regenerate", "resume_variants"), ("highlight", "url-123")]
    assert highlight_calls[-1]["variant_key"] == "v2"

    calls.clear()
    run = webapp._create_background_action_run(  # noqa: SLF001
        title="generate draft, v2, manual, and highlight"
    )
    webapp._run_background_action(  # noqa: SLF001
        run_id=run.run_id,
        regenerate_mode="resume_variants",
        job_ids=["url-123"],
        run_manual=True,
        highlight_with_codex=True,
    )

    assert calls == [
        ("regenerate", "resume_variants"),
        ("regenerate", "manual_pass"),
        ("highlight", "url-123"),
    ]
    assert highlight_calls[-1]["variant_key"] == "manual"

    calls.clear()
    run = webapp._create_background_action_run(title="run v2 refinement")  # noqa: SLF001
    webapp._run_background_action(  # noqa: SLF001
        run_id=run.run_id,
        regenerate_mode="refine_drafts",
        job_ids=["url-123"],
    )

    assert calls == [("regenerate", "refine_drafts")]

    calls.clear()
    run = webapp._create_background_action_run(  # noqa: SLF001
        title="run v2 refinement and highlight"
    )
    webapp._run_background_action(  # noqa: SLF001
        run_id=run.run_id,
        regenerate_mode="refine_drafts",
        job_ids=["url-123"],
        highlight_with_codex=True,
    )

    assert calls == [("regenerate", "refine_drafts"), ("highlight", "url-123")]
    assert highlight_calls[-1]["variant_key"] == "v2"

    calls.clear()
    run = webapp._create_background_action_run(title="regenerate ARO object")  # noqa: SLF001
    webapp._run_background_action(  # noqa: SLF001
        run_id=run.run_id,
        regenerate_mode="aro_objects",
        job_ids=["url-123"],
    )

    assert calls == [("regenerate", "aro_objects")]

    calls.clear()
    run = webapp._create_background_action_run(title="sync draft to ARO")  # noqa: SLF001
    webapp._run_background_action(  # noqa: SLF001
        run_id=run.run_id,
        regenerate_mode="sync_draft_to_aro",
        job_ids=["url-123"],
    )

    assert calls == [("regenerate", "sync_draft_to_aro")]

    calls.clear()
    run = webapp._create_background_action_run(title="Codex highlight selected resume")  # noqa: SLF001
    webapp._run_background_action(  # noqa: SLF001
        run_id=run.run_id,
        regenerate_mode="highlight_drafts",
        job_ids=["url-123"],
        highlight_with_codex=True,
    )

    assert calls == [("regenerate", "highlight_drafts")]

    calls.clear()
    run = webapp._create_background_action_run(title="Codex manual pass resume")  # noqa: SLF001
    webapp._run_background_action(  # noqa: SLF001
        run_id=run.run_id,
        regenerate_mode="manual_pass",
        job_ids=["url-123"],
    )

    assert calls == [("regenerate", "manual_pass")]

    calls.clear()
    run = webapp._create_background_action_run(  # noqa: SLF001
        title="Codex manual pass resume and highlight"
    )
    webapp._run_background_action(  # noqa: SLF001
        run_id=run.run_id,
        regenerate_mode="manual_pass",
        job_ids=["url-123"],
        highlight_with_codex=True,
    )

    assert calls == [("regenerate", "manual_pass"), ("highlight", "url-123")]
    assert highlight_calls[-1]["variant_key"] == "manual"


def test_seed_workflow_runs_selected_make_targets_for_seeded_jobs(monkeypatch):
    with webapp._ACTION_RUN_LOCK:  # noqa: SLF001
        webapp._ACTION_RUNS.clear()  # noqa: SLF001

    commands: list[list[str]] = []

    def fake_run_make_command(**kwargs):
        command = kwargs["command"]
        commands.append(command)
        if command[:2] == ["make", "seed-jobs"]:
            return """
            {
              "jobs_seeded": 2,
              "seeded_applications": [
                {"job_id": "url-123"},
                {"job_id": "url-456"}
              ]
            }
            """
        return ""

    monkeypatch.setattr(webapp, "_run_make_command", fake_run_make_command)

    run = webapp._create_background_action_run(title="seed workflow")  # noqa: SLF001
    webapp._run_seed_workflow_action(  # noqa: SLF001
        run_id=run.run_id,
        max_jobs=3,
        date_posted="past_month",
        run_v1=True,
        run_v2=True,
        run_manual=True,
        run_highlight=True,
    )

    assert commands == [
        ["make", "seed-jobs", "MAX_JOBS=3", "DATE_POSTED=past_month"],
        [
            "make",
            "regenerate-draft-resumes",
            "JOB_IDS=url-123",
            "FIRST_DRAFT_FORCE=1",
        ],
        [
            "make",
            "regenerate-draft-resumes",
            "JOB_IDS=url-456",
            "FIRST_DRAFT_FORCE=1",
        ],
        ["make", "refine-draft-resumes", "JOB_IDS=url-123"],
        ["make", "refine-draft-resumes", "JOB_IDS=url-456"],
        [
            "make",
            "manual-pass-resumes",
            "JOB_IDS=url-123",
            "MANUAL_PASS_PROFILE=regular",
        ],
        [
            "make",
            "manual-pass-resumes",
            "JOB_IDS=url-456",
            "MANUAL_PASS_PROFILE=regular",
        ],
        [
            "make",
            "highlight-draft-resumes",
            "JOB_IDS=url-123",
            "HIGHLIGHT_RESUME_VARIANT=manual",
        ],
        [
            "make",
            "highlight-draft-resumes",
            "JOB_IDS=url-456",
            "HIGHLIGHT_RESUME_VARIANT=manual",
        ],
    ]
    status = webapp.background_action_snapshots()[0]
    assert status["status"] == "completed"
    assert any("Seeded job IDs: url-123 url-456" in line for line in status["messages"])


def test_background_action_continues_batch_after_single_job_failure(monkeypatch):
    with webapp._ACTION_RUN_LOCK:  # noqa: SLF001
        webapp._ACTION_RUNS.clear()  # noqa: SLF001

    calls: list[tuple[str, str]] = []
    highlights: list[tuple[str, object]] = []

    def fake_regenerate_action(**kwargs):
        job_id = kwargs["job_ids"][0]
        regenerate_mode = kwargs["regenerate_mode"]
        calls.append((regenerate_mode, job_id))
        if regenerate_mode == "resume_variants" and job_id == "url-456":
            raise RuntimeError("Oracle experience rewrite timed out")

    def fake_highlight_action(**kwargs):
        job_id = kwargs["job_ids"][0]
        highlights.append((job_id, kwargs.get("variant_key")))

    monkeypatch.setattr(webapp, "_run_regenerate_action", fake_regenerate_action)
    monkeypatch.setattr(webapp, "_run_highlight_action", fake_highlight_action)

    run = webapp._create_background_action_run(title="batch workflow")  # noqa: SLF001
    webapp._run_background_action(  # noqa: SLF001
        run_id=run.run_id,
        regenerate_mode="resume_variants",
        job_ids=["url-123", "url-456", "url-789"],
        run_manual=True,
        highlight_with_codex=True,
    )

    status = webapp.background_action_snapshots()[0]
    assert status["status"] == "completed"
    assert calls == [
        ("resume_variants", "url-123"),
        ("resume_variants", "url-456"),
        ("resume_variants", "url-789"),
        ("manual_pass", "url-123"),
        ("manual_pass", "url-789"),
    ]
    assert highlights == [("url-123", "manual"), ("url-789", "manual")]
    assert any("partial failures" in line for line in status["messages"])
    assert any("url-456" in line and "timed out" in line for line in status["messages"])


def test_background_action_fails_when_every_batch_job_fails(monkeypatch):
    with webapp._ACTION_RUN_LOCK:  # noqa: SLF001
        webapp._ACTION_RUNS.clear()  # noqa: SLF001

    def fake_regenerate_action(**kwargs):
        raise RuntimeError(f"{kwargs['job_ids'][0]} timed out")

    monkeypatch.setattr(webapp, "_run_regenerate_action", fake_regenerate_action)

    run = webapp._create_background_action_run(title="batch workflow")  # noqa: SLF001
    webapp._run_background_action(  # noqa: SLF001
        run_id=run.run_id,
        regenerate_mode="resume_variants",
        job_ids=["url-123", "url-456"],
    )

    status = webapp.background_action_snapshots()[0]
    assert status["status"] == "failed"
    assert any("All workflow jobs failed" in line for line in status["messages"])


def test_seed_workflow_skips_selected_steps_when_no_jobs_seeded(monkeypatch):
    with webapp._ACTION_RUN_LOCK:  # noqa: SLF001
        webapp._ACTION_RUNS.clear()  # noqa: SLF001

    commands: list[list[str]] = []

    def fake_run_make_command(**kwargs):
        commands.append(kwargs["command"])
        return '{"jobs_seeded": 0, "seeded_applications": []}'

    monkeypatch.setattr(webapp, "_run_make_command", fake_run_make_command)

    run = webapp._create_background_action_run(title="seed workflow")  # noqa: SLF001
    webapp._run_seed_workflow_action(  # noqa: SLF001
        run_id=run.run_id,
        max_jobs=3,
        date_posted="past_week",
        run_v1=True,
        run_v2=True,
        run_manual=False,
        run_highlight=False,
    )

    assert commands == [["make", "seed-jobs", "MAX_JOBS=3", "DATE_POSTED=past_week"]]
    status = webapp.background_action_snapshots()[0]
    assert status["status"] == "completed"
    assert any("no new job IDs" in line for line in status["messages"])


def test_add_application_seed_starts_seed_workflow(tmp_path: Path):
    with webapp._ACTION_RUN_LOCK:  # noqa: SLF001
        webapp._ACTION_RUNS.clear()  # noqa: SLF001

    calls = []
    completed = threading.Event()

    def runner(**kwargs):
        calls.append(kwargs)
        webapp._finish_background_action_run(  # noqa: SLF001
            kwargs["run_id"],
            status="completed",
            return_code=0,
        )
        completed.set()

    output_dir = tmp_path / "output"
    database_path = output_dir / "tracking/applications.sqlite3"
    app = create_app(
        database_path=database_path,
        output_dir=output_dir,
        background_action_runner=runner,
    )
    client = app.test_client()

    response = client.post(
        "/applications/add/seed",
        data={
            "max_jobs": "5",
            "date_posted": "past_24_hours",
            "run_v1": "1",
            "run_v2": "1",
            "run_manual": "1",
            "manual_pass_profile": "premium",
            "run_highlight": "1",
            "return_to": "/?q=Platform",
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"] == (
        "/applications/add?return_to=%2F%3Fq%3DPlatform"
    )
    assert completed.wait(timeout=2)
    assert calls[0]["max_jobs"] == 5
    assert calls[0]["date_posted"] == "past_24_hours"
    assert calls[0]["run_v1"] is True
    assert calls[0]["run_v2"] is True
    assert calls[0]["run_manual"] is True
    assert calls[0]["run_highlight"] is True
    assert calls[0]["manual_pass_profile"].value == "premium"

    status = client.get("/actions/status").get_json()
    assert status is not None
    assert status["runs"][0]["title"] == (
        "seed up to 5 job(s) + last 24 hours + v1 draft + v2 refinement + "
        "Codex manual pass (premium) + Codex highlight"
    )


def test_add_application_seed_rejects_invalid_dependencies(tmp_path: Path):
    with webapp._ACTION_RUN_LOCK:  # noqa: SLF001
        webapp._ACTION_RUNS.clear()  # noqa: SLF001

    calls = []

    def runner(**kwargs):
        calls.append(kwargs)

    output_dir = tmp_path / "output"
    database_path = output_dir / "tracking/applications.sqlite3"
    app = create_app(
        database_path=database_path,
        output_dir=output_dir,
        background_action_runner=runner,
    )
    client = app.test_client()

    response = client.post(
        "/applications/add/seed",
        data={"max_jobs": "5", "run_v2": "1", "return_to": "/?q=Platform"},
    )

    assert response.status_code == 302
    assert calls == []
    status = client.get("/actions/status").get_json()
    assert status is not None
    assert status["runs"] == []


def test_add_application_loads_linkedin_job_and_starts_regeneration(
    tmp_path: Path,
    monkeypatch,
):
    with webapp._ACTION_RUN_LOCK:  # noqa: SLF001
        webapp._ACTION_RUNS.clear()  # noqa: SLF001

    async def fake_fetch_linkedin_job_details(linkedin_url: str) -> JobDetails:
        assert linkedin_url == "https://www.linkedin.com/jobs/view/12345/"
        return JobDetails(
            job_id="12345",
            title="Senior Python Engineer",
            company="Acme Corp",
            listed_at="2026-06-05",
            job_url="https://www.linkedin.com/jobs/view/12345",
            description="Raw public JOD with benefits and practical Python work.",
            seniority_level="Mid-Senior level",
        )

    monkeypatch.setattr(
        webapp,
        "_fetch_linkedin_job_details",
        fake_fetch_linkedin_job_details,
    )
    monkeypatch.setattr(
        webapp,
        "_clean_prompt_job_description",
        lambda description: "Clean prompt JOD with practical Python work.",
    )

    calls = []
    completed = threading.Event()

    def runner(**kwargs):
        calls.append(kwargs)
        webapp._append_background_action_message(  # noqa: SLF001
            kwargs["run_id"],
            "processing job 12345",
        )
        webapp._finish_background_action_run(  # noqa: SLF001
            kwargs["run_id"],
            status="completed",
            return_code=0,
        )
        completed.set()

    output_dir = tmp_path / "output"
    database_path = output_dir / "tracking/applications.sqlite3"
    app = create_app(
        database_path=database_path,
        output_dir=output_dir,
        background_action_runner=runner,
    )
    client = app.test_client()

    add_page = client.get("/applications/add?return_to=/?q=Platform")
    add_html = add_page.data.decode()
    assert add_page.status_code == 200
    assert "Seed jobs" in add_html
    assert "LinkedIn URLs" in add_html
    assert "Other URLs" in add_html
    assert 'action="/applications/add/seed"' in add_html
    assert 'action="/applications/add/linkedin"' in add_html
    assert 'action="/applications/add/other"' in add_html
    assert add_html.index('action="/applications/add/seed"') < add_html.index(
        'action="/applications/add/linkedin"'
    )
    assert 'name="max_jobs"' in add_html
    assert 'value="5"' in add_html
    assert 'name="date_posted"' in add_html
    assert 'value="past_24_hours"' in add_html
    assert 'value="past_week"' in add_html
    assert 'value="past_month"' in add_html
    assert "Last 24 hours" in add_html
    assert "Past week" in add_html
    assert "Past month" in add_html
    add_soup = BeautifulSoup(add_html, "html.parser")
    checked_date = add_soup.find("input", {"name": "date_posted", "checked": True})
    assert checked_date is not None
    assert checked_date["value"] == "past_week"
    assert 'name="run_v1" value="1" checked' in add_html
    assert 'name="run_v2" value="1" checked' in add_html
    assert 'name="run_manual" value="1"' in add_html
    assert 'name="run_highlight" value="1"' in add_html
    assert 'textarea' in add_html
    assert 'name="linkedin_url"' in add_html
    assert 'name="other_url"' in add_html
    assert "Run Codex bullet highlighting after resume generation" in add_html
    assert 'name="highlight_with_codex" value="1" checked' in add_html
    url_run_v2_inputs = add_soup.select(
        'form[action="/applications/add/linkedin"] input[name="run_v2"], '
        'form[action="/applications/add/other"] input[name="run_v2"]'
    )
    assert len(url_run_v2_inputs) == 2
    assert [input_tag.get("value") for input_tag in url_run_v2_inputs] == ["1", "1"]
    url_run_manual_inputs = add_soup.select(
        'form[action="/applications/add/linkedin"] input[name="run_manual"], '
        'form[action="/applications/add/other"] input[name="run_manual"]'
    )
    assert len(url_run_manual_inputs) == 2
    assert [input_tag.get("disabled") for input_tag in url_run_manual_inputs] == [
        "",
        "",
    ]
    forms_by_action = {
        form["action"]: form
        for form in add_soup.select("form[action]")
    }
    assert set(forms_by_action) == {
        "/applications/add/seed",
        "/applications/add/linkedin",
        "/applications/add/other",
    }
    for action, form in forms_by_action.items():
        profile_control = form.select_one("[data-manual-pass-profile-control]")
        assert profile_control is not None, action
        assert profile_control.has_attr("hidden"), action
        _assert_manual_pass_profile_select(
            profile_control.select_one("select[name='manual_pass_profile']")
        )

    seed_form = forms_by_action["/applications/add/seed"]
    assert seed_form.select_one('input[name="run_v1"]').has_attr("checked")
    assert seed_form.select_one('input[name="run_v2"]').has_attr("checked")
    seed_manual = seed_form.select_one('input[name="run_manual"]')
    assert seed_manual is not None
    assert not seed_manual.has_attr("checked")
    assert not seed_manual.has_attr("disabled")

    for action in ("/applications/add/linkedin", "/applications/add/other"):
        url_form = forms_by_action[action]
        assert not url_form.select_one('input[name="run_v2"]').has_attr("checked")
        manual_input = url_form.select_one('input[name="run_manual"]')
        assert manual_input is not None
        assert not manual_input.has_attr("checked")
        assert manual_input.has_attr("disabled")
        highlight_input = url_form.select_one(
            'input[name="highlight_with_codex"]'
        )
        assert highlight_input is not None
        assert highlight_input.has_attr("checked")

    assert add_html.count("Economy — Terra / High") == 3
    assert add_html.count("Regular — Sol / High (Recommended)") == 3
    assert add_html.count("Premium — Sol / X-High") == 3
    assert add_html.count("Run v2 refinement") == 3
    assert add_html.count("Run Codex manual pass") == 3

    response = client.post(
        "/applications/add/linkedin",
        data={
            "linkedin_url": "https://www.linkedin.com/jobs/view/12345/",
            "return_to": "/?q=Platform",
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"] == (
        "/applications/add?return_to=%2F%3Fq%3DPlatform"
    )
    assert completed.wait(timeout=2)
    assert calls
    assert "sync_requested" not in calls[0]
    assert calls[0]["regenerate_mode"] == "draft_resumes"
    assert calls[0]["highlight_with_codex"] is False
    assert calls[0]["job_ids"] == ["12345"]

    with webapp.connect_database(database_path) as connection:
        row = connection.execute(
            """
            SELECT company, job_title, linkedin_url, job_description,
                   prompt_job_description, date_posted, experience_level
            FROM applications
            WHERE job_id = '12345'
            """
        ).fetchone()

    assert row["company"] == "Acme Corp"
    assert row["job_title"] == "Senior Python Engineer"
    assert row["linkedin_url"] == "https://www.linkedin.com/jobs/view/12345"
    assert row["job_description"] == "Raw public JOD with benefits and practical Python work."
    assert row["prompt_job_description"] == "Clean prompt JOD with practical Python work."
    assert row["date_posted"] == "2026-06-05"
    assert row["experience_level"] == "Mid-Senior level"


def test_add_application_loads_batch_linkedin_urls_and_starts_one_workflow(
    tmp_path: Path,
    monkeypatch,
):
    with webapp._ACTION_RUN_LOCK:  # noqa: SLF001
        webapp._ACTION_RUNS.clear()  # noqa: SLF001

    details_by_url = {
        "https://www.linkedin.com/jobs/view/12345/": JobDetails(
            job_id="12345",
            title="Senior Python Engineer",
            company="Acme Corp",
            listed_at="2026-06-05",
            job_url="https://www.linkedin.com/jobs/view/12345",
            description="Raw public JOD with practical Python work.",
        ),
        "https://www.linkedin.com/jobs/view/67890/": JobDetails(
            job_id="67890",
            title="Staff Platform Engineer",
            company="Example Corp",
            listed_at="2026-06-06",
            job_url="https://www.linkedin.com/jobs/view/67890",
            description="Raw public JOD with platform engineering work.",
        ),
    }

    async def fake_fetch_linkedin_job_details(linkedin_url: str) -> JobDetails:
        return details_by_url[linkedin_url]

    monkeypatch.setattr(
        webapp,
        "_fetch_linkedin_job_details",
        fake_fetch_linkedin_job_details,
    )
    monkeypatch.setattr(
        webapp,
        "_clean_prompt_job_description",
        lambda description: f"Clean {description}",
    )

    calls = []
    completed = threading.Event()

    def runner(**kwargs):
        calls.append(kwargs)
        webapp._finish_background_action_run(  # noqa: SLF001
            kwargs["run_id"],
            status="completed",
            return_code=0,
        )
        completed.set()

    output_dir = tmp_path / "output"
    database_path = output_dir / "tracking/applications.sqlite3"
    app = create_app(
        database_path=database_path,
        output_dir=output_dir,
        background_action_runner=runner,
    )
    client = app.test_client()

    response = client.post(
        "/applications/add/linkedin",
        data={
            "linkedin_url": (
                "https://www.linkedin.com/jobs/view/12345/,\n"
                "https://www.linkedin.com/jobs/view/67890/"
            ),
            "run_v2": "1",
            "run_manual": "1",
            "highlight_with_codex": "1",
        },
    )

    assert response.status_code == 302
    assert completed.wait(timeout=2)
    assert calls[0]["regenerate_mode"] == "resume_variants"
    assert calls[0]["run_manual"] is True
    assert calls[0]["highlight_with_codex"] is True
    assert calls[0]["job_ids"] == ["12345", "67890"]

    with webapp.connect_database(database_path) as connection:
        rows = connection.execute(
            "SELECT job_id FROM applications ORDER BY job_id"
        ).fetchall()
    assert [row["job_id"] for row in rows] == ["12345", "67890"]

    html = client.get("/applications/add").data.decode()
    assert "Added 2 LinkedIn job(s)." in html
    assert "Failed" not in html


def test_add_application_linkedin_rejects_manual_without_v2(
    tmp_path: Path,
    monkeypatch,
):
    with webapp._ACTION_RUN_LOCK:  # noqa: SLF001
        webapp._ACTION_RUNS.clear()  # noqa: SLF001

    calls = []

    async def fake_fetch_linkedin_job_details(linkedin_url: str) -> JobDetails:
        calls.append(linkedin_url)
        return JobDetails(
            job_id="12345",
            title="Senior Python Engineer",
            company="Acme Corp",
            job_url="https://www.linkedin.com/jobs/view/12345",
            description="Raw public JOD.",
        )

    monkeypatch.setattr(
        webapp,
        "_fetch_linkedin_job_details",
        fake_fetch_linkedin_job_details,
    )

    output_dir = tmp_path / "output"
    database_path = output_dir / "tracking/applications.sqlite3"
    app = create_app(database_path=database_path, output_dir=output_dir)
    client = app.test_client()

    response = client.post(
        "/applications/add/linkedin",
        data={
            "linkedin_url": "https://www.linkedin.com/jobs/view/12345/",
            "run_manual": "1",
        },
    )

    assert response.status_code == 302
    assert calls == []
    html = client.get("/applications/add").data.decode()
    assert "Run v2 refinement must be selected before Codex manual pass" in html


def test_add_application_linkedin_can_run_v2_before_highlighting(
    tmp_path: Path,
    monkeypatch,
):
    with webapp._ACTION_RUN_LOCK:  # noqa: SLF001
        webapp._ACTION_RUNS.clear()  # noqa: SLF001

    async def fake_fetch_linkedin_job_details(linkedin_url: str) -> JobDetails:
        assert linkedin_url == "https://www.linkedin.com/jobs/view/67890/"
        return JobDetails(
            job_id="67890",
            title="AI Platform Engineer",
            company="Acme AI",
            listed_at="2026-07-01",
            job_url="https://www.linkedin.com/jobs/view/67890",
            description="Raw public JOD with AI platform automation work.",
            seniority_level="Senior",
        )

    monkeypatch.setattr(
        webapp,
        "_fetch_linkedin_job_details",
        fake_fetch_linkedin_job_details,
    )
    monkeypatch.setattr(
        webapp,
        "_clean_prompt_job_description",
        lambda description: "Clean prompt JOD with AI platform automation work.",
    )

    calls = []
    completed = threading.Event()

    def runner(**kwargs):
        calls.append(kwargs)
        webapp._finish_background_action_run(  # noqa: SLF001
            kwargs["run_id"],
            status="completed",
            return_code=0,
        )
        completed.set()

    output_dir = tmp_path / "output"
    database_path = output_dir / "tracking/applications.sqlite3"
    app = create_app(
        database_path=database_path,
        output_dir=output_dir,
        background_action_runner=runner,
    )
    client = app.test_client()

    response = client.post(
        "/applications/add/linkedin",
        data={
            "linkedin_url": "https://www.linkedin.com/jobs/view/67890/",
            "run_v2": "1",
            "highlight_with_codex": "1",
        },
    )

    assert response.status_code == 302
    assert completed.wait(timeout=2)
    assert calls
    assert calls[0]["regenerate_mode"] == "resume_variants"
    assert calls[0]["highlight_with_codex"] is True
    assert calls[0]["job_ids"] == ["67890"]

    status = client.get("/actions/status").get_json()
    assert status is not None
    assert status["runs"][0]["title"] == (
        "run v1 and v2 resume workflow for 1 job(s) + "
        "Codex highlight selected resume for 1 job(s)"
    )


def test_add_application_loads_other_job_url_and_starts_regeneration(
    tmp_path: Path,
    monkeypatch,
):
    with webapp._ACTION_RUN_LOCK:  # noqa: SLF001
        webapp._ACTION_RUNS.clear()  # noqa: SLF001

    async def fake_fetch_generic_job_details(job_url: str) -> JobDetails:
        assert job_url == "https://jobs.example.com/staff-engineer"
        return JobDetails(
            job_id="url-abc123def456",
            title="Staff Platform Engineer",
            company="Example Jobs",
            listed_at="2026-06-14",
            job_url="https://jobs.example.com/staff-engineer",
            description="Raw generic JOD with platform reliability and secure API work.",
            seniority_level="Senior",
            source="generic_url",
        )

    monkeypatch.setattr(
        webapp,
        "_fetch_generic_job_details",
        fake_fetch_generic_job_details,
    )
    monkeypatch.setattr(
        webapp,
        "_clean_prompt_job_description",
        lambda description: "Clean generic JOD with platform reliability.",
    )

    calls = []
    completed = threading.Event()

    def runner(**kwargs):
        calls.append(kwargs)
        webapp._finish_background_action_run(  # noqa: SLF001
            kwargs["run_id"],
            status="completed",
            return_code=0,
        )
        completed.set()

    output_dir = tmp_path / "output"
    database_path = output_dir / "tracking/applications.sqlite3"
    app = create_app(
        database_path=database_path,
        output_dir=output_dir,
        background_action_runner=runner,
    )
    client = app.test_client()

    response = client.post(
        "/applications/add/other",
        data={
            "other_url": "https://jobs.example.com/staff-engineer",
            "return_to": "/?status=No",
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/applications/add?return_to=%2F%3Fstatus%3DNo"
    assert completed.wait(timeout=2)
    assert calls
    assert "sync_requested" not in calls[0]
    assert calls[0]["regenerate_mode"] == "draft_resumes"
    assert calls[0]["highlight_with_codex"] is False
    assert calls[0]["job_ids"] == ["url-abc123def456"]

    with webapp.connect_database(database_path) as connection:
        row = connection.execute(
            """
            SELECT company, job_title, linkedin_url, job_description,
                   prompt_job_description, date_posted, experience_level
            FROM applications
            WHERE job_id = 'url-abc123def456'
            """
        ).fetchone()

    assert row["company"] == "Example Jobs"
    assert row["job_title"] == "Staff Platform Engineer"
    assert row["linkedin_url"] == "https://jobs.example.com/staff-engineer"
    assert row["job_description"] == (
        "Raw generic JOD with platform reliability and secure API work."
    )
    assert row["prompt_job_description"] == "Clean generic JOD with platform reliability."
    assert row["date_posted"] == "2026-06-14"
    assert row["experience_level"] == "Senior"


def test_add_application_other_url_batch_continues_after_partial_failure(
    tmp_path: Path,
    monkeypatch,
):
    with webapp._ACTION_RUN_LOCK:  # noqa: SLF001
        webapp._ACTION_RUNS.clear()  # noqa: SLF001

    async def fake_fetch_generic_job_details(job_url: str) -> JobDetails:
        if job_url == "https://jobs.example.com/bad":
            raise ValueError("No usable job description was found at that URL.")
        return JobDetails(
            job_id="url-good123",
            title="Staff Platform Engineer",
            company="Example Jobs",
            listed_at="2026-06-14",
            job_url=job_url,
            description="Raw generic JOD with platform reliability and secure API work.",
            seniority_level="Senior",
            source="generic_url",
        )

    monkeypatch.setattr(
        webapp,
        "_fetch_generic_job_details",
        fake_fetch_generic_job_details,
    )
    monkeypatch.setattr(
        webapp,
        "_clean_prompt_job_description",
        lambda description: "Clean generic JOD with platform reliability.",
    )

    calls = []
    completed = threading.Event()

    def runner(**kwargs):
        calls.append(kwargs)
        webapp._finish_background_action_run(  # noqa: SLF001
            kwargs["run_id"],
            status="completed",
            return_code=0,
        )
        completed.set()

    output_dir = tmp_path / "output"
    database_path = output_dir / "tracking/applications.sqlite3"
    app = create_app(
        database_path=database_path,
        output_dir=output_dir,
        background_action_runner=runner,
    )
    client = app.test_client()

    response = client.post(
        "/applications/add/other",
        data={
            "other_url": (
                "https://jobs.example.com/platform-engineer, "
                "https://jobs.example.com/bad"
            ),
            "run_v2": "1",
            "highlight_with_codex": "1",
        },
    )

    assert response.status_code == 302
    assert completed.wait(timeout=2)
    assert calls[0]["regenerate_mode"] == "resume_variants"
    assert calls[0]["run_manual"] is False
    assert calls[0]["highlight_with_codex"] is True
    assert calls[0]["job_ids"] == ["url-good123"]

    html = client.get("/applications/add").data.decode()
    assert "Added 1 job URL(s)." in html
    assert "Failed 1 URL(s)" in html
    assert "No usable job description" in html


def test_add_application_other_url_can_run_v2_before_highlighting(
    tmp_path: Path,
    monkeypatch,
):
    with webapp._ACTION_RUN_LOCK:  # noqa: SLF001
        webapp._ACTION_RUNS.clear()  # noqa: SLF001

    async def fake_fetch_generic_job_details(job_url: str) -> JobDetails:
        assert job_url == "https://jobs.example.com/ai-platform"
        return JobDetails(
            job_id="url-fedcba987654",
            title="AI Platform Engineer",
            company="Example AI Jobs",
            listed_at="2026-07-02",
            job_url="https://jobs.example.com/ai-platform",
            description="Raw generic JOD with AI platform and reliability work.",
            seniority_level="Staff",
            source="generic_url",
        )

    monkeypatch.setattr(
        webapp,
        "_fetch_generic_job_details",
        fake_fetch_generic_job_details,
    )
    monkeypatch.setattr(
        webapp,
        "_clean_prompt_job_description",
        lambda description: "Clean generic JOD with AI platform work.",
    )

    calls = []
    completed = threading.Event()

    def runner(**kwargs):
        calls.append(kwargs)
        webapp._finish_background_action_run(  # noqa: SLF001
            kwargs["run_id"],
            status="completed",
            return_code=0,
        )
        completed.set()

    output_dir = tmp_path / "output"
    database_path = output_dir / "tracking/applications.sqlite3"
    app = create_app(
        database_path=database_path,
        output_dir=output_dir,
        background_action_runner=runner,
    )
    client = app.test_client()

    response = client.post(
        "/applications/add/other",
        data={
            "other_url": "https://jobs.example.com/ai-platform",
            "run_v2": "1",
            "highlight_with_codex": "1",
        },
    )

    assert response.status_code == 302
    assert completed.wait(timeout=2)
    assert calls
    assert calls[0]["regenerate_mode"] == "resume_variants"
    assert calls[0]["highlight_with_codex"] is True
    assert calls[0]["job_ids"] == ["url-fedcba987654"]

    status = client.get("/actions/status").get_json()
    assert status is not None
    assert status["runs"][0]["title"] == (
        "run v1 and v2 resume workflow for 1 job(s) + "
        "Codex highlight selected resume for 1 job(s)"
    )


@pytest.mark.parametrize(
    (
        "path",
        "url_field",
        "url",
        "add_function_name",
        "job_id",
        "profile",
    ),
    [
        (
            "/applications/add/linkedin",
            "linkedin_url",
            "https://www.linkedin.com/jobs/view/12345/",
            "add_linkedin_application_from_url",
            "12345",
            "premium",
        ),
        (
            "/applications/add/other",
            "other_url",
            "https://jobs.example.com/platform-engineer",
            "add_generic_application_from_url",
            "url-platform",
            "economy",
        ),
    ],
)
def test_add_url_manual_profiles_reach_exact_workflow_commands(
    tmp_path: Path,
    monkeypatch,
    path: str,
    url_field: str,
    url: str,
    add_function_name: str,
    job_id: str,
    profile: str,
):
    with webapp._ACTION_RUN_LOCK:  # noqa: SLF001
        webapp._ACTION_RUNS.clear()  # noqa: SLF001

    monkeypatch.setattr(
        webapp,
        add_function_name,
        lambda **_kwargs: job_id,
    )
    commands: list[list[str]] = []
    completed = threading.Event()

    def fake_run_make_command(**kwargs):
        commands.append(kwargs["command"])
        return ""

    def runner(**kwargs):
        webapp._run_background_action(**kwargs)  # noqa: SLF001
        completed.set()

    monkeypatch.setattr(webapp, "_run_make_command", fake_run_make_command)
    output_dir = tmp_path / "output"
    app = create_app(
        database_path=output_dir / "tracking/applications.sqlite3",
        output_dir=output_dir,
        background_action_runner=runner,
    )

    response = app.test_client().post(
        path,
        data={
            url_field: url,
            "run_v2": "1",
            "run_manual": "1",
            "manual_pass_profile": profile,
            "highlight_with_codex": "1",
        },
    )

    assert response.status_code == 302
    assert completed.wait(timeout=2)
    assert commands == [
        [
            "make",
            "regenerate-resumes",
            f"JOB_IDS={job_id}",
            "FIRST_DRAFT_FORCE=1",
        ],
        [
            "make",
            "manual-pass-resumes",
            f"JOB_IDS={job_id}",
            f"MANUAL_PASS_PROFILE={profile}",
        ],
        [
            "make",
            "highlight-draft-resumes",
            f"JOB_IDS={job_id}",
            "HIGHLIGHT_RESUME_VARIANT=manual",
        ],
    ]
    status = webapp.background_action_snapshots()[0]
    assert status["status"] == "completed"
    assert f"Codex manual pass resume ({profile})" in status["title"]


def _edit_form_data(html: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form", {"action": "/resumes/123/edit"})
    assert form is not None
    data: dict[str, str] = {}
    for field in form.find_all(["input", "textarea"]):
        name = field.get("name")
        if not name:
            continue
        if field.name == "textarea":
            data[name] = field.text
            continue
        field_type = str(field.get("type") or "text").lower()
        if field_type == "checkbox":
            if field.has_attr("checked"):
                data[name] = str(field.get("value") or "on")
            continue
        data[name] = str(field.get("value") or "")
    return data


def _sample_application_resume_yaml(*, paragraph: str, bullet: str) -> str:
    return f"""schema_version: test
header_top:
  line_1_name_header_text: Max Perkhounkov
  line_2_header_text: ''
  line_3_applicant_info_text: max@example.com
  contact_items:
  - max@example.com
  links: []
professional_summary:
  render: true
  header_text: Professional Summary
  paragraph: {paragraph}
  summary_note: ''
core_technical_skills:
  render: true
  header_text: Core Technical Skills
  bullet_points:
  - order: 1
    category: Platform Engineering
    items:
      primary:
      - Python
      - AWS
      additional:
      - authentication
      - Java
    jod_matched_items:
    - authentication
professional_experience:
  render: true
  header_text: Professional Experience
  jobs:
  - order: 1
    render: true
    line_1:
      company_name_text: Example Co
      position_name_text: Senior Engineer
      position_dates_text: 2020 - Present
    line_2:
      position_intro_text: Platform engineering role.
    bullet_points:
    - order: 1
      render: true
      text: {bullet}
education:
  render: true
  header_text: Education
  entries:
  - order: 1
    render: true
    line_1:
      institution_name_text: University
    line_2:
      degree_name_text: BS Physics
      degree_dates_text: 2009 - 2013
    bullet_points:
    - order: 1
      render: true
      text: Applied math coursework.
certifications:
  render: true
  header_text: Certifications
  bullet_points:
  - order: 1
    render: true
    text: OCI Engineer
portfolio:
  render: true
  header_text: Portfolio
  projects:
  - order: 1
    render: true
    title_text: LinkedIn Career MCP
    url: https://github.com/mperkhou/linkedin-career-mcp
    description_text: Resume automation workflow.
"""


def _pdf_bytes(text: str) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    text_object = pdf.beginText(40, 760)
    for line in text.strip().splitlines():
        text_object.textLine(line.strip())
    pdf.drawText(text_object)
    pdf.save()
    return buffer.getvalue()
