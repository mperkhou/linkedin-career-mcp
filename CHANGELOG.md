# linkedin-career-mcp CHANGELOG

## 4.0.0 - Add DB-backed second-pass resume variants

* Add explainable ATS diagnostics, noisy phrase regressions, structured GLM 5.2
  second-pass critique parsing, external critique classification, and
  evidence-backed patch validation. The v2 prompt sends job context, the current
  ARO, JOD targets, MRO/ARO source evidence, and ATS evidence; the validator
  accepts only supported recommendations and stores rejected recommendations as
  review metadata instead of resume content.
* Retry empty or thinking-only API LLM completions with the existing
  backoff/retry policy so transient OpenRouter responses do not fail the
  first-draft resume generation Make target.
* Store resume variants in SQLite so first drafts remain available as `v1`, GLM
  5.2 refinements are stored as `v2`, and Codex manual pass output is stored as
  `manual` without overwriting prior drafts.
* Add `make regenerate-resumes` as the main v1-plus-v2 workflow while keeping
  `make regenerate-draft-resumes` available for v1-only draft generation.
* Add `make refine-draft-resumes`, defaulting to
  `SECOND_PASS_MODEL ?= z-ai/glm-5.2`, for one-job or all-active v2 refinement
  runs with DB-stored critique, validation, ATS diagnostics, and model metadata.
* Add Flask tracker review controls for Draft v1, Refined v2, and Manual pass
  variants, including reversible selection, per-variant HTML/PDF downloads, ATS
  deltas, ARO diff, accepted/rejected changes, and unsupported claim details.
* Add `make manual-pass-resumes` and tracker support for storing a Codex manual
  pass variant from v1, v2, critique/validation output, ATS diagnostics, JOD
  text, prompt JOD text, and master-resume evidence.
* Add a tracker Add-popup seeding workflow that runs `make seed-jobs` with a
  selected job count and posting age window, defaulting to `past_week`, then
  chains selected v1, v2, Codex manual pass, and Codex highlighting steps for
  the newly seeded rows.
* Shade tracker rows for `Accepted for interview` and `N/A` statuses while
  preserving the existing applied-row green treatment.
* Keep in-app tracker compare-description, review, and edit links in the
  current window while leaving external job and artifact links in new tabs.
* Refresh the architecture docs, add ADRs for DB-backed variants and
  tracker-orchestrated workflows, update the README narrative and workflow
  diagram, and regenerate tracker screenshots for the Add seed widget, Actions
  menu, variant review page, main tracker, and background progress panel.
* Document the second-pass variant workflow, GLM critique prompt structure,
  accepted/rejected recommendation handling, evidence rules, manual critique
  ingestion, ATS diagnostics, and migration notes in the README, skill docs, and
  4.0.0 release notes.
* Bump the package version to `4.0.0` because resume storage, schema, and review
  workflow behavior changed.

## 3.5.0 - Add manual resume passthrough workflow

* Open tracker `Job URL` links directly to the stored LinkedIn posting in a new
  tab instead of routing through the local `/linkedin/<job_id>` helper.
* Show a `Manual pass` badge in the Flask tracker for applications whose notes
  record a manual second-pass resume refresh.
* Add a project Codex skill that packages the grounded manual resume passthrough
  workflow for reuse from future sessions, and link it through the default
  `make install` skill setup.
* Bump the package version to `3.5.0` for the tracker badge and reusable
  second-pass workflow.

## 3.4.1 - Refresh Oracle agentic AI evidence and cover letter PDFs

* Add Oracle OLAM MCP runtime architecture and agent-facing tool-contract
  evidence to the master resume source text and structured resume YAML.
* Link the new agentic AI evidence to the factual AI, platform engineering,
  automation, observability, and security skill inventory used by ARO matching.
* Tighten edited cover-letter PDF body typography so LTS-length manual drafts can
  stay on one page without collapsing the original margins or header spacing.
* Bump the package version to `3.4.1` for the master resume data and cover-letter
  PDF polish.

## 3.4.0 - Add Codex resume highlighting workflow

* Add a guarded Codex post-generation workflow that proposes selective
  `<strong>` emphasis for professional-experience bullets and rejects any output
  that changes resume wording or uses unsupported markup.
* Add `make highlight-draft-resumes`, a Flask tracker batch action, and an
  add-job checkbox so highlighted draft resumes can be generated from the CLI or
  chained after normal draft generation.
* Allow Codex highlighting runs to be limited to a specific rendered
  Professional Experience company or ARO job order for selective polishing.
* Document the design decision behind using Codex as an agentic polish step,
  including portfolio signaling and cost-aware use of already-budgeted Codex
  subscription capacity.
* Bump the package version to `3.4.0` for the new resume highlighting workflow.

