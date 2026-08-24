---
name: agentic-feature-workflow
description: Use when Codex should plan, launch, supervise, resume, or reassess a multi-phase feature workflow with one living Markdown plan, separate user-owned implementor tasks, exact approval before each task creation or prompt delivery, and independent supervisor gates. Apply it to new or existing feature implementations that need bounded P steps, matching G gates, correction handling, task reuse decisions, or release-closeout control without a machine workflow tracker.
---

# Agentic Feature Workflow

## Establish Authority

1. Discover the active repository and read its `AGENTS.md` and other applicable
   local instructions completely.
2. Treat repository instructions as authoritative for Git, release, validation,
   safety, private data, and product-specific behavior.
3. Inspect the request, repository state, supplied evidence, and existing plans.
4. Surface contradictions, unsafe assumptions, and blockers before proposing
   implementation.

Use this skill as procedural guidance. Do not treat a plan, task status, gate,
or skill instruction as permission for destructive actions, Git publication,
release actions, product-data changes, or external-system mutations.

## Draft And Approve One Living Plan

1. Copy `assets/implementation-plan.template.md` as the starting skeleton.
2. Draft the plan conversationally with the user. Make every implementation
   phase bounded, verifiable, and immediately followed by its matching gate:
   `P01 -> G01 -> P02 -> G02`.
3. Iterate until the user explicitly approves the plan content.
4. After content approval, ask whether the durable plan is local-only/untracked
   or tracked in Git. Do not infer this choice from plan approval.
5. Recommend local-only storage. For that choice, use
   `<repository>/.codex/plans/` and add the exact root ignore entry
   `/.codex/plans/` only when needed. Never broadly ignore, overwrite, or
   untrack unrelated `.codex` content.
6. For a tracked plan, discover and use the repository's existing plan
   convention. Do not impose a universal tracked-plan directory.
7. Maintain the approved Markdown file as the sole workflow source of truth.
   Do not add a runtime plan, JSON state, schema, digest, cursor, lock, evidence
   database, daemon, scheduler, or workflow engine.

Record dated decisions and update every affected future P step and G gate.
Preserve completed execution context unless a correction note explicitly
explains a necessary amendment.

## Keep Roles Separate

The planning task becomes the supervisor. The supervisor owns the living plan,
implementor selection, exact prompt previews, task orchestration, gates,
corrections, commits, and release closeout.

Normal implementation occurs in a separate user-owned Codex task, not a child
subagent and not the supervisor task. Give an implementor exactly one complete
P step. Require it to:

- verify repository, branch, base, worktree, target release, local rules, and
  scope before editing;
- own only the phase's bounded edits and validation;
- preserve user and prior-implementor changes;
- avoid broadening scope, amending the plan, passing its own gate, or launching
  another implementor;
- avoid staging, committing, remote actions, releases, destructive operations,
  product-data mutations, and external-system changes unless that exact phase
  and the user explicitly authorize them;
- return the plan's structured handoff; and
- stop before the matching G gate.

Read `references/implementor-task-orchestration.md` completely before
discovering task capabilities, previewing a task action, creating or reusing an
implementor task, sending a correction, or starting passive observation.

## Dispatch One P Step At A Time

1. Confirm the prior gate passed and no correction remains unresolved.
2. Reconcile the real repository state with the living plan.
3. Prepare one self-contained implementor prompt from the complete next P step.
4. Follow the orchestration reference to recommend environment, model,
   reasoning effort, and a fresh or reused task.
5. Show the exact launch or send preview and wait for explicit approval. Plan
   approval never supplies task-creation or prompt-delivery approval.
6. Perform only the approved task action. Preserve and reconcile task identity
   before retrying an ambiguous operation.
7. Use the supervision mode explicitly selected for this complete `Pnn/Gnn`
   cycle and the three-checkpoint model below. Do not carry a mode into a later
   phase or replacement task.

Do not create an empty task, infer its prompt later, send multiple P steps,
retain standing launch authority, silently change an approved field, or replace
an implementor without fresh approval.

## Supervise Through Three Checkpoints

Select exactly one mode in every launch or later P-step preview:

