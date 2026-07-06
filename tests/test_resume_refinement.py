from __future__ import annotations

import json
from pathlib import Path

from reportlab.pdfgen import canvas

from linkedin_career_mcp.ats import calculate_ats_diagnostics
from linkedin_career_mcp.resume_refinement import (
    SECOND_PASS_RESUME_CRITIQUE_SCHEMA_VERSION,
    assess_second_pass_critique_support,
    build_resume_critique_evidence_packet,
    build_second_pass_resume_critique_prompt,
    classify_external_resume_critique,
    parse_second_pass_resume_critique_response,
    validate_and_apply_second_pass_resume_patches,
)


def test_build_resume_critique_prompt_includes_aro_jod_ats_and_mro_evidence(
    tmp_path: Path,
):
    resume_pdf = tmp_path / "resume.pdf"
    _write_pdf(
        resume_pdf,
        """
        Professional Summary
        Senior platform engineer building Python automation and observability.

        Core Technical Skills
        Python, observability.

        Professional Experience
        Built Python automation for platform reliability and observability.
        """,
    )
    master_resume = _sample_master_resume()
    application_resume = _sample_application_resume()
    diagnostics = calculate_ats_diagnostics(
        resume_pdf=resume_pdf.read_bytes(),
        job_description="Required Python automation and observability experience.",
    )

    evidence_packet = build_resume_critique_evidence_packet(
        application_resume=application_resume,
        master_resume=master_resume,
        ats_diagnostics=diagnostics,
    )
    prompt = build_second_pass_resume_critique_prompt(
        job_id="url-nscale",
        company="Nscale",
        job_title="AI Product Engineer",
        application_resume=application_resume,
        master_resume=master_resume,
        ats_diagnostics=diagnostics,
    )

    evidence_ids = {
        item.id
        for item in [
            *evidence_packet.jod_targets,
            *evidence_packet.source_evidence,
            *evidence_packet.ats_evidence,
        ]
    }
    assert "mro:summary" in evidence_ids
    assert "mro:skill:platform-engineering:python" in evidence_ids
    assert "mro:job:1:bullet:1" in evidence_ids
    assert "aro:job:1:bullet:1" in evidence_ids
    assert "jod:target:1" in evidence_ids
    assert "ats:score" in evidence_ids
    assert "ats:matched:python" in evidence_ids

    assert SECOND_PASS_RESUME_CRITIQUE_SCHEMA_VERSION in prompt
    assert "unsupported_claims" in prompt
    assert "mro:job:1:bullet:1" in prompt
    assert "jod:target:1" in prompt
    assert "ats:matched:python" in prompt


