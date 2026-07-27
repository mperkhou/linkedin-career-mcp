from __future__ import annotations

import json
import subprocess
from io import BytesIO
from pathlib import Path

import yaml
from reportlab.pdfgen import canvas

from linkedin_career_mcp import resume_manual_pass, webapp


def test_build_manual_pass_input_bundle_includes_variant_and_master_evidence(
    tmp_path: Path,
) -> None:
    master_resume_path = tmp_path / "MASTER-RESUME.yml"
    master_resume_path.write_text("core_technical_skills: {}\n", encoding="utf-8")
    master_resume_text_path = tmp_path / "MP-MASTER-RESUME.txt"
    master_resume_text_path.write_text("Oracle platform automation evidence.", encoding="utf-8")

    row = {
        "job_id": "123",
        "company": "Example Co",
        "job_title": "Senior Engineer",
        "linkedin_url": "https://www.linkedin.com/jobs/view/123",
        "selected_resume_variant": "v1",
        "applied_to": "No",
        "date_applied": None,
        "notes": "",
        "job_description": "Full JOD requires Python automation.",
        "prompt_job_description": "Prompt JOD requires observability.",
    }
    v1_variant = _variant_mapping("v1", "Draft v1", "summary: Draft v1\n")
    v2_variant = _variant_mapping(
        "v2",
        "Refined v2",
        "summary: Refined v2\n",
        validation={"accepted_change_ids": ["summary-1"]},
        critique={"proposed_changes": [{"change_id": "summary-1"}]},
    )

    bundle = resume_manual_pass.build_manual_pass_input_bundle(
        row=row,
        v1_variant=v1_variant,
        v2_variant=v2_variant,
        master_resume_path=master_resume_path,
        master_resume_text_path=master_resume_text_path,
    )

    assert bundle["schema_version"] == "manual_resume_pass_input_bundle.v1"
    assert bundle["job"]["job_id"] == "123"
    assert bundle["job_descriptions"]["prompt_jod"] == "Prompt JOD requires observability."
    assert bundle["master_resume_evidence"]["master_resume_text"].startswith("Oracle")
    assert bundle["variants"]["v1"]["application_resume_object"]["summary"] == "Draft v1"
    assert bundle["variants"]["v2"]["application_resume_object"]["summary"] == "Refined v2"
    assert bundle["v2_second_pass"]["validation"]["accepted_change_ids"] == ["summary-1"]
    assert bundle["v2_second_pass"]["critique"]["proposed_changes"][0]["change_id"] == (
        "summary-1"
    )


def test_parse_manual_pass_response_accepts_fenced_json_with_yaml_aro() -> None:
    response = resume_manual_pass.parse_manual_pass_response(
        "```json\n"
        + json.dumps(
            {
                "schema_version": "manual_resume_pass_response.v1",
                "application_resume_object": "schema_version: test\nsummary: Manual\n",
                "rationale": "Combined supported v1/v2 edits.",
                "unsupported_terms": ["Kubernetes"],
                "reviewer_notes": ["Kept AWS wording evidence-backed."],
            }
        )
        + "\n```"
    )

    assert response.application_resume["summary"] == "Manual"
    assert response.unsupported_terms == ["Kubernetes"]
    assert response.reviewer_notes == ["Kept AWS wording evidence-backed."]


