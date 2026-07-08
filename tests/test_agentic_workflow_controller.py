from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = PROJECT_ROOT / "skills" / "agentic-workflow-controller"
SCRIPT = SKILL_DIR / "scripts" / "workflow_state.py"
TRACKER_TEMPLATE = SKILL_DIR / "assets" / "workflow-tracker.template.json"
TRACKER_SCHEMA = SKILL_DIR / "assets" / "workflow-tracker.schema.json"
PLAN_TEMPLATE = SKILL_DIR / "assets" / "workflow-plan.template.md"
ROUTE_TEMPLATE = SKILL_DIR / "assets" / "evidence-route.prompt.md"


def test_agentic_workflow_skill_documents_repo_guardrails() -> None:
    skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

    assert "AGENTS.md" in skill
    assert "tmp/agentic-workflows/" in skill
    assert "P-step" in skill
    assert "G-step" in skill
    assert "Pause Conditions" in skill
    assert "not a daemon" in skill
    assert "Evidence Routes" in skill
    assert "Subagents should receive a narrow read-only prompt" in skill
    assert "read-only evidence routes" in skill
    assert "The main agent owns" in skill
    assert "local_fallback" in skill


def test_agentic_workflow_templates_are_valid_json() -> None:
    tracker = json.loads(TRACKER_TEMPLATE.read_text(encoding="utf-8"))
    schema = json.loads(TRACKER_SCHEMA.read_text(encoding="utf-8"))
    plan = PLAN_TEMPLATE.read_text(encoding="utf-8")

    assert tracker["schema_version"] == 1
    assert tracker["workflow_id"] == "__WORKFLOW_ID__"
    assert tracker["release_version"] == "__VERSION__"
    assert tracker["objective"] == "__OBJECTIVE__"
    assert tracker["completed_steps"] == []
    assert tracker["evidence_routes"] == []
    assert tracker["gates"] == []
    assert "workflow_id" in schema["required"]
    assert "pause_conditions" in schema["required"]
    assert "evidence_routes" not in schema["required"]
    assert "evidence_routes" in schema["properties"]
    assert "__WORKFLOW_ID__" in plan
    assert "AGENTS.md" in plan
    route_prompt = ROUTE_TEMPLATE.read_text(encoding="utf-8")
    assert "__ROUTE_ID__" in route_prompt
    assert "read-only evidence route" in route_prompt


