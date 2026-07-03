from __future__ import annotations

import json
import shlex
import sqlite3
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

from linkedin_career_mcp.ats import calculate_ats_diagnostics, extract_pdf_text
from linkedin_career_mcp.errors import WorkflowError
from linkedin_career_mcp.resume_highlighting import (
    DEFAULT_CODEX_COMMAND,
    DEFAULT_CODEX_MODEL,
    DEFAULT_CODEX_TIMEOUT_SECONDS,
)
from linkedin_career_mcp.resume_rendering import (
    render_resume_html_from_mapping,
    render_resume_pdf_from_html,
)
from linkedin_career_mcp.webapp import (
    DEFAULT_RESUME_VARIANT,
    MANUAL_PASS_RESUME_VARIANT,
    SECOND_PASS_RESUME_VARIANT,
    connect_database,
    store_application_resume_variant,
)

MANUAL_PASS_INPUT_BUNDLE_SCHEMA_VERSION = "manual_resume_pass_input_bundle.v1"
MANUAL_PASS_RESPONSE_SCHEMA_VERSION = "manual_resume_pass_response.v1"
MANUAL_PASS_VALIDATION_SCHEMA_VERSION = "manual_resume_pass_validation.v1"


class ResumeManualPassError(WorkflowError):
    """Raised when the manual resume pass workflow cannot safely continue."""


@dataclass(frozen=True)
class ManualPassResponse:
    application_resume: dict[str, Any]
    rationale: str
    unsupported_terms: list[str]
    reviewer_notes: list[str]


