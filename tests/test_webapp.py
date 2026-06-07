from pathlib import Path

from openpyxl import Workbook, load_workbook

from linkedin_career_mcp import webapp
from linkedin_career_mcp.webapp import create_app, import_output_artifacts


def test_import_output_artifacts_stores_workbook_rows_and_resume_blob(tmp_path: Path, monkeypatch):
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
    assert database_path.exists()

    app = create_app(database_path=database_path, output_dir=output_dir)
    client = app.test_client()

    db_resume = client.get("/resumes/123")
    assert db_resume.status_code == 200
    assert db_resume.data == b"%PDF-1.4 fake pdf"

    output_resume = client.get(
        "/output/resumes/Example_Co/123_senior_engineer/mp_resume_senior_engineer.pdf"
    )
    assert output_resume.status_code == 200
    assert output_resume.data == b"%PDF-1.4 fake pdf"

    opened_urls: list[str] = []
    monkeypatch.setattr(webapp, "_open_url_in_chromium", opened_urls.append)
    linkedin_response = client.get("/linkedin/123")
    assert linkedin_response.status_code == 302
    assert opened_urls == ["https://www.linkedin.com/jobs/view/123"]

    response = client.post("/applications/delete", data={"job_id": "123"})
    assert response.status_code == 302
    assert client.get("/resumes/123").status_code == 404

    workbook = load_workbook(tracking_path)
    sheet = workbook.active
    assert sheet.max_row == 1
