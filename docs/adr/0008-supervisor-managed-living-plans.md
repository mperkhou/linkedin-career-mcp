# ADR 0008: Adopt Supervisor-Managed Living Plans for New Agentic Workflows

## Status

Accepted. Supersedes ADR 0006 and ADR 0007 for new workflows while preserving
their machine-tracked architecture and historical evidence for compatible use.

## Date

2026-08-21

## Context

The repository needs a durable way to plan and supervise multi-phase feature
work without turning a workflow tracker into a second source of truth or an
implicit permission system. The prior controller, evidence-route, bootstrap,
and plan-binding design remains valuable historical evidence, but it requires
machine-tracked state that is no longer the default for new work.

The post-G03 steering research and practice synthesis informed a different
oversight posture: selective, trajectory-aware, risk-weighted intervention
rather than either per-action approval or unconditional silence until handoff.
It supports using exposed, material, and time-sensitive evidence to decide when
attention is warranted, with the expected cost of waiting compared against the
cost of interruption. These sources are design evidence, not proof of settled
scientific consensus or a precise automated policy.

## Decision

Adopt `agentic-feature-workflow` as the active approach for new multi-phase
repository changes.

One approved living Markdown plan is the workflow source of truth. A supervisor
task owns that plan, exact task-action previews, implementor selection,
independent gates, correction prompts, and release closeout. A separate
user-owned implementor task receives exactly one bounded P phase, performs only
that phase's edits and validation, returns a structured handoff, and stops
before the matching G gate.

Each P/G cycle explicitly selects one supervision mode:

- **Observation only** permits bounded read-only observation and no implementor
  message.
- **Approval-gated attention** requires a verified destination, complete exact
  message preview, and fresh approval for every message.
- **Bounded contract restoration** permits at most one narrowly restorative
  message across the selected cycle when it directly maps to an existing
  approved contract. It cannot broaden scope, grant authority, or become
  general autonomous messaging.

The detailed thresholds, scenarios, message-budget mechanics, and correction
handling remain canonical in the agentic-feature-workflow orchestration
reference. New workflows do not initialize, validate, rebind, or mutate
machine-tracker JSON.

## Consequences

Positive:

- New workflows have one visible, human-readable source of truth.
- Supervisor and implementor responsibilities remain separate and auditable.
- The three modes make observation, approval, and the narrow restorative
  envelope explicit instead of leaving message authority implicit.
- Detailed oversight rules stay in one operational reference rather than being
  duplicated across general repository documentation.

Tradeoffs:

- Supervisors must keep the living plan current and independently verify every
  gate.
- The bounded mode deliberately has a narrow, non-replenishing message budget;
  ambiguous, expansive, or repeated direction still requires fresh approval.
- The legacy init/controller machinery remains available for compatibility but
  must not be mistaken for the new-workflow default.

This decision changes repository workflow guidance only. It does not change the
application tracker, product data, resume variants, generated artifacts, or
release authorization boundaries.

## Related Links

- [Agentic workflow documentation](../agentic-workflows/README.md)
- [Agentic feature workflow skill](../../skills/agentic-feature-workflow/SKILL.md)
- [Implementor task orchestration reference](../../skills/agentic-feature-workflow/references/implementor-task-orchestration.md)
- [AGENTS.md](../../AGENTS.md)
- [ADR 0006: Agentic workflow evidence routes](0006-agentic-workflow-evidence-routes.md)
- [ADR 0007: Agentic workflow bootstrap and plan binding](0007-agentic-workflow-bootstrap-and-plan-binding.md)

### Post-G03 Steering Research And Practice Evidence

- [Anthropic: Measuring AI agent autonomy in practice](https://www.anthropic.com/research/measuring-agent-autonomy)
- [Comparing Human Oversight Strategies for Computer-Use Agents](https://arxiv.org/abs/2604.04918)
- [Oversight Has a Capacity](https://arxiv.org/abs/2606.08919)
- [Reliable Weak-to-Strong Monitoring of LLM Agents](https://arxiv.org/abs/2508.19461)
- [DreamGuard](https://arxiv.org/abs/2608.05695)
- [Human oversight of agentic systems in practice](https://arxiv.org/abs/2606.05391)
- [Progress Mirage](https://arxiv.org/abs/2607.25152)
- [Understanding Code Agent Behaviour](https://arxiv.org/abs/2511.00197)
- [Anthropic: SLEIGHT-Bench](https://alignment.anthropic.com/2026/sleight-bench/)
- [OpenAI: A practical guide to building AI agents](https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/)
- [OpenAI: How we monitor internal coding agents](https://openai.com/index/how-we-monitor-internal-coding-agents-misalignment/)
- [OpenAI: Running Codex safely](https://openai.com/index/running-codex-safely/)
