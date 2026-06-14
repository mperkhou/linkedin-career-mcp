from __future__ import annotations

import copy
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from linkedin_career_mcp.errors import WorkflowError

DEFAULT_MASTER_RESUME_PATH = Path("profile/MASTER-RESUME.yml")
CORE_SKILLS_PROMPT_JOD_MAX_CHARS = 12_000


class ApplicationResumeError(WorkflowError):
    """Raised when an application resume object cannot be initialized or scored."""


def initialize_application_resume_object(
    master_resume_path: Path = DEFAULT_MASTER_RESUME_PATH,
) -> dict[str, Any]:
    """Load the master resume YAML and reset all job-specific ARO fields."""

    with master_resume_path.open(encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    if not isinstance(value, dict):
        raise ApplicationResumeError(
            f"{master_resume_path} must contain a YAML mapping at the document root."
        )
    return reset_application_resume_jod_state(value)


def reset_application_resume_jod_state(application_resume: Mapping[str, Any]) -> dict[str, Any]:
    aro = copy.deepcopy(dict(application_resume))

    for bucket in _core_skill_buckets(aro):
        bucket["jod_matched_items"] = []

    for bullet in _professional_experience_bullets(aro):
        bullet["bullet_point_total_match_count"] = 0
        for skill_entry in _skill_entries(bullet):
            skill_entry["jod_match_count"] = 0

    return aro


def build_core_skills_jod_match_prompt(
    *,
    application_resume: Mapping[str, Any],
    trimmed_job_description: str,
    max_jod_chars: int = CORE_SKILLS_PROMPT_JOD_MAX_CHARS,
) -> str:
    """Build the first ARO prompt: match master skills to a trimmed JOD.

    The prompt intentionally includes only the Core Technical Skills inventory and the
    trimmed JOD. It does not send professional-experience bullets, cover-letter context,
    CJD files, or the whole resume object.
    """

    core_skills = _core_skill_prompt_payload(application_resume)
    core_skills_json = json.dumps(core_skills, ensure_ascii=True, indent=2)
    jod = _limit_text(trimmed_job_description, max_chars=max_jod_chars)
    return f"""
You select which factual master-resume skills match one job opening description.
Return only valid JSON. Do not return markdown fences, commentary, advice, or a resume.

Context:
- ARO means Application Resume Object.
- The local workflow has already created a hard copy of profile/MASTER-RESUME.yml.
- You only update Core Technical Skills by selecting jod_matched_items.
- The local workflow will apply your response to the ARO and score experience bullets.

Rules:
- Preserve the category names exactly.
- Only select skills already present in that category's primary or additional lists.
- Include primary skills when the JOD asks for them; the renderer already includes primary
  skills and will not duplicate them.
- Include additional skills when the JOD asks for them; the renderer can add those skills
  to the visible Core Technical Skills section.
- Do not invent skills, employers, tools, responsibilities, or credentials.
- If a category has no clear overlap with the JOD, return an empty jod_matched_items list.

Return this exact JSON shape:
{{
  "core_technical_skills": [
    {{
      "category": "Languages & Frameworks",
      "jod_matched_items": ["Python", "Django"]
    }}
  ]
}}

Core Technical Skills inventory:
{core_skills_json}

Trimmed job opening description:
{jod}
""".strip()


def apply_core_skill_jod_matches(
    *,
    application_resume: Mapping[str, Any],
    core_skill_response: Any,
) -> dict[str, Any]:
    """Apply the LLM's Core Technical Skills match response to an ARO copy."""

    aro = copy.deepcopy(dict(application_resume))
    response_by_category = _extract_core_skill_match_response(core_skill_response)
    inventory_by_category = _core_skill_inventory_by_category(aro)

    for bucket in _core_skill_buckets(aro):
        category = str(bucket.get("category") or "").strip()
        normalized_category = _normalize(category)
        inventory = inventory_by_category.get(normalized_category, [])
        requested = response_by_category.get(normalized_category, set())
        bucket["jod_matched_items"] = [
            skill for skill in inventory if _normalize(skill) in requested
        ]

    return aro


def calculate_experience_jod_match_counts(
    application_resume: Mapping[str, Any],
) -> dict[str, Any]:
    """Fill per-skill and per-bullet JOD match counts from Core Technical Skills matches."""

    aro = copy.deepcopy(dict(application_resume))
    jod_matches_by_category = _jod_matched_items_by_category(aro)

    for bullet in _professional_experience_bullets(aro):
        bullet_total = 0
        for skill_entry in _skill_entries(bullet):
            category = str(skill_entry.get("category") or "").strip()
            category_matches = jod_matches_by_category.get(_normalize(category), set())
            count = sum(
                1
                for skill in _string_list(skill_entry.get("matched"))
                if _normalize(skill) in category_matches
            )
            skill_entry["jod_match_count"] = count
            bullet_total += count
        bullet["bullet_point_total_match_count"] = bullet_total

    return aro


def apply_core_skill_matches_and_score_experience(
    *,
    application_resume: Mapping[str, Any],
    core_skill_response: Any,
) -> dict[str, Any]:
    """Apply Core Technical Skills JOD matches, then score experience bullets locally."""

    aro = apply_core_skill_jod_matches(
        application_resume=application_resume,
        core_skill_response=core_skill_response,
    )
    return calculate_experience_jod_match_counts(aro)


def select_predraft_experience_bullets(
    application_resume: Mapping[str, Any],
) -> dict[str, Any]:
    """Set job and bullet render flags for the first structured resume pre-draft.

    Bullet selection is deterministic and score-bucket based: positive-score bullets are
    considered from highest score to lowest score, complete score ties are kept together,
    and selection stops before a bucket that would exceed ``max_bullet_points``. Jobs with
    explicit ``render: false`` stay disabled, but their candidate bullet flags are still
    populated so later ATS experiments can enable the job without reselecting bullets.
    """

    aro = copy.deepcopy(dict(application_resume))
    for job in _professional_experience_jobs(aro):
        bullets = _job_bullets(job)
        min_bullets = _nonnegative_int(job.get("min_bullet_points"))
        max_bullets = _nonnegative_int(job.get("max_bullet_points"), default=len(bullets))
        selected_indices = _select_positive_score_bullet_indices(
            bullets=bullets,
            max_bullets=max_bullets,
        )
        selected_index_set = set(selected_indices)

        job["render"] = _render_enabled(job.get("render")) and min_bullets > 0
        for index, bullet in enumerate(bullets):
            bullet["render"] = index in selected_index_set
        job["bullet_points"] = [
            *(bullets[index] for index in selected_indices),
            *(
                bullet
                for index, bullet in enumerate(bullets)
                if index not in selected_index_set
            ),
        ]

    return aro


def _core_skill_prompt_payload(application_resume: Mapping[str, Any]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for bucket in _core_skill_buckets(application_resume):
        items = bucket.get("items")
        item_mapping = items if isinstance(items, Mapping) else {}
        payload.append(
            {
                "category": str(bucket.get("category") or "").strip(),
                "primary": _string_list(item_mapping.get("primary")),
                "additional": _string_list(item_mapping.get("additional")),
            }
        )
    return payload


def _core_skill_inventory_by_category(
    application_resume: Mapping[str, Any],
) -> dict[str, list[str]]:
    inventory: dict[str, list[str]] = {}
    for bucket in _core_skill_buckets(application_resume):
        category = str(bucket.get("category") or "").strip()
        items = bucket.get("items")
        item_mapping = items if isinstance(items, Mapping) else {}
        inventory[_normalize(category)] = _dedupe_preserve_order(
            [
                *_string_list(item_mapping.get("primary")),
                *_string_list(item_mapping.get("additional")),
            ]
        )
    return inventory


def _extract_core_skill_match_response(response: Any) -> dict[str, set[str]]:
    raw_items: Any = response
    if isinstance(response, str):
        try:
            raw_items = json.loads(response)
        except json.JSONDecodeError:
            return {}
    if isinstance(raw_items, Mapping):
        raw_items = raw_items.get("core_technical_skills", raw_items)
        if isinstance(raw_items, Mapping):
            raw_items = raw_items.get("bullet_points", raw_items)
    if not isinstance(raw_items, Sequence) or isinstance(raw_items, str):
        return {}

    by_category: dict[str, set[str]] = {}
    for item in raw_items:
        if not isinstance(item, Mapping):
            continue
        category = str(item.get("category") or item.get("name") or "").strip()
        if not category:
            continue
        matches = (
            item.get("jod_matched_items")
            or item.get("matched")
            or item.get("skills")
            or []
        )
        by_category[_normalize(category)] = {_normalize(skill) for skill in _string_list(matches)}
    return by_category


def _jod_matched_items_by_category(
    application_resume: Mapping[str, Any],
) -> dict[str, set[str]]:
    inventory_by_category = _core_skill_inventory_by_category(application_resume)
    by_category: dict[str, set[str]] = {}
    for bucket in _core_skill_buckets(application_resume):
        category = str(bucket.get("category") or "").strip()
        normalized_category = _normalize(category)
        valid_items = {
            _normalize(skill) for skill in inventory_by_category.get(normalized_category, [])
        }
        by_category[normalized_category] = {
            normalized_skill
            for normalized_skill in (
                _normalize(skill) for skill in _string_list(bucket.get("jod_matched_items"))
            )
            if normalized_skill in valid_items
        }
    return by_category


def _core_skill_buckets(application_resume: Mapping[str, Any]) -> list[dict[str, Any]]:
    core_skills = application_resume.get("core_technical_skills")
    if not isinstance(core_skills, Mapping):
        return []
    buckets = core_skills.get("bullet_points")
    if not isinstance(buckets, list):
        return []
    return [bucket for bucket in buckets if isinstance(bucket, dict)]


def _professional_experience_bullets(
    application_resume: Mapping[str, Any],
) -> list[dict[str, Any]]:
    bullets: list[dict[str, Any]] = []
    for job in _professional_experience_jobs(application_resume):
        bullets.extend(_job_bullets(job))
    return bullets


def _professional_experience_jobs(
    application_resume: Mapping[str, Any],
) -> list[dict[str, Any]]:
    experience = application_resume.get("professional_experience")
    if not isinstance(experience, Mapping):
        return []
    jobs = experience.get("jobs")
    if not isinstance(jobs, list):
        return []
    return [job for job in jobs if isinstance(job, dict)]


def _job_bullets(job: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw_bullets = job.get("bullet_points")
    if not isinstance(raw_bullets, list):
        return []
    return [bullet for bullet in raw_bullets if isinstance(bullet, dict)]


def _skill_entries(bullet: Mapping[str, Any]) -> list[dict[str, Any]]:
    entries = bullet.get("skills")
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        normalized = _normalize(item)
        if normalized not in seen:
            result.append(item)
            seen.add(normalized)
    return result


def _select_positive_score_bullet_indices(
    *,
    bullets: Sequence[Mapping[str, Any]],
    max_bullets: int,
) -> list[int]:
    if max_bullets <= 0:
        return []

    score_buckets: dict[int, list[int]] = {}
    for index, bullet in enumerate(bullets):
        score = _nonnegative_int(bullet.get("bullet_point_total_match_count"))
        if score <= 0:
            continue
        score_buckets.setdefault(score, []).append(index)

    selected: list[int] = []
    for score in sorted(score_buckets, reverse=True):
        bucket = score_buckets[score]
        if len(selected) + len(bucket) > max_bullets:
            break
        selected.extend(bucket)
    return selected


def _nonnegative_int(value: Any, *, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, str):
        try:
            return max(int(value), 0)
        except ValueError:
            return default
    return default


def _render_enabled(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().casefold() not in {"false", "no", "0", "off"}
    return bool(value)


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _limit_text(value: str, *, max_chars: int) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars].rstrip()}\n\n[truncated]"
