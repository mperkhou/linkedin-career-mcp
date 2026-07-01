---
name: manual-resume-passthrough
description: Use when the user asks for a manual second pass, manual passthrough, Jack & Jill feedback pass, ATS refinement pass, or "next do JOB_ID" for a generated LinkedIn Career MCP resume. Guides Codex through a grounded human-in-the-loop ARO/resume refinement, artifact refresh, tracker note, visual PDF verification, and Flask UI badge marker.
---

# Manual Resume Passthrough

Use this workflow after the generator has already created a first-draft ARO,
HTML, PDF, and ATS score for a job row in `output/tracking/applications.sqlite3`.
The goal is a factual second pass, not a keyword-stuffing pass.

## Inputs

- Job id, usually from a prompt like `next do 4434941023`.
- Live DB: `output/tracking/applications.sqlite3`.
- Master evidence: `profile/MP-MASTER-RESUME.txt` and `profile/MASTER-RESUME.yml`.
- Existing generated ARO from the `applications.application_resume_object` column.

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
   - First call `save_application_resume_edit(..., backup_current=True)` so the
     prior ARO is available in the tracker backup slot.
   - Then run `scripts/application_resume_store_first_draft.py` with explicit
     `--output-html` and `--output-pdf` paths under
     `output/resumes/<Company_Slug>/<job_id>_<title_slug>/`.
   - Re-query the row and verify source paths, ATS fields, and backup presence.

7. Add the tracker note:
   - Append, do not replace, any existing notes.
   - Start the note with `Manual second pass YYYY-MM-DD:` so the Flask tracker
     can display the `Manual pass` badge.
   - Include old score to new score, what was emphasized, and what was left
     unsupported.

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
- Confirmation that the tracker note was appended and the `Manual pass` badge
  should appear.
- Verification commands run.

## Guardrails

- Do not edit `profile/MASTER-RESUME.yml` during a per-job passthrough unless the
  user explicitly asks for a master-resume update.
- Do not add skills solely because ATS or Jack & Jill suggested them.
- Do not remove user notes or unrelated row state.
- Do not mark `applied_to` or `date_applied` unless the user asks.
- Keep the final PDF to a clean two-page layout unless the target role clearly
  warrants a different format.
