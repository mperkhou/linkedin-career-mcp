from __future__ import annotations

import copy
import html
import json
import re
import shlex
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from linkedin_career_mcp.errors import WorkflowError

DEFAULT_CODEX_COMMAND = "codex"
DEFAULT_CODEX_MODEL = "gpt-5.5"
DEFAULT_CODEX_REASONING_EFFORT = "xhigh"
DEFAULT_CODEX_TIMEOUT_SECONDS = 900
DEFAULT_MAX_STRONG_SPANS_PER_BULLET = 3
DEFAULT_MIN_STRONG_SPANS_PER_BULLET = 1
_STRONG_TAG_RE = re.compile(r"</?\s*strong\s*>", re.IGNORECASE)


class ResumeHighlightError(WorkflowError):
    """Raised when Codex highlighting output cannot be safely applied."""


@dataclass(frozen=True)
class HighlightBullet:
    job_order: str
    bullet_order: str
    job_label: str
    text: str


@dataclass(frozen=True)
class HighlightStats:
    bullet_count: int
    strong_span_count: int


def collect_highlight_bullets(application_resume: Mapping[str, Any]) -> list[HighlightBullet]:
    """Return rendered professional-experience bullets that may receive emphasis."""

    return collect_highlight_bullets_for_jobs(application_resume)


def collect_highlight_bullets_for_jobs(
    application_resume: Mapping[str, Any],
    *,
    experience_company: str | None = None,
    experience_job_order: str | None = None,
) -> list[HighlightBullet]:
    """Return rendered professional-experience bullets for matching jobs."""

    jobs = application_resume.get("professional_experience", {}).get("jobs")
    if not isinstance(jobs, list):
        return []

    bullets: list[HighlightBullet] = []
    for job_index, job in enumerate(jobs, start=1):
        if not isinstance(job, Mapping) or not _renders(job):
            continue
        line_1 = job.get("line_1")
        line_1 = line_1 if isinstance(line_1, Mapping) else {}
        company = _string(line_1.get("company_name_text"))
        position = _string(line_1.get("position_name_text"))
        job_order = _order_value(job.get("order"), fallback=job_index)
        if not _matches_job_filter(
            company=company,
            job_order=job_order,
            experience_company=experience_company,
            experience_job_order=experience_job_order,
        ):
            continue
        label_parts = [part for part in [company, position] if part]
        job_label = " | ".join(label_parts) or f"Job {job_index}"
        raw_bullets = job.get("bullet_points")
        if not isinstance(raw_bullets, list):
            continue
        for bullet_index, bullet in enumerate(raw_bullets, start=1):
            if not isinstance(bullet, Mapping) or not _renders(bullet):
                continue
            text = _string(bullet.get("text"))
            if not text:
                continue
            bullets.append(
                HighlightBullet(
                    job_order=job_order,
                    bullet_order=_order_value(bullet.get("order"), fallback=bullet_index),
                    job_label=job_label,
                    text=text,
                )
            )
    return bullets