def run_manual_resume_pass_for_job(
    *,
    database_path: Path,
    job_id: str,
    master_resume_path: Path,
    master_resume_text_path: Path | None,
    template_path: Path,
    codex_command: str = DEFAULT_CODEX_COMMAND,
    codex_model: str = DEFAULT_CODEX_MODEL,
    timeout_seconds: int = DEFAULT_CODEX_TIMEOUT_SECONDS,
    artifact_dir: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    row, v1_variant, v2_variant = _load_manual_pass_rows(
        database_path=database_path,
        job_id=job_id,
    )
    selected_variant_before = str(
        row["selected_resume_variant"] or DEFAULT_RESUME_VARIANT
    )
    bundle = build_manual_pass_input_bundle(
        row=row,
        v1_variant=v1_variant,
        v2_variant=v2_variant,
        master_resume_path=master_resume_path,
        master_resume_text_path=master_resume_text_path,
    )
    prompt = build_manual_pass_prompt(bundle)
    response_text = run_codex_manual_pass(
        prompt,
        project_root=_project_root(),
        codex_command=codex_command,
        codex_model=codex_model,
        timeout_seconds=timeout_seconds,
    )
    parsed_response = parse_manual_pass_response(response_text)
    aro_yaml = yaml.safe_dump(
        parsed_response.application_resume,
        sort_keys=False,
        allow_unicode=False,
    )
    resume_html = render_resume_html_from_mapping(
        resume=parsed_response.application_resume,
        template_path=template_path,
    )
    resume_pdf = render_resume_pdf_from_html(resume_html)
    job_description = str(row["prompt_job_description"] or row["job_description"] or "")
    diagnostics = calculate_ats_diagnostics(
        resume_pdf=resume_pdf,
        job_description=job_description,
    )

    validation_payload = {
        "schema_version": MANUAL_PASS_VALIDATION_SCHEMA_VERSION,
        "is_valid": True,
        "unsupported_terms": parsed_response.unsupported_terms,
        "reviewer_notes": parsed_response.reviewer_notes,
        "parent_variant_key": SECOND_PASS_RESUME_VARIANT,
    }
    model_metadata = {
        "client": "Codex CLI",
        "model": codex_model,
        "codex_command": codex_command,
    }
    parsed_response_payload = {
        "schema_version": MANUAL_PASS_RESPONSE_SCHEMA_VERSION,
        "rationale": parsed_response.rationale,
        "unsupported_terms": parsed_response.unsupported_terms,
        "reviewer_notes": parsed_response.reviewer_notes,
    }

    if artifact_dir is not None:
        _write_manual_pass_artifacts(
            artifact_dir=artifact_dir,
            job_id=job_id,
            bundle=bundle,
            prompt=prompt,
            response_text=response_text,
            aro_yaml=aro_yaml,
            resume_html=resume_html,
            resume_pdf=resume_pdf,
        )

    if not dry_run:
        store_application_resume_variant(
            database_path=database_path,
            job_id=job_id,
            variant_key=MANUAL_PASS_RESUME_VARIANT,
            variant_label="Manual pass",
            source="codex_manual_pass",
            parent_variant_key=SECOND_PASS_RESUME_VARIANT,
            application_resume_object=aro_yaml,
            resume_html=resume_html,
            resume_pdf=resume_pdf,
            ats_score=diagnostics.score,
            ats_diagnostics=asdict(diagnostics),
            evidence_packet=bundle,
            critique_prompt=prompt,
            critique_response=response_text,
            critique=parsed_response_payload,
            validation=validation_payload,
            model_metadata=model_metadata,
        )
    selected_variant_after = (
        _load_selected_resume_variant(database_path=database_path, job_id=job_id)
        if not dry_run
        else selected_variant_before
    )

    return {
        "job_id": job_id,
        "company": row["company"],
        "job_title": row["job_title"],
        "stored_variant": MANUAL_PASS_RESUME_VARIANT,
        "selected_variant_changed": selected_variant_after != selected_variant_before,
        "selected_resume_variant": selected_variant_after,
        "dry_run": dry_run,
        "ats_score": diagnostics.score.overall_score,
        "v1_ats_score": v1_variant["ats_score"],
        "v2_ats_score": v2_variant["ats_score"],
        "unsupported_terms": parsed_response.unsupported_terms,
        "reviewer_notes": parsed_response.reviewer_notes,
        "model": codex_model,
    }


def build_manual_pass_input_bundle(
    *,
    row: sqlite3.Row | Mapping[str, Any],
    v1_variant: sqlite3.Row | Mapping[str, Any],
    v2_variant: sqlite3.Row | Mapping[str, Any],
    master_resume_path: Path,
    master_resume_text_path: Path | None,
) -> dict[str, Any]:
    master_resume_yaml = master_resume_path.read_text(encoding="utf-8")
    master_resume_text = (
        master_resume_text_path.read_text(encoding="utf-8")
        if master_resume_text_path is not None and master_resume_text_path.is_file()
        else ""
    )
    return {
        "schema_version": MANUAL_PASS_INPUT_BUNDLE_SCHEMA_VERSION,
        "job": {
            "job_id": row["job_id"],
            "company": row["company"],
            "job_title": row["job_title"],
            "linkedin_url": row["linkedin_url"],
            "selected_resume_variant": row["selected_resume_variant"]
            or DEFAULT_RESUME_VARIANT,
            "applied_to": row["applied_to"],
            "date_applied": row["date_applied"],
            "notes": row["notes"],
        },
        "job_descriptions": {
            "full_jod": row["job_description"] or "",
            "prompt_jod": row["prompt_job_description"] or "",
        },
        "master_resume_evidence": {
            "master_resume_yaml": _yaml_or_text(master_resume_yaml),
            "master_resume_text": master_resume_text,
        },
        "variants": {
            DEFAULT_RESUME_VARIANT: _variant_bundle(v1_variant),
            SECOND_PASS_RESUME_VARIANT: _variant_bundle(v2_variant),
        },
        "v2_second_pass": {
            "critique": _json_or_empty(v2_variant["critique_json"]),
            "validation": _json_or_empty(v2_variant["validation_json"]),
            "evidence_packet": _json_or_empty(v2_variant["evidence_packet_json"]),
            "external_critique": _json_or_empty(v2_variant["external_critique_json"]),
            "model_metadata": _json_or_empty(v2_variant["model_metadata_json"]),
        },
    }


def build_manual_pass_prompt(bundle: Mapping[str, Any]) -> str:
    return (
        "You are Codex running the manual resume passthrough workflow for the "
        "LinkedIn Career MCP tracker.\n"
        "Produce one factual manual-pass Application Resume Object (ARO) that may "
        "borrow the best supported edits from v1 and v2 while rejecting unsupported "
        "claims. This is a human-quality pass, not keyword stuffing.\n\n"
        "Hard rules:\n"
        "- Return only valid JSON. Do not include Markdown fences or commentary.\n"
        "- Preserve the ARO schema and return the complete ARO, not a patch.\n"
        "- Use only claims supported by the master-resume evidence or existing ARO "
        "evidence. Do not invent tools, certifications, metrics, employers, or "
        "responsibilities.\n"
        "- Consider the v2 critique, validation, accepted changes, rejected changes, "
        "ATS diagnostics, full JOD, and prompt JOD.\n"
        "- Prefer clear, role-aligned language over chasing a numeric ATS score.\n"
        "- Leave unsupported requested terms out and report them in unsupported_terms.\n\n"
        "JSON shape:\n"
        "{\n"
        f'  "schema_version": "{MANUAL_PASS_RESPONSE_SCHEMA_VERSION}",\n'
        '  "application_resume_object": { "schema_version": "..." },\n'
        '  "rationale": "short explanation of the manual pass",\n'
        '  "unsupported_terms": ["term left out because evidence was insufficient"],\n'
        '  "reviewer_notes": ["short note"]\n'
        "}\n\n"
        "Input bundle:\n"
        f"{json.dumps(bundle, indent=2, ensure_ascii=True)}\n"
    )


def run_codex_manual_pass(
    prompt: str,
    *,
    project_root: Path,
    codex_command: str = DEFAULT_CODEX_COMMAND,
    codex_model: str = DEFAULT_CODEX_MODEL,
    timeout_seconds: int = DEFAULT_CODEX_TIMEOUT_SECONDS,
) -> str:
    command = shlex.split(codex_command)
    if not command:
        raise ResumeManualPassError("Codex command cannot be empty.")

    with tempfile.TemporaryDirectory(prefix="resume-manual-pass-") as temp_dir:
        output_path = Path(temp_dir) / "codex-output.txt"
        args = [
            *command,
            "--ask-for-approval",
            "never",
            "exec",
            "-C",
            str(project_root),
            "--sandbox",
            "read-only",
            "--output-last-message",
            str(output_path),
        ]
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
            raise ResumeManualPassError(
                f"Codex manual pass timed out after {timeout_seconds} seconds."
            ) from exc

        if completed.returncode != 0:
            stderr = _short_process_output(completed.stderr or completed.stdout)
            raise ResumeManualPassError(
                f"Codex manual pass exited with status {completed.returncode}: {stderr}"
            )
        if not output_path.is_file():
            raise ResumeManualPassError("Codex did not write a final-message output file.")
        response = output_path.read_text(encoding="utf-8").strip()
        if not response:
            raise ResumeManualPassError("Codex returned an empty manual-pass response.")
        return response


def parse_manual_pass_response(response_text: str) -> ManualPassResponse:
    payload = _extract_json_object(response_text)
    schema_version = str(payload.get("schema_version") or "")
    if schema_version and schema_version != MANUAL_PASS_RESPONSE_SCHEMA_VERSION:
        raise ResumeManualPassError(
            f"Codex manual pass used unsupported schema_version={schema_version!r}."
        )
    application_resume = payload.get("application_resume_object")
    if isinstance(application_resume, str):
        application_resume = yaml.safe_load(application_resume)
    if not isinstance(application_resume, dict):
        raise ResumeManualPassError(
            "Codex manual pass response must include application_resume_object."
        )
    return ManualPassResponse(
        application_resume=application_resume,
        rationale=str(payload.get("rationale") or "").strip(),
        unsupported_terms=_string_list(payload.get("unsupported_terms")),
        reviewer_notes=_string_list(payload.get("reviewer_notes")),
    )


def _load_manual_pass_rows(
    *,
    database_path: Path,
    job_id: str,
) -> tuple[sqlite3.Row, sqlite3.Row, sqlite3.Row]:
    with connect_database(database_path) as connection:
        row = connection.execute(
            """
            SELECT *
            FROM applications
            WHERE job_id = ?
            """,
            (job_id,),
        ).fetchone()
        if row is None:
            raise ResumeManualPassError(f"Application row was not found for job_id={job_id}.")
        variants = {
            variant["variant_key"]: variant
            for variant in connection.execute(
                """
                SELECT *
                FROM application_resume_variants
                WHERE job_id = ?
                  AND variant_key IN (?, ?)
                """,
                (job_id, DEFAULT_RESUME_VARIANT, SECOND_PASS_RESUME_VARIANT),
            ).fetchall()
        }
    missing = [
        variant_key
        for variant_key in (DEFAULT_RESUME_VARIANT, SECOND_PASS_RESUME_VARIANT)
        if variant_key not in variants
    ]
    if missing:
        raise ResumeManualPassError(
            f"Manual pass requires stored variants for: {', '.join(missing)}."
        )
    return row, variants[DEFAULT_RESUME_VARIANT], variants[SECOND_PASS_RESUME_VARIANT]


def _load_selected_resume_variant(*, database_path: Path, job_id: str) -> str:
    with connect_database(database_path) as connection:
        row = connection.execute(
            """
            SELECT selected_resume_variant
            FROM applications
            WHERE job_id = ?
            """,
            (job_id,),
        ).fetchone()
    if row is None:
        raise ResumeManualPassError(f"Application row was not found for job_id={job_id}.")
    return str(row["selected_resume_variant"] or DEFAULT_RESUME_VARIANT)


def _variant_bundle(variant: sqlite3.Row | Mapping[str, Any]) -> dict[str, Any]:
    resume_pdf = variant["resume_content"]
    return {
        "variant_key": variant["variant_key"],
        "variant_label": variant["variant_label"],
        "source": variant["source"],
        "parent_variant_key": variant["parent_variant_key"],
        "application_resume_object": _yaml_or_text(variant["application_resume_object"]),
        "artifacts": {
            "resume_filename": variant["resume_filename"],
            "resume_html_filename": variant["resume_html_filename"],
            "resume_html_content": variant["resume_html_content"] or "",
            "resume_pdf_text": _safe_pdf_text(resume_pdf),
            "resume_pdf_bytes": len(resume_pdf) if resume_pdf is not None else 0,
        },
        "ats_diagnostics": _variant_ats_diagnostics(variant),
        "updated_at": variant["updated_at"],
    }


def _variant_ats_diagnostics(variant: sqlite3.Row | Mapping[str, Any]) -> dict[str, Any]:
    stored = _json_or_empty(variant["ats_diagnostics_json"])
    if stored:
        return stored
    return {
        "score": {
            "overall_score": variant["ats_score"],
            "parsing_score": variant["ats_parsing_score"],
            "keyword_match_score": variant["ats_keyword_score"],
            "semantic_match_score": variant["ats_semantic_score"],
            "formatting_risk": variant["ats_formatting_risk"],
            "missing_high_value_terms": _split_terms(variant["ats_missing_terms"]),
        }
    }


def _write_manual_pass_artifacts(
    *,
    artifact_dir: Path,
    job_id: str,
    bundle: Mapping[str, Any],
    prompt: str,
    response_text: str,
    aro_yaml: str,
    resume_html: str,
    resume_pdf: bytes,
) -> None:
    target_dir = artifact_dir / _safe_filename(job_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "manual_pass_input_bundle.json").write_text(
        f"{json.dumps(bundle, indent=2, sort_keys=True)}\n",
        encoding="utf-8",
    )
    (target_dir / "manual_pass_prompt.txt").write_text(prompt, encoding="utf-8")
    (target_dir / "manual_pass_response.json").write_text(
        f"{response_text.strip()}\n",
        encoding="utf-8",
    )
    (target_dir / "manual_pass.yml").write_text(aro_yaml, encoding="utf-8")
    (target_dir / "manual_pass.html").write_text(resume_html, encoding="utf-8")
    (target_dir / "manual_pass.pdf").write_bytes(resume_pdf)


def _yaml_or_text(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        parsed = yaml.safe_load(value)
    except yaml.YAMLError:
        return value
    return parsed if parsed is not None else value


def _json_or_empty(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _extract_json_object(response_text: str) -> dict[str, Any]:
    text = response_text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ResumeManualPassError(f"Codex manual pass returned invalid JSON: {exc}") from exc
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError as nested_exc:
            raise ResumeManualPassError(
                f"Codex manual pass returned invalid JSON: {nested_exc}"
            ) from nested_exc
    if not isinstance(payload, dict):
        raise ResumeManualPassError("Codex manual pass response must be a JSON object.")
    return payload


def _safe_pdf_text(resume_pdf: bytes | None) -> str:
    if not resume_pdf:
        return ""
    try:
        return extract_pdf_text(resume_pdf)
    except Exception:  # noqa: BLE001
        return ""


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _split_terms(value: Any) -> list[str]:
    return [term.strip() for term in str(value or "").split(",") if term.strip()]


def _short_process_output(value: str, *, max_chars: int = 1200) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}..."


def _safe_filename(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)


def _project_root() -> Path:
    candidate = Path(__file__).resolve().parents[2]
    if (candidate / "Makefile").is_file():
        return candidate
    return Path.cwd()
