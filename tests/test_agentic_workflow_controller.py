from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_DIR = PROJECT_ROOT / "skills" / "agentic-workflow-controller"
INIT_DIR = PROJECT_ROOT / "skills" / "agentic-workflow-init"
SCRIPT = CONTROLLER_DIR / "scripts" / "workflow_state.py"
TRACKER_TEMPLATE = CONTROLLER_DIR / "assets" / "workflow-tracker.template.json"
TRACKER_SCHEMA = CONTROLLER_DIR / "assets" / "workflow-tracker.schema.json"
PLAN_TEMPLATE = CONTROLLER_DIR / "assets" / "workflow-plan.template.md"
ROUTE_TEMPLATE = CONTROLLER_DIR / "assets" / "evidence-route.prompt.md"
ARTIFACT_MANIFEST_SCHEMA = CONTROLLER_DIR / "assets" / "artifact-manifest.schema.json"


def _run(*args: str | Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *(str(arg) for arg in args)],
        cwd=PROJECT_ROOT,
        check=check,
        capture_output=True,
        text=True,
    )


def _repo_plan(tmp_path: Path, text: str = "# Test Plan\n\nInitial plan.\n") -> Path:
    plan_slug = hashlib.sha256(str(tmp_path).encode("utf-8")).hexdigest()[:12]
    plan_dir = PROJECT_ROOT / "tmp" / "pytest-agentic-plans" / plan_slug
    plan_dir.mkdir(parents=True, exist_ok=True)
    plan_path = plan_dir / "4.10.0-test-plan.md"
    plan_path.write_text(text, encoding="utf-8")
    return plan_path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _init_tracker(
    tmp_path: Path,
    workflow_id: str = "sample-flow",
    *,
    plan_path: Path | None = None,
) -> Path:
    command: list[str | Path] = [
        "init",
        workflow_id,
        "--version",
        "4.10.0",
        "--objective",
        "Exercise workflow state transitions",
        "--current-step",
        "P01",
        "--branch",
        "codex/test-flow",
        "--runtime-root",
        tmp_path,
    ]
    if plan_path is not None:
        command.extend(
            [
                "--plan-path",
                plan_path.relative_to(PROJECT_ROOT),
                "--plan-revision",
                "1",
                "--bootstrap-commit",
                "abc1234",
            ]
        )
    _run(*command)
    return tmp_path / workflow_id / "tracker.json"


def test_agentic_workflow_skills_document_bootstrap_and_execution_boundaries() -> None:
    init_skill = (INIT_DIR / "SKILL.md").read_text(encoding="utf-8")
    controller_skill = (CONTROLLER_DIR / "SKILL.md").read_text(encoding="utf-8")

    assert "AGENTS.md" in init_skill
    assert "bootstrap" in init_skill
    assert "must not implement the feature" in init_skill
    assert "bootstrap commit" in init_skill
    assert "agentic-workflow-controller" in init_skill
    assert (INIT_DIR / "agents" / "openai.yaml").exists()

    assert "AGENTS.md" in controller_skill
    assert "execute or resume" in controller_skill
    assert "Do not use to scaffold" in controller_skill
    assert "committed canonical plan" in controller_skill
    assert "runtime tracker" in controller_skill
    assert "cursor and evidence log" in controller_skill
    assert "plan digest" in controller_skill
    assert "Evidence Routes" in controller_skill
    assert "The main agent owns" in controller_skill
    assert "local_fallback" in controller_skill


