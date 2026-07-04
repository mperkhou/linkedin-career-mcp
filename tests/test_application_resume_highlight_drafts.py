from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import yaml
from reportlab.pdfgen import canvas

from linkedin_career_mcp import webapp
from scripts import application_resume_highlight_drafts as highlight_drafts


def test_highlight_updates_auto_selected_v2_variant(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "applications.sqlite3"
    _store_resume_variants(database_path)
    monkeypatch.setattr(
        highlight_drafts,
        "run_codex_highlight",
        lambda *args, **kwargs: _highlight_response("Refined v2 API bullet."),
    )
    monkeypatch.setattr(
        highlight_drafts,
        "render_resume_pdf_from_html",
        lambda html: _pdf_bytes(f"Rendered {html}"),
    )

    _run_highlight(database_path)

    with webapp.connect_database(database_path) as connection:
        application = _fetch_application(connection)
        v1 = _fetch_variant(connection, "v1")
        v2 = _fetch_variant(connection, "v2")

    assert application["selected_resume_variant"] == "v2"
    assert application["resume_variant_selection_mode"] == "auto"
    assert "<strong>Refined v2</strong> API bullet." in application[
        "application_resume_object"
    ]
    assert "<strong>Refined v2</strong> API bullet." in v2["application_resume_object"]
    assert "<b>Refined v2</b> API bullet." in v2["resume_html_content"]
    assert "<strong>" not in v1["application_resume_object"]


def test_highlight_preserves_explicit_v1_selection_when_v2_exists(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "applications.sqlite3"
    _store_resume_variants(database_path)
    webapp.select_application_resume_variant(
        database_path=database_path,
        job_id="url-123",
        variant_key="v1",
    )
    monkeypatch.setattr(
        highlight_drafts,
        "run_codex_highlight",
        lambda *args, **kwargs: _highlight_response("Draft v1 API bullet."),
    )
    monkeypatch.setattr(
        highlight_drafts,
        "render_resume_pdf_from_html",
        lambda html: _pdf_bytes(f"Rendered {html}"),
    )

    _run_highlight(database_path)

    with webapp.connect_database(database_path) as connection:
        application = _fetch_application(connection)
        v1 = _fetch_variant(connection, "v1")
        v2 = _fetch_variant(connection, "v2")

    assert application["selected_resume_variant"] == "v1"
    assert application["resume_variant_selection_mode"] == "manual"
    assert "<strong>Draft v1</strong> API bullet." in application[
        "application_resume_object"
    ]
    assert "<strong>Draft v1</strong> API bullet." in v1["application_resume_object"]
    assert "<strong>" not in v2["application_resume_object"]


def test_highlight_updates_selected_manual_variant(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "applications.sqlite3"
    _store_resume_variants(database_path, include_manual=True)
    monkeypatch.setattr(
        highlight_drafts,
        "run_codex_highlight",
        lambda *args, **kwargs: _highlight_response("Manual pass API bullet."),
    )
    monkeypatch.setattr(
        highlight_drafts,
        "render_resume_pdf_from_html",
        lambda html: _pdf_bytes(f"Rendered {html}"),
    )

    _run_highlight(database_path)

    with webapp.connect_database(database_path) as connection:
        application = _fetch_application(connection)
        manual = _fetch_variant(connection, "manual")
        v2 = _fetch_variant(connection, "v2")

    assert application["selected_resume_variant"] == "manual"
    assert application["resume_variant_selection_mode"] == "auto"
    assert "<strong>Manual pass</strong> API bullet." in application[
        "application_resume_object"
    ]
    assert "<strong>Manual pass</strong> API bullet." in manual[
        "application_resume_object"
    ]
    assert "<strong>" not in v2["application_resume_object"]


def _run_highlight(database_path: Path) -> None:
    rows = highlight_drafts._load_rows(  # noqa: SLF001
        database_path=database_path,
        job_ids={"url-123"},
        limit=None,
    )
    assert len(rows) == 1
    outcome = highlight_drafts._highlight_row(  # noqa: SLF001
        row=rows[0],
        database_path=database_path,
        template_path=webapp.DEFAULT_RESUME_TEMPLATE,
        artifact_dir=None,
        dry_run=False,
        codex_command="codex",
        codex_model="gpt-5.5",
        timeout_seconds=30,
        max_strong_spans_per_bullet=3,
        experience_company=None,
        experience_job_order=None,
    )
    assert outcome == "processed"


def _store_resume_variants(database_path: Path, *, include_manual: bool = False) -> None:
    webapp.upsert_application_artifact(
        database_path=database_path,
        job_id="url-123",
        company="Example Co",
        job_title="Senior Engineer",
        linkedin_url="https://www.linkedin.com/jobs/view/123",
        resume_path=None,
        job_description="Requires Python APIs.",
        prompt_job_description="Requires Python APIs.",
    )
    webapp.store_application_resume_first_draft(
        database_path=database_path,
        job_id="url-123",
        application_resume_object=_sample_application_resume_yaml(
            "Draft v1 summary.",
            "Draft v1 API bullet.",
        ),
        resume_html="<html><body>Draft v1 API bullet.</body></html>",
        resume_pdf=_pdf_bytes("Draft v1 API bullet."),
    )
    webapp.store_application_resume_variant(
        database_path=database_path,
        job_id="url-123",
        variant_key="v2",
        variant_label="Refined v2",
        source="second_pass",
        parent_variant_key="v1",
        application_resume_object=_sample_application_resume_yaml(
            "Refined v2 summary.",
            "Refined v2 API bullet.",
        ),
        resume_html="<html><body>Refined v2 API bullet.</body></html>",
        resume_pdf=_pdf_bytes("Refined v2 API bullet."),
    )
    if include_manual:
        webapp.store_application_resume_variant(
            database_path=database_path,
            job_id="url-123",
            variant_key="manual",
            variant_label="Manual pass",
            source="codex_manual_pass",
            parent_variant_key="v2",
            application_resume_object=_sample_application_resume_yaml(
                "Manual pass summary.",
                "Manual pass API bullet.",
            ),
            resume_html="<html><body>Manual pass API bullet.</body></html>",
            resume_pdf=_pdf_bytes("Manual pass API bullet."),
        )


def _fetch_application(connection):
    return connection.execute(
        """
        SELECT selected_resume_variant, resume_variant_selection_mode,
               application_resume_object, resume_html_content
        FROM applications
        WHERE job_id = 'url-123'
        """
    ).fetchone()


def _fetch_variant(connection, variant_key: str):
    return connection.execute(
        """
        SELECT application_resume_object, resume_html_content
        FROM application_resume_variants
        WHERE job_id = 'url-123'
          AND variant_key = ?
        """,
        (variant_key,),
    ).fetchone()


def _highlight_response(text: str) -> str:
    highlight_text = text.split(" API ")[0]
    highlighted = text.replace(highlight_text, f"<strong>{highlight_text}</strong>")
    return json.dumps(
        {
            "bullet_updates": [
                {
                    "job_order": "1",
                    "bullet_order": "1",
                    "text": highlighted,
                }
            ]
        }
    )


def _sample_application_resume_yaml(paragraph: str, bullet: str) -> str:
    resume = {
        "schema_version": "test",
        "header_top": {
            "render": True,
            "line_1_name_header_text": "Max Perkhounkov",
            "line_2_header_text": "",
            "line_3_applicant_info_text": "max@example.com",
            "contact_items": ["max@example.com"],
            "links": [],
        },
        "professional_summary": {
            "render": True,
            "header_text": "Professional Summary",
            "paragraph": paragraph,
            "summary_note": "",
        },
        "core_technical_skills": {
            "render": True,
            "header_text": "Core Technical Skills",
            "bullet_points": [],
        },
        "professional_experience": {
            "render": True,
            "header_text": "Professional Experience",
            "jobs": [
                {
                    "order": 1,
                    "render": True,
                    "min_bullet_points": 1,
                    "max_bullet_points": 1,
                    "line_1": {
                        "company_name_text": "Oracle | Remote",
                        "position_name_text": "Senior Platform Engineer",
                        "position_dates_text": "2022 - Present",
                    },
                    "line_2": {"position_intro_text": ""},
                    "bullet_points": [
                        {
                            "order": 1,
                            "render": True,
                            "categories": {"assigned": [], "matched": []},
                            "skills": [],
                            "text": bullet,
                            "bullet_point_total_match_count": 0,
                        }
                    ],
                }
            ],
        },
        "education": {"render": False, "header_text": "Education", "entries": []},
        "certifications": {
            "render": False,
            "header_text": "Certifications",
            "bullet_points": [],
        },
        "portfolio": {"render": False, "header_text": "Portfolio", "items": []},
    }
    return yaml.safe_dump(resume, sort_keys=False)


def _pdf_bytes(text: str) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(72, 720, text)
    pdf.save()
    return buffer.getvalue()