def test_workflow_state_init_validate_and_overwrite_protection(tmp_path: Path) -> None:
    init = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "init",
            "v4-8-0-render-stamats-vida",
            "--version",
            "4.8.0",
            "--objective",
            "Render Stamats and VIDA as older resume experience",
            "--current-step",
            "P01",
            "--runtime-root",
            str(tmp_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    init_result = json.loads(init.stdout)
    tracker_path = Path(init_result["tracker"])
    plan_path = Path(init_result["plan"])

    assert tracker_path.exists()
    assert plan_path.exists()
    tracker = json.loads(tracker_path.read_text(encoding="utf-8"))
    assert tracker["workflow_id"] == "v4-8-0-render-stamats-vida"
    assert tracker["release_version"] == "4.8.0"
    assert tracker["objective"] == "Render Stamats and VIDA as older resume experience"
    assert tracker["current_step"] == "P01"
    assert "Render Stamats and VIDA" in plan_path.read_text(encoding="utf-8")

    validate = subprocess.run(
        [sys.executable, str(SCRIPT), "validate", str(tracker_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    validate_result = json.loads(validate.stdout)
    assert validate_result["valid"] is True
    assert validate_result["current_step"] == "P01"

    duplicate = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "init",
            "v4-8-0-render-stamats-vida",
            "--version",
            "4.8.0",
            "--objective",
            "Render Stamats and VIDA as older resume experience",
            "--runtime-root",
            str(tmp_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert duplicate.returncode == 2
    assert "already exists" in duplicate.stderr


def test_workflow_state_records_step_gate_and_pause(tmp_path: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "init",
            "sample-flow",
            "--version",
            "4.7.0",
            "--objective",
            "Exercise workflow state transitions",
            "--current-step",
            "P01",
            "--runtime-root",
            str(tmp_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    tracker_path = tmp_path / "sample-flow" / "tracker.json"

    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "complete",
            str(tracker_path),
            "P01",
            "--next-step",
            "G01",
            "--evidence",
            "git status checked",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "gate",
            str(tracker_path),
            "G01",
            "--decision",
            "amend",
            "--next-step",
            "P02",
            "--amendment",
            "tighten validation",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "pause",
            str(tracker_path),
            "--condition-id",
            "needs-user-approval",
            "--reason",
            "Live tracker mutation requires approval",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    tracker = json.loads(tracker_path.read_text(encoding="utf-8"))
    assert tracker["state"] == "paused"
    assert tracker["completed_steps"][0]["step_id"] == "P01"
    assert tracker["completed_steps"][0]["evidence"] == ["git status checked"]
    assert tracker["gates"][0]["gate_id"] == "G01"
    assert tracker["gates"][0]["decision"] == "amend"
    assert tracker["gates"][0]["amendments"] == ["tighten validation"]
    assert tracker["pause_conditions"][0]["condition_id"] == "needs-user-approval"


def test_workflow_state_accepts_legacy_tracker_without_evidence_routes(tmp_path: Path) -> None:
    tracker = json.loads(TRACKER_TEMPLATE.read_text(encoding="utf-8"))
    tracker.pop("evidence_routes")
    tracker["workflow_id"] = "legacy-flow"
    tracker["release_version"] = "4.7.0"
    tracker["objective"] = "Validate legacy tracker compatibility"
    tracker["current_step"] = "P01"
    tracker["created_at"] = "2026-07-08T00:00:00+00:00"
    tracker["updated_at"] = "2026-07-08T00:00:00+00:00"
    tracker_path = tmp_path / "legacy-flow" / "tracker.json"
    tracker_path.parent.mkdir()
    tracker_path.write_text(json.dumps(tracker), encoding="utf-8")

    validate = subprocess.run(
        [sys.executable, str(SCRIPT), "validate", str(tracker_path)],
        check=True,
        capture_output=True,
        text=True,
    )

    validate_result = json.loads(validate.stdout)
    assert validate_result["valid"] is True


def test_workflow_state_records_evidence_route_lifecycle(tmp_path: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "init",
            "route-flow",
            "--version",
            "4.9.0",
            "--objective",
            "Exercise evidence routes",
            "--current-step",
            "P01",
            "--runtime-root",
            str(tmp_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    tracker_path = tmp_path / "route-flow" / "tracker.json"

    route_start = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "route-start",
            str(tracker_path),
            "P01-evidence-routes",
            "--step-id",
            "P01",
            "--title",
            "Evidence route audit",
            "--execution-mode",
            "subagent",
            "--prompt-summary",
            "Inspect route behavior",
            "--prompt-text",
            "Read only and report findings.",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    route_start_result = json.loads(route_start.stdout)
    assert route_start_result["evidence_routes"] == 1

    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "route-complete",
            str(tracker_path),
            "P01-evidence-routes",
            "--summary",
            "Route behavior is covered.",
            "--finding",
            "Route prompt was recorded.",
            "--finding",
            "Route artifact was recorded.",
            "--recommendation",
            "continue",
            "--artifact-text",
            "# P01-evidence-routes\n\nSummary: route complete.\n",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    tracker = json.loads(tracker_path.read_text(encoding="utf-8"))
    route = tracker["evidence_routes"][0]
    assert route["route_id"] == "P01-evidence-routes"
    assert route["step_id"] == "P01"
    assert route["status"] == "complete"
    assert route["execution_mode"] == "subagent"
    assert route["summary"] == "Route behavior is covered."
    assert route["findings"] == [
        "Route prompt was recorded.",
        "Route artifact was recorded.",
    ]
    assert route["recommendation"] == "continue"
    assert route["prompt_path"].endswith("P01-evidence-routes.prompt.md")
    assert route["artifact_path"].endswith("P01-evidence-routes.md")
    assert (tmp_path / "route-flow" / "routes" / "P01-evidence-routes.prompt.md").exists()
    assert (tmp_path / "route-flow" / "routes" / "P01-evidence-routes.md").exists()


def test_workflow_state_records_failed_evidence_route(tmp_path: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "init",
            "failed-route-flow",
            "--version",
            "4.9.0",
            "--objective",
            "Exercise failed evidence routes",
            "--runtime-root",
            str(tmp_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    tracker_path = tmp_path / "failed-route-flow" / "tracker.json"
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "route-start",
            str(tracker_path),
            "P02-evidence-quality",
            "--step-id",
            "P02",
            "--title",
            "Quality route",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "route-fail",
            str(tracker_path),
            "P02-evidence-quality",
            "--summary",
            "Route could not inspect required artifacts.",
            "--finding",
            "Expected artifact was missing.",
            "--recommendation",
            "pause",
            "--error",
            "missing artifact",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    tracker = json.loads(tracker_path.read_text(encoding="utf-8"))
    route = tracker["evidence_routes"][0]
    assert route["status"] == "failed"
    assert route["execution_mode"] == "local_fallback"
    assert route["error"] == "missing artifact"
    assert route["recommendation"] == "pause"
