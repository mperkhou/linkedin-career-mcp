from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_agents_guidance_exists_with_release_closeout_guardrails() -> None:
    guidance_path = PROJECT_ROOT / "AGENTS.md"
    assert guidance_path.exists()

    guidance = guidance_path.read_text(encoding="utf-8")
    assert "docs/release-notes/<version>.md" in guidance
    assert "annotated tag" in guidance
    assert "push tag `vX.Y.Z` to `origin`" in guidance
    assert "git ls-remote --tags origin refs/tags/vX.Y.Z" in guidance


def test_agents_guidance_captures_core_repo_invariants() -> None:
    guidance = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")

    assert "profile/MASTER-RESUME.yml" in guidance
    assert "output/tracking/applications.sqlite3" in guidance
    assert "manual > v2 > v1" in guidance
    assert "git diff --check" in guidance
    assert "make lint" in guidance
    assert "make test" in guidance


def test_agents_guidance_is_linked_from_docs() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    architecture = (PROJECT_ROOT / "docs/architecture.md").read_text(encoding="utf-8")
    adr = (PROJECT_ROOT / "docs/adr/0005-canonical-agent-guidance.md").read_text(
        encoding="utf-8"
    )
    release_notes = (PROJECT_ROOT / "docs/release-notes/4.3.0.md").read_text(
        encoding="utf-8"
    )

    assert "AGENTS.md" in readme
    assert "docs/adr/0005-canonical-agent-guidance.md" in readme
    assert "docs/release-notes/4.3.0.md" in readme
    assert "AGENTS.md" in architecture
    assert "AGENTS.md" in adr
    assert "AGENTS.md" in release_notes


def test_agentic_orchestration_docs_describe_evidence_routes() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    adr = (PROJECT_ROOT / "docs/adr/0006-agentic-workflow-evidence-routes.md").read_text(
        encoding="utf-8"
    )
    bootstrap_adr = (
        PROJECT_ROOT / "docs/adr/0007-agentic-workflow-bootstrap-and-plan-binding.md"
    ).read_text(encoding="utf-8")
    workflow_docs = (PROJECT_ROOT / "docs/agentic-workflows/README.md").read_text(
        encoding="utf-8"
    )
    release_notes = (PROJECT_ROOT / "docs/release-notes/4.9.0.md").read_text(
        encoding="utf-8"
    )
    release_410_notes = (PROJECT_ROOT / "docs/release-notes/4.10.0.md").read_text(
        encoding="utf-8"
    )

    assert "P steps" in readme
    assert "G gates" in readme
    assert "evidence_routes" in readme
    assert "agentic-workflow-init" in readme
    assert "agentic-workflow-controller" in readme
    assert "local_fallback" in readme
    assert "subagents gather findings" in readme
    assert "main agent owns edits" in readme
    assert "reduces repeated prompt/response management" in adr
    assert "separates read-only evidence gathering from mutation authority" in adr
    assert "subagents are unavailable" in adr
    assert "bootstrap layer creates" in bootstrap_adr
    assert "plan digest" in bootstrap_adr
    assert "Bootstrap Skill Vs Controller Skill" in workflow_docs
    assert "plan digest" in workflow_docs
    assert "Artifact Storage" in workflow_docs
    assert "evidence routes" in release_notes
    assert "agentic-workflow-init" in release_410_notes
    assert "plan digest" in release_410_notes