def build_resume_highlight_prompt(
    application_resume: Mapping[str, Any],
    *,
    job_id: str,
    company: str,
    job_title: str,
    experience_company: str | None = None,
    experience_job_order: str | None = None,
    max_strong_spans_per_bullet: int = DEFAULT_MAX_STRONG_SPANS_PER_BULLET,
) -> str:
    bullets = collect_highlight_bullets_for_jobs(
        application_resume,
        experience_company=experience_company,
        experience_job_order=experience_job_order,
    )
    payload = {
        "job_id": job_id,
        "company": company,
        "job_title": job_title,
        "experience_company_filter": experience_company or "",
        "experience_job_order_filter": experience_job_order or "",
        "professional_experience_bullets": [
            {
                "job_order": bullet.job_order,
                "bullet_order": bullet.bullet_order,
                "job_label": bullet.job_label,
                "text": bullet.text,
            }
            for bullet in bullets
        ],
    }
    return (
        "You are Codex running as a post-generation resume polish workflow.\n"
        "Your task is selective visual emphasis only. Add tasteful <strong>...</strong> "
        "tags to the professional-experience bullet text so the generated resume scans "
        "like a senior, polished PDF.\n\n"
        "Hard rules:\n"
        "- Return only valid JSON. Do not include Markdown fences or commentary.\n"
        "- Return one update for every input bullet, and no extra bullets.\n"
        "- Preserve every original word, number, punctuation mark, capitalization, and "
        "space exactly. The only allowed text changes are adding <strong> and </strong> "
        "wrappers.\n"
        "- Use only <strong> tags. Do not use Markdown, <b>, <em>, links, attributes, "
        "or nested tags.\n"
        f"- Use 1 to {max_strong_spans_per_bullet} strong spans per bullet.\n"
        "- Prefer short phrases: platforms, systems, outcomes, tools, or leadership "
        "moments. Avoid bolding whole clauses or the entire bullet.\n"
        "- Keep emphasis aesthetically varied across bullets. Do not always bold the "
        "first words.\n\n"
        "JSON shape:\n"
        "{\n"
        '  "bullet_updates": [\n'
        '    {"job_order": "1", "bullet_order": "1", "text": "original text with '
        '<strong>selective emphasis</strong>"}\n'
        "  ]\n"
        "}\n\n"
        "Resume payload:\n"
        f"{json.dumps(payload, indent=2, ensure_ascii=True)}\n"
    )