- **Observation only:** use bounded read-only task checks, report meaningful
  status or attention evidence, and send no implementor message.
- **Approval-gated attention:** observe for the evidence threshold below, but
  require a verified destination, exact preview, and fresh user approval for
  every message.
- **Bounded contract restoration:** when the user explicitly selects it for
  this cycle, allow at most one automatic message across the complete P/G
  cycle. The message must restore an existing contract under the orchestration
  reference's evidence, mapping, budget, reporting, and exclusion rules.

The bounded mode does not transfer to a later phase or replacement task, and
its one-message budget does not replenish during a correction cycle. Keep the
three checkpoint states distinct in every mode:

1. **Observation state:** use bounded compact task-status checks. Send no
   message unless the selected mode and attention rules expressly authorize
   it. Observation-only mode always remains no-send.
2. **Attention checkpoint:** consider an intervention only for an implementor
   question or request, or through evidence-triggered steering. For a
   supervisor-detected checkpoint, require evidence that is observable in
   exposed commentary, actions, tool output, tests, or repository state;
   material to scope, authorization, safety, correctness, or significant
   rework; and time-sensitive because waiting would make recovery meaningfully
   harder, costlier, or impossible. Never use hidden reasoning or private
   chain-of-thought as evidence.
3. **Gate checkpoint:** after handoff, independently run the matching `Gnn`.
   Prepare a correction or the next `Pnn` only when the verified evidence
   supports it.

Apply a non-numeric threshold: immediate attention requires one high-severity
signal; normal attention requires one strong signal or two corroborating
signals; persistence attention requires the same moderate concern across two
snapshots, repeated attempts, or a plan-defined threshold; otherwise defer to
the gate. Intervene only when the expected cost of waiting clearly exceeds the
cost of interruption. Observation-only mode reports the evidence without
sending. Approval-gated mode requires the complete exact preview and fresh
approval. Bounded mode permits one automatic message only when it maps directly
and unambiguously to an existing repository rule, approved plan term, P-step
prompt, acceptance criterion, or exclusion and restores only that contract.

Bounded restoration cannot broaden scope, change requirements, amend the plan,
grant permission, alter user-owned work, authorize external or destructive
action, choose or replace a task, or let the supervisor apply the correction.
An imminent high-severity destructive, external, secret, permission, or
live-data risk may consume the same budget for a hold/stop message; recovery
still requires approval. Ambiguity, conflict, repeated intervention, a second
message, scope amendment, or non-restorative direction always requires an exact
preview and fresh approval.

After an automatic message, immediately report and durably record the exposed
evidence, rationale, verified destination, and exact message under the plan's
visibility rules. Resume observation unless the message pauses or stops the
implementor. Follow the orchestration reference for the complete authority,
budget, gate-correction, and handling rules.

## Evaluate Every Gate Independently

At each G gate, inspect the real repository root, worktree, branch and base,
user-owned changes, actual diff, commits, scope, exclusions, release metadata,
focused tests, broader validation, and residual risks. Treat the implementor's
handoff as evidence to verify, not a conclusion to adopt.

Record one decision:

- `pass`: record evidence and prepare the next P-step preview;
- `fail/correction`: keep the gate open and prepare a complete bounded
  correction prompt. Use fresh approval unless the selected bounded mode still
  has its one-message budget and the defect maps directly to an existing
  criterion; after correction, independently rerun the same gate; or
- `pause/amend`: stop dispatch, resolve the plan contradiction with the user,
  and update affected future work plus the decision log.

Never repair, consolidate, or implement corrections in the supervisor task.
Steer corrections only through the selected mode's exact authority boundary.
A request to collapse those roles requires pausing and amending the plan. At a
final gate, a child subagent may collect bounded read-only evidence when
appropriate and available, but the supervisor must verify that evidence and
retain the gate decision.

## Close Out Deliberately

Keep commit, push, pull-request, merge, deployment, publication, tagging, and
other release-closeout actions outside implementor P-step authority unless a
plan explicitly requires a bounded exception and the user separately approves
it. After the final gate passes, preview the exact closeout actions and obtain
authorization at the granularity required by the active repository's rules.