def test_agentic_workflow_templates_and_schemas_are_valid_json() -> None:
    tracker = json.loads(TRACKER_TEMPLATE.read_text(encoding="utf-8"))
    schema = json.loads(TRACKER_SCHEMA.read_text(encoding="utf-8"))
    manifest_schema = json.loads(ARTIFACT_MANIFEST_SCHEMA.read_text(encoding="utf-8"))
    plan = PLAN_TEMPLATE.read_text(encoding="utf-8")
    route_prompt = ROUTE_TEMPLATE.read_text(encoding="utf-8")

    assert tracker["schema_version"] == 1
    assert tracker["workflow_id"] == "__WORKFLOW_ID__"
    assert tracker["release_version"] == "__VERSION__"
    assert tracker["target_version"] == "__VERSION__"
    assert tracker["attempted_steps"] == []
    assert tracker["completed_steps"] == []
    assert tracker["artifact_manifests"] == []
    assert tracker["evidence_routes"] == []
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(tracker)
    assert "workflow_id" in schema["required"]
    assert "evidence_routes" not in schema["required"]
    assert "attempted_steps" in schema["properties"]
    assert "artifact_manifests" in schema["properties"]
    assert "plan_digest" in schema["properties"]
    assert manifest_schema["properties"]["storage_root"]["enum"] == ["repo", "external"]
    Draft202012Validator.check_schema(manifest_schema)
    Draft202012Validator(manifest_schema).validate(
        {
            "schema_version": 1,
            "manifest_id": "manifest-1",
            "workflow_id": "sample-flow",
            "step_id": "P01",
            "run_id": "run-1",
            "created_at": "2026-07-08T00:00:00+00:00",
            "storage_root": "external",
            "artifacts": [
                {
                    "artifact_id": "evidence-1",
                    "path": "/tmp/linkedin-career-mcp-agentic/sample-flow/P01/run-1/log.txt",
                    "kind": "log",
                    "summary": "Sanitized log hash only.",
                    "sha256": "a" * 64,
                    "sensitive": False,
                    "sanitized": True,
                }
            ],
        }
    )
    assert "__WORKFLOW_ID__" in plan
    assert "committed plan" in plan
    assert "AGENTS.md" in plan
    assert "__ROUTE_ID__" in route_prompt
    assert "read-only evidence route" in route_prompt


def test_workflow_state_init_binds_to_committed_plan_and_validates_digest(
    tmp_path: Path,
) -> None:
    plan_path = _repo_plan(tmp_path)
    tracker_path = _init_tracker(tmp_path, plan_path=plan_path)
    runtime_plan = tmp_path / "sample-flow" / "plan.md"
    tracker = json.loads(tracker_path.read_text(encoding="utf-8"))

    assert tracker["release_version"] == "4.10.0"
    assert tracker["target_version"] == "4.10.0"
    assert tracker["branch"] == "codex/test-flow"
    assert tracker["plan_path"] == str(plan_path.relative_to(PROJECT_ROOT))
    assert tracker["plan_revision"] == 1
    assert tracker["plan_digest"] == _sha256(plan_path)
    assert tracker["bootstrap_commit"] == "abc1234"
    assert "Runtime Plan Pointer" in runtime_plan.read_text(encoding="utf-8")

    validate = _run("validate", tracker_path)
    assert json.loads(validate.stdout)["valid"] is True

    plan_path.write_text("# Test Plan\n\nChanged plan.\n", encoding="utf-8")
    stale = _run("validate", tracker_path, check=False)
    assert stale.returncode == 2
    assert "digest does not match" in stale.stderr

    rebound = _run(
        "rebind-plan",
        tracker_path,
        "--plan-path",
        plan_path.relative_to(PROJECT_ROOT),
        "--plan-revision",
        "2",
        "--note",
        "G01 amended future work",
    )
    assert json.loads(rebound.stdout)["plan_revision"] == 2
    tracker = json.loads(tracker_path.read_text(encoding="utf-8"))
    assert tracker["release_version"] == "4.10.0"
    assert tracker["target_version"] == "4.10.0"
    assert tracker["plan_digest"] == _sha256(plan_path)
    assert tracker["validation"][-1]["kind"] == "plan_rebind"


