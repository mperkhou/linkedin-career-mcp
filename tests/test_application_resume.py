from __future__ import annotations

import json
from pathlib import Path

import yaml

from linkedin_career_mcp.application_resume import (
    apply_core_skill_jod_matches,
    apply_core_skill_matches_and_score_experience,
    build_core_skills_jod_match_prompt,
    calculate_experience_jod_match_counts,
    initialize_application_resume_object,
    select_first_draft_experience_bullets,
)
from scripts.application_resume_pass_one import main as application_resume_pass_one_main
from scripts.application_resume_select_bullets import main as application_resume_select_bullets_main


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


def test_calculate_experience_jod_match_counts_uses_core_skill_matches() -> None:
    aro = _sample_aro(jod_items=["Python", "Django", "Terraform"], count=0)

    scored = calculate_experience_jod_match_counts(aro)
    bullet = scored["professional_experience"]["jobs"][0]["bullet_points"][0]

    assert bullet["skills"][0]["jod_match_count"] == 2
    assert bullet["skills"][1]["jod_match_count"] == 1
    assert bullet["bullet_point_total_match_count"] == 3
    assert aro["professional_experience"]["jobs"][0]["bullet_points"][0][
        "bullet_point_total_match_count"
    ] == 0


def test_apply_core_skill_matches_and_score_experience_runs_pass_one() -> None:
    aro = _sample_aro(jod_items=[], count=0)

    updated = apply_core_skill_matches_and_score_experience(
        application_resume=aro,
        core_skill_response={
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
        },
    )
    bullet = updated["professional_experience"]["jobs"][0]["bullet_points"][0]

    assert bullet["skills"][0]["jod_match_count"] == 1
    assert bullet["skills"][1]["jod_match_count"] == 1
    assert bullet["bullet_point_total_match_count"] == 2


def test_application_resume_pass_one_script_writes_prompt_and_scored_aro(
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
    scored = yaml.safe_load(output_path.read_text(encoding="utf-8"))
    bullet = scored["professional_experience"]["jobs"][0]["bullet_points"][0]
    assert bullet["skills"][0]["jod_match_count"] == 1
    assert bullet["skills"][1]["jod_match_count"] == 1
    assert bullet["bullet_point_total_match_count"] == 2


def test_select_first_draft_experience_bullets_uses_score_buckets_without_splitting_ties() -> None:
    aro = _sample_selection_aro()

    selected = select_first_draft_experience_bullets(aro)
    jobs = selected["professional_experience"]["jobs"]

    assert jobs[0]["render"] is True
    assert _selected_scores(jobs[0]) == [5, 4, 4, 4, 4, 3, 3, 3, 3]
    assert jobs[1]["render"] is True
    assert _selected_scores(jobs[1]) == [2, 1, 1, 1]
    assert jobs[2]["render"] is True
    assert _selected_scores(jobs[2]) == [4, 2, 1, 1]

    assert jobs[3]["render"] is False
    assert _selected_scores(jobs[3]) == [3, 1]
    assert jobs[4]["render"] is False
    assert _selected_scores(jobs[4]) == []

    assert _selected_scores(aro["professional_experience"]["jobs"][0]) == []


def test_application_resume_select_bullets_script_writes_first_draft_aro(tmp_path: Path) -> None:
    aro_path = tmp_path / "scored-aro.yml"
    output_path = tmp_path / "first-draft-aro.yml"
    aro_path.write_text(
        yaml.safe_dump(_sample_selection_aro(), sort_keys=False),
        encoding="utf-8",
    )

    application_resume_select_bullets_main(
        [
            "--input",
            str(aro_path),
            "--output",
            str(output_path),
        ]
    )

    selected = yaml.safe_load(output_path.read_text(encoding="utf-8"))
    jobs = selected["professional_experience"]["jobs"]
    assert jobs[0]["render"] is True
    assert _selected_scores(jobs[0]) == [5, 4, 4, 4, 4, 3, 3, 3, 3]
    assert jobs[3]["render"] is False
    assert _selected_scores(jobs[3]) == [3, 1]


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
                    "Oracle | Remote / International Datacenters",
                    scores=[
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
                    "University of Iowa Hospitals and Clinics | Iowa City, IA",
                    scores=[0, 2, 1, 0, 0, 1, 1],
                    render=True,
                    min_bullets=2,
                    max_bullets=5,
                ),
                _selection_job(
                    "Steindler Orthopedic Clinic | Iowa City, IA",
                    scores=[1, 2, 4, 0, 0, 0, 1, 0, 0],
                    render=True,
                    min_bullets=2,
                    max_bullets=5,
                ),
                _selection_job(
                    "Stamats Communications | Cedar Rapids, IA",
                    scores=[1, 0, 0, 0, 0, 3, 0],
                    render=False,
                    min_bullets=0,
                    max_bullets=2,
                ),
                _selection_job(
                    "VIDA Diagnostics | Coralville, IA",
                    scores=[1, 0, 1, 0, 1, 0, 0, 0, 0, 0],
                    render=False,
                    min_bullets=0,
                    max_bullets=2,
                ),
            ]
        }
    }


def _selection_job(
    company: str,
    *,
    scores: list[int],
    render: bool,
    min_bullets: int,
    max_bullets: int,
) -> dict[str, object]:
    return {
        "render": render,
        "min_bullet_points": min_bullets,
        "max_bullet_points": max_bullets,
        "line_1": {"company_name_text": company},
        "bullet_points": [
            {
                "text": f"Bullet {index} score {score}.",
                "bullet_point_total_match_count": score,
                "render": False,
            }
            for index, score in enumerate(scores, start=1)
        ],
    }


def _selected_scores(job: dict[str, object]) -> list[int]:
    return [
        int(bullet["bullet_point_total_match_count"])
        for bullet in job["bullet_points"]  # type: ignore[index]
        if isinstance(bullet, dict) and bullet.get("render") is True
    ]
