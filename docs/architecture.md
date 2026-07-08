# Architecture

`linkedin-career-mcp` is a local-first, Python-centric job-search and
resume-tailoring system. MCP is the integration boundary for external clients,
but the core product is a local SQLite-backed workflow with CLI entrypoints,
Make targets, reusable Python modules, and a Flask tracker for human review.

The project intentionally does not authenticate to LinkedIn, read private member
data, submit applications, or automate final application submission. Public job
discovery, local resume generation, and manual review are the supported system
boundaries.

## System Boundaries

```text
MCP clients / CLI / Make / Flask tracker
  -> tools and workflows
  -> providers and LLM clients
  -> SQLite tracker database
  -> rendered HTML/PDF artifacts stored in SQLite
```

- The MCP server exposes public LinkedIn search, public job details, raw payload
  inspection, and matching workflow tools.
- Make and CLI entrypoints are the main automation surface for local runs and
  CI-style validation.
- The Flask tracker is the primary operating surface for review, status updates,
  editing, resume variant selection, downloads, and long-running background
  actions.
- SQLite is the source of truth for application rows, job descriptions, resume
  objects, rendered artifacts, ATS fields, cover letters, and resume variants.

## Agent Guidance Layer

`AGENTS.md` is the canonical operational guidance layer for agents working in
this repository. It is intentionally separate from the user-facing product docs:
`README.md` explains what the system does and how an operator uses it, while
`AGENTS.md` defines repo-working guardrails such as edit safety, release
closeout, tracker workflow invariants, generated-artifact caution, and
resume-evidence discipline.

The skill docs stay focused on workflow-specific command reference. The
`skills/linkedin-career-mcp/SKILL.md` file points agents to `AGENTS.md` for
shared repo behavior before providing MCP and Make target details. The
`skills/manual-resume-passthrough/SKILL.md` file does the same for manual resume
pass work, so the manual-pass protocol can stay focused on per-job evidence
review while release and safety rules remain centralized.

This keeps agent behavior aligned across tracker workflows, Codex manual pass,
Codex highlighting, release closeout, and application-writing work without
duplicating the same operational rules in every human-facing document.

The `skills/agentic-workflow-controller/` skill extends that guidance for large
multi-step repo changes. It defines a procedural controller pattern for staged
implementation prompts, P-step execution, G-step reassessment gates, validation
evidence, and pause conditions. The tracked skill assets define the plan and
tracker templates; a live workflow copies them into ignored
`tmp/agentic-workflows/<workflow_id>/` state so progress can be resumed without
committing noisy cursor data. The controller does not run as a daemon, grant
extra permissions, or replace `AGENTS.md`; it gives Codex sessions a repeatable
way to execute already-authorized work while preserving release, artifact, and
resume-evidence guardrails.

## Core Layers

```text
server.py
  Creates the FastMCP server and wires MCP tools.

tools/
  Registers MCP tools. Tool functions stay thin and return serializable models.

services/
  Coordinates provider calls, caps, defaults, and tool-friendly errors.

providers/
  Encapsulates external systems. Providers return domain models, not MCP
  payloads.

workflows/
  Owns multi-step job discovery and database-seeding flows.

application_resume.py
  Builds per-job AROs, matches skills, creates JOD targets, rewrites rendered
  experience bullets, and produces first-draft resume objects.

resume_refinement.py / resume_refinement_cli.py
  Builds ATS diagnostics, critiques v1 drafts, validates evidence-backed
  changes, and stores v2 resume variants.

resume_manual_pass.py
  Builds the Codex manual-pass evidence bundle and stores a manual resume
  variant without overwriting v1 or v2.

resume_highlighting.py
  Runs guarded Codex JSON-patch highlighting for rendered experience bullets.

resume_rendering.py
  Renders ARO mappings into resume HTML and PDF bytes.

webapp.py
  Owns SQLite migrations, tracker views, artifact downloads, editing, variant
  selection, background action orchestration, and cover-letter rendering.
```

## Object Model

The workflow is organized around explicit objects instead of large freeform
prompt bundles.

- **JOD**: Job Opening Description. The raw public posting text is stored on the
  application row, and the prompt JOD stores the cleaned, low-noise version used
  by resume and ATS workflows.
- **MRO**: Master Resume Object. `profile/MASTER-RESUME.yml` is the canonical
  source object. It stores neutral render flags, Core Technical Skills groups,
  and professional-experience source evidence.
- **ARO**: Application Resume Object. A per-job deep copy of the MRO, enriched
  with JOD match lists, JOD targets, generated rendered experience bullets,
  render decisions, and manual edits.
- **CLO**: Cover Letter Object. A manually edited rich-text cover letter stored
  in SQLite and rendered to PDF bytes on save.
- **Resume variant**: A DB-backed resume version for one job. `v1` is the first
  draft, `v2` is the GLM second-pass refinement, and `manual` is the Codex
  manual pass.

The active resume fields on `applications` are a selected view of a stored
variant. Selecting `v1`, `v2`, or `manual` copies that variant into the active
resume HTML/PDF/ATS columns and updates `selected_resume_variant`; it does not
delete other variants.

## Persistence Model

The local tracker database is `output/tracking/applications.sqlite3`.

`applications` stores:

- application identity, company, title, source URL, status, notes, archive state,
  and dates
