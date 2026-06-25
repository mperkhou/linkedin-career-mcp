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
JOD_TARGET_PROMPT_JOD_MAX_CHARS = 12_000
DEFAULT_JOD_LLM_API_MODEL = "z-ai/glm-5.2"
JOB_OPENING_DESCRIPTION_SCHEMA_VERSION = "job_opening_description.v1"


class ApplicationResumeError(WorkflowError):
    """Raised when an application resume object cannot be initialized or generated."""


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
    aro.pop("job_opening_description", None)

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
    extra profile files, or the whole resume object.
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
- The local workflow will apply your response to the ARO before generating experience bullets.

Rules:
- Preserve the category names exactly.
- Only select display skills already present in that category's primary or additional lists.
- Use match_terms as non-display aliases/evidence for those display skills. Do not return
  match_terms directly.
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
            skill
            for skill, aliases in inventory
            if requested.intersection(aliases)
        ]

    return aro


def build_jod_requirements_target_prompt(
    *,
    trimmed_job_description: str,
    max_jod_chars: int = JOD_TARGET_PROMPT_JOD_MAX_CHARS,
) -> str:
    """Build the prompt that distills a JOD into requirement targets."""

    jod = _limit_text(trimmed_job_description, max_chars=max_jod_chars)
    return f"""
You convert a job opening description into small, resume-targetable requirements.
Return only valid JSON. Do not return markdown fences, commentary, or advice.

Rules:
- Extract concrete responsibilities, qualifications, technologies, domains, and outcomes.
- Keep each target short enough to drive one resume-bullet rewrite.
- Do not invent requirements that are not present in the job opening description.
- Merge duplicates and near-duplicates.
- Drop compensation, benefits, equal-opportunity, privacy, and application-process boilerplate.
- Prefer 6 to 14 targets unless the job description clearly has fewer meaningful requirements.

Return this exact JSON shape:
{{
  "job_opening_description": {{
    "requirements_targets": [
      "Looking for production Python automation and platform engineering experience.",
      "Preferred experience with observability, incident response, and cloud operations."
    ]
  }}
}}

Job opening description:
{jod}
""".strip()


def create_job_opening_description_object(
    *,
    trimmed_job_description: str,
    requirements_response: Any,
    model: str = "",
) -> dict[str, Any]:
    """Create the compact JOD object from an LLM requirements response."""

    targets = _extract_jod_target_texts(requirements_response)
    if not targets:
        raise ApplicationResumeError("JOD requirements response did not contain targets.")

    llm: dict[str, str] = {}
    if model.strip():
        llm["model"] = model.strip()

    return {
        "schema_version": JOB_OPENING_DESCRIPTION_SCHEMA_VERSION,
        "source": {
            "type": "trimmed_job_description",
            "character_count": len(str(trimmed_job_description or "").strip()),
        },
        "llm": llm,
        "requirements_targets": [
            {
                "order": index,
                "text": target,
            }
            for index, target in enumerate(targets, start=1)
        ],
    }


def attach_job_opening_description_object(
    *,
    application_resume: Mapping[str, Any],
    job_opening_description: Mapping[str, Any],
) -> dict[str, Any]:
    aro = copy.deepcopy(dict(application_resume))
    aro["job_opening_description"] = copy.deepcopy(dict(job_opening_description))
    return aro


def job_opening_description_target_texts(
    job_opening_description: Mapping[str, Any],
) -> list[str]:
    return _extract_jod_target_texts(job_opening_description)