def run_codex_highlight(
    prompt: str,
    *,
    project_root: Path,
    codex_command: str = DEFAULT_CODEX_COMMAND,
    codex_model: str = DEFAULT_CODEX_MODEL,
    codex_reasoning_effort: str = DEFAULT_CODEX_REASONING_EFFORT,
    timeout_seconds: int = DEFAULT_CODEX_TIMEOUT_SECONDS,
    retry_count: int = 0,
) -> str:
    command = shlex.split(codex_command)
    if not command:
        raise ResumeHighlightError("Codex command cannot be empty.")

    attempts = max(1, retry_count + 1)
    for attempt in range(1, attempts + 1):
        with tempfile.TemporaryDirectory(prefix="resume-highlight-") as temp_dir:
            output_path = Path(temp_dir) / "codex-output.txt"
            args = [
                *command,
                "--ask-for-approval",
                "never",
            ]
            _append_codex_reasoning_effort(args, codex_reasoning_effort)
            args.extend(
                [
                    "exec",
                    "-C",
                    str(project_root),
                    "--sandbox",
                    "read-only",
                    "--output-last-message",
                    str(output_path),
                ]
            )
            if codex_model:
                args.extend(["--model", codex_model])
            args.append("-")

            try:
                completed = subprocess.run(  # noqa: S603
                    args,
                    input=prompt,
                    text=True,
                    capture_output=True,
                    timeout=timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                if attempt < attempts:
                    print(
                        (
                            "Codex highlighting timed out; retrying "
                            f"(attempt {attempt + 1}/{attempts})"
                        ),
                        file=sys.stderr,
                        flush=True,
                    )
                    continue
                raise ResumeHighlightError(
                    f"Codex highlighting timed out after {timeout_seconds} seconds."
                ) from exc

            if completed.returncode != 0:
                stderr = _short_process_output(completed.stderr or completed.stdout)
                raise ResumeHighlightError(
                    f"Codex highlighting exited with status {completed.returncode}: {stderr}"
                )
            if not output_path.is_file():
                raise ResumeHighlightError("Codex did not write a final-message output file.")

            response = output_path.read_text(encoding="utf-8").strip()
            if not response:
                raise ResumeHighlightError("Codex returned an empty highlighting response.")
            return response
    raise AssertionError("unreachable retry loop exit")


def _append_codex_reasoning_effort(args: list[str], codex_reasoning_effort: str) -> None:
    effort = codex_reasoning_effort.strip()
    if not effort:
        return
    args.extend(["-c", f"model_reasoning_effort={json.dumps(effort)}"])


def apply_highlight_response(
    application_resume: Mapping[str, Any],
    response_text: str,
    *,
    experience_company: str | None = None,
    experience_job_order: str | None = None,
    min_strong_spans_per_bullet: int = DEFAULT_MIN_STRONG_SPANS_PER_BULLET,
    max_strong_spans_per_bullet: int = DEFAULT_MAX_STRONG_SPANS_PER_BULLET,
) -> tuple[dict[str, Any], HighlightStats]:
    original_bullets = collect_highlight_bullets_for_jobs(
        application_resume,
        experience_company=experience_company,
        experience_job_order=experience_job_order,
    )
    updates = parse_highlight_response(response_text)
    expected_keys = {(bullet.job_order, bullet.bullet_order) for bullet in original_bullets}
    seen_keys: set[tuple[str, str]] = set()
    update_by_key: dict[tuple[str, str], str] = {}

    for update in updates:
        key = (
            _order_value(update.get("job_order")),
            _order_value(update.get("bullet_order")),
        )
        if key in seen_keys:
            raise ResumeHighlightError(
                f"Duplicate highlight update for job_order={key[0]} bullet_order={key[1]}."
            )
        if key not in expected_keys:
            raise ResumeHighlightError(
                f"Unexpected highlight update for job_order={key[0]} bullet_order={key[1]}."
            )
        text = update.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ResumeHighlightError(
                f"Highlight update for job_order={key[0]} bullet_order={key[1]} has no text."
            )
        seen_keys.add(key)
        update_by_key[key] = text

    missing = expected_keys - seen_keys
    if missing:
        formatted = ", ".join(f"{job}/{bullet}" for job, bullet in sorted(missing))
        raise ResumeHighlightError(f"Missing highlight updates for bullet(s): {formatted}.")

    updated_resume = copy.deepcopy(dict(application_resume))
    total_spans = 0
    for bullet in _mutable_professional_experience_bullets(
        updated_resume,
        experience_company=experience_company,
        experience_job_order=experience_job_order,
    ):
        key = (
            _order_value(bullet["job"].get("order"), fallback=bullet["job_index"]),
            _order_value(bullet["bullet"].get("order"), fallback=bullet["bullet_index"]),
        )
        if key not in update_by_key:
            continue
        highlighted_text = update_by_key[key]
        total_spans += validate_highlighted_text(
            original_text=_string(bullet["bullet"].get("text")),
            highlighted_text=highlighted_text,
            min_strong_spans=min_strong_spans_per_bullet,
            max_strong_spans=max_strong_spans_per_bullet,
            bullet_label=f"job_order={key[0]} bullet_order={key[1]}",
        )
        bullet["bullet"]["text"] = highlighted_text

    return updated_resume, HighlightStats(
        bullet_count=len(original_bullets),
        strong_span_count=total_spans,
    )


def parse_highlight_response(response_text: str) -> list[Mapping[str, Any]]:
    try:
        payload = json.loads(_extract_json_object(response_text))
    except json.JSONDecodeError as exc:
        raise ResumeHighlightError(f"Codex returned invalid JSON: {exc}") from exc

    if not isinstance(payload, Mapping):
        raise ResumeHighlightError("Codex highlight response must be a JSON object.")
    updates = payload.get("bullet_updates")
    if not isinstance(updates, list):
        raise ResumeHighlightError("Codex highlight response must include bullet_updates.")
    for update in updates:
        if not isinstance(update, Mapping):
            raise ResumeHighlightError("Each highlight update must be a JSON object.")
    return updates


def validate_highlighted_text(
    *,
    original_text: str,
    highlighted_text: str,
    min_strong_spans: int = DEFAULT_MIN_STRONG_SPANS_PER_BULLET,
    max_strong_spans: int = DEFAULT_MAX_STRONG_SPANS_PER_BULLET,
    bullet_label: str = "bullet",
) -> int:
    soup = BeautifulSoup(highlighted_text, "html.parser")
    strong_spans = 0
    for tag in soup.find_all(True):
        if tag.name != "strong":
            raise ResumeHighlightError(f"{bullet_label} contains unsupported <{tag.name}> tag.")
        if tag.attrs:
            raise ResumeHighlightError(f"{bullet_label} contains a <strong> tag with attributes.")
        if tag.find("strong") is not None:
            raise ResumeHighlightError(f"{bullet_label} contains nested <strong> tags.")
        if not tag.get_text(strip=True):
            raise ResumeHighlightError(f"{bullet_label} contains an empty <strong> tag.")
        if not any(char.isalnum() for char in tag.get_text()):
            raise ResumeHighlightError(
                f"{bullet_label} contains a <strong> tag without meaningful text."
            )
        strong_spans += 1

    if strong_spans < min_strong_spans:
        raise ResumeHighlightError(
            f"{bullet_label} has {strong_spans} strong spans; expected at least "
            f"{min_strong_spans}."
        )
    if strong_spans > max_strong_spans:
        raise ResumeHighlightError(
            f"{bullet_label} has {strong_spans} strong spans; expected at most "
            f"{max_strong_spans}."
        )

    if _plain_text_without_strong(highlighted_text) != _plain_text_without_strong(original_text):
        raise ResumeHighlightError(f"{bullet_label} changed the bullet text.")

    return strong_spans


def _mutable_professional_experience_bullets(
    application_resume: dict[str, Any],
    *,
    experience_company: str | None = None,
    experience_job_order: str | None = None,
) -> list[dict[str, Any]]:
    jobs = application_resume.get("professional_experience", {}).get("jobs")
    if not isinstance(jobs, list):
        return []

    bullets: list[dict[str, Any]] = []
    for job_index, job in enumerate(jobs, start=1):
        if not isinstance(job, dict) or not _renders(job):
            continue
        line_1 = job.get("line_1")
        line_1 = line_1 if isinstance(line_1, Mapping) else {}
        if not _matches_job_filter(
            company=_string(line_1.get("company_name_text")),
            job_order=_order_value(job.get("order"), fallback=job_index),
            experience_company=experience_company,
            experience_job_order=experience_job_order,
        ):
            continue
        raw_bullets = job.get("bullet_points")
        if not isinstance(raw_bullets, list):
            continue
        for bullet_index, bullet in enumerate(raw_bullets, start=1):
            if not isinstance(bullet, dict) or not _renders(bullet):
                continue
            if _string(bullet.get("text")):
                bullets.append(
                    {
                        "job": job,
                        "bullet": bullet,
                        "job_index": job_index,
                        "bullet_index": bullet_index,
                    }
                )
    return bullets


def _extract_json_object(response_text: str) -> str:
    text = response_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ResumeHighlightError("Codex highlight response did not contain a JSON object.")
    return text[start : end + 1]


def _plain_text_without_strong(value: str) -> str:
    return html.unescape(_STRONG_TAG_RE.sub("", value))


def _matches_job_filter(
    *,
    company: str,
    job_order: str,
    experience_company: str | None,
    experience_job_order: str | None,
) -> bool:
    if experience_company and experience_company.casefold() not in company.casefold():
        return False
    return not experience_job_order or _order_value(experience_job_order) == job_order


def _short_process_output(value: str, *, limit: int = 800) -> str:
    text = " ".join(value.split())
    return text[:limit] or "no process output"


def _renders(value: Mapping[str, Any]) -> bool:
    return value.get("render", True) is not False


def _order_value(value: object, *, fallback: int | None = None) -> str:
    if value is None and fallback is not None:
        return str(fallback)
    return str(value or "").strip()


def _string(value: object) -> str:
    return str(value or "").strip()