def test_run_manual_resume_pass_for_job_stores_manual_variant_and_defaults_to_it(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "applications.sqlite3"
    master_resume_path = tmp_path / "MASTER-RESUME.yml"
    master_resume_path.write_text(
        _sample_application_resume_yaml("Master summary.", "Master bullet."),
        encoding="utf-8",
    )
    master_resume_text_path = tmp_path / "MP-MASTER-RESUME.txt"
    master_resume_text_path.write_text(
        "Master evidence: Python, AWS, observability.",
        encoding="utf-8",
    )
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
    v1_aro = _sample_application_resume_yaml(
        "Draft v1 summary for platform APIs.",
        "Draft v1 Python API bullet.",
    )
    v2_aro = _sample_application_resume_yaml(
        "Refined v2 summary for platform observability.",
        "Refined v2 Python API observability bullet.",
    )
    manual_aro = yaml.safe_load(
        _sample_application_resume_yaml(
            "Manual summary balancing v1 and v2 evidence.",
            "Manual Python API observability bullet.",
        )
    )
    v1_pdf = _pdf_bytes("Draft v1 Python AWS APIs")
    v2_pdf = _pdf_bytes("Refined v2 Python AWS APIs observability")
    manual_pdf = _pdf_bytes("Manual Python AWS APIs observability")
    webapp.store_application_resume_first_draft(
        database_path=database_path,
        job_id="123",
        application_resume_object=v1_aro,
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
        application_resume_object=v2_aro,
        resume_html="<html><body><h1>Refined v2</h1></body></html>",
        resume_pdf=v2_pdf,
        validation={"accepted_change_ids": ["summary-1"], "rejected_changes": []},
        critique={"proposed_changes": [{"change_id": "summary-1"}]},
        model_metadata={"model": "z-ai/glm-5.2"},
    )
    monkeypatch.setattr(
        resume_manual_pass,
        "run_codex_manual_pass",
        lambda *args, **kwargs: json.dumps(
            {
                "schema_version": "manual_resume_pass_response.v1",
                "application_resume_object": manual_aro,
                "rationale": "Manual pass kept supported v2 improvements.",
                "unsupported_terms": ["Kubernetes"],
                "reviewer_notes": ["Stored as a manual variant."],
            }
        ),
    )
    monkeypatch.setattr(
        resume_manual_pass,
        "render_resume_pdf_from_html",
        lambda html: manual_pdf,
    )

    result = resume_manual_pass.run_manual_resume_pass_for_job(
        database_path=database_path,
        job_id="123",
        master_resume_path=master_resume_path,
        master_resume_text_path=master_resume_text_path,
        template_path=webapp.DEFAULT_RESUME_TEMPLATE,
        codex_command="codex",
        manual_pass_profile="premium",
        codex_model="operator/model",
        codex_reasoning_effort="",
        timeout_seconds=30,
    )

    assert result["stored_variant"] == "manual"
    assert result["selected_variant_changed"] is True
    assert result["selected_resume_variant"] == "manual"
    assert result["unsupported_terms"] == ["Kubernetes"]
    with webapp.connect_database(database_path) as connection:
        current = connection.execute(
            """
            SELECT selected_resume_variant, application_resume_object, resume_content
            FROM applications
            WHERE job_id = '123'
            """
        ).fetchone()
        manual_variant = connection.execute(
            """
            SELECT application_resume_object, resume_content, evidence_packet_json,
                   critique_response, validation_json, model_metadata_json
            FROM application_resume_variants
            WHERE job_id = '123' AND variant_key = 'manual'
            """
        ).fetchone()
    assert current["selected_resume_variant"] == "manual"
    assert "Manual summary balancing" in current["application_resume_object"]
    assert current["resume_content"] == manual_pdf
    assert manual_variant is not None
    assert "Manual summary balancing" in manual_variant["application_resume_object"]
    assert manual_variant["resume_content"] == manual_pdf
    evidence_packet = json.loads(manual_variant["evidence_packet_json"])
    assert evidence_packet["variants"]["v2"]["application_resume_object"][
        "professional_summary"
    ]["paragraph"].startswith("Refined v2")
    validation = json.loads(manual_variant["validation_json"])
    assert validation["unsupported_terms"] == ["Kubernetes"]
    model_metadata = json.loads(manual_variant["model_metadata_json"])
    assert model_metadata["profile"] == "premium"
    assert model_metadata["model"] == "operator/model"
    assert model_metadata["reasoning_effort"] == ""
    assert model_metadata["client"] == "Codex CLI"
    assert model_metadata["codex_command"] == "codex"


def test_run_codex_manual_pass_pins_reasoning_effort(tmp_path: Path, monkeypatch) -> None:
    captured_args: list[str] = []

    def fake_run(args, **kwargs):
        captured_args.extend(args)
        output_path = args[args.index("--output-last-message") + 1]
        Path(output_path).write_text(
            json.dumps(
                {
                    "schema_version": "manual_resume_pass_response.v1",
                    "application_resume_object": {"schema_version": "test"},
                    "rationale": "Manual pass.",
                    "unsupported_terms": [],
                    "reviewer_notes": [],
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    response = resume_manual_pass.run_codex_manual_pass(
        "prompt",
        project_root=tmp_path,
        codex_command="codex",
        codex_model="manual/model",
    )

    assert "manual_resume_pass_response.v1" in response
    assert "-c" in captured_args
    assert 'model_reasoning_effort="high"' in captured_args
    assert captured_args.index('model_reasoning_effort="high"') < captured_args.index("exec")
    assert captured_args[captured_args.index("--model") + 1] == "manual/model"


def test_run_codex_manual_pass_empty_effort_inherits_codex_config(
    tmp_path: Path,
    monkeypatch,
) -> None:
    captured_args: list[str] = []

    def fake_run(args, **kwargs):
        captured_args.extend(args)
        output_path = args[args.index("--output-last-message") + 1]
        Path(output_path).write_text(
            json.dumps(
                {
                    "schema_version": "manual_resume_pass_response.v1",
                    "application_resume_object": {"schema_version": "test"},
                    "rationale": "Manual pass.",
                    "unsupported_terms": [],
                    "reviewer_notes": [],
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    resume_manual_pass.run_codex_manual_pass(
        "prompt",
        project_root=tmp_path,
        codex_model="manual/model",
        codex_reasoning_effort="",
    )

    assert "--model" in captured_args
    assert all(not arg.startswith("model_reasoning_effort=") for arg in captured_args)


def test_run_codex_manual_pass_retries_timeout(tmp_path: Path, monkeypatch) -> None:
    calls = 0

    def fake_run(args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise subprocess.TimeoutExpired(cmd=args, timeout=kwargs["timeout"])
        output_path = args[args.index("--output-last-message") + 1]
        Path(output_path).write_text(
            json.dumps(
                {
                    "schema_version": "manual_resume_pass_response.v1",
                    "application_resume_object": {"schema_version": "test"},
                    "rationale": "Manual pass.",
                    "unsupported_terms": [],
                    "reviewer_notes": [],
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    response = resume_manual_pass.run_codex_manual_pass(
        "prompt",
        project_root=tmp_path,
        codex_command="codex",
        retry_count=1,
    )

    assert calls == 2
    assert "manual_resume_pass_response.v1" in response


def _variant_mapping(
    variant_key: str,
    variant_label: str,
    aro_yaml: str,
    *,
    validation: dict[str, object] | None = None,
    critique: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "variant_key": variant_key,
        "variant_label": variant_label,
        "source": "test",
        "parent_variant_key": None,
        "application_resume_object": aro_yaml,
        "resume_filename": f"{variant_key}.pdf",
        "resume_html_filename": f"{variant_key}.html",
        "resume_html_content": f"<html><body>{variant_label}</body></html>",
        "resume_content": _pdf_bytes(f"{variant_label} PDF text"),
        "ats_score": 88,
        "ats_parsing_score": 100,
        "ats_keyword_score": 80,
        "ats_semantic_score": 90,
        "ats_formatting_risk": "Low",
        "ats_missing_terms": "",
        "ats_diagnostics_json": "",
        "critique_json": json.dumps(critique or {}),
        "validation_json": json.dumps(validation or {}),
        "evidence_packet_json": "{}",
        "external_critique_json": "{}",
        "model_metadata_json": "{}",
        "updated_at": "2026-07-01T00:00:00+00:00",
    }


def _sample_application_resume_yaml(paragraph: str, bullet: str) -> str:
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
      - observability
    jod_matched_items:
    - observability
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
  entries: []
certifications:
  render: false
  header_text: Certifications
  bullet_points: []
portfolio:
  render: false
  header_text: Portfolio
  projects: []
"""


def _pdf_bytes(text: str) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    for index, line in enumerate(text.splitlines() or [text], start=1):
        pdf.drawString(72, 760 - index * 14, line)
    pdf.save()
    return buffer.getvalue()