## 3.3.1 - Align Education section resume layout

* Render Education entries with the same heading-and-bullet hierarchy as
  Professional Experience so institutions are not nested behind bullets and
  education details use standard filled bullets.
* Bump the package version to `3.3.1` for the resume layout polish.

## 3.3.0 - Add job-aware experience bullet rewriting

* Replace the literal Google XYZ experience-bullet rewrite instruction with a
  job-aware senior resume editing prompt that preserves evidence while allowing
  varied action verbs, sentence structures, and one- or two-sentence bullets.
* Tune the rewrite prompt for senior platform roles so supported production
  pressure, architecture ownership, identity/security, observability, and
  operational judgment can surface naturally from the source evidence.
* Cap rendered matched Core Technical Skills additions per category so live
  regeneration can keep the visible skills section focused while preserving the
  full match context in the Application Resume Object.
* Bump the package version to `3.3.0` for the bullet rewrite prompt improvement.

## 3.2.0 - Tune Core Technical Skills matching

* Split Core Technical Skills matching aids from renderable skills by adding
  non-display `match_terms` aliases to the master resume inventory.
* Canonicalize matched helper terms such as managed PostgreSQL, Python 3, REST
  APIs, and Linux environments back to display skills before storing ARO matches.
* Render Core Technical Skills through a global canonical de-duplication pass so
  repeated skills do not appear across multiple skill rows.
* Tighten the master resume Core Technical Skills inventory so process phrases
  like incident response lifecycle remain useful matching context without
  appearing as resume skills.
* Preserve job-specific ARO experience bullets and attached JOD context when
  refreshing ARO objects from the master resume without API calls.
* Restore a readable two-page resume PDF layout by removing over-aggressive
  print page-avoid rules and replacing sub-9pt resume text.
* Link the `mperkhou/linkedin-career-mcp` workflow note to the GitHub repository
  in rendered resume HTML/PDF output.
* Bump the package version to `3.2.0` for the ARO matching and rendering
  improvement.

## 3.1.0 - Add Flask tracker archiving

* Add a non-destructive archive state for tracker application rows so stale job
  postings and their generated artifacts can stay in SQLite for development
  data without cluttering the default active view.
* Add batch Archive and Restore controls to the Flask tracker, plus Active,
  Archived, and All posting views that preserve the current search, status, and
  sort state.
* Bump the package version to `3.1.0` for the new tracker feature.

## 3.0.0 - Finalize JOD-target ARO resume generation

* Promote current-role paragraph-evidence resume source into the canonical master
  resume text and YAML so ARO generation no longer depends on
  `tmp/master-paragraphs.md`.
* Make JOD-target bullet rewriting the primary draft-generation workflow,
  including Method 2 generation from ARO paragraph evidence and rendered
  prior-role job rewrites.
* Remove legacy local experience-bullet scoring and score-bucket selection from
  the production draft-generation and ARO-regeneration paths while preserving
  Core Technical Skills JOD matching for the rendered skills section.
* Keep `MASTER_RESUME=<path>` workflow flexibility and replace the experimental
  JOD rewrite Makefile toggle with the final `JOD_MODEL=<model-id>` override.
* Route Core Technical Skills matching through the same GLM 5.2 draft-generation
  default as JOD target creation and experience bullet rewrites.
* Document SemVer release guardrails and add a metadata test that keeps the
  package version aligned with the top changelog entry.
* Refresh README workflow diagrams and add a cached end-to-end JOD target rewrite
  example showing database fields, GLM prompts, and generated prior-role bullets.
* Replace cluttered README screenshot overlays with external legends and a shared
  numbered color palette across screenshots and workflow diagrams.
* Add a companion README JOD editor screenshot showing the same page scrolled to
  the removed-text and line-level diff panels.
* Tweak README progress-panel callout placement so labels and status controls
  remain unobstructed.
* Add v3.0.0 release notes, an experiment log, and an ADR documenting why the
  architecture moved from bullet/paragraph selection to JOD-targeted generation.
* Remove the retired `profile/algorithm.txt` placeholder now that experiment
  history and workflow decisions live under `docs/`.
* Fix generic Greenhouse URL imports so company names can be inferred from page
  titles instead of falling back to the job-board hostname.
* Bump the package version to `3.0.0` because the default resume-generation
  architecture changed in a breaking way.

## 2.0.3 - Local checkpoint: Experimental JOD rewrite and senior resume layout

* Add an opt-in experimental JOD-target ARO workflow that generates compact JOD
  requirements, rewrites rendered non-Oracle experience bullets with GLM 5.2,
  and caches prompts/responses alongside rendered artifacts.
* Preserve the existing Core Technical Skills JOD matching, local bullet scoring,
  and first-draft render flag selection before running the experimental rewrite.
