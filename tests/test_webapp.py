import sqlite3
import threading
from pathlib import Path

from openpyxl import Workbook, load_workbook

from linkedin_career_mcp import webapp
from linkedin_career_mcp.webapp import create_app, import_output_artifacts


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
                'output/resumes/resume.pdf', 'No',
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
    assert "cover_letter_filename" in columns
    assert "cover_letter_content" in columns
    assert "source_cover_letter_path" in columns
    assert "date_matched" in columns
    assert "date_posted" in columns
    assert "experience_level" in columns
    assert "ats_score" in columns
    assert "ats_parsing_score" in columns
    assert "ats_keyword_score" in columns
    assert "ats_semantic_score" in columns
    assert "ats_formatting_risk" in columns
    assert "ats_missing_terms" in columns
    with webapp.connect_database(database_path) as connection:
        row = connection.execute(
            """
            SELECT date_matched, date_posted
            FROM applications
            WHERE job_id = '123'
            """
        ).fetchone()
    assert row["date_matched"] == "2026-06-08T10:00:00+00:00"
    assert row["date_posted"] is None


def test_import_output_artifacts_stores_workbook_rows_and_artifact_blobs(
    tmp_path: Path,
    monkeypatch,
):
    output_dir = tmp_path / "output"
    resume_path = (
        output_dir
        / "resumes"
        / "Example_Co"
        / "123_senior_engineer"
        / "mp_resume_senior_engineer.pdf"
    )
    resume_path.parent.mkdir(parents=True)
    resume_path.write_bytes(b"%PDF-1.4 fake pdf")
    cover_letter_path = (
        output_dir
        / "cover_letters"
        / "Example_Co"
        / "123_senior_engineer"
        / "mp_cover_letter_senior_engineer.pdf"
    )
    cover_letter_path.parent.mkdir(parents=True)
    cover_letter_path.write_bytes(b"%PDF-1.4 fake cover")

    tracking_path = output_dir / "tracking/read_applications/linkedin_applications.xlsx"
    tracking_path.parent.mkdir(parents=True)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Applications"
    sheet.append(
        [
            "job_id",
            "company",
            "job_title",
            "linkedin_url",
            "customized_resume",
            "cover_letter",
            "applied_to",
            "date_applied",
        ]
    )
    sheet.append(
        [
            "123",
            "Example Co",
            "Senior Engineer",
            "https://www.linkedin.com/jobs/view/123",
            str(resume_path.relative_to(tmp_path)),
            str(cover_letter_path.relative_to(tmp_path)),
            "No",
            "",
        ]
    )
    workbook.save(tracking_path)

    database_path = output_dir / "tracking/applications.sqlite3"
    result = import_output_artifacts(output_dir=output_dir, database_path=database_path)

    assert result.rows_seen == 1
    assert result.rows_imported == 1
    assert result.missing_resumes == 0
    assert result.missing_cover_letters == 0
    assert database_path.exists()
    webapp.upsert_application_artifact(
        database_path=database_path,
        job_id="123",
        company="Example Co",
        job_title="Senior Engineer",
        linkedin_url="https://www.linkedin.com/jobs/view/123",
        resume_path=resume_path,
        cover_letter_path=cover_letter_path,
        job_description="Full parsed JOD with mission boilerplate and role requirements.",
        prompt_job_description="Clean prompt JOD with role requirements.",
        date_posted="2026-06-07T12:00:00Z",
        experience_level="Mid-Senior level",
    )
    with webapp.connect_database(database_path) as connection:
        score_row = connection.execute(
            """
            SELECT ats_score, ats_parsing_score, ats_keyword_score,
                   ats_semantic_score, ats_formatting_risk, ats_missing_terms,
                   experience_level
            FROM applications
            WHERE job_id = '123'
            """
        ).fetchone()
    assert score_row["ats_score"] is not None
    assert score_row["ats_formatting_risk"] in {"Low", "Medium", "High"}
    assert score_row["ats_missing_terms"] is not None
    assert score_row["experience_level"] == "Mid-Senior level"

    app = create_app(database_path=database_path, output_dir=output_dir)
    client = app.test_client()

    index = client.get("/")
    assert index.status_code == 200
    html = index.data.decode()
    assert b"/descriptions/123" in index.data
    assert b"Compare descriptions" in index.data
    assert b"Cover Letter" in index.data
    assert b"/cover-letters/123" in index.data
    assert 'action="/resumes/123/copy-to-downloads"' in html
    assert 'action="/cover-letters/123/copy-to-downloads"' in html
    assert 'id="actions-form"' in html
    assert 'action="/actions/run"' in html
    assert 'id="action-sync"' in html
    assert "Sync from output" in html
    assert 'id="action-regenerate"' in html
    assert "Regenerate docs" in html
    assert "Cover letters" in html
    assert "Resumes" in html
    assert 'id="action-status"' in html
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
    assert b"Mid-Senior level" in index.data
    assert b'id="company-sort"' in index.data
    assert b'id="matched-sort"' in index.data
    assert b'id="ats-sort"' in index.data
    assert b'data-company-sort="Example Co"' in index.data
    assert b'data-matched-sort=' in index.data
    assert b"data-ats-sort=" in index.data
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

    descriptions = client.get("/descriptions/123")
    assert descriptions.status_code == 200
    assert b"Parsed Job Description" in descriptions.data
    assert b"Prompt Job Description" in descriptions.data
    assert b"Full parsed JOD with mission boilerplate and role requirements." in descriptions.data
    assert b"Clean prompt JOD with role requirements." in descriptions.data

    db_resume = client.get("/resumes/123")
    assert db_resume.status_code == 200
    assert db_resume.data == b"%PDF-1.4 fake pdf"

    resume_download = client.get("/resumes/123/download")
    assert resume_download.status_code == 200
    assert resume_download.data == b"%PDF-1.4 fake pdf"
    assert "attachment" in resume_download.headers["Content-Disposition"]

    db_cover_letter = client.get("/cover-letters/123")
    assert db_cover_letter.status_code == 200
    assert db_cover_letter.data == b"%PDF-1.4 fake cover"

    cover_letter_download = client.get("/cover-letters/123/download")
    assert cover_letter_download.status_code == 200
    assert cover_letter_download.data == b"%PDF-1.4 fake cover"
    assert "attachment" in cover_letter_download.headers["Content-Disposition"]

    downloads_dir = tmp_path / "Downloads"
    downloads_dir.mkdir()
    downloaded_resume = downloads_dir / "mp_resume_senior_engineer.pdf"
    downloaded_cover_letter = downloads_dir / "mp_cover_letter_senior_engineer.pdf"
    unrelated_pdf = downloads_dir / "other_resume.pdf"
    monkeypatch.setenv("HOME", str(tmp_path))

    resume_copy = client.post("/resumes/123/copy-to-downloads")
    assert resume_copy.status_code == 302
    assert downloaded_resume.read_bytes() == b"%PDF-1.4 fake pdf"

    cover_letter_copy = client.post("/cover-letters/123/copy-to-downloads")
    assert cover_letter_copy.status_code == 302
    assert downloaded_cover_letter.read_bytes() == b"%PDF-1.4 fake cover"

    copy_index = client.get("/")
    assert b"Copied resume to ~/Downloads/mp_resume_senior_engineer.pdf." in copy_index.data
    assert (
        b"Copied cover letter to ~/Downloads/mp_cover_letter_senior_engineer.pdf."
        in copy_index.data
    )

    unrelated_pdf.write_bytes(b"other")

    yes_response = client.post(
        "/applications/123",
        data={"applied_to": "Yes", "date_applied": "2026-06-08", "notes": ""},
    )
    assert yes_response.status_code == 302
    assert not downloaded_resume.exists()
    assert not downloaded_cover_letter.exists()
    assert unrelated_pdf.exists()

    update_response = client.post(
        "/applications/123",
        data={"applied_to": "N/A", "date_applied": "", "notes": "Skip this one"},
    )
    assert update_response.status_code == 302
    refreshed_index = client.get("/")
    assert b'N/A: 1' in refreshed_index.data

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

    rejected_response = client.post(
        "/applications/123",
        data={"applied_to": "Rejected", "date_applied": "", "notes": "Closed out"},
    )
    assert rejected_response.status_code == 302
    rejected_index = client.get("/")
    assert b"Rejected: 1" in rejected_index.data
    assert b'data-status="Rejected"' in rejected_index.data

    output_resume = client.get(
        "/output/resumes/Example_Co/123_senior_engineer/mp_resume_senior_engineer.pdf"
    )
    assert output_resume.status_code == 200
    assert output_resume.data == b"%PDF-1.4 fake pdf"

    output_cover_letter = client.get(
        "/output/cover_letters/Example_Co/123_senior_engineer/mp_cover_letter_senior_engineer.pdf"
    )
    assert output_cover_letter.status_code == 200
    assert output_cover_letter.data == b"%PDF-1.4 fake cover"

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

    response = client.post("/applications/delete", data={"job_id": "123"})
    assert response.status_code == 302
    assert client.get("/resumes/123").status_code == 404
    assert client.get("/cover-letters/123").status_code == 404

    workbook = load_workbook(tracking_path)
    sheet = workbook.active
    assert sheet.max_row == 1


