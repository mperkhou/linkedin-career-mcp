from __future__ import annotations

import re
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = PROJECT_ROOT / "skills" / "agentic-feature-workflow"
SKILL_PATH = SKILL_DIR / "SKILL.md"
AGENT_PATH = SKILL_DIR / "agents" / "openai.yaml"
TEMPLATE_PATH = SKILL_DIR / "assets" / "implementation-plan.template.md"
ORCHESTRATION_PATH = (
    SKILL_DIR / "references" / "implementor-task-orchestration.md"
)

EXPECTED_SKILL_FILES = {
    Path("SKILL.md"),
    Path("agents/openai.yaml"),
    Path("assets/implementation-plan.template.md"),
    Path("references/implementor-task-orchestration.md"),
}
EXPECTED_TEMPLATE_SECTIONS = [
    "1. Purpose And Operating Summary",
    "2. Repository, Release, Evidence, And Source Context",
    "3. Final Architecture And Agreed Design",
    "4. Decisions Superseding Earlier Proposals",
    "5. Implementation Sequence",
    "6. Release Closeout Boundary",
    "7. Downstream And Explicitly Excluded Work",
    "8. Living-Plan Instructions",
    "9. Decision Log",
]
REQUIRED_PHASE_SECTIONS = [
    "Implementor-Task Orchestration Record",
    "Safety And Preconditions",
    "Bounded Objective",
    "Required Behavior And Acceptance Criteria",
    "Relevant Repository Areas",
    "Strict Exclusions",
    "Focused Tests",
    "Complete Verification",
    "Structured Handoff",
]
IMMEDIATE_ATTENTION_SIGNALS = (
    "irreversible or destructive action",
    "external publication",
    "secret exposure",
    "permission bypass",
    "live-data mutation",
    "explicit exclusion violation",
)
DEFER_TO_GATE_SCENARIOS = (
    "Stylistic disagreement",
    "one transient failure",
    "ordinary debugging",
    "incomplete reasoning",
    "a reversible local experiment",
    "speculation",
)
SUPERVISION_MODES = (
    "Observation only",
    "Approval-gated attention",
    "Bounded contract restoration",
)
BOUNDED_SCENARIOS = {
    "legacy controller and runtime tracker": "Eligible restoration",
    "imminent edit outside the exact files allowed": "Eligible restoration",
    "imminent destructive, external, secret, permission-bypass, or live-data action": (
        "Eligible hold/stop"
    ),
    "could reasonably mean two different things": "Approval required",
    "adds a useful deliverable or changes a requirement": "Approval required",
    "grants write, external, destructive, or other new permission": (
        "Approval required"
    ),
    "already been sent in this P/G cycle": "Approval required",
    "ordinary debugging failure": "Defer to gate",
    "prefers a different style": "Defer to gate",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _frontmatter(path: Path) -> dict[str, object]:
    text = _read(path)
    assert text.startswith("---\n")
    _, raw_frontmatter, _ = text.split("---", 2)
    parsed = yaml.safe_load(raw_frontmatter)
    assert isinstance(parsed, dict)
    return parsed


def _section(text: str, heading: str, *, level: int = 2) -> str:
    marker = f"{'#' * level} {heading}"
    start = text.index(marker)
    next_heading = re.search(
        rf"^{'#' * level} (?!#)",
        text[start + len(marker) :],
        flags=re.MULTILINE,
    )
    if next_heading is None:
        return text[start:]
    return text[start : start + len(marker) + next_heading.start()]


def _collapsed(text: str) -> str:
    return " ".join(text.split())


def _markdown_table_rows(text: str) -> list[tuple[str, ...]]:
    rows = []
    for line in text.splitlines():
        if not line.startswith("|") or re.fullmatch(r"[| :\-]+", line):
            continue
        rows.append(tuple(cell.strip() for cell in line.strip("|").split("|")))
    return rows


def test_skill_metadata_interface_and_size_contract() -> None:
    metadata = _frontmatter(SKILL_PATH)
    agent = yaml.safe_load(_read(AGENT_PATH))

    assert list(metadata) == ["name", "description"]
    assert metadata["name"] == SKILL_DIR.name == "agentic-feature-workflow"
    assert set(agent) == {"interface"}
    assert set(agent["interface"]) == {
        "display_name",
        "short_description",
        "default_prompt",
    }
    assert agent["interface"]["display_name"] == "Agentic Feature Workflow"
    assert "$agentic-feature-workflow" in agent["interface"]["default_prompt"]
    assert len(_read(SKILL_PATH).splitlines()) < 500


def test_template_has_stable_sections_and_adjacent_phase_gates() -> None:
    template = _read(TEMPLATE_PATH)
    top_sections = re.findall(r"^## (?!#)(.+)$", template, flags=re.MULTILINE)
    phase_gate_headings = re.findall(
        r"^### ([PG])(\d{2}) - .+$",
        template,
        flags=re.MULTILINE,
    )

    assert top_sections == EXPECTED_TEMPLATE_SECTIONS
    assert phase_gate_headings == [("P", "01"), ("G", "01"), ("P", "02"), ("G", "02")]
    for index in range(0, len(phase_gate_headings), 2):
        phase_kind, phase_number = phase_gate_headings[index]
        gate_kind, gate_number = phase_gate_headings[index + 1]
        assert phase_kind == "P"
        assert gate_kind == "G"
        assert phase_number == gate_number


def test_template_requires_phase_handoffs_and_supervision_mode_states() -> None:
    template = _read(TEMPLATE_PATH)
    phase_matches = list(
        re.finditer(r"^### P(\d{2}) - .+$", template, flags=re.MULTILINE)
    )

    for phase_match in phase_matches:
        gate_match = re.search(
            rf"^### G{phase_match.group(1)} - .+$",
            template[phase_match.end() :],
            flags=re.MULTILINE,
        )
        assert gate_match is not None
        phase_block = template[
            phase_match.start() : phase_match.end() + gate_match.start()
        ]
        phase_sections = re.findall(
            r"^#### (.+)$",
            phase_block,
            flags=re.MULTILINE,
        )
        assert phase_sections == REQUIRED_PHASE_SECTIONS
        assert "exact validation commands with exit codes" in phase_block
        assert "residual risks or" in phase_block
        assert "every exclusion was respected" in phase_block

    mode_contract = _collapsed(
        _section(template, "Supervision Mode Contract", level=3)
    )
    assert "Per-cycle mode selection:" in mode_contract
    for mode in SUPERVISION_MODES:
        assert mode in mode_contract
    assert "no-send behavior" in mode_contract
    assert "fresh approval for every message" in mode_contract
    assert "one automatic-message budget across the P/G cycle" in mode_contract
    assert "non-replenishment during correction" in mode_contract
    assert "implementor ownership of correction work" in mode_contract

    for phase_match in phase_matches:
        gate_match = re.search(
            rf"^### G{phase_match.group(1)} - .+$",
            template[phase_match.end() :],
            flags=re.MULTILINE,
        )
        assert gate_match is not None
        phase_block = template[
            phase_match.start() : phase_match.end() + gate_match.start()
        ]
        assert "Supervision mode: not selected" in phase_block
        assert "Automatic-message budget:" in phase_block


def test_template_exposes_plan_specific_steering_calibration() -> None:
    mode_contract = _collapsed(
        _section(_read(TEMPLATE_PATH), "Supervision Mode Contract", level=3)
    )

    assert "evidence-triggered baseline" in mode_contract
    for placeholder in (
        "Stricter attention thresholds:",
        "Retry or persistence limits:",
        "Repository-specific high-severity signals:",
        "Contract sources eligible for bounded restoration:",
    ):
        assert placeholder in mode_contract
    assert "may tighten but never weaken the portable baseline" in mode_contract


def test_plan_location_choice_and_root_anchored_ignore_are_explicit() -> None:
    skill = _read(SKILL_PATH)
    ignore_lines = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert "local-only/untracked" in skill
    assert "tracked in Git" in skill
    assert "<repository>/.codex/plans/" in skill
    assert "discover and use the repository's existing plan" in skill
    assert ignore_lines.count("/.codex/plans/") == 1
    assert ".codex/plans/" not in [line for line in ignore_lines if not line.startswith("/")]
    assert "/.codex/" not in ignore_lines


def test_active_skill_has_no_machine_state_resources() -> None:
    actual_files = {
        path.relative_to(SKILL_DIR) for path in SKILL_DIR.rglob("*") if path.is_file()
    }
    skill = _read(SKILL_PATH)

    assert actual_files == EXPECTED_SKILL_FILES
    assert not (SKILL_DIR / "scripts").exists()
    assert not any(
        path.suffix in {".json", ".py", ".sql", ".db", ".sqlite"}
        for path in actual_files
    )
    for marker in (
        "runtime plan",
        "JSON state",
        "schema",
        "digest",
        "cursor",
        "lock",
        "workflow engine",
    ):
        assert marker in skill


def test_generic_skill_files_remain_repository_and_organization_neutral() -> None:
    generic_text = "\n".join(_read(SKILL_DIR / path) for path in EXPECTED_SKILL_FILES)
    forbidden_literals = (
        "/Users/",
        "linkedin-career-mcp",
        "career-agent-workbench",
        "applications.sqlite3",
        "output/tracking",
        "profile/MASTER-RESUME",
    )

    for forbidden in forbidden_literals:
        assert forbidden.casefold() not in generic_text.casefold()
    assert re.search(r"\b(?:oracle|oci|jod|mro|aro|clo)\b", generic_text, re.I) is None


def test_launch_and_send_previews_require_complete_separate_approval() -> None:
    reference = _read(ORCHESTRATION_PATH)
    preview = _collapsed(_section(reference, "Preview Exact Approval"))

    assert "Plan approval is separate from task-action approval" in preview
    for marker in (
        "destination project and repository path",
        "direct checkout or worktree configuration",
        "new title, or the exact existing task identity",
        "complete prompt exactly as it will be delivered",
        "model and reasoning effort",
        "configuration rationale",
        "explicit supervision mode",
        "automatic-message budget state",
        "bounded waiting capability",
        "authorization boundaries",
        "implementor stop conditions",
    ):
        assert marker in preview
    assert "one approved launch action" in preview
    assert "Never infer standing launch or send authority" in preview


def test_task_identity_reconciliation_and_portable_titles_are_durable() -> None:
    reference = _read(ORCHESTRATION_PATH)
    creation = _collapsed(_section(reference, "Create And Reconcile A Task"))
    naming = _collapsed(_section(reference, "Name Tasks Portably"))

    assert "Capture every returned stable identifier immediately" in creation
    assert "without treating it as a ready task ID" in creation
    assert "ambiguous delivery" in creation
    assert "do not retry creation immediately" in creation
    assert "proves that no task was created" in creation
    assert "title-only retry" in creation
    assert "must not recreate the task, resend the initial prompt" in creation
    assert "Never silently create a replacement task" in creation

    assert "target project's release version" in naming
    assert "`v<version>: Implementor`" in naming
    assert "`v<version>: Implementor: Pnn`" in naming
    assert "`v.Unversioned: Implementor`" in naming
    assert "Retain the original title when reusing a task" in naming


def test_supervision_modes_preserve_three_separate_checkpoint_states() -> None:
    skill = _read(SKILL_PATH)
    reference = _read(ORCHESTRATION_PATH)
    supervision = _section(reference, "Apply The Selected Supervision Mode")
    collapsed_supervision = _collapsed(supervision)
    checkpoint_headings = re.findall(
        r"^### (.+)$", supervision, flags=re.MULTILINE
    )

    assert checkpoint_headings[:3] == [
        "Observation State",
        "Attention Checkpoint",
        "Gate Checkpoint",
    ]
    assert "## Supervise Through Three Checkpoints" in skill
    for mode in SUPERVISION_MODES:
        assert mode in supervision
    assert "Observation boundary:" in collapsed_supervision
    assert "Observation-only mode sends no message" in collapsed_supervision
    assert "not standing or general autonomous messaging authority" in collapsed_supervision


def test_attention_uses_only_exposed_material_evidence_and_fresh_approval() -> None:
    supervision = _section(
        _read(ORCHESTRATION_PATH), "Apply The Selected Supervision Mode"
    )
    attention = _collapsed(
        _section(supervision, "Attention Checkpoint", level=3)
    )

    for implementor_trigger in (
        "asks a question",
        "requests authorization",
        "proposes an external action",
        "reports a blocker",
    ):
        assert implementor_trigger in attention
    for exposed_source in ("commentary", "status", "proposed actions", "output"):
        assert exposed_source in attention
    for material_deviation in (
        "material confusion",
        "false premise",
        "scope drift",
        "unsafe behavior",
        "repeated misunderstanding",
        "likely costly rework",
    ):
        assert material_deviation in attention

    assert "Common Evidence And Decision Boundary" in attention
    assert "Never use hidden reasoning or private chain-of-thought" in attention
    for scenario in DEFER_TO_GATE_SCENARIOS:
        assert scenario in attention
    assert "Show the concrete exposed evidence" in attention
    assert "Explain why waiting for the matching gate is inappropriate" in attention
    assert "verified destination task" in attention
    assert "Preview the exact message in complete form" in attention
    assert "fresh user approval for that one message" in attention


def test_supervisor_detected_attention_requires_all_three_evidence_factors() -> None:
    skill = _collapsed(_read(SKILL_PATH))
    attention = _collapsed(
        _section(
            _section(
                _read(ORCHESTRATION_PATH), "Apply The Selected Supervision Mode"
            ),
            "Attention Checkpoint",
            level=3,
        )
    )

    assert "approval-gated attention" in skill.casefold()
    assert "bounded contract restoration" in skill.casefold()
    assert "evidence must satisfy all three factors" in attention
    for factor in ("Observable:", "Material:", "Time-sensitive:"):
        assert factor in attention
    for exposed_source in (
        "exposed commentary",
        "proposed or completed actions",
        "tool output",
        "tests",
        "repository state",
    ):
        assert exposed_source in attention
    assert "All three are required" in attention
    assert "hidden reasoning or private chain-of-thought" in attention


def test_attention_thresholds_use_table_driven_representative_scenarios() -> None:
    attention = _collapsed(
        _section(
            _section(
                _read(ORCHESTRATION_PATH), "Apply The Selected Supervision Mode"
            ),
            "Attention Checkpoint",
            level=3,
        )
    )
    threshold_scenarios = {
        "Immediate attention": (
            "One high-severity signal",
            *IMMEDIATE_ATTENTION_SIGNALS,
        ),
        "Normal attention": (
            "One strong signal or two corroborating signals",
            "Scope drift plus an imminent edit",
            "repeated failures plus validation weakening",
            "a false premise driving substantial implementation",
        ),
        "Persistence attention": (
            "same moderate concern across two snapshots",
            "repeated attempts",
            "plan-defined retry or action threshold",
        ),
    }

    for threshold, markers in threshold_scenarios.items():
        assert threshold in attention
        for marker in markers:
            assert marker in attention


def test_defer_cases_and_signal_categories_preserve_judgment_boundaries() -> None:
    attention = _collapsed(
        _section(
            _section(
                _read(ORCHESTRATION_PATH), "Apply The Selected Supervision Mode"
            ),
            "Attention Checkpoint",
            level=3,
        )
    )

    assert "Defer to gate" in attention
    for scenario in DEFER_TO_GATE_SCENARIOS:
        assert scenario in attention
    for signal in (
        "scope or authority crossing",
        "high-impact or irreversible action",
        "material goal misunderstanding",
        "validation bypass or weakening",
        "repeated failure without new evidence",
        "self-reported progress contradicted by objective results",
        "expanding work from an unverified premise",
        "wrong repository, branch, task, or environment",
        "attempts to evade safeguards",
    ):
        assert signal in attention
    assert "may impose stricter" in attention
    assert "may not weaken this portable baseline" in attention


def test_waiting_cost_rule_grants_proposal_only_and_no_automated_authority() -> None:
    attention = _collapsed(
        _section(
            _section(
                _read(ORCHESTRATION_PATH), "Apply The Selected Supervision Mode"
            ),
            "Attention Checkpoint",
            level=3,
        )
    )

    assert "detection authorizes only an intervention proposal" in attention
    assert "grants no send authority" in attention
    assert (
        "expected cost of waiting clearly exceeds the cost of interruption"
        in attention
    )
    for excluded_mechanism in (
        "automated monitor",
        "classifier",
        "scoring engine",
        "numerical risk score",
        "permission system",
    ):
        assert excluded_mechanism in attention
    assert "does not calculate a score or automate" in attention
    assert "not a claim of scientific precision or settled scientific consensus" in attention


def test_each_attention_message_is_single_send_then_observation_resumes() -> None:
    attention = _collapsed(
        _section(
            _section(
                _read(ORCHESTRATION_PATH), "Apply The Selected Supervision Mode"
            ),
            "Attention Checkpoint",
            level=3,
        )
    )

    assert "Send the approved message exactly once" in attention
    assert "grants no follow-up authority" in attention
    assert "reply to an implementor question" in attention
    assert "own exact preview and fresh approval" in attention
    assert "Resume observation after the send" in attention
    assert "explicitly pauses or stops the implementor" in attention


def test_supervision_mode_is_explicit_per_cycle_and_never_inherited() -> None:
    supervision = _collapsed(
        _section(
            _read(ORCHESTRATION_PATH), "Apply The Selected Supervision Mode"
        )
    )
    skill = _collapsed(_read(SKILL_PATH))

    assert "must select exactly one mode" in supervision
    assert "complete `Pnn/Gnn` cycle" in supervision
    assert "previous choice supplies no default" in supervision
    assert "does not transfer to a later phase or replacement task" in supervision
    assert "does not replenish when a correction is dispatched" in supervision
    assert "explicitly selected for this complete `Pnn/Gnn` cycle" in skill
    assert "Observation-only mode always remains no-send" in skill


def test_bounded_mode_restores_only_a_verified_existing_contract() -> None:
    supervision = _section(
        _read(ORCHESTRATION_PATH), "Apply The Selected Supervision Mode"
    )
    attention = _section(supervision, "Attention Checkpoint", level=3)
    bounded = _collapsed(
        _section(attention, "Bounded Contract Restoration", level=4)
    )

    assert "every common evidence and decision condition" in bounded
    assert "shared P/G-cycle budget is unused" in bounded
    assert "destination is verified" in bounded
    for contract_source in (
        "repository `AGENTS.md` rule",
        "approved living-plan term",
        "current P-step prompt",
        "acceptance criterion",
        "explicit exclusion",
    ):
        assert contract_source in bounded
    for forbidden_direction in (
        "broaden scope",
        "change requirements",
        "amend the plan",
        "grant or change permissions",
        "alter user-owned work",
        "authorize external or destructive action",
        "select or replace a task",
        "provide recovery direction beyond restoration",
        "implement the correction",
    ):
        assert forbidden_direction in bounded
    assert "hold consumes the same shared budget" in bounded
    assert "grants no recovery or expanded authority" in bounded
    assert "Messaging cannot preempt an operation that has already run" in bounded


def test_bounded_mode_scenario_table_covers_positive_and_negative_cases() -> None:
    bounded = _section(
        _section(
            _section(
                _read(ORCHESTRATION_PATH),
                "Apply The Selected Supervision Mode",
            ),
            "Attention Checkpoint",
            level=3,
        ),
        "Bounded Contract Restoration",
        level=4,
    )
    rows = _markdown_table_rows(bounded)
    collapsed_bounded = _collapsed(bounded)

    for scenario, expected_result in BOUNDED_SCENARIOS.items():
        matching_rows = [row for row in rows if scenario in row[0]]
        assert len(matching_rows) == 1
        assert matching_rows[0][1] == f"**{expected_result}**"
    assert "Directly restate the existing no-tracker plan term" in collapsed_bounded
    assert "Restate the exact approved file criterion" in collapsed_bounded
    assert (
        "Ambiguous interpretation cannot support an automatic message"
        in collapsed_bounded
    )
    assert "Scope expansion is not contract restoration" in collapsed_bounded


def test_automatic_send_is_reported_recorded_and_exhausts_follow_up_authority() -> None:
    supervision = _collapsed(
        _section(
            _read(ORCHESTRATION_PATH), "Apply The Selected Supervision Mode"
        )
    )

    for record_field in (
        "exposed evidence",
        "decision rationale",
        "verified destination",
        "exact message",
        "budget is consumed",
    ):
        assert record_field in supervision
    assert "report to the user" in supervision
    assert "durably record those same fields" in supervision
    assert "under the living plan's visibility rules" in supervision
    assert "One automatic message grants no follow-up authority" in supervision
    for approval_case in (
        "Recovery",
        "conflicting instructions",
        "ambiguous contract interpretation",
        "repeated intervention",
        "second message",
        "scope amendment",
        "non-restorative direction",
    ):
        assert approval_case in supervision
    assert "complete exact preview and fresh user approval" in supervision


def test_failed_gate_uses_only_unused_budget_and_stays_open_for_reassessment() -> None:
    gate = _collapsed(
        _section(
            _section(
                _read(ORCHESTRATION_PATH), "Apply The Selected Supervision Mode"
            ),
            "Gate Checkpoint",
            level=3,
        )
    )

    assert "budget remains unused" in gate
    assert "maps directly and unambiguously to an existing criterion" in gate
    assert "does not replenish for that correction" in gate
    assert "Keep `Gnn` open" in gate
    assert "independently rerun the same gate" in gate
    assert "Every other gate correction requires" in gate
    assert "fresh user approval" in gate


def test_gate_review_correction_ownership_and_reuse_boundaries_are_explicit() -> None:
    skill = _read(SKILL_PATH)
    reference = _read(ORCHESTRATION_PATH)
    gate = _collapsed(
        _section(
            _section(reference, "Apply The Selected Supervision Mode"),
            "Gate Checkpoint",
            level=3,
        )
    )
    reuse = _section(reference, "Choose Fresh Or Reused")
    later_sends = _collapsed(
        _section(reference, "Send Later Phases And Corrections")
    )
    collapsed_skill = _collapsed(skill)

    assert "independently perform the matching `Gnn`" in gate
    assert "Every other gate correction requires" in gate
    assert "complete exact message preview, and fresh user approval" in gate
    assert "never repairs, consolidates, or implements the correction" in gate
    assert "implementor apply and validate the correction" in gate
    assert "Never repair, consolidate, or implement the correction" in later_sends
    assert "Prefer reuse when:" in reuse
    assert "Prefer a fresh task when:" in reuse
    assert "Explain the recommendation in the exact preview" in reuse

    assert "At each G gate, inspect the real repository root" in skill
    assert "Treat the implementor's handoff as evidence to verify" in collapsed_skill
    assert "Never repair, consolidate, or implement corrections" in collapsed_skill
    assert "final gate" in collapsed_skill
    assert "bounded read-only evidence" in collapsed_skill
    assert "supervisor must verify that evidence" in collapsed_skill


def test_repository_instructions_preserve_product_and_application_boundaries() -> None:
    skill = _read(SKILL_PATH)
    guidance = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")

    assert "Treat repository instructions as authoritative" in skill
    assert "product-specific behavior" in skill
    assert "product-data mutations" in skill
    assert "external-system changes" in skill
    assert "output/tracking/applications.sqlite3" in guidance
    assert "Do not mutate tracker DB data" in guidance