def test_second_pass_critique_support_assessment_identifies_unsupported_claims(
    tmp_path: Path,
):
    resume_pdf = tmp_path / "resume.pdf"
    _write_pdf(
        resume_pdf,
        """
        Professional Summary
        Senior platform engineer building Python automation and observability.

        Core Technical Skills
        Python, observability.
        """,
    )
    evidence_packet = build_resume_critique_evidence_packet(
        application_resume=_sample_application_resume(),
        master_resume=_sample_master_resume(),
        ats_diagnostics=calculate_ats_diagnostics(
            resume_pdf=resume_pdf.read_bytes(),
            job_description="Required Python automation and observability experience.",
        ),
    )
    response = json.dumps(
        {
            "schema_version": SECOND_PASS_RESUME_CRITIQUE_SCHEMA_VERSION,
            "proposed_changes": [
                {
                    "change_id": "supported-1",
                    "change_type": "rewrite_bullet",
                    "target": {
                        "section": "professional_experience",
                        "field": "text",
                        "job_order": "1",
                        "bullet_order": "1",
                    },
                    "current_text": (
                        "Built Python automation for platform reliability."
                    ),
                    "proposed_text": (
                        "Built Python automation for platform reliability and "
                        "observability."
                    ),
                    "rationale": "Uses supported role evidence and JOD target.",
                    "evidence_refs": [
                        "mro:job:1:bullet:1",
                        "jod:target:1",
                        "ats:matched:python",
                    ],
                    "unsupported_claims": [],
                },
                {
                    "change_id": "unsupported-1",
                    "change_type": "rewrite_bullet",
                    "target": {
                        "section": "professional_experience",
                        "field": "text",
                        "job_order": "1",
                        "bullet_order": "1",
                    },
                    "current_text": (
                        "Built Python automation for platform reliability."
                    ),
                    "proposed_text": (
                        "Owned Kubernetes GPU scheduling compliance for regulated "
                        "AI workloads."
                    ),
                    "rationale": "Would align to AI infrastructure language.",
                    "evidence_refs": ["mro:job:99:bullet:1"],
                    "unsupported_claims": [
                        "Kubernetes GPU scheduling",
                        "regulated AI workloads",
                    ],
                },
                {
                    "change_id": "missing-ref-1",
                    "change_type": "rewrite_summary",
                    "target": {
                        "section": "professional_summary",
                        "field": "paragraph",
                    },
                    "current_text": "Senior platform engineer.",
                    "proposed_text": "Senior platform engineer with observability depth.",
                    "rationale": "Could improve summary alignment.",
                    "evidence_refs": [],
                    "unsupported_claims": [],
                },
            ],
        }
    )

    critique = parse_second_pass_resume_critique_response(response)
    assessment = assess_second_pass_critique_support(
        critique=critique,
        evidence_packet=evidence_packet,
    )

    assert assessment.is_fully_supported is False
    unsupported_by_id = {
        change.change_id: change for change in assessment.unsupported_changes
    }
    assert "supported-1" not in unsupported_by_id
    assert unsupported_by_id["unsupported-1"].reasons == [
        "unknown_evidence_refs",
        "unsupported_claims_declared",
    ]
    assert unsupported_by_id["unsupported-1"].unknown_evidence_refs == [
        "mro:job:99:bullet:1"
    ]
    assert unsupported_by_id["unsupported-1"].unsupported_claims == [
        "Kubernetes GPU scheduling",
        "regulated AI workloads",
    ]
    assert unsupported_by_id["missing-ref-1"].reasons == ["missing_evidence_refs"]


def test_parse_second_pass_critique_response_accepts_fenced_json():
    critique = parse_second_pass_resume_critique_response(
        f"""```json
{{"schema_version": "{SECOND_PASS_RESUME_CRITIQUE_SCHEMA_VERSION}", "proposed_changes": []}}
```"""
    )

    assert critique.proposed_changes == []


def test_parse_second_pass_critique_response_normalizes_common_model_aliases():
    critique = parse_second_pass_resume_critique_response(
        json.dumps(
            {
                "schema_version": SECOND_PASS_RESUME_CRITIQUE_SCHEMA_VERSION,
                "proposed_changes": [
                    {
                        "change_id": "summary-1",
                        "change_type": "rewrite_summary",
                        "target": {
                            "section": "summary",
                            "field": "paragraph",
                        },
                        "current_text": "Old summary.",
                        "proposed_text": "New summary.",
                        "rationale": "Aligns the summary.",
                        "evidence_refs": ["mro:summary"],
                        "unsupported_claims": [],
                    },
                    {
                        "change_id": "skills-1",
                        "change_type": "add_skill",
                        "target": {
                            "section": "skills",
                            "field": "items",
                        },
                        "current_text": "Python",
                        "proposed_text": "Python, observability",
                        "rationale": "Uses supported evidence.",
                        "evidence_refs": ["mro:skills:1"],
                        "unsupported_claims": [],
                    },
                    {
                        "change_id": "bullets-1",
                        "change_type": "reorder_bullets",
                        "target": {
                            "section": "professional_experience",
                            "field": "text",
                            "job_order": "1",
                            "bullet_order": "1",
                        },
                        "current_text": "Built Python automation.",
                        "proposed_text": "Built Python automation.",
                        "rationale": "Model used a near-miss change type.",
                        "evidence_refs": ["mro:job:1:bullet:1"],
                        "unsupported_claims": [],
                    },
                ],
            }
        )
    )

    assert critique.proposed_changes[0].target.section == "professional_summary"
    assert critique.proposed_changes[1].target.section == "core_technical_skills"
    assert critique.proposed_changes[1].change_type == "emphasize_supported_term"
    assert critique.proposed_changes[2].change_type == "other"