def test_workflow_state_accepts_legacy_tracker_without_new_optional_fields(
    tmp_path: Path,
) -> None:
    tracker = json.loads(TRACKER_TEMPLATE.read_text(encoding="utf-8"))
    for key in (
        "target_version",
        "plan_path",
        "plan_revision",
        "plan_digest",
        "bootstrap_commit",
        "attempted_steps",
        "artifact_manifests",
        "evidence_routes",
    ):
        tracker.pop(key)
    tracker["workflow_id"] = "legacy-flow"
    tracker["release_version"] = "4.9.0"
    tracker["objective"] = "Validate legacy tracker compatibility"
    tracker["current_step"] = "P01"
    tracker["created_at"] = "2026-07-08T00:00:00+00:00"
    tracker["updated_at"] = "2026-07-08T00:00:00+00:00"
    tracker_path = tmp_path / "legacy-flow" / "tracker.json"
    tracker_path.parent.mkdir()
    tracker_path.write_text(json.dumps(tracker), encoding="utf-8")

    validate = _run("validate", tracker_path)
    validate_result = json.loads(validate.stdout)

    assert validate_result["valid"] is True


def test_workflow_state_handles_missing_and_corrupt_trackers_without_fabricating_state(
    tmp_path: Path,
) -> None:
    missing_path = tmp_path / "missing-flow" / "tracker.json"
    corrupt_path = tmp_path / "corrupt-flow" / "tracker.json"
    corrupt_path.parent.mkdir()
    corrupt_path.write_text("{not-json", encoding="utf-8")

    missing = _run("validate", missing_path, check=False)
    corrupt = _run("validate", corrupt_path, check=False)

    assert missing.returncode == 2
    assert "tracker not found" in missing.stderr
    assert not missing_path.exists()
    assert corrupt.returncode == 2
    assert "tracker is not valid JSON" in corrupt.stderr
    assert "completed_steps" not in corrupt_path.read_text(encoding="utf-8")


def test_workflow_state_tracks_attempted_and_immutable_completed_steps(
    tmp_path: Path,
) -> None:
    tracker_path = _init_tracker(tmp_path)

    _run(
        "begin",
        tracker_path,
        "P01",
        "--note",
        "Started readiness",
        "--evidence",
        "git status checked",
    )
    _run(
        "complete",
        tracker_path,
        "P01",
        "--next-step",
        "G01",
        "--note",
        "Readiness complete",
        "--evidence",
        "metadata aligned",
    )
    duplicate = _run(
        "complete",
        tracker_path,
        "P01",
        "--next-step",
        "P02",
        "--note",
        "Changed definition",
        check=False,
    )

    tracker = json.loads(tracker_path.read_text(encoding="utf-8"))
    assert tracker["attempted_steps"][0]["step_id"] == "P01"
    assert tracker["completed_steps"][0]["step_id"] == "P01"
    assert duplicate.returncode == 2
    assert "immutable" in duplicate.stderr


def test_workflow_state_uses_lock_file_and_atomic_json_write(tmp_path: Path) -> None:
    tracker_path = _init_tracker(tmp_path)

    _run("begin", tracker_path, "P01", "--note", "First attempt")
    assert json.loads(tracker_path.read_text(encoding="utf-8"))["attempted_steps"]
    assert list(tracker_path.parent.glob(".tracker.json.*.tmp")) == []

    lock_path = tracker_path.with_suffix(tracker_path.suffix + ".lock")
    lock_path.write_text("pid=pytest\n", encoding="utf-8")
    locked = _run("begin", tracker_path, "P02", "--note", "Blocked by lock", check=False)
    lock_path.unlink()

    assert locked.returncode == 2
    assert "tracker lock already exists" in locked.stderr


