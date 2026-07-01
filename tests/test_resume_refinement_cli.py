from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import pytest
import yaml
from reportlab.pdfgen import canvas

from linkedin_career_mcp import webapp
from linkedin_career_mcp.resume_refinement import SECOND_PASS_RESUME_CRITIQUE_SCHEMA_VERSION
from linkedin_career_mcp.resume_refinement_cli import (
    SECOND_PASS_RESUME_REFINEMENT_AUDIT_SCHEMA_VERSION,
    run_second_pass_refinement_for_job,
)


@pytest.mark.asyncio
async def test_second_pass_refinement_dry_run_writes_audit_without_updating_sqlite(
    tmp_path: Path,
):
    database_path, master_resume_path = _seed_refinement_row(tmp_path)
    audit_dir = tmp_path / "audits"
    llm = _FakeLlm(_supported_patch_response())
    external_critique_text = """
    Jack & Jill output:
    - Add observability to the Python platform bullet.
    - Emphasize LTS support and long-term maintenance ownership.
    """

    audit = await run_second_pass_refinement_for_job(
        database_path=database_path,
        job_id="123",
        master_resume_path=master_resume_path,
        template_path=webapp.DEFAULT_RESUME_TEMPLATE,
        artifact_dir=audit_dir,
        apply=False,
        llm=llm,
        external_critique_text=external_critique_text,
    )

    audit_path = Path(audit["audit_path"])
    assert audit_path.is_file()
    saved_audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert saved_audit["schema_version"] == SECOND_PASS_RESUME_REFINEMENT_AUDIT_SCHEMA_VERSION
    assert saved_audit["applied"] is False
    assert saved_audit["validation"]["accepted_change_ids"] == ["supported-observability"]
    assert saved_audit["validation"]["rejected_changes"] == []
    classifications = {
        suggestion["text"]: suggestion["classification"]
        for suggestion in saved_audit["external_critique"]["suggestions"]
    }
    assert (
        classifications["Add observability to the Python platform bullet."]
        == "supported"
    )
    assert (
        classifications[
            "Emphasize LTS support and long-term maintenance ownership."
        ]
        == "noisy_or_role_mismatch"
    )
    assert "Payload:" in llm.prompts[0]
    assert "Add observability to the Python platform bullet." in llm.prompts[0]
    assert "LTS" not in llm.prompts[0]

    with webapp.connect_database(database_path) as connection:
        row = connection.execute(
            "SELECT application_resume_object FROM applications WHERE job_id = '123'"
        ).fetchone()
    stored_aro = yaml.safe_load(row["application_resume_object"])
    assert (
        stored_aro["professional_experience"]["jobs"][0]["bullet_points"][0]["text"]
        == "Built Python automation for platform reliability."
    )


@pytest.mark.asyncio
async def test_second_pass_refinement_apply_updates_sqlite_for_accepted_patches(
    tmp_path: Path,
):
    database_path, master_resume_path = _seed_refinement_row(tmp_path)
    audit_dir = tmp_path / "audits"

    audit = await run_second_pass_refinement_for_job(
        database_path=database_path,
        job_id="123",
        master_resume_path=master_resume_path,
        template_path=webapp.DEFAULT_RESUME_TEMPLATE,
        artifact_dir=audit_dir,
        apply=True,
        llm=_FakeLlm(_supported_patch_response()),
    )

    assert audit["applied"] is True
    assert audit["applied_change_ids"] == ["supported-observability"]
    with webapp.connect_database(database_path) as connection:
        row = connection.execute(
            """
            SELECT application_resume_object, resume_content, ats_score
            FROM applications
            WHERE job_id = '123'
            """
        ).fetchone()
    stored_aro = yaml.safe_load(row["application_resume_object"])
    assert (
        stored_aro["professional_experience"]["jobs"][0]["bullet_points"][0]["text"]
        == "Built Python automation for platform reliability and observability."
    )
    assert row["resume_content"]
    assert row["ats_score"] is not None


class _FakeLlm:
    def __init__(self, response: str) -> None:
        self._response = response
        self.prompts: list[str] = []

    async def generate_text(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self._response


def _supported_patch_response() -> str:
    return json.dumps(
        {
            "schema_version": SECOND_PASS_RESUME_CRITIQUE_SCHEMA_VERSION,
            "proposed_changes": [
                {
                    "change_id": "supported-observability",
                    "change_type": "rewrite_bullet",
                    "target": {
                        "section": "professional_experience",
                        "field": "text",
                        "job_order": "1",
                        "bullet_order": "1",
                    },
                    "current_text": "Built Python automation for platform reliability.",
                    "proposed_text": (
                        "Built Python automation for platform reliability and observability."
                    ),
                    "rationale": "Observability is supported by the MRO source bullet.",
                    "evidence_refs": ["mro:job:1:bullet:1"],
                    "unsupported_claims": [],
                }
            ],
        }
    )


def _seed_refinement_row(tmp_path: Path) -> tuple[Path, Path]:
    database_path = tmp_path / "applications.sqlite3"
    master_resume_path = tmp_path / "MASTER-RESUME.yml"
    master_resume_path.write_text(
        _sample_resume_yaml(
            paragraph="Senior platform engineer building Python automation.",
            bullet="Built Python automation for platform reliability and observability.",
        ),
        encoding="utf-8",
    )
    webapp.upsert_application_artifact(
        database_path=database_path,
        job_id="123",
        company="Nscale",
        job_title="AI Product Engineer",
        linkedin_url="https://www.linkedin.com/jobs/view/123",
        resume_path=None,
        job_description="Requires Python automation and observability.",
        prompt_job_description="Requires Python automation and observability.",
    )
    webapp.store_application_resume_first_draft(
        database_path=database_path,
        job_id="123",
        application_resume_object=_sample_resume_yaml(
            paragraph="Senior platform engineer building Python automation.",
            bullet="Built Python automation for platform reliability.",
        ),
        resume_html="<html><body>Built Python automation for platform reliability.</body></html>",
        resume_pdf=_pdf_bytes("Built Python automation for platform reliability."),
    )
    return database_path, master_resume_path


def _sample_resume_yaml(*, paragraph: str, bullet: str) -> str:
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
      additional:
      - observability
    jod_matched_items:
    - Python
professional_experience:
  render: true
  header_text: Professional Experience
  jobs:
  - order: 1
    render: true
    line_1:
      company_name_text: Oracle
      position_name_text: Senior Engineer
      position_dates_text: 2020 - Present
    line_2:
      position_intro_text: Platform engineering role.
    bullet_points:
    - order: 1
      render: true
      text: {bullet}
job_opening_description:
  schema_version: job_opening_description.v1
  requirements_targets:
  - order: 1
    text: Requires Python automation and observability.
education:
  render: false
  entries: []
certifications:
  render: false
  bullet_points: []
portfolio:
  render: false
  projects: []
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
