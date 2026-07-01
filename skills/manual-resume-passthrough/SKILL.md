---
name: manual-resume-passthrough
description: Use when the user asks for a manual second pass, manual passthrough, Jack & Jill feedback pass, ATS refinement pass, or "next do JOB_ID" for a generated LinkedIn Career MCP resume. Guides Codex through a grounded human-in-the-loop ARO/resume refinement, artifact refresh, tracker note, visual PDF verification, and Flask UI badge marker.
---

# Manual Resume Passthrough

Use this workflow after the generator has already created a first-draft ARO,
HTML, PDF, and ATS score for a job row in `output/tracking/applications.sqlite3`.
The goal is a factual manual pass, not a keyword-stuffing pass. In the current
tracker, the app-triggered workflow stores the result as a `manual` resume
variant in `application_resume_variants`; it does not overwrite the v1 or v2
variant rows or switch the selected resume automatically.

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

3. Checkpoint the database:
   - Copy the DB before any live write:
     `cp output/tracking/applications.sqlite3 output/tracking/applications.pre-<slug>-second-pass-<UTC>.sqlite3`

4. Build the candidate ARO:
   - Start from the existing ARO.
   - Update the summary, visible skill rows, selected rendered jobs, and bullets.
   - Preserve truthfulness over ATS score movement.
   - Prefer supported, role-aligned phrasing such as production cloud automation,
     IaC, observability, security, runbooks, CI/CD, and prior regulated systems
     only when the evidence supports them.
   - Avoid unverified platform-specific claims, certifications, services, or
     frameworks even when the JOD asks for them.
   - Write candidates to `tmp/manual_second_pass/<job_id>/candidate*.yml`.

5. Render and score candidates:
   - Render with `render_resume_html()` and `render_resume_pdf_from_html()` or
     `scripts/application_resume_store_first_draft.py` for the final write.
   - Score with `calculate_ats_proxy_score()` against the prompt JOD when
     available, otherwise the full JOD.
   - Prefer the cleanest credible version, not necessarily the highest score.

6. Store the final pass:
   - Prefer the app-triggerable path:
     `make manual-pass-resumes JOB_IDS=<job_id>`.
   - The script builds the v1/v2 evidence bundle, calls Codex, renders the
     returned ARO, recalculates ATS diagnostics, and stores a `manual` variant
     through the same DB-backed variant model used by v1/v2.
   - Re-query `application_resume_variants` and verify the `manual` row has ARO,
     HTML, PDF, ATS diagnostics, the Codex prompt/response, validation payload,
     and model metadata.
   - Do not switch the selected resume automatically. Use the tracker variant
     review page to select `Manual pass` when it is ready.

7. Tracker review:
   - Open `/resumes/<job_id>/variants` in the Flask tracker.
   - Compare v1, v2, and Manual pass ATS movement, diff, accepted/rejected
     evidence, unsupported terms, and artifact links.
   - Select `Use manual pass` only after review. This action is reversible.

8. Visual verification:
   - Render the stored PDF to PNG with `pdftoppm`.
   - Inspect every page for page count, overlap, clipped text, awkward wrapping,
     and readable density.
   - Recalculate ATS from the stored PDF and confirm it matches the row.

## Output Contract

When finished, report:

- Job id, company, title.
- ATS movement and remaining missing high-value terms.
- PDF, HTML, and candidate YAML paths.
- DB checkpoint path.
- Confirmation that the `manual` resume variant was stored and remains
  unselected until explicitly chosen from the tracker.
- Verification commands run.

## Guardrails

- Do not edit `profile/MASTER-RESUME.yml` during a per-job passthrough unless the
  user explicitly asks for a master-resume update.
- Do not add skills solely because ATS or Jack & Jill suggested them.
- Do not remove user notes or unrelated row state.
- Do not mark `applied_to` or `date_applied` unless the user asks.
- Keep the final PDF to a clean two-page layout unless the target role clearly
  warrants a different format.
