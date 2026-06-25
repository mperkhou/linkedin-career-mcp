from __future__ import annotations

import json
from pathlib import Path

import yaml

from linkedin_career_mcp.application_resume import (
    apply_core_skill_jod_matches,
    attach_job_opening_description_object,
    build_core_skills_jod_match_prompt,
    build_experience_job_bullet_rewrite_prompt,
    build_jod_requirements_target_prompt,
    create_job_opening_description_object,
    experience_jobs_for_jod_bullet_rewrite,
    initialize_application_resume_object,
    oracle_job_for_jod_bullet_rewrite,
    replace_experience_job_bullets_from_text_response,
)
from scripts.application_resume_pass_one import main as application_resume_pass_one_main
from scripts.application_resume_regenerate_aros import _preserve_job_specific_aro_sections


def test_initialize_application_resume_object_resets_job_specific_fields(
    tmp_path: Path,
) -> None:
    master_path = tmp_path / "MASTER-RESUME.yml"
    master_path.write_text(
        yaml.safe_dump(_sample_aro(jod_items=["Python"], count=4), sort_keys=False),
        encoding="utf-8",
    )

    aro = initialize_application_resume_object(master_path)

    assert aro["core_technical_skills"]["bullet_points"][0]["jod_matched_items"] == []
    bullet = aro["professional_experience"]["jobs"][0]["bullet_points"][0]
    assert bullet["bullet_point_total_match_count"] == 0
    assert bullet["skills"][0]["jod_match_count"] == 0


def test_core_skills_prompt_uses_only_core_skills_and_trimmed_jod() -> None:
    aro = _sample_aro(jod_items=[], count=0)
    prompt = build_core_skills_jod_match_prompt(
        application_resume=aro,
        trimmed_job_description="We need Python, Terraform, and production reliability.",
    )

    assert "Core Technical Skills inventory" in prompt
    assert "Python" in prompt
    assert "Terraform" in prompt
    assert "We need Python" in prompt
    assert "This professional experience bullet should not be sent" not in prompt


def test_apply_core_skill_jod_matches_filters_to_existing_inventory() -> None:
    aro = _sample_aro(jod_items=[], count=0)

    updated = apply_core_skill_jod_matches(
        application_resume=aro,
        core_skill_response={
            "core_technical_skills": [
                {
                    "category": "Languages & Frameworks",
                    "jod_matched_items": ["Django", "Python", "Not real"],
                },
                {
                    "category": "Automation & IaC",
                    "jod_matched_items": ["Terraform", "Not real"],
                },
            ]
        },
    )

    assert aro["core_technical_skills"]["bullet_points"][0]["jod_matched_items"] == []
    assert updated["core_technical_skills"]["bullet_points"][0]["jod_matched_items"] == [
        "Python",
        "Django",
    ]
    assert updated["core_technical_skills"]["bullet_points"][1]["jod_matched_items"] == [
        "Terraform"
    ]


def test_apply_core_skill_jod_matches_canonicalizes_match_terms() -> None:
    aro = _sample_aro(jod_items=[], count=0)
    bucket = aro["core_technical_skills"]["bullet_points"][1]
    bucket["items"]["additional"].extend(["PostgreSQL", "Linux"])
    bucket["items"]["match_terms"] = {
        "PostgreSQL": ["managed PostgreSQL"],
        "Linux": ["Linux environments"],
    }

    updated = apply_core_skill_jod_matches(
        application_resume=aro,
        core_skill_response={
            "core_technical_skills": [
                {
                    "category": "Automation & IaC",
                    "jod_matched_items": [
                        "managed PostgreSQL",
                        "Linux environments",
                        "incident response lifecycle",
                    ],
                },
            ]
        },
    )

    assert updated["core_technical_skills"]["bullet_points"][1]["jod_matched_items"] == [
        "PostgreSQL",
        "Linux",
    ]


def test_apply_core_skill_jod_matches_accepts_json_string_response() -> None:
    aro = _sample_aro(jod_items=[], count=0)

    updated = apply_core_skill_jod_matches(
        application_resume=aro,
        core_skill_response=json.dumps(
            {
                "core_technical_skills": [
                    {
                        "category": "Languages & Frameworks",
                        "jod_matched_items": ["Django"],
                    }
                ]
            }
        ),
    )

    assert updated["core_technical_skills"]["bullet_points"][0]["jod_matched_items"] == [
        "Django"
    ]