def test_external_critique_classification_handles_nscale_lts_mismatch(
    tmp_path: Path,
):
    resume_pdf = tmp_path / "resume.pdf"
    _write_pdf(
        resume_pdf,
        "Built Python automation for platform reliability.",
    )
    application_resume = _sample_application_resume()
    application_resume["job_opening_description"]["requirements_targets"] = [
        {
            "order": 1,
            "text": (
                "Nscale AI Product Engineer role requires Python automation, "
                "Kubernetes GPU scheduling, and observability."
            ),
        }
    ]
    evidence_packet = build_resume_critique_evidence_packet(
        application_resume=application_resume,
        master_resume=_sample_master_resume(),
        ats_diagnostics=calculate_ats_diagnostics(
            resume_pdf=resume_pdf.read_bytes(),
            job_description=(
                "Nscale AI Product Engineer role requires Python automation, "
                "Kubernetes GPU scheduling, and observability."
            ),
        ),
    )

    report = classify_external_resume_critique(
        external_critique_text="""
        Jack & Jill output:
        - Add observability to the Python platform bullet.
        - Add Kubernetes GPU scheduling if you have examples.
        - Emphasize LTS support and long-term maintenance ownership.
        - Overall score: 71/100.
        """,
        evidence_packet=evidence_packet,
    )

    by_text = {suggestion.text: suggestion for suggestion in report.suggestions}
    assert (
        by_text["Add observability to the Python platform bullet."].classification
        == "supported"
    )
    assert by_text[
        "Add observability to the Python platform bullet."
    ].evidence_refs
    assert (
        by_text["Add Kubernetes GPU scheduling if you have examples."].classification
        == "needs_user_evidence"
    )
    assert (
        by_text[
            "Emphasize LTS support and long-term maintenance ownership."
        ].classification
        == "noisy_or_role_mismatch"
    )
    assert by_text["Overall score: 71/100."].classification == "rejected"
    assert [
        suggestion.text for suggestion in report.supported_suggestions
    ] == ["Add observability to the Python platform bullet."]


def test_validate_and_apply_accepts_supported_rewording_and_skill_alias(
    tmp_path: Path,
):
    resume_pdf = tmp_path / "resume.pdf"
    _write_pdf(
        resume_pdf,
        "Built Python automation for platform reliability.",
    )
    application_resume = _sample_application_resume()
    evidence_packet = build_resume_critique_evidence_packet(
        application_resume=application_resume,
        master_resume=_sample_master_resume(),
        ats_diagnostics=calculate_ats_diagnostics(
            resume_pdf=resume_pdf.read_bytes(),
            job_description="Need Python automation and REST APIs.",
        ),
    )
    critique = parse_second_pass_resume_critique_response(
        json.dumps(
            {
                "schema_version": SECOND_PASS_RESUME_CRITIQUE_SCHEMA_VERSION,
                "proposed_changes": [
                    {
                        "change_id": "supported-rest-alias",
                        "change_type": "rewrite_bullet",
                        "target": {
                            "section": "professional_experience",
                            "field": "text",
                            "job_order": "1",
                            "bullet_order": "1",
                        },
                        "current_text": (
                            "Built Python automation for platform reliability."
                        ),
                        "proposed_text": (
                            "Built Python automation and REST APIs for platform "
                            "reliability."
                        ),
                        "rationale": "REST APIs is supported by MRO RESTful APIs evidence.",
                        "evidence_refs": [
                            "mro:job:1:bullet:1",
                            "mro:skill:platform-engineering:restful-apis",
                        ],
                        "unsupported_claims": [],
                    }
                ],
            }
        )
    )

    result = validate_and_apply_second_pass_resume_patches(
        application_resume=application_resume,
        critique=critique,
        evidence_packet=evidence_packet,
    )

    assert result.validation.is_valid is True
    assert result.validation.accepted_change_ids == ["supported-rest-alias"]
    assert result.validation.rejected_changes == []
    assert (
        result.updated_resume["professional_experience"]["jobs"][0]["bullet_points"][0][
            "text"
        ]
        == "Built Python automation and REST APIs for platform reliability."
    )
    assert (
        application_resume["professional_experience"]["jobs"][0]["bullet_points"][0][
            "text"
        ]
        == "Built Python automation for platform reliability."
    )


