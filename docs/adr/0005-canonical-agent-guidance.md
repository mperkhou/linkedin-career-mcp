# ADR 0005: Adopt AGENTS.md as Canonical Agent Guidance

## Status

Accepted.

## Date

2026-07-06

## Context

The project now has several repo-working agents and agent-like workflows:
Codex-driven implementation sessions, Codex manual resume pass, Codex resume
highlighting, release closeout, tracker workflow diagnostics, and application
writing grounded in local evidence.

The operational rules for those agents had accumulated across README sections,
skills, changelog entries, memory, and prior release notes. That made the system
easy to drift: a README section could describe product behavior correctly while
missing release closeout rules, or a skill could explain a command without
restating the shared safety contract for generated artifacts and evidence-backed
resume claims.

The project needs a single repo-level place for agent behavior that:

- applies before edits, tests, releases, and tracker diagnostics
- keeps release closeout requirements visible, including remote tag verification
- protects tracker DB data, generated artifacts, and profile evidence
- keeps resume and cover-letter claims grounded in local evidence
- avoids duplicating the same operational rules across README and skill docs

## Decision

Adopt root `AGENTS.md` as the canonical operational guidance file for agents
working in this repository.

`AGENTS.md` owns shared guardrails for:

- edit safety and dirty-worktree handling
- canonical state such as `profile/MASTER-RESUME.yml` and
  `output/tracking/applications.sqlite3`
- resume and cover-letter evidence discipline
- tracker variant and highlighting workflow invariants
- release versioning, validation, PR merge, annotated tag push, and remote tag
  verification
- long-running workflow visibility

`README.md` remains product- and operator-facing. It should link to
`AGENTS.md`, but it should not duplicate the full agent rulebook.

The skill docs remain workflow-specific command references. They should point
to `AGENTS.md` for shared repo behavior, then keep their own instructions
focused on MCP commands or manual resume pass mechanics.

## Consequences

Positive:

- Agents have one canonical repo-level guardrail file to read before working.
- Human-facing docs can stay readable instead of absorbing every operational
  safety rule.
- Skill docs can remain concise and command-focused.
- Release closeout and remote tag requirements are harder to miss.
- Resume evidence rules stay consistent across generated resumes, manual pass,
  cover letters, and application answers.

Tradeoffs:

- `AGENTS.md` becomes another top-level file that needs maintenance when repo
  workflow rules change.
- README and skill docs still need short links so users and agents can discover
  the canonical file.
- Tests need to assert the presence of key guidance links and release closeout
  language without becoming brittle prose snapshots.

## Alternatives Considered

### Keep Guidance in README

Rejected. The README should explain the product and operator workflows. Putting
all repo-agent rules there would make it longer, harder to scan, and more likely
to mix human documentation with internal operating constraints.

### Keep Guidance in Skills Only

Rejected. Skills are useful when invoked, but shared repo behavior should not
depend on which skill happens to trigger first. Release closeout, artifact
safety, and resume-evidence rules apply across more than one skill.

### Use Tool-Specific Files Only

Rejected for now. Files such as `.clinerules` or `CLAUDE.md` would fragment the
source of truth by client. A root `AGENTS.md` gives the repo one neutral
contract that other client-specific files can reference later if needed.

## References

- [Architecture](../architecture.md)
- [AGENTS.md](../../AGENTS.md)
- [4.3.0 release notes](../release-notes/4.3.0.md)
- [LinkedIn Career MCP skill](../../skills/linkedin-career-mcp/SKILL.md)
- [Manual resume passthrough skill](../../skills/manual-resume-passthrough/SKILL.md)
