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


def test_agentic_workflow_skill_documents_repo_guardrails() -> None:
    skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

    assert "AGENTS.md" in skill
    assert "tmp/agentic-workflows/" in skill
    assert "P-step" in skill
    assert "G-step" in skill
    assert "Pause Conditions" in skill
    assert "not a daemon" in skill


def test_agentic_workflow_templates_are_valid_json() -> None:
    tracker = json.loads(TRACKER_TEMPLATE.read_text(encoding="utf-8"))
    schema = json.loads(TRACKER_SCHEMA.read_text(encoding="utf-8"))
    plan = PLAN_TEMPLATE.read_text(encoding="utf-8")

    assert tracker["schema_version"] == 1
    assert tracker["workflow_id"] == "__WORKFLOW_ID__"
    assert tracker["release_version"] == "__VERSION__"
    assert tracker["objective"] == "__OBJECTIVE__"
    assert tracker["completed_steps"] == []
    assert tracker["gates"] == []
    assert "workflow_id" in schema["required"]
    assert "pause_conditions" in schema["required"]
    assert "__WORKFLOW_ID__" in plan
    assert "AGENTS.md" in plan


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