* Update the resume template for senior-engineer two-page layouts by grouping
  Education, Certifications, and Portfolio after Professional Experience while
  keeping an explicit page-break override available.
* Document the experimental workflow flags and supporting-section layout behavior.
* Bump the package version to `1.0.3`.

## 2.0.2 - PR #32: Refresh MRO data and active status handling

* Refresh the master resume source text and YAML with expanded Oracle platform
  automation, OCI, observability, network automation, and AI-assisted workflow
  evidence.
* Add a profile algorithm notes placeholder for future resume-selection
  experiments.
* Make the Flask tracker status panel prefer currently running background
  actions over newer completed actions.
* Bump the package version to `1.0.2`.

## 2.0.1 - PR #31: Package structure foundation

* Refactor job-search models and service orchestration into `models/` and
  `services/` packages while preserving existing import paths.
* Update the architecture documentation to describe the package-based layout.
* Align CI test execution with the local `make test` command.
* Bump the package version to `1.0.1`.

## 2.0.0 - ARO structured resume refactor

* commit `36ab962`: First commit of resume restructure
* commit `d833805`: Add master resume YAML skill
* commit `71060cb`: Add JOD match count placeholders
* commit `9669b45`: Add ARO pass-one resume scoring workflow
* commit `48b6835`: Add ARO predraft bullet selection
* commit `9bc7766`: Rename ARO selection to first draft
* commit `4f4d37d`: Add ARO first-draft storage and ATS scoring improvements
* commit `f30c617`: Preserve ARO first-draft resume artifacts
* commit `7b8f0b4`: Add manual ARO resume editor
* commit `f88454d`: Add manual cover letter editor
* commit `6d415c1`: Add editable job description comparison
* commit `cc376f5`: Add manual LinkedIn job entry
* commit `8f7e7b7`: Add generic URL first-draft workflow
* commit `be57528`: Add resume rich-text editing and header line
* commit `8018ae1`: Update master resume source text
* commit `9257e96`: Refresh master resume YAML mappings
* commit `1b7a17b`: Add ARO sync actions
* commit `27dd305`: Fix JOD trimming diff display
* commit `ca55e50`: Fix resume editor skill preservation
* Remove the retired output/workbook artifact workflow and keep only the
  database-backed ARO resume workflow.
* Standardize the refactor terminology around MRO and ARO, removing the accidental
  alternate object naming from commands, UI labels, docs, skills, and workflow prompts.
* Decode escaped Streamdown rich-text spans in rendered resume headers.
* Fix the job-description comparison view so wrapping differences do not make
  kept prompt text appear as removed-by-trimming content.
* Fix the resume editor so Core Technical Skills inventories render in the edit
  form and cannot be blanked by missing or empty skill fields.

## 1.29.0 - PR #29: Remove standalone artifact stylizers

* Remove the standalone resume and cover-letter PDF stylizer commands from this repo.
* Keep static artifact refresh focused on targeted link/text patches instead of PDF restyling.
* Recognize full month names in generated resume job-date rows.

## 1.28.0 - PR #28: Tune JOD cleaner from live tracker audit

* Tune ML-assisted JOD chunk selection with live keep/drop examples.
* Add a reusable tracker JOD audit and backfill command.

## 1.27.0 - PR #27: Add ML-assisted JOD chunk ranking

* commit `27a5176`: Add ML-assisted JOD chunk ranking

## 1.26.0 - PR #26: Detect dynamic resume sections during stylizing

* commit `6573e2e`: Detect extra resume sections during stylizing

## 1.25.0 - PR #25: Add webapp regeneration actions and artifact stylizers

* commit `5d79e39`: Add webapp regeneration actions
* commit `6b7b9da`: Track artifact timestamps in the tracker
* commit `2a20329`: Add standalone resume stylizer
* commit `ff5d019`: Add standalone cover letter stylizer
* commit `1e0b844`: Preserve hyperlinks in stylized PDFs
* commit `4814923`: Preserve cover letter bold styling

## 1.24.0 - PR #24: Bust README diagram image cache

* commit `bebeaf0`: Bust README diagram image cache

## 1.23.0 - PR #23: Add source-resume ATS repair loop

* commit `a9cd5e4`: Add source-resume ATS repair loop
* commit `00f64c2`: Refine ATS repair scoring evidence
* commit `f698425`: Raise API generation timeout default
* commit `9535335`: Revamp workflow documentation diagrams

## 1.22.0 - PR #22: Tune cover-letter Oracle alignment

* commit `bbed732`: Tune cover-letter Oracle alignment

## 1.21.0 - PR #21: Split planner and artifact LLM models

* commit `e2b0a2c`: Split planner and artifact LLM models

## 1.20.0 - PR #20: Add artifact workflow logging

