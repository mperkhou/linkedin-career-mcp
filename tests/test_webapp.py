import sqlite3
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
    )

    app = create_app(database_path=database_path, output_dir=output_dir)
    client = app.test_client()

    index = client.get("/")
    assert index.status_code == 200
    assert b"/descriptions/123" in index.data
    assert b"Compare descriptions" in index.data
    assert b"Cover Letter" in index.data
    assert b"/cover-letters/123" in index.data
    assert b"/cover-letters/123/download" in index.data
    assert b"/resumes/123/download" in index.data
    assert b"N/A" in index.data
    assert b"<th>Posted</th>" in index.data
    assert b'id="company-sort"' in index.data
    assert b'id="matched-sort"' in index.data
    assert b'data-company-sort="Example Co"' in index.data
    assert b'data-matched-sort=' in index.data
    assert b"2026-06-07" in index.data

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
    downloaded_resume.write_bytes(b"resume")
    downloaded_cover_letter.write_bytes(b"cover")
    unrelated_pdf.write_bytes(b"other")
    monkeypatch.setenv("HOME", str(tmp_path))

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
    linkedin_response = client.get("/linkedin/123")
    assert linkedin_response.status_code == 302
    assert opened_urls == ["https://www.linkedin.com/jobs/view/123"]

    response = client.post("/applications/delete", data={"job_id": "123"})
    assert response.status_code == 302
    assert client.get("/resumes/123").status_code == 404
    assert client.get("/cover-letters/123").status_code == 404

    workbook = load_workbook(tracking_path)
    sheet = workbook.active
    assert sheet.max_row == 1
