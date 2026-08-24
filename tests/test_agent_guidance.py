from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ACTIVE_SKILL = PROJECT_ROOT / "skills/agentic-feature-workflow/SKILL.md"
ADR_0006 = PROJECT_ROOT / "docs/adr/0006-agentic-workflow-evidence-routes.md"
ADR_0007 = PROJECT_ROOT / "docs/adr/0007-agentic-workflow-bootstrap-and-plan-binding.md"
ADR_0008 = PROJECT_ROOT / "docs/adr/0008-supervisor-managed-living-plans.md"
WORKFLOW_DOCS = PROJECT_ROOT / "docs/agentic-workflows/README.md"
PUBLIC_REBUILD_PLAN = (
    PROJECT_ROOT
    / "docs/agentic-workflows/5.0.0-public-rebuild-workspace-separation.md"
)
REVIEW_COMPARISON_PLAN = (
    PROJECT_ROOT
    / "docs/agentic-workflows/5.1.0-review-resume-variant-comparison.md"
)
PUBLIC_REBUILD_ROADMAP = (
    PROJECT_ROOT / "docs/agentic-workflows/5.2.0-public-rebuild-roadmap.md"
)
SUPERVISION_MODES = (
    "Observation only",
    "Approval-gated attention",
    "Bounded contract restoration",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _assert_local_markdown_links_resolve(path: Path) -> None:
    for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", _read(path)):
        target = target.strip()
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        local_target = target.split("#", 1)[0].split("?", 1)[0]
        assert local_target
        assert (path.parent / local_target).exists(), (
            f"{path.relative_to(PROJECT_ROOT)} has an unresolved link: {target}"
        )


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


def test_active_agentic_workflow_docs_describe_living_plan_architecture() -> None:
    guidance = _read(PROJECT_ROOT / "AGENTS.md")
    readme = _read(PROJECT_ROOT / "README.md")
    architecture = _read(PROJECT_ROOT / "docs/architecture.md")
    workflow_docs = _read(WORKFLOW_DOCS)

    assert ACTIVE_SKILL.exists()
    assert "skills/agentic-feature-workflow/SKILL.md" in guidance
    assert "supervisor/implementor workflow" in guidance
    assert "agentic-feature-workflow" in readme
    assert "supervisor-owned living Markdown" in readme
    assert "one bounded P phase" in readme
    assert "one living Markdown plan" in architecture
    assert "bounded P phase at a time" in architecture
    assert "$agentic-feature-workflow" in workflow_docs
    assert "sole workflow source of truth" in workflow_docs
    assert "independent G gate" in workflow_docs


def test_active_docs_distinguish_all_three_supervision_modes() -> None:
    active_docs = (
        PROJECT_ROOT / "README.md",
        PROJECT_ROOT / "docs/architecture.md",
        WORKFLOW_DOCS,
        ADR_0008,
    )

    for path in active_docs:
        text = _read(path)
        for mode in SUPERVISION_MODES:
            assert mode in text

    assert "never sends an implementor message" in _read(PROJECT_ROOT / "README.md")
    assert "fresh user approval for every message" in _read(PROJECT_ROOT / "README.md")
    assert "not general autonomous authority" in _read(PROJECT_ROOT / "README.md")


def test_adr_0008_supersedes_new_workflows_without_erasing_legacy_history() -> None:
    adr_0008 = _read(ADR_0008)
    evidence_routes_adr = _read(ADR_0006)
    bootstrap_adr = _read(ADR_0007)

    assert ADR_0008.exists()
    for heading in ("## Context", "## Decision", "## Consequences", "## Related Links"):
        assert heading in adr_0008
    assert "Supersedes ADR 0006 and ADR 0007 for new workflows" in adr_0008
    assert "These sources are design evidence" in adr_0008
    assert "not proof of settled" in adr_0008
    assert "scientific consensus" in adr_0008
    assert "selective, trajectory-aware, risk-weighted intervention" in adr_0008

    for legacy_adr in (evidence_routes_adr, bootstrap_adr):
        assert "Superseded for new workflows by" in legacy_adr
        assert "0008-supervisor-managed-living-plans.md" in legacy_adr
        assert "## Context" in legacy_adr
        assert "## Consequences" in legacy_adr

    assert "runtime tracker" in evidence_routes_adr
    assert "plan digest" in bootstrap_adr


def test_active_documentation_links_resolve_and_legacy_material_is_preserved() -> None:
    active_docs = (
        PROJECT_ROOT / "README.md",
        PROJECT_ROOT / "docs/architecture.md",
        WORKFLOW_DOCS,
        ADR_0006,
        ADR_0007,
        ADR_0008,
        PUBLIC_REBUILD_PLAN,
        REVIEW_COMPARISON_PLAN,
        PUBLIC_REBUILD_ROADMAP,
    )
    for path in active_docs:
        _assert_local_markdown_links_resolve(path)

    historical_workflow = (
        PROJECT_ROOT / "docs/agentic-workflows/4.8.0-render-stamats-vida.md"
    )
    historical_release_notes = PROJECT_ROOT / "docs/release-notes/4.8.0.md"
    assert historical_workflow.exists()
    assert historical_release_notes.exists()
    assert "4.8.0" in _read(historical_workflow)
    assert "Older Professional Experience Rendering" in _read(historical_release_notes)
    assert "Historical release notes" in _read(WORKFLOW_DOCS)


def test_public_rebuild_plan_uses_bounded_implementors_and_supervisor_gates() -> None:
    plan = _read(PUBLIC_REBUILD_PLAN)

    prior_position = -1
    for phase_number in range(1, 9):
        for prefix in ("P", "G"):
            heading = f"## {prefix}{phase_number:02d}"
            position = plan.find(heading)
            assert position > prior_position, f"missing or out-of-order {heading}"
            prior_position = position

    assert "exactly one bounded `Pnn` step at a time" in plan
    assert "The supervisor independently evaluates every `Gnn`" in plan
    assert "An implementor never evaluates a gate" in plan
    assert "P07 and P08" in plan
    assert "supervisor-owned release-closeout phases" in plan
    assert "P07 is a supervisor-owned release-closeout phase" in plan
    assert "P08 is a supervisor-owned release-closeout phase" in plan
    assert "## Supervisor Dispatch And Closeout Sequence" in plan
    assert "No row authorizes a later row" in plan

    for stale_contract in (
        "Work directly without a supervisor",
        "## Prompt Sequence",
        "Execute P01, G01, P02, and G02",
        "execute P04, G04, P05, and G05",
    ):
        assert stale_contract not in plan


def test_public_rebuild_plans_preserve_migration_and_supervision_contracts() -> None:
    plan = _read(PUBLIC_REBUILD_PLAN)
    roadmap = _read(PUBLIC_REBUILD_ROADMAP)

    for path in (
        "/Users/mperkhou/dev/codex/linkedin-career-mcp/",
        "/Users/mperkhou/dev/codex/linkedin-career-mcp-public-exp/",
        "/Users/mperkhou/dev/codex/linkedin-career-mcp-workspace/",
    ):
        assert path in plan

    for requirement in (
        "SQLite's online backup facility",
        "content-free rollback record",
        "named pre-cutover stash",
        "clean `main`",
        "live user soak",
        "explicit acceptance",
        "v5.0.0",
    ):
        assert requirement in plan

    for document in (plan, roadmap):
        for mode in SUPERVISION_MODES:
            assert mode.lower() in document.lower()
        assert "exact preview" in document
        assert "fresh approval" in document

    comparison_plan = _read(REVIEW_COMPARISON_PLAN)
    normalized_comparison_plan = " ".join(comparison_plan.split())
    assert "two explicit comparison selectors" in comparison_plan
    assert "`v1` versus `v2`" in comparison_plan
    assert "`v2` versus `manual`" in comparison_plan
    assert "`v1` versus `manual`" in comparison_plan
    assert (
        "must not change the stored selected resume variant"
        in normalized_comparison_plan
    )
    assert "new fledgling `5.3.0` roadmap" in roadmap
    assert "one bounded P step at a time" in roadmap
    assert "independently evaluates the matching G gate" in roadmap
    assert "acceptance-before-tag" in _read(WORKFLOW_DOCS)


def test_new_workflow_docs_do_not_issue_legacy_tracker_commands() -> None:
    active_docs = (
        PROJECT_ROOT / "README.md",
        PROJECT_ROOT / "docs/architecture.md",
        WORKFLOW_DOCS,
        ADR_0008,
    )
    combined = "\n".join(_read(path) for path in active_docs)

    for legacy_command in (
        "$agentic-workflow-init",
        "$agentic-workflow-controller",
        "workflow_state.py rebind-plan",
        "tmp/agentic-workflows/<workflow_id>/",
    ):
        assert legacy_command not in combined
    assert "New workflows do not initialize, validate, rebind, or mutate" in combined