def test_application_resume_pass_one_script_writes_prompt_and_matched_aro(
    tmp_path: Path,
) -> None:
    master_path = tmp_path / "MASTER-RESUME.yml"
    jod_path = tmp_path / "trimmed-jod.txt"
    response_path = tmp_path / "core-skill-response.json"
    prompt_path = tmp_path / "prompt.txt"
    output_path = tmp_path / "aro.yml"
    master_path.write_text(
        yaml.safe_dump(_sample_aro(jod_items=[], count=0), sort_keys=False),
        encoding="utf-8",
    )
    jod_path.write_text("Need Python and Terraform.", encoding="utf-8")
    response_path.write_text(
        json.dumps(
            {
                "core_technical_skills": [
                    {
                        "category": "Languages & Frameworks",
                        "jod_matched_items": ["Python"],
                    },
                    {
                        "category": "Automation & IaC",
                        "jod_matched_items": ["Terraform"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    application_resume_pass_one_main(
        [
            "--master-resume",
            str(master_path),
            "--trimmed-jod",
            str(jod_path),
            "--prompt-output",
            str(prompt_path),
            "--core-skill-response",
            str(response_path),
            "--output",
            str(output_path),
        ]
    )

    assert "Need Python and Terraform." in prompt_path.read_text(encoding="utf-8")
    matched = yaml.safe_load(output_path.read_text(encoding="utf-8"))
    bullet = matched["professional_experience"]["jobs"][0]["bullet_points"][0]
    assert matched["core_technical_skills"]["bullet_points"][0]["jod_matched_items"] == [
        "Python"
    ]
    assert matched["core_technical_skills"]["bullet_points"][1]["jod_matched_items"] == [
        "Terraform"
    ]
    assert bullet["skills"][0]["jod_match_count"] == 0
    assert bullet["skills"][1]["jod_match_count"] == 0
    assert bullet["bullet_point_total_match_count"] == 0


def test_regenerate_aro_preserves_tailored_job_specific_sections() -> None:
    fresh_aro = _sample_aro(jod_items=["Python"], count=0)
    fresh_aro["professional_experience"]["jobs"][0]["bullet_points"][0]["text"] = (
        "Raw master-resume Oracle evidence."
    )

    existing_aro = _sample_aro(jod_items=["Django"], count=3)
    existing_aro["job_opening_description"] = {
        "schema_version": "job_opening_description.v1",
        "requirements_targets": [{"order": 1, "text": "Need Django."}],
    }
    existing_aro["professional_experience"]["jobs"][0]["bullet_points"][0]["text"] = (
        "Tailored job-specific Oracle bullet."
    )

    refreshed = _preserve_job_specific_aro_sections(
        fresh_aro=fresh_aro,
        existing_aro=existing_aro,
    )

    assert refreshed["core_technical_skills"]["bullet_points"][0][
        "jod_matched_items"
    ] == ["Python"]
    assert refreshed["job_opening_description"] == existing_aro["job_opening_description"]
    bullet = refreshed["professional_experience"]["jobs"][0]["bullet_points"][0]
    assert bullet["text"] == "Tailored job-specific Oracle bullet."


def test_jod_requirements_target_prompt_and_object_are_compact() -> None:
    prompt = build_jod_requirements_target_prompt(
        trimmed_job_description=(
            "Responsibilities: Build Python automation and cloud observability. "
            "Benefits include medical coverage."
        )
    )

    assert "small, resume-targetable requirements" in prompt
    assert "Python automation" in prompt
    assert "requirements_targets" in prompt

    jod_object = create_job_opening_description_object(
        trimmed_job_description="Need Python and cloud observability.",
        requirements_response={
            "job_opening_description": {
                "requirements_targets": [
                    {"text": " Need Python automation. "},
                    {"requirement": "Need cloud observability."},
                    "Need Python automation.",
                ]
            }
        },
        model="z-ai/glm-5.2",
    )

    assert jod_object["schema_version"] == "job_opening_description.v1"
    assert jod_object["llm"]["model"] == "z-ai/glm-5.2"
    assert jod_object["requirements_targets"] == [
        {"order": 1, "text": "Need Python automation."},
        {"order": 2, "text": "Need cloud observability."},
    ]


def test_jod_bullet_rewrite_targets_rendered_non_oracle_jobs() -> None:
    source_aro = _sample_selection_aro()
    jod_object = create_job_opening_description_object(
        trimmed_job_description="Need Python automation and cloud observability.",
        requirements_response={
            "requirements_targets": [
                "Looking for Python automation experience.",
                "Preferred cloud observability and incident response experience.",
            ]
        },
        model="z-ai/glm-5.2",
    )
    attached = attach_job_opening_description_object(
        application_resume=source_aro,
        job_opening_description=jod_object,
    )
    jobs_to_rewrite = experience_jobs_for_jod_bullet_rewrite(attached)

    assert [job["order"] for job in jobs_to_rewrite] == [2, 3]

    prompt = build_experience_job_bullet_rewrite_prompt(
        job_opening_description=jod_object,
        job=jobs_to_rewrite[0],
    )
    assert "between 2 and 5 punchy bullet" in prompt
    assert "Looking for Python automation experience." in prompt
    assert "Bullet 1 evidence count 0." in prompt
    assert "Bullet 7 evidence count 1." in prompt

    rewritten = replace_experience_job_bullets_from_text_response(
        application_resume=attached,
        job_order=2,
        bullet_response=(
            "1. Accomplished a supported modernization outcome, as measured by the "
            "available role scope, by doing Python automation.\n"
            "- Accomplished operational reporting support, as measured by the available "
            "role scope, by doing cloud observability work."
        ),
    )
    jobs = rewritten["professional_experience"]["jobs"]

    assert jobs[0]["order"] == 1
    assert jobs[0]["bullet_points"][0]["text"] == "Bullet 1 evidence count 4."
    assert jobs[0]["bullet_points"][0]["render"] is False
    assert jobs[1]["bullet_points"] == [
        {
            "order": 1,
            "categories": {"assigned": [], "matched": []},
            "skills": [],
            "text": (
                "Accomplished a supported modernization outcome, as measured by the "
                "available role scope, by doing Python automation."
            ),
            "bullet_point_total_match_count": 0,
            "render": True,
        },
        {
            "order": 2,
            "categories": {"assigned": [], "matched": []},
            "skills": [],
            "text": (
                "Accomplished operational reporting support, as measured by the available "
                "role scope, by doing cloud observability work."
            ),
            "bullet_point_total_match_count": 0,
            "render": True,
        },
    ]


def test_jod_bullet_rewrite_can_replace_oracle_paragraph_evidence() -> None:
    source_aro = _sample_selection_aro()
    jod_object = create_job_opening_description_object(
        trimmed_job_description="Need network automation and responsible AI tooling.",
        requirements_response={
            "requirements_targets": [
                "Looking for network automation experience.",
                "Preferred responsible AI tooling experience.",
            ]
        },
        model="z-ai/glm-5.2",
    )
    attached = attach_job_opening_description_object(
        application_resume=source_aro,
        job_opening_description=jod_object,
    )
    oracle_job = oracle_job_for_jod_bullet_rewrite(attached)

    assert oracle_job["order"] == 1

    prompt = build_experience_job_bullet_rewrite_prompt(
        job_opening_description=jod_object,
        job=oracle_job,
    )
    assert "between 6 and 10 punchy bullet" in prompt
    assert "Looking for network automation experience." in prompt

    rewritten = replace_experience_job_bullets_from_text_response(
        application_resume=attached,
        job_order=1,
        bullet_response=(
            "Accomplished network automation support, as measured by supported "
            "source evidence, by building OLAM workflows.\n"
            "Accomplished responsible AI tooling, as measured by supported source "
            "evidence, by building Codex guardrails.\n"
            "Accomplished release hygiene, as measured by supported source evidence, "
            "by validating tests and changelogs.\n"
            "Accomplished observability coverage, as measured by supported source "
            "evidence, by building monitoring reports.\n"
            "Accomplished secure config handling, as measured by supported source "
            "evidence, by separating secrets.\n"
            "Accomplished platform reliability, as measured by supported source "
            "evidence, by diagnosing stuck jobs."
        ),
    )
    oracle_bullets = rewritten["professional_experience"]["jobs"][0]["bullet_points"]

    assert len(oracle_bullets) == 6
    assert oracle_bullets[0] == {
        "order": 1,
        "categories": {"assigned": [], "matched": []},
        "skills": [],
        "text": (
            "Accomplished network automation support, as measured by supported "
            "source evidence, by building OLAM workflows."
        ),
        "bullet_point_total_match_count": 0,
        "render": True,
    }


def _sample_aro(*, jod_items: list[str], count: int) -> dict[str, object]:
    return {
        "core_technical_skills": {
            "bullet_points": [
                {
                    "category": "Languages & Frameworks",
                    "items": {
                        "primary": ["Python"],
                        "additional": ["Django", "Ruby"],
                    },
                    "jod_matched_items": jod_items,
                },
                {
                    "category": "Automation & IaC",
                    "items": {
                        "primary": ["Ansible"],
                        "additional": ["Terraform"],
                    },
                    "jod_matched_items": jod_items,
                },
            ]
        },
        "professional_experience": {
            "jobs": [
                {
                    "bullet_points": [
                        {
                            "skills": [
                                {
                                    "category": "Languages & Frameworks",
                                    "matched": ["Python", "Django"],
                                    "jod_match_count": count,
                                },
                                {
                                    "category": "Automation & IaC",
                                    "matched": ["Terraform"],
                                    "jod_match_count": count,
                                },
                            ],
                            "text": "This professional experience bullet should not be sent.",
                            "bullet_point_total_match_count": count,
                            "render": False,
                        }
                    ]
                }
            ]
        },
    }


def _sample_selection_aro() -> dict[str, object]:
    return {
        "professional_experience": {
            "jobs": [
                _selection_job(
                    1,
                    "Oracle | Remote / International Datacenters",
                    evidence_counts=[
                        4,
                        2,
                        0,
                        4,
                        4,
                        2,
                        1,
                        0,
                        1,
                        1,
                        5,
                        4,
                        1,
                        1,
                        0,
                        0,
                        1,
                        0,
                        0,
                        0,
                        0,
                        3,
                        0,
                        1,
                        3,
                        1,
                        1,
                        0,
                        1,
                        2,
                        0,
                        0,
                        1,
                        1,
                        1,
                        2,
                        0,
                        0,
                        1,
                        3,
                        3,
                        1,
                        0,
                        1,
                        2,
                        2,
                        1,
                    ],
                    render=True,
                    min_bullets=6,
                    max_bullets=10,
                ),
                _selection_job(
                    2,
                    "University of Iowa Hospitals and Clinics | Iowa City, IA",
                    evidence_counts=[0, 2, 1, 0, 0, 1, 1],
                    render=True,
                    min_bullets=2,
                    max_bullets=5,
                ),
                _selection_job(
                    3,
                    "Steindler Orthopedic Clinic | Iowa City, IA",
                    evidence_counts=[1, 2, 4, 0, 0, 0, 1, 0, 0],
                    render=True,
                    min_bullets=2,
                    max_bullets=5,
                ),
                _selection_job(
                    4,
                    "Stamats Communications | Cedar Rapids, IA",
                    evidence_counts=[1, 0, 0, 0, 0, 3, 0],
                    render=False,
                    min_bullets=0,
                    max_bullets=2,
                ),
                _selection_job(
                    5,
                    "VIDA Diagnostics | Coralville, IA",
                    evidence_counts=[1, 0, 1, 0, 1, 0, 0, 0, 0, 0],
                    render=False,
                    min_bullets=0,
                    max_bullets=2,
                ),
            ]
        }
    }


def _selection_job(
    order: int,
    company: str,
    *,
    evidence_counts: list[int],
    render: bool,
    min_bullets: int,
    max_bullets: int,
) -> dict[str, object]:
    return {
        "order": order,
        "render": render,
        "min_bullet_points": min_bullets,
        "max_bullet_points": max_bullets,
        "line_1": {"company_name_text": company},
        "bullet_points": [
            {
                "text": f"Bullet {index} evidence count {evidence_count}.",
                "bullet_point_total_match_count": evidence_count,
                "render": False,
            }
            for index, evidence_count in enumerate(evidence_counts, start=1)
        ],
    }
