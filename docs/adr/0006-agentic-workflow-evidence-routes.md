# ADR 0006: Add Evidence Routes to Agentic Workflow Controller

## Status

Accepted.

## Date

2026-07-08

## Context

The project now uses Codex for larger repo changes, resume workflow debugging,
release closeout, and generated-artifact review. These tasks often require the
same pattern: collect evidence, compare it against the remaining plan, then
decide whether to continue, amend, or pause.

Plain prompt/response works, but it can become repetitive. A single main-agent
thread has to ask itself to inspect code, compare artifacts, remember pause
conditions, and judge whether the implementation still matches the plan. That
increases drift risk. For example, a layout-only validation can accidentally
stand in for a stronger generation-quality validation unless a separate route
is explicitly tasked with checking the missing evidence.

The project needs an orchestration layer that:

- reduces repeated prompt/response management for multi-step work
- increases automation while keeping the process guided and auditable
- separates read-only evidence gathering from mutation authority
- produces consistent release and validation evidence across sessions
- lets subagents perform independent inspections when the Codex surface
  supports them
- still works when subagents are unavailable

## Decision

Extend the `agentic-workflow-controller` skill with evidence routes.

An evidence route is a named, read-only investigation attached to a P step, such
as `P01-evidence-mro-policy` or `P05-evidence-generation-quality`. Routes may be
run by subagents or by the main agent as a local fallback. Each route records its
prompt, artifact path, execution mode, summary, findings, recommendation, and
timestamps in the runtime tracker.

The main agent remains the only actor that may:

- edit repository files
- mutate tracker database rows or generated artifacts
- update workflow gates and the runtime tracker
- make continue/amend/pause decisions
- stage, commit, push, open PRs, merge, or tag releases

Evidence routes feed G-step reassessment. A gate should compare completed route
findings against the remaining plan before continuing. If a route finds missing
evidence or a plan mismatch, the gate should amend future steps or pause.

## Consequences

Positive:

- Multi-step workflows need fewer manual prompt/response loops.
- Evidence collection becomes more consistent and easier to audit.
- Subagent work becomes useful without granting subagents mutation authority.
- G gates have clearer inputs when deciding whether to continue, amend, or
  pause.
- The controller remains usable in Codex surfaces without subagent support
  because route prompts can run locally.

Tradeoffs:

- The runtime tracker becomes slightly richer.
- Agents need to decide which routes are worth splitting out instead of routing
  every trivial check.
- Route evidence can still be incomplete if the main plan defines weak routes.

## Alternatives Considered

### Keep All Work in One Main Thread

Rejected. This is simplest, but it makes longer workflows depend too much on a
single thread's memory and self-review.

### Make Subagents Responsible for Gates

Rejected. Subagents are useful for independent read-only evidence, but gate
decisions can authorize mutations and release closeout. Those decisions should
remain with the main agent under `AGENTS.md`.

### Build a Full Workflow Engine

Rejected for now. The current need is a lightweight operating pattern and helper
state, not a daemon or scheduler.

## References

- [AGENTS.md](../../AGENTS.md)
- [Agentic workflow controller skill](../../skills/agentic-workflow-controller/SKILL.md)
- [4.9.0 release notes](../release-notes/4.9.0.md)