def test_validate_and_apply_rejects_unsupported_new_claims(
    tmp_path: Path,
):
    resume_pdf = tmp_path / "resume.pdf"
    _write_pdf(
        resume_pdf,
        "Built Python automation for platform reliability.",
    )
    application_resume = _sample_application_resume()
    evidence_packet = build_resume_critique_evidence_packet(
        application_resume=application_resume,
        master_resume=_sample_master_resume(),
        ats_diagnostics=calculate_ats_diagnostics(
            resume_pdf=resume_pdf.read_bytes(),
            job_description="Need Python automation.",
        ),
    )
    critique = parse_second_pass_resume_critique_response(
        json.dumps(
            {
                "schema_version": SECOND_PASS_RESUME_CRITIQUE_SCHEMA_VERSION,
                "proposed_changes": [
                    {
                        "change_id": "invented-infra-claim",
                        "change_type": "rewrite_bullet",
                        "target": {
                            "section": "professional_experience",
                            "field": "text",
                            "job_order": "1",
                            "bullet_order": "1",
                        },
                        "current_text": (
                            "Built Python automation for platform reliability."
                        ),
                        "proposed_text": (
                            "Owned Kubernetes GPU scheduling compliance for regulated "
                            "AI workloads and improved throughput by 40%."
                        ),
                        "rationale": "Would better match the job language.",
                        "evidence_refs": ["mro:job:1:bullet:1"],
                        "unsupported_claims": [],
                    }
                ],
            }
        )
    )

    result = validate_and_apply_second_pass_resume_patches(
        application_resume=application_resume,
        critique=critique,
        evidence_packet=evidence_packet,
    )

    assert result.validation.is_valid is False
    assert result.validation.accepted_change_ids == []
    rejected = result.validation.rejected_changes[0]
    assert rejected.change_id == "invented-infra-claim"
    factual_issue = next(
        issue
        for issue in rejected.issues
        if issue.reason == "unsupported_factual_terms"
    )
    assert {
        "40%",
        "compliance",
        "gpu",
        "kubernetes",
        "regulated",
        "owned",
    }.issubset(set(factual_issue.unsupported_terms))
    assert result.updated_resume == application_resume


def _sample_master_resume() -> dict[str, object]:
    return {
        "professional_summary": {
            "paragraph": "Senior platform engineer building Python automation."
        },
        "core_technical_skills": {
            "bullet_points": [
                {
                    "category": "Platform Engineering",
                    "items": {
                        "primary": ["Python"],
                        "additional": ["observability", "RESTful APIs"],
                    },
                }
            ]
        },
        "professional_experience": {
            "jobs": [
                {
                    "order": 1,
                    "render": True,
                    "line_1": {"company_name_text": "Oracle"},
                    "bullet_points": [
                        {
                            "order": 1,
                            "render": False,
                            "text": (
                                "Built Python automation for platform reliability "
                                "and observability with RESTful APIs."
                            ),
                        }
                    ],
                }
            ]
        },
    }


def _sample_application_resume() -> dict[str, object]:
    return {
        **_sample_master_resume(),
        "job_opening_description": {
            "schema_version": "job_opening_description.v1",
            "requirements_targets": [
                {
                    "order": 1,
                    "text": "Need Python automation and observability experience.",
                }
            ],
        },
        "professional_experience": {
            "jobs": [
                {
                    "order": 1,
                    "render": True,
                    "line_1": {"company_name_text": "Oracle"},
                    "bullet_points": [
                        {
                            "order": 1,
                            "render": True,
                            "text": (
                                "Built Python automation for platform reliability."
                            ),
                        }
                    ],
                }
            ]
        },
    }


def _write_pdf(path: Path, text: str) -> None:
    pdf = canvas.Canvas(str(path))
    text_object = pdf.beginText(40, 760)
    text_object.setFont("Helvetica", 10)
    for line in text.strip().splitlines():
        text_object.textLine(line.strip())
    pdf.drawText(text_object)
    pdf.save()
