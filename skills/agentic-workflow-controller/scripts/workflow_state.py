#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
ASSETS_DIR = SKILL_DIR / "assets"
TRACKER_TEMPLATE = ASSETS_DIR / "workflow-tracker.template.json"
PLAN_TEMPLATE = ASSETS_DIR / "workflow-plan.template.md"
DEFAULT_RUNTIME_ROOT = PROJECT_ROOT / "tmp" / "agentic-workflows"

REQUIRED_KEYS: dict[str, type | tuple[type, ...]] = {
    "schema_version": int,
    "workflow_id": str,
    "release_version": str,
    "objective": str,
    "state": str,
    "current_step": (str, type(None)),
    "planned_steps": list,
    "completed_steps": list,
    "gates": list,
    "pause_conditions": list,
    "validation": list,
    "branch": (str, type(None)),
    "pull_request": (str, int, type(None)),
    "artifacts": list,
    "created_at": str,
    "updated_at": str,
}
OPTIONAL_KEYS: dict[str, type | tuple[type, ...]] = {
    "evidence_routes": list,
}
VALID_STATES = {"running", "paused", "complete", "blocked"}
VALID_ROUTE_STATUSES = {"running", "complete", "failed"}
VALID_ROUTE_EXECUTION_MODES = {"subagent", "local_fallback"}


class WorkflowStateError(RuntimeError):
    """Raised when workflow state cannot be updated safely."""


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _replace_placeholders(value: Any, replacements: dict[str, str]) -> Any:
    if isinstance(value, str):
        for placeholder, replacement in replacements.items():
            value = value.replace(placeholder, replacement)
        return value
    if isinstance(value, list):
        return [_replace_placeholders(item, replacements) for item in value]
    if isinstance(value, dict):
        return {
            key: _replace_placeholders(item, replacements)
            for key, item in value.items()
        }
    return value


def _runtime_dir(workflow_id: str, runtime_root: Path) -> Path:
    return runtime_root / workflow_id


def _tracker_path(workflow_id: str, runtime_root: Path) -> Path:
    return _runtime_dir(workflow_id, runtime_root) / "tracker.json"


