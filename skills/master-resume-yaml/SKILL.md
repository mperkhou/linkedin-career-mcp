---
name: master-resume-yaml
description: Use before LinkedIn search planning or resume/cover-letter tailoring when creating, rebuilding, or refining profile/MASTER-RESUME.yml from a master resume text source such as profile/MP-MASTER-RESUME.txt. Includes staged setup of the bare resume YAML plus iterative category and skill linkage between job bullets and Core Technical Skills.
metadata:
  short-description: Build the master resume YAML
---

# Master Resume YAML

Use this skill to prepare the factual master resume object that later search, resume, cover-letter, and ATS workflows will consume. This skill is an initialization/refinement workflow only; do not run LinkedIn search planning, JOD tailoring, ATS repair, or cover-letter generation from this skill.

## Default Inputs

- Source text: `profile/MP-MASTER-RESUME.txt`
- Target YAML: `profile/MASTER-RESUME.yml`
- Preview renderer: `scripts/render_resume_html.py`
- Template: `templates/resume/master_resume.html.j2`

If the user gives a different source text path, use it, but keep `profile/MASTER-RESUME.yml` as the default target unless asked otherwise.

## Workflow

### 1. Inspect Before Editing

- Check `git status --short`.
- Confirm the source text and target YAML paths exist or clarify which one should be created.
- Read the source text section boundaries before writing YAML.
- Preserve user edits in `profile/MASTER-RESUME.yml`; update the existing structure instead of regenerating blindly unless the user asks for a full rebuild.

### 2. Build The Barebones Resume Object

Create or refresh these top-level sections:

- `schema_version`
- `source`
- `section_order`
- `header_top`
- `professional_summary`
- `core_technical_skills`
- `professional_experience`
- `education`
- `certifications`
- `portfolio`

Keep the object renderer-friendly:

- `core_technical_skills.bullet_points[*].items.primary` contains the always-rendered skills.
- `core_technical_skills.bullet_points[*].items.additional` contains factual optional skills that may be selected later.
- Every core skill bucket has `jod_matched_items: []`.
- Do not add static `rendered_text` for core skills; the renderer computes it from `items.primary` plus valid `jod_matched_items`.
- Every `professional_experience.jobs[*]` has `render`, `min_bullet_points`, and `max_bullet_points`.
- Every job bullet has `text`, `render`, `categories`, and `skills`.

### 3. Structure Experience Categories

For the current role, preserve source category headings as `categories.assigned` when the text contains explicit category groupings.

For prior roles, use:

```yaml
categories:
  assigned: null
```

Always populate `categories.matched` with Core Technical Skills category names only.

### 4. Link Bullets To Skills

For each professional-experience bullet, create a `skills` list with this shape:

```yaml
skills:
- category: Platform & API Engineering
  matched:
  - Systems Architecture
  - production troubleshooting
```

Rules:

- Every `skills[*].category` must also appear in `categories.matched`.
- Every matched skill must exist in that category's `items.primary` or `items.additional`.
- Prefer exact factual matches from the bullet text.
- Use broader skills only when the bullet clearly supports them.
- Do not invent technologies or responsibilities to make matches look stronger.
- If a useful skill is missing from Core Technical Skills, add it to the appropriate `items.additional` bucket first, then match bullets to it.
- Keep bullet text stable unless the user explicitly asks for wording changes.

### 5. Iterate In Passes

This work is expected to happen across a few review loops:

1. Bare YAML extraction from the master text.
2. Core Technical Skills normalization and enrichment.
3. Experience-bullet category matching.
4. Per-bullet skill matching.
5. Human review and small correction passes.

After each major pass, summarize what changed and call out ambiguous mappings rather than hiding them.

## Validation

Run these checks before finishing:

```bash
ruby -e "require 'yaml'; YAML.load_file('profile/MASTER-RESUME.yml'); puts 'YAML OK'"
.venv/bin/python scripts/render_resume_html.py --input profile/MASTER-RESUME.yml --output tmp/master_resume_preview.html
.venv/bin/python -m pytest tests/test_resume_html_template.py
make lint
```

For category and skill linkage changes, also run a structured inventory check:

```bash
ruby -ryaml -e "data=YAML.load_file('profile/MASTER-RESUME.yml'); inv=data.dig('core_technical_skills','bullet_points').to_h { |bp| [bp['category'], bp.dig('items','primary').to_a + bp.dig('items','additional').to_a] }; bad=[]; empty=[]; data.dig('professional_experience','jobs').to_a.each { |j| j['bullet_points'].to_a.each { |b| empty << [j['order'], b['order']] if b['skills'].to_a.empty? || b.dig('categories','matched').to_a.empty?; b['skills'].to_a.each { |s| s['matched'].to_a.each { |item| bad << [j['order'], b['order'], s['category'], item] unless inv.fetch(s['category'], []).include?(item) } } } }; puts \"empty matches=#{empty.size}\"; puts \"invalid matched skills=#{bad.size}\"; exit 1 unless empty.empty? && bad.empty?"
```

## Handoff

When done, report:

- Source text path used.
- Target YAML path updated.
- Whether Core Technical Skills were changed.
- Number of professional-experience bullets checked.
- Validation commands run and their result.

Leave search planning and tailored artifact generation for the next workflow phase.
