from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_agents_guidance_exists_with_release_closeout_guardrails() -> None:
    guidance_path = PROJECT_ROOT / "AGENTS.md"
    assert guidance_path.exists()

    guidance = guidance_path.read_text(encoding="utf-8")
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