def experience_jobs_for_jod_bullet_rewrite(
    application_resume: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Return rendered, non-oracle jobs for the JOD bullet rewrite."""

    jobs: list[dict[str, Any]] = []
    for job in _professional_experience_jobs(application_resume):
        if not _render_enabled(job.get("render")):
            continue
        if _normalize_order(job.get("order")) == "1":
            continue
        jobs.append(copy.deepcopy(job))
    return jobs


def oracle_job_for_jod_bullet_rewrite(
    application_resume: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the rendered Oracle/source-evidence job for the JOD bullet rewrite."""

    for job in _professional_experience_jobs(application_resume):
        if _normalize_order(job.get("order")) != "1":
            continue
        if not _render_enabled(job.get("render")):
            raise ApplicationResumeError("Oracle job is not enabled for rendering.")
        return copy.deepcopy(job)
    raise ApplicationResumeError("Oracle job order 1 was not found.")


def build_experience_job_bullet_rewrite_prompt(
    *,
    job_opening_description: Mapping[str, Any],
    job: Mapping[str, Any],
) -> str:
    targets = job_opening_description_target_texts(job_opening_description)
    if not targets:
        raise ApplicationResumeError("JOD object does not contain requirements targets.")

    bullet_texts = _job_bullet_texts(job)
    if not bullet_texts:
        raise ApplicationResumeError("Experience job does not contain bullet text.")

    min_bullets = _nonnegative_int(job.get("min_bullet_points"), default=1)
    max_bullets = _nonnegative_int(job.get("max_bullet_points"), default=len(bullet_texts))
    if min_bullets <= 0:
        min_bullets = 1
    if max_bullets < min_bullets:
        max_bullets = min_bullets

    target_lines = "\n".join(f"- {target}" for target in targets)
    raw_experience_lines = "\n".join(f"- {text}" for text in bullet_texts)
    job_label = _job_label(job)

    return f"""
You are an elite, deterministic ATS optimization script. Your objective is to modify
raw career history text to directly address the target job requirements.

Target Job Requirements:
{target_lines}

Raw Experience{f" ({job_label})" if job_label else ""}:
{raw_experience_lines}

CRITICAL RULES:
1. Strictly use the exact numerical metrics and outcomes provided in the Raw Experience.
2. Do NOT hallucinate new tools, soft skills, software competencies, or outcomes.
3. Rephrase verbs and phrase structures to align with the Target Job Requirements.
4. If a target cannot be supported by the Raw Experience, ignore that target.
5. Format the final output as between {min_bullets} and {max_bullets} punchy bullet
   points utilizing the Google XYZ framework: "Accomplished [X], as measured by [Y],
   by doing [Z]."
6. Output ONLY the raw string of each bullet point, one per line. No introductions,
   markdown, numbering, or chat text.
""".strip()


def replace_experience_job_bullets_from_text_response(
    *,
    application_resume: Mapping[str, Any],
    job_order: Any,
    bullet_response: Any,
) -> dict[str, Any]:
    """Replace one rendered job's inherited evidence bullets with generated bullets."""

    aro = copy.deepcopy(dict(application_resume))
    expected_order = _normalize_order(job_order)
    if not expected_order:
        raise ApplicationResumeError("Experience job order is required for bullet replacement.")

    jobs = _professional_experience_jobs(aro)
    for job in jobs:
        if _normalize_order(job.get("order")) != expected_order:
            continue
        if not _render_enabled(job.get("render")):
            raise ApplicationResumeError("Only rendered experience jobs can be rewritten.")

        bullet_texts = _extract_generated_bullet_texts(bullet_response)
        min_bullets = _nonnegative_int(job.get("min_bullet_points"), default=1)
        max_bullets = _nonnegative_int(job.get("max_bullet_points"), default=len(bullet_texts))
        if len(bullet_texts) < max(min_bullets, 1):
            raise ApplicationResumeError(
                f"Generated {len(bullet_texts)} bullets for job order {expected_order}; "
                f"minimum is {max(min_bullets, 1)}."
            )
        if max_bullets > 0 and len(bullet_texts) > max_bullets:
            raise ApplicationResumeError(
                f"Generated {len(bullet_texts)} bullets for job order {expected_order}; "
                f"maximum is {max_bullets}."
            )

        job["bullet_points"] = [
            {
                "order": index,
                "categories": {
                    "assigned": [],
                    "matched": [],
                },
                "skills": [],
                "text": text,
                "bullet_point_total_match_count": 0,
                "render": True,
            }
            for index, text in enumerate(bullet_texts, start=1)
        ]
        return aro

    raise ApplicationResumeError(f"Experience job order {expected_order} was not found.")


def _core_skill_prompt_payload(application_resume: Mapping[str, Any]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for bucket in _core_skill_buckets(application_resume):
        items = bucket.get("items")
        item_mapping = items if isinstance(items, Mapping) else {}
        match_terms = _core_skill_match_terms_by_skill(item_mapping)
        payload.append(
            {
                "category": str(bucket.get("category") or "").strip(),
                "primary": _string_list(item_mapping.get("primary")),
                "additional": _string_list(item_mapping.get("additional")),
                "match_terms": [
                    {
                        "skill": skill,
                        "terms": terms,
                    }
                    for skill, terms in match_terms.items()
                ],
            }
        )
    return payload


def _core_skill_inventory_by_category(
    application_resume: Mapping[str, Any],
) -> dict[str, list[tuple[str, set[str]]]]:
    inventory: dict[str, list[tuple[str, set[str]]]] = {}
    for bucket in _core_skill_buckets(application_resume):
        category = str(bucket.get("category") or "").strip()
        items = bucket.get("items")
        item_mapping = items if isinstance(items, Mapping) else {}
        display_items = _dedupe_preserve_order(
            [
                *_string_list(item_mapping.get("primary")),
                *_string_list(item_mapping.get("additional")),
            ]
        )
        match_terms = _core_skill_match_terms_by_skill(item_mapping)
        inventory[_normalize(category)] = [
            (
                display_item,
                {
                    _normalize(display_item),
                    *{
                        _normalize(term)
                        for term in match_terms.get(display_item, [])
                    },
                },
            )
            for display_item in display_items
        ]
    return inventory


def _core_skill_match_terms_by_skill(item_mapping: Mapping[str, Any]) -> dict[str, list[str]]:
    display_items = _dedupe_preserve_order(
        [
            *_string_list(item_mapping.get("primary")),
            *_string_list(item_mapping.get("additional")),
        ]
    )
    display_by_key = {_normalize(item): item for item in display_items}
    raw_match_terms = item_mapping.get("match_terms")
    if not isinstance(raw_match_terms, Mapping):
        return {}

    terms_by_skill: dict[str, list[str]] = {}
    for raw_skill, raw_terms in raw_match_terms.items():
        skill = display_by_key.get(_normalize(raw_skill))
        if skill is None:
            continue
        terms = _string_list(raw_terms)
        if terms:
            terms_by_skill[skill] = terms
    return terms_by_skill


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


def _extract_jod_target_texts(response: Any) -> list[str]:
    raw_items: Any = response
    if isinstance(response, str):
        try:
            raw_items = json.loads(response)
        except json.JSONDecodeError:
            raw_items = _split_text_lines(response)
    if isinstance(raw_items, Mapping):
        raw_items = (
            raw_items.get("requirements_targets")
            or raw_items.get("targets")
            or raw_items.get("jod_targets")
            or raw_items.get("requirements")
            or raw_items.get("bullet_points")
            or raw_items.get("queries")
            or raw_items.get("job_opening_description")
            or raw_items.get("jod")
            or raw_items
        )
        if isinstance(raw_items, Mapping):
            raw_items = (
                raw_items.get("requirements_targets")
                or raw_items.get("targets")
                or raw_items.get("jod_targets")
                or raw_items.get("requirements")
                or raw_items.get("bullet_points")
                or raw_items.get("queries")
                or []
            )
    if not isinstance(raw_items, Sequence) or isinstance(raw_items, str):
        return []

    targets: list[str] = []
    for item in raw_items:
        text = ""
        if isinstance(item, Mapping):
            text = str(
                item.get("text")
                or item.get("target")
                or item.get("requirement")
                or item.get("description")
                or ""
            )
        elif isinstance(item, str):
            text = item
        text = _clean_generated_line(text)
        if text:
            targets.append(text)
    return _dedupe_preserve_order(targets)


def _extract_generated_bullet_texts(response: Any) -> list[str]:
    raw_items: Any = response
    if isinstance(response, str):
        try:
            raw_items = json.loads(response)
        except json.JSONDecodeError:
            raw_items = _split_text_lines(response)
    if isinstance(raw_items, Mapping):
        raw_items = raw_items.get("bullet_points") or raw_items.get("bullets") or raw_items
        if isinstance(raw_items, Mapping):
            raw_items = raw_items.get("items") or raw_items.get("generated") or []
    if not isinstance(raw_items, Sequence) or isinstance(raw_items, str):
        return []

    bullets: list[str] = []
    for item in raw_items:
        text = ""
        if isinstance(item, Mapping):
            text = str(item.get("text") or item.get("bullet") or item.get("content") or "")
        elif isinstance(item, str):
            text = item
        text = _clean_generated_line(text)
        if text:
            bullets.append(text)
    return _dedupe_preserve_order(bullets)


def _split_text_lines(text: str) -> list[str]:
    lines: list[str] = []
    for line in str(text or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("```"):
            continue
        lines.append(stripped)
    return lines


def _clean_generated_line(text: str) -> str:
    cleaned = str(text or "").strip()
    cleaned = re.sub(r"^\s*(?:[-*]+|\d+[.)])\s*", "", cleaned)
    cleaned = cleaned.strip().strip('"').strip("'").strip()
    return cleaned


def _job_bullet_texts(job: Mapping[str, Any]) -> list[str]:
    texts: list[str] = []
    raw_bullets = job.get("bullet_points")
    if not isinstance(raw_bullets, list):
        return texts
    for bullet in raw_bullets:
        text = _bullet_text(bullet)
        if text:
            texts.append(text)
    return texts


def _bullet_text(bullet: Any) -> str:
    if isinstance(bullet, str):
        return bullet.strip()
    if not isinstance(bullet, Mapping):
        return ""
    return str(bullet.get("text") or "").strip()


def _job_label(job: Mapping[str, Any]) -> str:
    line_1 = job.get("line_1")
    line_mapping = line_1 if isinstance(line_1, Mapping) else {}
    parts = [
        str(line_mapping.get("company_name_text") or "").strip(),
        str(line_mapping.get("position_name_text") or "").strip(),
        str(line_mapping.get("position_dates_text") or "").strip(),
    ]
    return " | ".join(part for part in parts if part)


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


def _normalize_order(value: Any) -> str:
    if isinstance(value, bool):
        return ""
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return ""
        try:
            return str(int(stripped))
        except ValueError:
            return stripped.casefold()
    return ""


def _limit_text(value: str, *, max_chars: int) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars].rstrip()}\n\n[truncated]"