def test_regenerate_make_command_maps_modes_to_make_targets():
    assert webapp._regenerate_make_command(  # noqa: SLF001
        regenerate_mode="all",
        job_ids=["123", "456"],
    ) == ["make", "regenerate-all", "JOB_IDS=123 456"]
    assert webapp._regenerate_make_command(  # noqa: SLF001
        regenerate_mode="resumes",
        job_ids=["123"],
    ) == ["make", "regenerate-resumes", "JOB_IDS=123"]
    assert webapp._regenerate_make_command(  # noqa: SLF001
        regenerate_mode="cover_letters",
        job_ids=["123"],
    ) == ["make", "regenerate-cover-letters", "JOB_IDS=123"]


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
            "action_sync": "1",
            "action_regenerate": "1",
            "regenerate_mode": "all",
            "job_id": ["123", "123", "456"],
            "return_to": "/?q=Example",
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/?q=Example"
    assert completed.wait(timeout=2)
    assert calls
    assert calls[0]["sync_requested"] is True
    assert calls[0]["regenerate_mode"] == "all"
    assert calls[0]["job_ids"] == ["123", "456"]

    status = client.get("/actions/status").get_json()
    assert status is not None
    assert status["runs"][0]["status"] == "completed"
    assert status["runs"][0]["return_code"] == 0
    assert status["runs"][0]["title"] == "sync output + regenerate all docs for 2 job(s)"
    assert any("processing job 123" in message for message in status["runs"][0]["messages"])
