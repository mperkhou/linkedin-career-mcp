---
name: manual-resume-passthrough
description: Use when the user asks for a manual second pass, manual passthrough, Jack & Jill feedback pass, ATS refinement pass, or "next do JOB_ID" for a generated LinkedIn Career MCP resume. Guides Codex through a grounded ARO/resume review that stores a DB-backed manual variant, keeps v1/v2 intact, and verifies the final PDF before tracker selection.
---

# Manual Resume Passthrough

Follow the repository root `AGENTS.md` for shared safety, release, tracker, and
resume-evidence guardrails. This skill covers the manual resume pass workflow
itself.

Use this workflow after the normal resume path has created `v1` and `v2`
variants for a job row in `output/tracking/applications.sqlite3`. The goal is a
factual manual pass, not a keyword-stuffing pass. In the current tracker, the
app-triggered workflow stores the result as a `manual` resume variant in
`application_resume_variants`; it does not overwrite the v1 or v2 variant rows
and every profile upserts the same one manual row for the job. It preserves an
explicit Review-page selection; when selection is automatic, the normal
preference becomes `manual`, then `v2`, then `v1`.

## Inputs

- Job id, usually from a prompt like `next do 4434941023`.
- Live DB: `output/tracking/applications.sqlite3`.
- Master evidence: `profile/MP-MASTER-RESUME.txt` and `profile/MASTER-RESUME.yml`.
- Stored v1/v2 resume variants from `application_resume_variants`.
- v2 critique, validation report, evidence packet, ATS diagnostics, JOD, prompt
  JOD, and master-resume evidence.

## Workflow

1. Inspect the row before editing:
   - Query company, title, URL, applied status, notes, ATS fields, missing terms,
     source paths, JOD lengths, and ARO/PDF/HTML presence.
   - Save the current ARO, full JOD, and prompt JOD under
     `tmp/manual_second_pass/<job_id>/`.
   - Read the prompt JOD and existing ARO shape before writing.

2. Audit evidence:
   - Compare JOD targets against Oracle and prior-role evidence in the master
     resume sources.
   - Treat ATS missing terms as semantic evidence, not automatic insertions.
   - Keep supported aliases and transferability language.
   - Leave unsupported terms missing when the master evidence does not support
     them. Call those out in the final note.
   - Apply the same truthfulness rule used by v2 refinement: model or ATS
     suggestions can improve wording, ordering, or emphasis, but they cannot
     create new skills, tools, metrics, employers, certifications, or
     responsibilities that are absent from the evidence.

3. Optionally checkpoint the database:
   - For risky manual inspection or local recovery, copy the DB before a live
     write:
     `cp output/tracking/applications.sqlite3 output/tracking/applications.pre-<slug>-second-pass-<UTC>.sqlite3`

4. Build the manual variant:
   - Prefer the app-triggerable path:
     `make manual-pass-resumes JOB_IDS=<job_id>`.
   - Select only an allowlisted profile:
     - `economy`: `gpt-5.6-terra` with `high` reasoning.
     - `regular`: `gpt-5.6-sol` with `high` reasoning; this is the default.
     - `premium`: `gpt-5.6-sol` with `xhigh` reasoning.
   - For example:
     `MANUAL_PASS_PROFILE=premium make manual-pass-resumes JOB_IDS=<job_id>`.
     Model and effort overrides resolve independently from a direct script
     option or workflow-specific Make value, then the matching
     `LINKEDIN_CAREER_MCP_MANUAL_PASS_CODEX_*` environment value, then the
     deprecated shared Make and script environment fallbacks, then the selected
     profile. An explicitly empty effort inherits Codex CLI configuration.
     Existing `CODEX_MODEL`, `CODEX_REASONING_EFFORT`,
     `LINKEDIN_CAREER_MCP_CODEX_MODEL`, and
     `LINKEDIN_CAREER_MCP_CODEX_REASONING_EFFORT` inputs remain compatibility
     fallbacks but are deprecated.
   - The script builds the v1/v2 evidence bundle, including the v2 critique,
     validation report, accepted and rejected changes, unsupported terms, ATS
     diagnostics, JOD text, prompt JOD text, and master-resume evidence.
   - Codex returns a candidate ARO. The workflow renders it, recalculates ATS
     diagnostics, validates it against the evidence bundle, and stores a
     `manual` variant through the same DB-backed model used by v1/v2.
   - Re-query `application_resume_variants` and verify the `manual` row has ARO,
     HTML, PDF, ATS diagnostics, the Codex prompt/response, validation payload,
     and model metadata. Its metadata must include the profile and resolved
     model, reasoning effort, client, and command.
   - Confirm an explicit selection remains unchanged. For a row in automatic
     selection mode, confirm the normal `manual > v2 > v1` preference makes the
     new manual variant active.

5. Tracker review:
   - Open `/resumes/<job_id>/variants` in the Flask tracker.
   - Compare v1, v2, and Manual pass ATS movement, diff, accepted/rejected
     evidence, unsupported terms, and artifact links.
   - If an explicit selection should move to the reviewed manual result, select
     `Use manual pass` only after review. This action is reversible.

   If highlighting is chained after the manual pass, it targets `manual` but
   uses its own independent `gpt-5.6-luna`/`high` default. A manual profile must
   never configure highlighting. Verify that highlighting preserved the
   generation/manual metadata and added separate nested `highlighting`
   provenance with its resolved client, model, effort, and command.

6. Visual verification:
   - Render the stored PDF to PNG with `pdftoppm`.
   - Inspect every page for page count, overlap, clipped text, awkward wrapping,
     and readable density.
   - Recalculate ATS from the stored PDF and confirm it matches the row.

## Output Contract

When finished, report:

- Job id, company, title.
- ATS movement and remaining missing high-value terms.
- PDF, HTML, and manual variant details.
- DB checkpoint path, if one was created.
- Confirmation that the one `manual` resume variant was stored, the previous
  manual row was replaced on rerun, and explicit or automatic selection behaved
  as described above.
- Verification commands run.

## Guardrails

- Do not edit `profile/MASTER-RESUME.yml` during a per-job passthrough unless the
  user explicitly asks for a master-resume update.
- Do not add skills solely because ATS or Jack & Jill suggested them.
- Do not remove user notes or unrelated row state.
- Do not mark `applied_to` or `date_applied` unless the user asks.
- Treat profiles as execution configuration, not variant keys. Keep one
  `manual` variant and never let a manual profile control highlighting.
- Keep the final PDF to a clean two-page layout unless the target role clearly
  warrants a different format.