* commit `f4e30e5`: Add artifact workflow logging

## 1.19.0 - PR #19: Harden OpenRouter provider throttling

* commit `3fe51d0`: Handle OpenRouter provider rate limits

## 1.18.0 - PR #18: Tracker download and application state polish

* commit `28e5bd4`: Copy tracker artifacts to Downloads
* commit `f8f5255`: Add interview and rejected application statuses
* commit `4dfa04e`: Preserve tracker view state

## 1.17.0 - PR #17: Add contextual query optimizer

* commit `3d7e58d`: Add contextual query optimizer

## 1.16.0 - PR #16: Improve tracker downloads and experience filtering

* commit `6d0e917`: Keep PDF downloads in tracker tab
* commit `0206efb`: Filter low-experience jobs and track seniority

## 1.15.0 - PR #15: Add ATS-informed resume skill repair

* commit `33f208c`: Add ATS-informed resume skill repair
* commit `d578092`: Document ATS workflow and tracker visuals

## 1.14.0 - PR #14: Harden tracker metadata and add ATS scoring

* commit `d52e04b`: Harden matching workflow and tracker metadata
* commit `2df54b5`: Add sortable tracker columns
* commit `778f9dd`: Add ATS proxy scoring to tracker

## 1.13.0 - PR #13: Refresh cover-letter text and README visuals

* commit `0db2b05`: Update cover letter project paragraph
* commit `0bd3515`: Add section-aware template graphic
* commit `f65e1dd`: Refresh stale resume PDF styling
* commit `6b4b8ef`: Add annotated tracker screenshot

## 1.12.0 - PR #12: Add artifact progress, cover-letter retry, and static link refresh

* commit `150c456`: Add artifact audit progress and cover letter retry
* commit `aa6fa81`: Update LinkedIn profile links in templates
* commit `9fcf62f`: Add static artifact refresh command

## 1.11.0 - PR #11: Add cover letter generation and polished artifact styling

* commit `caeaf17`: Show regenerate resume LLM status
* commit `1f9ccca`: Add cover letter workflow and README graphic
* commit `5df2b13`: Clarify README workflow diagram acronyms
* commit `60d975d`: Emphasize template sections in workflow diagram
* commit `b150091`: Show shared artifact output path in workflow diagram
* commit `e443db2`: Reorient workflow diagram into top-down lanes
* commit `f87e7f2`: Polish resume and cover letter PDF styling

## 1.10.0 - PR #10: Clean job descriptions and resume regeneration flow

* commit `dce8a20`: Add raw LinkedIn payload debugging
* commit `e3dab78`: Store cleaned job descriptions for resume prompts
* commit `58e0d26`: Add resume regeneration command
* commit `5194bf0`: Add job description comparison view
* commit `6e0bf35`: Tidy generated resume skills formatting
* commit `d720dca`: Improve stored job description parsing

## 1.9.0 - PR #9: feat: ✨ flask webapp to launch windows in chromium if installed

* commit `fddfb60`: feat: ✨ flask webapp to launch windows in chromium if installed

## 1.8.0 - PR #8: feat: ✨ adding a flask webserver & management page

* commit `aaf9008`: feat: ✨ adding a flask webserver & management page
* commit `8abbe6f`: docs: 📝 update README.md to cover new features

## 1.7.0 - PR #7: fix: ⚡️ improve output resume template stylistics

* commit `0c67aca`: fix: ⚡️ improve output resume template stylistics

## 1.6.0 - PR #6: fix: ⚡️ improve performance with more guardrails & use openrouter API

* commit `5db2124`: fix: ⚡️ improve performance by adding some elaborate guiderails & use external AI provider

## 1.5.0 - PR #5: fix: ⚡️ improve performance by adding some guiderails

* commit `46e0338`: fix: ⚡️ improve performance by adding some guiderails
* commit `0a2f70e`: test: fix tests to pass CI/CD pipeline in GitHub
* commit `914c30e`: test: fix tests to pass CI/CD pipeline in GitHub again

## 1.4.0 - PR #4: fix: ⚡️ adding small improvements based on first live test on 2 openings

* commit `ac52442`: fix: ⚡️ adding small improvements based on first live test on 2 openings

## 1.3.0 - PR #3: Document Qwen3 matching workflow

* commit `82fc493`: Document Qwen3 matching workflow

## 1.2.0 - PR #2: Add Ollama matching workflow

* commit `6b1d30f`: Add Ollama matching workflow

## 1.1.0 - PR #1: Add install workflow and Codex skill

* commit `33ec1d0`: Add install workflow and Codex skill

## 1.0.0 - Initial baseline

* commit `dff4161`: Initial Python LinkedIn career MCP server
* commit `24b0f21`: Handle current LinkedIn public job card markup