- raw JOD and prompt JOD
- the active ARO YAML, resume HTML, resume PDF bytes, filenames, timestamps, and
  source paths
- active ATS proxy fields
- the selected resume variant key
- cover-letter object YAML, rendered cover-letter PDF bytes, filenames, and
  timestamps

`application_resume_variants` stores:

- `job_id`, `variant_key`, label, source, parent variant, and timestamps
- ARO YAML, rendered HTML, PDF bytes, filenames, and MIME metadata
- ATS scores and missing-term details for that variant
- ATS diagnostics, evidence packets, critique prompts/responses, parsed
  critique, validation reports, accepted/rejected patches, external critique,
  and model metadata

SQLite migrations are owned by `webapp.py`. Opening the tracker or connecting
through the webapp migration path ensures newer columns and the variant table
exist. Existing first-draft ARO rows are backfilled into `v1` variants when
possible.

## Main Workflow

```text
MRO
  -> search planning
  -> public LinkedIn search and job-detail fetch
  -> JOD cleaning
  -> application row in SQLite
  -> v1 ARO generation
  -> HTML/PDF rendering and ATS scoring
  -> v2 refinement and validation
  -> optional manual or highlighting passes
  -> tracker review and reversible variant selection
```

The main resume workflow is v1 plus v2. The first-draft stage creates or
refreshes the ARO as `v1`; the second-pass stage writes `v2` and leaves the
selected resume unchanged. A v1-only target remains available for explicit
first-draft runs, debugging, and lower-cost iteration.

The Add popup in the tracker can seed a batch of public postings and then chain
selected workflow stages for only the newly seeded job IDs. It passes the job
count and posting-age filter into the seed command, parses the seeded job IDs
from the seed workflow output, and runs the selected background steps against
that batch.

## Resume Refinement and Evidence Rules

Second-pass refinement is designed as a versioned review layer, not an
overwrite. GLM 5.2 reads the v1 ARO, selected JOD text, ATS diagnostics, JOD
targets, and master-resume evidence. It can propose rewording, reordering,
emphasis, and supported aliases when those changes are grounded in existing
evidence.

The validator rejects unsupported skills, tools, employers, metrics, compliance
claims, and responsibilities. ATS missing terms are treated as review signals,
not instructions to stuff keywords into the resume. Unsupported suggestions can
be recorded, but they should not become accepted resume content without new user
evidence.

The Codex manual pass is a separate variant-producing workflow. It reads v1, v2,
v2 critique and validation output, ATS diagnostics, JOD text, prompt JOD text,
and master-resume evidence, then stores a `manual` variant through the same DB
model.

## Tracker and Background Actions

The Flask tracker is local-only and operates directly against SQLite. It owns:

- filtering, status updates, archive state, notes, and row-level visual status
- JOD review and prompt-JOD editing
- resume editing against the active ARO
- variant review, comparison, downloads, and reversible selection
- cover-letter rich-text editing and PDF rendering
- artifact copy-to-downloads actions
- background action creation, status streaming, and progress display

Long-running actions run in background threads and stream command output into a
bounded in-memory status panel. The tracker prefers showing a currently running
action over a newer completed action so expensive workflows remain visible.

In-app review and edit links stay in the current window. External job URLs and
rendered artifacts continue to open in new tabs.

## CLI and Make Orchestration

Make targets are the stable local automation contract:

- `seed-jobs` plans searches, fetches public job details, trims JODs, and writes
  application rows.
- `regenerate-resumes` is the main v1-plus-v2 resume workflow.
- `regenerate-draft-resumes` intentionally runs only the v1 draft stage.
- `refine-draft-resumes` creates or reruns v2 for existing first drafts.
- `manual-pass-resumes` creates manual variants through the Codex workflow.
- `highlight-draft-resumes` applies guarded Codex `<strong>` highlighting.
- `regenerate-aro-objects` refreshes stored ARO objects from the current MRO
  without draft-generation LLM calls.
- `sync-draft-to-aro` re-renders the stored active ARO and refreshes ATS fields.

The LLM boundary is centralized through provider clients. API LLM calls use
retry/backoff behavior for transient transport failures and empty or thinking-only
generations. The workflow still treats final generated content as untrusted
until it passes schema, evidence, and rendering validation.

## Design Rules

- Keep LinkedIn public scraping isolated in `providers/linkedin_public.py`.
- Do not introduce LinkedIn authentication or private member access without a
  separate provider boundary and explicit scope decision.
- Keep MCP tools thin; place career workflow behavior in reusable Python modules.
- Treat SQLite as the local source of truth for tracker state and generated
  artifacts.
- Preserve v1 before writing refinements; never make v2 or manual generation an
  overwrite-only operation.
- Keep resume changes evidence-backed. New facts require user-provided source
  evidence before they can become accepted content.
- Future application submission workflows must require explicit user approval
  before any external submit action.
- Add new job boards as providers, not as separate MCP servers, unless their
  auth or runtime needs diverge.

## Extension Points

- New job boards should implement provider-level search/detail behavior and
  return shared domain models.
- New resume review stages should store outputs as variants or variant metadata
  instead of mutating prior variants in place.
- New tracker actions should stream through the existing background-action
  status model when they can run longer than a normal request.
- New evidence sources should attach to the MRO/ARO evidence model before they
  are used by resume generation or refinement.
