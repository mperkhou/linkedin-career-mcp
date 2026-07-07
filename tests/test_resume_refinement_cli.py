from __future__ import annotations

import asyncio
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
    _generate_text_with_timeout,
    run_second_pass_refinement_for_job,
)


@pytest.mark.asyncio
async def test_second_pass_refinement_stores_v2_variant_and_defaults_current_links(
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

    assert "audit_path" not in audit
    assert not audit_dir.exists()
    assert audit["schema_version"] == SECOND_PASS_RESUME_REFINEMENT_AUDIT_SCHEMA_VERSION
    assert audit["stored_variant"] == "v2"
    assert audit["selected_variant_changed"] is True
    assert audit["applied"] is False
    assert audit["validation"]["accepted_change_ids"] == ["supported-observability"]
    assert audit["validation"]["rejected_changes"] == []
    classifications = {
        suggestion["text"]: suggestion["classification"]
        for suggestion in audit["external_critique"]["suggestions"]
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
            """
            SELECT application_resume_object, resume_content, selected_resume_variant
            FROM applications
            WHERE job_id = '123'
            """
        ).fetchone()
        variants = {
            variant["variant_key"]: variant
            for variant in connection.execute(
                """
                SELECT variant_key, application_resume_object, resume_content,
                       critique_prompt, critique_response, validation_json,
                       external_critique_json, ats_score
                FROM application_resume_variants
                WHERE job_id = '123'
                """
            ).fetchall()
        }
    stored_aro = yaml.safe_load(row["application_resume_object"])
    assert (
        stored_aro["professional_experience"]["jobs"][0]["bullet_points"][0]["text"]
        == "Built Python automation for platform reliability and observability."
    )
    assert row["resume_content"]
    assert row["selected_resume_variant"] == "v2"
    assert set(variants) == {"v1", "v2"}
    v2_aro = yaml.safe_load(variants["v2"]["application_resume_object"])
    assert (
        v2_aro["professional_experience"]["jobs"][0]["bullet_points"][0]["text"]
        == "Built Python automation for platform reliability and observability."
    )
    assert variants["v2"]["resume_content"]
    assert variants["v2"]["ats_score"] is not None
    assert "Payload:" in variants["v2"]["critique_prompt"]
    assert variants["v2"]["critique_response"] == _supported_patch_response()
    validation = json.loads(variants["v2"]["validation_json"])
    assert validation["accepted_change_ids"] == ["supported-observability"]
    external_critique = json.loads(variants["v2"]["external_critique_json"])
    assert len(external_critique["suggestions"]) == 2


@pytest.mark.asyncio
async def test_second_pass_refinement_apply_flag_uses_default_precedence(
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

    assert audit["apply_requested"] is True
    assert audit["applied"] is False
    assert audit["applied_change_ids"] == []
    assert audit["stored_variant"] == "v2"
    assert audit["selected_variant_changed"] is True
    assert audit["comparison"]["v2"]["accepted_changes"] == 1
    with webapp.connect_database(database_path) as connection:
        row = connection.execute(
            """
            SELECT application_resume_object, resume_content, ats_score,
                   selected_resume_variant
            FROM applications
            WHERE job_id = '123'
            """
        ).fetchone()
        variant = connection.execute(
            """
            SELECT application_resume_object, resume_content, ats_score
            FROM application_resume_variants
            WHERE job_id = '123' AND variant_key = 'v2'
            """
        ).fetchone()
    stored_aro = yaml.safe_load(row["application_resume_object"])
    assert (
        stored_aro["professional_experience"]["jobs"][0]["bullet_points"][0]["text"]
        == "Built Python automation for platform reliability and observability."
    )
    v2_aro = yaml.safe_load(variant["application_resume_object"])
    assert (
        v2_aro["professional_experience"]["jobs"][0]["bullet_points"][0]["text"]
        == "Built Python automation for platform reliability and observability."
    )
    assert row["selected_resume_variant"] == "v2"
    assert row["resume_content"]
    assert row["ats_score"] is not None
    assert variant["resume_content"]
    assert variant["ats_score"] is not None


class _FakeLlm:
    def __init__(self, response: str) -> None:
        self._response = response
        self.prompts: list[str] = []

    async def generate_text(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self._response


class _FlakyTimeoutLlm:
    def __init__(self) -> None:
        self.calls = 0

    async def generate_text(self, prompt: str) -> str:
        self.calls += 1
        if self.calls == 1:
            await asyncio.sleep(1)
        return "ok"


@pytest.mark.asyncio
async def test_second_pass_generation_retries_timeout_once(capsys) -> None:
    llm = _FlakyTimeoutLlm()

    response = await _generate_text_with_timeout(
        llm=llm,
        prompt="prompt",
        timeout_seconds=0.01,
        retry_count=1,
    )

    assert response == "ok"
    assert llm.calls == 2
    assert "Second-pass critique timed out; retrying (attempt 2/2)" in capsys.readouterr().err


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
