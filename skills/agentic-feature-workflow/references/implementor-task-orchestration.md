# Implementor Task Orchestration

Use this reference only after a living plan is approved and before creating,
reusing, messaging, renaming, or observing an implementor task.

## Contents

1. [Discover Task Capabilities](#discover-task-capabilities)
2. [Build A Complete Implementor Prompt](#build-a-complete-implementor-prompt)
3. [Preview Exact Approval](#preview-exact-approval)
4. [Create And Reconcile A Task](#create-and-reconcile-a-task)
5. [Name Tasks Portably](#name-tasks-portably)
6. [Recommend Model And Reasoning](#recommend-model-and-reasoning)
7. [Choose Fresh Or Reused](#choose-fresh-or-reused)
8. [Send Later Phases And Corrections](#send-later-phases-and-corrections)
9. [Apply The Selected Supervision Mode](#apply-the-selected-supervision-mode)
10. [Use The Manual Fallback](#use-the-manual-fallback)
11. [Preserve Task Identity And Plan Visibility](#preserve-task-identity-and-plan-visibility)

## Discover Task Capabilities

Inspect the task-management capabilities available in the current Codex
surface before offering automation. Look for purpose-built operations to:

- list projects or environments;
- create a user-owned task in a direct checkout or isolated worktree;
- list and read tasks;
- wait for bounded status changes;
- send a later prompt to an existing task;
- set or verify a task title; and
- report stable task and host identity.

Use the available operations according to their documented schemas. Do not
invent a tool name, assume a capability exists, use a child subagent as a
substitute implementor, or claim that an unavailable action occurred.

Prefer a direct checkout only when the approved plan expects shared in-place
work and confirms that no other implementor is writing it. Prefer an isolated
worktree when repository policy, concurrent work, or phase isolation requires
it. Resolve the exact project, repository path, branch/base, and environment
before previewing creation.

If automated user-owned task creation is unavailable, use the manual fallback
below. Capability discovery is read-only and supplies no creation authority.

## Build A Complete Implementor Prompt

Build one self-contained prompt for exactly one P step. Include:

- supervisor or source-task identity when useful;
- repository path and expected environment;
- expected branch, base, and target release;
- living-plan path and the complete P-step scope;
- applicable instructions the implementor must read before editing;
- pre-existing user or prior-phase changes to preserve;
- safety preconditions and stop conditions;
- bounded objective, required files or areas, and acceptance criteria;
- strict exclusions and authorization boundaries;
- focused and complete validation requirements;
- exact structured-handoff fields; and
- an explicit stop before the matching G gate.

Do not rely on the implementor discovering material scope in the supervisor's
conversation. Do not bundle multiple P steps, authorize the implementor to
decide a gate, or make later-phase authority implicit.

For a correction, state the gate evidence, the exact defect to correct, the
permitted files, required revalidation, unchanged exclusions, and the same stop
boundary. Do not leak unrelated private reasoning or broaden the original
phase.

## Preview Exact Approval

Plan approval is separate from task-action approval. Before every new task
creation or later prompt delivery, show the user the exact proposed action,
including:

- destination project and repository path;
- direct checkout or worktree configuration, including starting state;
- new title, or the exact existing task identity for reuse;
- the complete prompt exactly as it will be delivered;
- model and reasoning effort;
- evidence-based configuration rationale;
- explicit supervision mode for the complete `Pnn/Gnn` cycle: `observation
  only`, `approval-gated attention`, or `bounded contract restoration`;
- automatic-message budget state for that cycle (`unavailable` or `one
  unused`);
- available bounded waiting capability or manual observation boundary;
- authorization boundaries; and
- implementor stop conditions.

Ask for explicit approval of that preview. Treat any user change as a new
preview field and show the reconciled preview before acting. Never infer
standing launch or send authority from plan approval, a previous launch, a gate
decision, or approval of another phase.

Creation plus delivery of the complete initial prompt is one approved launch
action. Do not create an empty task, plan to add the real prompt later, silently
change a field after approval, or create a speculative placeholder.

## Create And Reconcile A Task

After exact approval:

1. Create one user-owned task with the approved environment, title when the
   capability supports it, complete initial prompt, model, and reasoning.
2. Capture every returned stable identifier immediately. If setup is pending,
   preserve the pending identifier without treating it as a ready task ID.
3. Use bounded read-only list/read checks to let automatic setup and initial
   title generation settle.
4. Reconcile repository path, host, environment, prompt delivery, task ID, and
   title against the approved preview.
5. Apply the approved title once if creation could not set it reliably, then
   read it back once to verify persistence.
6. Record the final task ID and approved configuration in the living plan when
   the plan's visibility rules allow it.

If creation returns an error, times out, or has ambiguous delivery, do not retry
creation immediately. First list and inspect plausible tasks using bounded
read-only checks. Reuse the already-created task if identity is established.
Retry creation only after reconciliation proves that no task was created and
the original approval still exactly covers the retry.

If only the title failed, request separate approval for a title-only retry. A
title retry must not recreate the task, resend the initial prompt, or alter the
model, environment, or scope.

Never silently create a replacement task. Preview a replacement as a fresh
creation and obtain new approval.

## Name Tasks Portably

Use the target project's release version, never the workflow skill's version:

- first implementor: `v<version>: Implementor`;
- fresh task first launched for a later phase:
  `v<version>: Implementor: Pnn`; and
- unresolved target release: `v.Unversioned: Implementor`.

Retain the original title when reusing a task for later work. Do not add the
repository, organization, company, or skill name to the portable title. Do not
write `v.<version>` or reorder the later-phase suffix.

## Recommend Model And Reasoning

Make an evidence-based recommendation and allow the user to override it:

- Supervisor default: `gpt-5.6-sol` with `high` reasoning.
- Escalate supervisor reasoning only for genuinely difficult cross-contract or
  release-readiness judgment.
- Clear bounded implementation: `gpt-5.6-terra` with `xhigh` reasoning.
- Localized correction: normally retain `gpt-5.6-terra` with `xhigh` reasoning.
- Complex, ambiguous, or cross-cutting implementation: `gpt-5.6-sol` with
  `high` reasoning.

Do not escalate merely because a plan or prompt is long. Check that the chosen
model and reasoning combination is available in the destination environment.
A model change alone neither requires nor prevents task reuse.

## Choose Fresh Or Reused

Always use a fresh implementor task for P01. Before every later P step or
correction, independently recommend reuse or a fresh task.

Prefer reuse when:

- repository and environment identity are unchanged;
- supervisor and implementor roles remain cleanly separated;
- retained context is accurate and focused;
- the prior gate found no issue or only a localized correction; and
- the next phase benefits from repository context already acquired.

Prefer a fresh task when:

- systemic requirements were missed;
- corrections repeatedly failed;
- the task acted outside its role or context became contaminated;
- task identity cannot be reconciled;
- repository, branch, worktree, or environment materially changed; or
- retained assumptions are likely to reproduce the defect.

Explain the recommendation in the exact preview. User preference controls the
final choice after the consequences are visible.

## Send Later Phases And Corrections

Treat every later P-step prompt and every correction as a new action. Reconcile
the destination task first and prepare the complete prompt. Show the full exact
send preview and obtain fresh approval unless the already selected bounded
contract-restoration mode permits its one automatic message under the complete
rules below.

Send exactly once to the verified task. If delivery is ambiguous, inspect the
task before retrying. Never resend merely because an immediate response is
absent. A correction grants no authority for the next P step, and a P-step send
grants no authority for later questions, gate decisions, or replacement tasks.

The supervisor prepares corrections and the implementor applies them. Never
repair, consolidate, or implement the correction in the supervisor task. If
the user wants to collapse those roles, pause and amend the living plan before
continuing instead of treating message approval as a role exception.

## Apply The Selected Supervision Mode

Every launch or later P-step preview must select exactly one mode for the
complete `Pnn/Gnn` cycle. A previous choice supplies no default. The selection
does not transfer to a later phase or replacement task, and bounded authority
does not replenish when a correction is dispatched.

| Mode | Observation behavior | Message authority |
| --- | --- | --- |
| **Observation only** | Use bounded read-only checks and report meaningful progress, completion, failure, or qualifying attention evidence. | No implementor message may be sent. |
| **Approval-gated attention** | Use the same observation and evidence rules. | Every message requires a verified destination, complete exact preview, and fresh user approval. This preserves the evidence-triggered, approval-gated steering contract. |
| **Bounded contract restoration** | Use the same observation and evidence rules. | At most one automatic contract-restoring message is available across the complete P/G cycle, subject to every condition below. |

Record the selected mode and, for bounded mode, whether the shared automatic
message budget is `unused` or `consumed`. Selecting bounded mode is prospective
authorization for that envelope only; it is not standing or general autonomous
messaging authority.

### Observation State

Use bounded compact task waits or equivalent read-only status checks. Report
meaningful progress, completion, failure, or concrete exposed evidence that may
require an attention checkpoint. Do not narrate unchanged snapshots.

**Observation boundary:** Observation may not edit repository or plan state,
inject a correction, broaden scope, grant authority, create or replace a task,
answer a question, decide a gate, implement a correction, or archive the
supervisor task. Observation-only mode sends no message or unsolicited
instruction under any circumstance.

### Attention Checkpoint

Enter an attention checkpoint when the implementor asks a question, requests
authorization, proposes an external action, or reports a blocker.

The supervisor may also detect a checkpoint when exposed task commentary,
status, proposed actions, or output concretely shows material confusion, a
false premise, scope drift, unsafe behavior, repeated misunderstanding, or
likely costly rework.

#### Common Evidence And Decision Boundary

For a supervisor-detected attention checkpoint, the evidence must satisfy all
three factors:

1. **Observable:** Ground it in exposed commentary, proposed or completed
   actions, tool output, tests, or repository state. Exposed status may route
   attention to that evidence. Never use hidden reasoning or private
   chain-of-thought as evidence for intervention.
2. **Material:** Show relevance to scope, authorization, safety, correctness,
   or significant rework.
3. **Time-sensitive:** Show that waiting until the matching gate would likely
   make recovery meaningfully harder, costlier, or impossible.

All three are required. If any factor is absent, remain in observation and
defer the concern to the independent gate.

Use these qualitative thresholds without an automated monitor, classifier,
scoring engine, numerical risk score, or permission system:

| Threshold | Evidence required | Representative scenarios |
| --- | --- | --- |
| **Immediate attention** | One high-severity signal. | An irreversible or destructive action, external publication, secret exposure, permission bypass, live-data mutation, or an explicit exclusion violation. |
| **Normal attention** | One strong signal or two corroborating signals. | Scope drift plus an imminent edit, repeated failures plus validation weakening, or a false premise driving substantial implementation. |
| **Persistence attention** | The same moderate concern across two snapshots, repeated attempts, or a plan-defined retry or action threshold. | A concern that becomes intervention-worthy through repeated exposed evidence rather than one ambiguous observation. |
| **Defer to gate** | The attention threshold is not met. | Stylistic disagreement, one transient failure, ordinary debugging, incomplete reasoning, a reversible local experiment, or speculation. |

Relevant signal categories include:

- scope or authority crossing;
- a high-impact or irreversible action;
- a material goal misunderstanding;
- validation bypass or weakening;
- repeated failure without new evidence;
- self-reported progress contradicted by objective results;
- expanding work from an unverified premise;
- the wrong repository, branch, task, or environment; and
- attempts to evade safeguards.

Repository `AGENTS.md` guidance and the approved living plan may impose stricter
thresholds, retry limits, or high-severity signals, but may not weaken this
portable baseline.

Apply the common policy in this order:

1. Capture the exact exposed evidence and its source.
2. Confirm that it is observable, material, and time-sensitive.
3. Determine whether the immediate, normal, or persistence threshold is met;
   otherwise defer to the gate.
4. Apply any stricter repository or approved-plan threshold.
5. Intervene only when the expected cost of waiting clearly exceeds the cost of
   interruption.
6. Reconcile and verify the exact destination task immediately before any send.

This procedure supports judgment; it does not calculate a score or automate
observation, classification, task monitoring, permission, or general messaging.
It is a portable procedural baseline informed by current research and practice,
not a claim of scientific precision or settled scientific consensus.

#### Approval-Gated Attention

In approval-gated mode, detection authorizes only an intervention proposal; it
grants no send authority and does not permit the supervisor to apply the
correction. Before every message:

1. Show the concrete exposed evidence.
2. Explain why waiting for the matching gate is inappropriate.
3. Identify the verified destination task.
4. Preview the exact message in complete form.
5. Obtain fresh user approval for that one message.

Send the approved message exactly once. One approved intervention grants no
follow-up authority. A reply to an implementor question, a correction, or any
additional instruction requires its own exact preview and fresh approval.
Resume observation after the send unless the approved message explicitly
pauses or stops the implementor.

#### Bounded Contract Restoration

In bounded mode, one automatic message may be sent only when every common
evidence and decision condition above is satisfied, the shared P/G-cycle budget
is unused, the destination is verified, and the exact instruction maps directly
and unambiguously to at least one existing contract source:

- a repository `AGENTS.md` rule;
- an approved living-plan term;
- the current P-step prompt;
- an acceptance criterion; or
- an explicit exclusion.

The message may only restore that existing contract. It may not broaden scope,
change requirements, amend the plan, grant or change permissions, alter
user-owned work, authorize external or destructive action, select or replace a
task, provide recovery direction beyond restoration, or let the supervisor
repair, consolidate, or implement the correction.

An imminent destructive, external, secret-exposing, permission-bypassing, or
live-data action may instead receive one automatic **hold/stop** message. The
hold consumes the same shared budget and grants no recovery or expanded
authority. Messaging cannot preempt an operation that has already run; never
claim that a hold reversed or prevented completed behavior.

Immediately after any automatic send:

1. report to the user the exposed evidence, decision rationale, verified
   destination, exact message, and that the budget is consumed; and
2. durably record those same fields under the living plan's visibility rules.
   In a tracked plan, keep opaque task identity in the supervisor conversation
   rather than committing it.

One automatic message grants no follow-up authority. Resume observation unless
the message explicitly pauses or stops the implementor. Recovery, conflicting
instructions, ambiguous contract interpretation, repeated intervention, a
second message, scope amendment, or any non-restorative direction requires a
complete exact preview and fresh user approval.

Use these representative scenarios to preserve the authority boundary:

| Scenario | Automatic result in bounded mode | Why |
| --- | --- | --- |
| Implementor proposes the legacy controller and runtime tracker despite an approved living-plan/no-tracker contract. | **Eligible restoration** | Directly restate the existing no-tracker plan term before incompatible state is created. |
| Implementor announces an imminent edit outside the exact files allowed by the current P-step. | **Eligible restoration** | Restate the exact approved file criterion without adding work or permission. |
| Implementor announces an imminent destructive, external, secret, permission-bypass, or live-data action. | **Eligible hold/stop** | Stop only; consume the budget and require approval for recovery. |
| The governing contract could reasonably mean two different things. | **Approval required** | Ambiguous interpretation cannot support an automatic message. |
| The proposed message adds a useful deliverable or changes a requirement. | **Approval required** | Scope expansion is not contract restoration. |
| The proposed message grants write, external, destructive, or other new permission. | **Approval required** | Permission changes are outside the bounded envelope. |
| One automatic message has already been sent in this P/G cycle. | **Approval required** | Repeated or second sends exceed the shared budget. |
| The implementor is working through an ordinary debugging failure. | **Defer to gate** | Ordinary debugging does not satisfy the attention threshold. |
| The supervisor prefers a different style with no contract defect. | **Defer to gate** | Stylistic disagreement is neither material restoration nor time-sensitive. |

### Gate Checkpoint

After the implementor handoff, independently perform the matching `Gnn` against
the real repository evidence. The gate may prepare a correction or the next
bounded `Pnn`. A failed gate may use the one automatic bounded-restoration
message only when the same P/G-cycle budget remains unused and the defect maps
directly and unambiguously to an existing criterion. The budget does not
replenish for that correction. Keep `Gnn` open, have the implementor apply and
validate the correction, and independently rerun the same gate after it returns.

Every other gate correction requires a verified destination, complete exact
message preview, and fresh user approval. The supervisor never repairs,
consolidates, or implements the correction.

### Bounded Waiting Unavailable

When bounded waiting is unavailable, report the exact task ID, end the
supervisor turn, do not poll, and ask the user to reactivate the supervisor when
the implementor is ready. Do not archive the supervisor task.

## Use The Manual Fallback

When user-owned task creation or messaging is unavailable:

1. State which capability is unavailable.
2. Produce the same exact launch or send preview, including the complete prompt,
   title, environment, model recommendation, explicit supervision mode,
   message-budget state, observation limitation, authorization boundaries, and
   stop conditions.
3. Obtain user approval for the copyable handoff.
4. Give the user the exact prompt and task configuration to create or send
   manually.
5. Do not claim task creation, delivery, title persistence, or task identity.
6. Ask the user to return the stable task ID and any relevant environment
   identity after manual creation.
7. Reconcile the returned identity through read-only capabilities if they later
   become available; otherwise record it as user-reported.
8. Do not poll. Ask the user to reactivate the supervisor for the gate.

Manual operation relaxes no approval, role, scope, naming, supervision-mode,
message-budget, correction, or gate contract. It does not create automatic
delivery capability when messaging is unavailable.

## Preserve Task Identity And Plan Visibility

Treat task identity as durable workflow evidence. Keep the exact task ID, host
or environment identity when needed, launch phase, approved title, model,
reasoning, and reuse history aligned with the plan's orchestration record.

A local-only plan may retain opaque task IDs. A tracked Git plan must not commit
opaque Codex task IDs; record the intended configuration in the plan and retain
the exact runtime identity in the supervisor conversation. Never invent,
truncate, substitute, or expose a private identifier in a public artifact.

Task reconciliation does not replace independent gate verification. At every
gate, inspect repository evidence directly and confirm that the task acted only
within its approved phase.