def test_workflow_state_rejects_unconfined_paths_and_secret_like_values(
    tmp_path: Path,
) -> None:
    tracker_path = _init_tracker(tmp_path)

    outside = _run(
        "route-start",
        tracker_path,
        "P01-evidence-outside",
        "--step-id",
        "P01",
        "--title",
        "Outside path route",
        "--artifact-path",
        "/tmp/outside-route.md",
        check=False,
    )
    secret = _run(
        "route-start",
        tracker_path,
        "P01-evidence-secret",
        "--step-id",
        "P01",
        "--title",
        "Secret route",
        "--prompt-summary",
        "api_key=abcdefghijk",
        check=False,
    )

    assert outside.returncode == 2
    assert "runtime path must stay inside" in outside.stderr
    assert secret.returncode == 2
    assert "secret-like value" in secret.stderr


def test_workflow_state_rejects_recursive_secret_like_manifest_keys(tmp_path: Path) -> None:
    tracker_path = _init_tracker(tmp_path)
    manifest_path = tmp_path / "sample-flow" / "secret-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_id": "manifest-1",
                "workflow_id": "sample-flow",
                "step_id": "P01",
                "run_id": "run-1",
                "created_at": "2026-07-08T00:00:00+00:00",
                "storage_root": "external",
                "artifacts": [
                    {
                        "artifact_id": "evidence-1",
                        "path": "/tmp/linkedin-career-mcp-agentic/sample-flow/P01/run-1/log.txt",
                        "kind": "log",
                        "summary": "Sanitized log hash only.",
                        "sha256": "a" * 64,
                        "credential_hint": "do not write keys here",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    rejected = _run("manifest-add", tracker_path, "secret-manifest.json", check=False)

    assert rejected.returncode == 2
    assert "secret-like key" in rejected.stderr


def test_workflow_state_records_artifact_manifest(tmp_path: Path) -> None:
    tracker_path = _init_tracker(tmp_path)
    manifest_path = tmp_path / "sample-flow" / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest_id": "manifest-1",
                "workflow_id": "sample-flow",
                "step_id": "P01",
                "run_id": "run-1",
                "created_at": "2026-07-08T00:00:00+00:00",
                "storage_root": "external",
                "artifacts": [
                    {
                        "artifact_id": "evidence-1",
                        "path": "/tmp/linkedin-career-mcp-agentic/sample-flow/P01/run-1/log.txt",
                        "kind": "log",
                        "summary": "Sanitized log hash only.",
                        "sha256": "a" * 64,
                        "sensitive": False,
                        "sanitized": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = _run("manifest-add", tracker_path, "manifest.json")
    tracker = json.loads(tracker_path.read_text(encoding="utf-8"))

    assert json.loads(result.stdout)["artifact_manifests"] == 1
    assert tracker["artifact_manifests"][0]["manifest_id"] == "manifest-1"
    assert tracker["artifact_manifests"][0]["storage_root"] == "external"


def test_workflow_state_records_evidence_route_lifecycle(tmp_path: Path) -> None:
    tracker_path = _init_tracker(tmp_path, workflow_id="route-flow")

    route_start = _run(
        "route-start",
        tracker_path,
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
    )
    route_start_result = json.loads(route_start.stdout)
    assert route_start_result["evidence_routes"] == 1

    _run(
        "route-complete",
        tracker_path,
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
    tracker_path = _init_tracker(tmp_path, workflow_id="failed-route-flow")
    _run(
        "route-start",
        tracker_path,
        "P02-evidence-quality",
        "--step-id",
        "P02",
        "--title",
        "Quality route",
    )
    _run(
        "route-fail",
        tracker_path,
        "P02-evidence-quality",
        "--summary",
        "Route could not inspect required artifacts.",
        "--finding",
        "Expected artifact was missing.",
        "--recommendation",
        "pause",
        "--error",
        "missing artifact",
    )

    tracker = json.loads(tracker_path.read_text(encoding="utf-8"))
    route = tracker["evidence_routes"][0]
    assert route["status"] == "failed"
    assert route["execution_mode"] == "local_fallback"
    assert route["error"] == "missing artifact"
    assert route["recommendation"] == "pause"