def _plan_path(workflow_id: str, runtime_root: Path) -> Path:
    return _runtime_dir(workflow_id, runtime_root) / "plan.md"


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise WorkflowStateError(f"{path} must contain a JSON object.")
    return data


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _validate_payload(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key, expected_type in REQUIRED_KEYS.items():
        if key not in payload:
            errors.append(f"missing required key: {key}")
            continue
        if not isinstance(payload[key], expected_type):
            errors.append(
                f"{key} must be {expected_type}, got {type(payload[key]).__name__}"
            )
    for key, expected_type in OPTIONAL_KEYS.items():
        if key not in payload:
            continue
        if not isinstance(payload[key], expected_type):
            errors.append(
                f"{key} must be {expected_type}, got {type(payload[key]).__name__}"
            )
    extra_keys = sorted(set(payload) - set(REQUIRED_KEYS) - set(OPTIONAL_KEYS))
    for key in extra_keys:
        errors.append(f"unexpected key: {key}")
    if payload.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if payload.get("state") not in VALID_STATES:
        errors.append(f"state must be one of {sorted(VALID_STATES)}")
    for index, route in enumerate(payload.get("evidence_routes") or []):
        if not isinstance(route, dict):
            errors.append(f"evidence_routes[{index}] must be an object")
            continue
        for key in ("route_id", "step_id", "title", "status", "execution_mode"):
            if not route.get(key):
                errors.append(f"evidence_routes[{index}].{key} is required")
        if route.get("status") not in VALID_ROUTE_STATUSES:
            errors.append(
                f"evidence_routes[{index}].status must be one of "
                f"{sorted(VALID_ROUTE_STATUSES)}"
            )
        if route.get("execution_mode") not in VALID_ROUTE_EXECUTION_MODES:
            errors.append(
                f"evidence_routes[{index}].execution_mode must be one of "
                f"{sorted(VALID_ROUTE_EXECUTION_MODES)}"
            )
    return errors


def _load_valid_tracker(path: Path) -> dict[str, Any]:
    payload = _read_json(path)
    errors = _validate_payload(payload)
    if errors:
        raise WorkflowStateError("; ".join(errors))
    return payload


def _save_tracker(path: Path, payload: dict[str, Any]) -> None:
    payload["updated_at"] = _now()
    errors = _validate_payload(payload)
    if errors:
        raise WorkflowStateError("; ".join(errors))
    _write_json(path, payload)


def _routes_dir(tracker_path: Path) -> Path:
    return tracker_path.parent / "routes"


def _route_artifact_path(tracker_path: Path, route_id: str) -> Path:
    return _routes_dir(tracker_path) / f"{route_id}.md"


def _route_prompt_path(tracker_path: Path, route_id: str) -> Path:
    return _routes_dir(tracker_path) / f"{route_id}.prompt.md"


def _relative_to_project(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _route_list(payload: dict[str, Any]) -> list[dict[str, Any]]:
    routes = payload.setdefault("evidence_routes", [])
    if not isinstance(routes, list):
        raise WorkflowStateError("evidence_routes must be a list")
    return routes


def _find_route(payload: dict[str, Any], route_id: str) -> dict[str, Any]:
    for route in _route_list(payload):
        if route.get("route_id") == route_id:
            return route
    raise WorkflowStateError(f"evidence route not found: {route_id}")


def _write_optional_text(path: Path, text: str | None) -> None:
    if text is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def init_workflow(args: argparse.Namespace) -> dict[str, Any]:
    runtime_root = args.runtime_root.resolve()
    workflow_dir = _runtime_dir(args.workflow_id, runtime_root)
    tracker_path = _tracker_path(args.workflow_id, runtime_root)
    plan_path = _plan_path(args.workflow_id, runtime_root)
    if workflow_dir.exists() and not args.force:
        raise WorkflowStateError(
            f"{workflow_dir} already exists; use --force only when intentionally replacing it."
        )
    if workflow_dir.exists():
        shutil.rmtree(workflow_dir)
    workflow_dir.mkdir(parents=True, exist_ok=True)

    created_at = _now()
    replacements = {
        "__WORKFLOW_ID__": args.workflow_id,
        "__VERSION__": args.version,
        "__OBJECTIVE__": args.objective,
        "__CREATED_AT__": created_at,
    }
    template = _read_json(TRACKER_TEMPLATE)
    tracker = _replace_placeholders(template, replacements)
    tracker["current_step"] = args.current_step
    _save_tracker(tracker_path, tracker)

    plan_text = PLAN_TEMPLATE.read_text(encoding="utf-8")
    for placeholder, replacement in replacements.items():
        plan_text = plan_text.replace(placeholder, replacement)
    plan_path.write_text(plan_text, encoding="utf-8")

    return {
        "workflow_id": args.workflow_id,
        "tracker": str(tracker_path),
        "plan": str(plan_path),
        "state": tracker["state"],
        "current_step": tracker["current_step"],
    }


def status(args: argparse.Namespace) -> dict[str, Any]:
    payload = _load_valid_tracker(args.tracker)
    routes = payload.get("evidence_routes") or []
    return {
        "workflow_id": payload["workflow_id"],
        "release_version": payload["release_version"],
        "state": payload["state"],
        "current_step": payload["current_step"],
        "completed_steps": len(payload["completed_steps"]),
        "gates": len(payload["gates"]),
        "evidence_routes": len(routes),
        "pause_conditions": len(payload["pause_conditions"]),
        "updated_at": payload["updated_at"],
    }


def set_current(args: argparse.Namespace) -> dict[str, Any]:
    payload = _load_valid_tracker(args.tracker)
    payload["current_step"] = args.step_id
    if payload["state"] == "paused":
        payload["state"] = "running"
    _save_tracker(args.tracker, payload)
    return status(args)


def complete(args: argparse.Namespace) -> dict[str, Any]:
    payload = _load_valid_tracker(args.tracker)
    payload["completed_steps"].append(
        {
            "step_id": args.step_id,
            "completed_at": _now(),
            "note": args.note,
            "evidence": args.evidence or [],
        }
    )
    payload["current_step"] = args.next_step
    payload["state"] = "running"
    _save_tracker(args.tracker, payload)
    return status(args)


def gate(args: argparse.Namespace) -> dict[str, Any]:
    payload = _load_valid_tracker(args.tracker)
    payload["gates"].append(
        {
            "gate_id": args.gate_id,
            "assessed_at": _now(),
            "decision": args.decision,
            "note": args.note,
            "amendments": args.amendment or [],
        }
    )
    payload["current_step"] = args.next_step
    payload["state"] = "paused" if args.decision == "pause" else "running"
    _save_tracker(args.tracker, payload)
    return status(args)


def pause(args: argparse.Namespace) -> dict[str, Any]:
    payload = _load_valid_tracker(args.tracker)
    payload["pause_conditions"].append(
        {
            "condition_id": args.condition_id,
            "paused_at": _now(),
            "reason": args.reason,
            "needed": args.needed,
        }
    )
    payload["state"] = "paused"
    _save_tracker(args.tracker, payload)
    return status(args)


def validate(args: argparse.Namespace) -> dict[str, Any]:
    payload = _load_valid_tracker(args.tracker)
    return {
        "workflow_id": payload["workflow_id"],
        "valid": True,
        "state": payload["state"],
        "current_step": payload["current_step"],
    }


def route_start(args: argparse.Namespace) -> dict[str, Any]:
    payload = _load_valid_tracker(args.tracker)
    routes = _route_list(payload)
    if any(route.get("route_id") == args.route_id for route in routes):
        raise WorkflowStateError(f"evidence route already exists: {args.route_id}")
    if args.execution_mode not in VALID_ROUTE_EXECUTION_MODES:
        raise WorkflowStateError(
            f"execution_mode must be one of {sorted(VALID_ROUTE_EXECUTION_MODES)}"
        )

    routes_directory = _routes_dir(args.tracker)
    routes_directory.mkdir(parents=True, exist_ok=True)
    prompt_path = args.prompt_path or _route_prompt_path(args.tracker, args.route_id)
    artifact_path = args.artifact_path or _route_artifact_path(args.tracker, args.route_id)
    _write_optional_text(prompt_path, args.prompt_text)
    created_at = _now()
    routes.append(
        {
            "route_id": args.route_id,
            "step_id": args.step_id,
            "title": args.title,
            "status": "running",
            "execution_mode": args.execution_mode,
            "prompt_path": _relative_to_project(prompt_path),
            "prompt_summary": args.prompt_summary,
            "artifact_path": _relative_to_project(artifact_path),
            "summary": "",
            "findings": [],
            "recommendation": "",
            "created_at": created_at,
            "updated_at": created_at,
        }
    )
    _save_tracker(args.tracker, payload)
    return status(args)


def route_complete(args: argparse.Namespace) -> dict[str, Any]:
    payload = _load_valid_tracker(args.tracker)
    route = _find_route(payload, args.route_id)
    artifact_path = Path(args.artifact_path) if args.artifact_path else Path(route["artifact_path"])
    if not artifact_path.is_absolute():
        artifact_path = PROJECT_ROOT / artifact_path
    _write_optional_text(artifact_path, args.artifact_text)
    route.update(
        {
            "status": "complete",
            "summary": args.summary,
            "findings": args.finding or [],
            "recommendation": args.recommendation,
            "artifact_path": _relative_to_project(artifact_path),
            "updated_at": _now(),
        }
    )
    _save_tracker(args.tracker, payload)
    return status(args)


def route_fail(args: argparse.Namespace) -> dict[str, Any]:
    payload = _load_valid_tracker(args.tracker)
    route = _find_route(payload, args.route_id)
    artifact_path = Path(args.artifact_path) if args.artifact_path else Path(route["artifact_path"])
    if not artifact_path.is_absolute():
        artifact_path = PROJECT_ROOT / artifact_path
    _write_optional_text(artifact_path, args.artifact_text)
    route.update(
        {
            "status": "failed",
            "summary": args.summary,
            "findings": args.finding or [],
            "recommendation": args.recommendation,
            "error": args.error,
            "artifact_path": _relative_to_project(artifact_path),
            "updated_at": _now(),
        }
    )
    _save_tracker(args.tracker, payload)
    return status(args)


def _tracker_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("tracker", type=Path, help="Path to runtime tracker.json.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage agentic workflow runtime state.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create runtime state from templates.")
    init_parser.add_argument("workflow_id")
    init_parser.add_argument("--version", required=True)
    init_parser.add_argument("--objective", required=True)
    init_parser.add_argument("--current-step")
    init_parser.add_argument(
        "--runtime-root",
        type=Path,
        default=DEFAULT_RUNTIME_ROOT,
        help="Directory that contains ignored runtime workflow folders.",
    )
    init_parser.add_argument("--force", action="store_true")
    init_parser.set_defaults(func=init_workflow)

    status_parser = subparsers.add_parser("status", help="Print tracker status.")
    _tracker_arg(status_parser)
    status_parser.set_defaults(func=status)

    set_parser = subparsers.add_parser("set-current", help="Set current P/G step.")
    _tracker_arg(set_parser)
    set_parser.add_argument("step_id")
    set_parser.set_defaults(func=set_current)

    complete_parser = subparsers.add_parser("complete", help="Mark a P step complete.")
    _tracker_arg(complete_parser)
    complete_parser.add_argument("step_id")
    complete_parser.add_argument("--next-step")
    complete_parser.add_argument("--note", default="")
    complete_parser.add_argument("--evidence", action="append")
    complete_parser.set_defaults(func=complete)

    gate_parser = subparsers.add_parser("gate", help="Record a G reassessment gate.")
    _tracker_arg(gate_parser)
    gate_parser.add_argument("gate_id")
    gate_parser.add_argument(
        "--decision",
        choices=("continue", "amend", "pause"),
        required=True,
    )
    gate_parser.add_argument("--next-step")
    gate_parser.add_argument("--note", default="")
    gate_parser.add_argument("--amendment", action="append")
    gate_parser.set_defaults(func=gate)

    pause_parser = subparsers.add_parser("pause", help="Pause for user or external input.")
    _tracker_arg(pause_parser)
    pause_parser.add_argument("--condition-id", required=True)
    pause_parser.add_argument("--reason", required=True)
    pause_parser.add_argument("--needed", default="")
    pause_parser.set_defaults(func=pause)

    validate_parser = subparsers.add_parser("validate", help="Validate tracker shape.")
    _tracker_arg(validate_parser)
    validate_parser.set_defaults(func=validate)

    route_start_parser = subparsers.add_parser(
        "route-start",
        help="Record a read-only evidence route as running.",
    )
    _tracker_arg(route_start_parser)
    route_start_parser.add_argument("route_id")
    route_start_parser.add_argument("--step-id", required=True)
    route_start_parser.add_argument("--title", required=True)
    route_start_parser.add_argument(
        "--execution-mode",
        choices=sorted(VALID_ROUTE_EXECUTION_MODES),
        default="local_fallback",
    )
    route_start_parser.add_argument("--prompt-path", type=Path)
    route_start_parser.add_argument("--prompt-summary", default="")
    route_start_parser.add_argument("--prompt-text")
    route_start_parser.add_argument("--artifact-path", type=Path)
    route_start_parser.set_defaults(func=route_start)

    route_complete_parser = subparsers.add_parser(
        "route-complete",
        help="Mark an evidence route complete with findings.",
    )
    _tracker_arg(route_complete_parser)
    route_complete_parser.add_argument("route_id")
    route_complete_parser.add_argument("--summary", default="")
    route_complete_parser.add_argument("--finding", action="append")
    route_complete_parser.add_argument("--recommendation", default="")
    route_complete_parser.add_argument("--artifact-path", type=Path)
    route_complete_parser.add_argument("--artifact-text")
    route_complete_parser.set_defaults(func=route_complete)

    route_fail_parser = subparsers.add_parser(
        "route-fail",
        help="Mark an evidence route failed with findings.",
    )
    _tracker_arg(route_fail_parser)
    route_fail_parser.add_argument("route_id")
    route_fail_parser.add_argument("--summary", default="")
    route_fail_parser.add_argument("--finding", action="append")
    route_fail_parser.add_argument("--recommendation", default="")
    route_fail_parser.add_argument("--error", required=True)
    route_fail_parser.add_argument("--artifact-path", type=Path)
    route_fail_parser.add_argument("--artifact-text")
    route_fail_parser.set_defaults(func=route_fail)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = args.func(args)
    except WorkflowStateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
