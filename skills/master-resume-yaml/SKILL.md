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

- Every renderable top-level section has an explicit `render: true` unless the section
  should be hidden in a generated ARO.
- `header_top.line_1_name_header_text` is the name, `header_top.line_2_header_text`
  is an optional empty-by-default headline line, and
  `header_top.line_3_applicant_info_text` is the fallback contact line. Preserve
  `contact_items`/`links` for structured rendering; the HTML renderer hides line 2
  when it is empty.
- `core_technical_skills.bullet_points[*].items.primary` contains the always-rendered skills.
- `core_technical_skills.bullet_points[*].items.additional` contains factual optional skills that may be selected later.
- Every core skill bucket in the master YAML has `jod_matched_items: []`.
- Job-specific ARO copies may fill `jod_matched_items` with matching `primary` and
  `additional` skills so local code can score professional-experience bullets.
- Do not add static `rendered_text` for core skills; the renderer computes visible rows from
  `items.primary` plus valid matched `items.additional` entries, avoiding duplicate primary
  skills.
- Every `professional_experience.jobs[*]` has `render`, `min_bullet_points`, and `max_bullet_points`.
- Every job bullet has `text`, `bullet_point_total_match_count`, `render`, `categories`, and `skills`.
- Initialize `bullet_point_total_match_count: 0` until a JOD-specific matching pass calculates a real value.

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
  jod_match_count: 0
```

Rules:

- Every `skills[*].category` must also appear in `categories.matched`.
- Every matched skill must exist in that category's `items.primary` or `items.additional`.
- Every `skills[*]` entry must include `jod_match_count: 0` until a JOD-specific matching pass calculates a real value.
- Every bullet must include `bullet_point_total_match_count: 0` until a JOD-specific matching pass calculates a real value.
- Prefer exact factual matches from the bullet text.
- Use broader skills only when the bullet clearly supports them.
- Do not invent technologies or responsibilities to make matches look stronger.
- If a useful skill is missing from Core Technical Skills, add it to the appropriate `items.additional` bucket first, then match bullets to it.
- Preserve slash-delimited compound phrases from the source text when they are
  meaningful resume skills or workflow labels. Do not split terms such as
  `Jenkins/CloudLab CI/CD release paths`, `dynamic Ansible/AWX inventory
  management`, or `Prometheus/Grafana` during matching; add the exact compound
  phrase to `items.additional` when it carries distinct signal, and also link
  the bullet to supported component skills such as `Jenkins`, `CloudLab CI/CD
  Pipelines`, `Ansible`, or `AWX`.
- Keep bullet text stable unless the user explicitly asks for wording changes.

### 5. Iterate In Passes

This work is expected to happen across a few review loops:

1. Bare YAML extraction from the master text.
2. Core Technical Skills normalization and enrichment.
3. Experience-bullet category matching.
4. Per-bullet skill matching.
5. Human review and small correction passes.

After each major pass, summarize what changed and call out ambiguous mappings rather than hiding them.

### 6. Hand Off To The ARO Pass

After a trimmed JOD exists for a specific job, use
`scripts/application_resume_pass_one.py` or the Application Resume Object helpers in
`src/linkedin_career_mcp/application_resume.py` instead of editing the master YAML directly:

1. Initialize an ARO as a reset hard copy of `profile/MASTER-RESUME.yml`.
2. Build a compact Core Technical Skills prompt from the ARO plus the trimmed JOD.
3. Apply the returned `jod_matched_items` to the ARO.
4. Let local code calculate `skills[*].jod_match_count` and
   `bullet_point_total_match_count` across all professional-experience bullets.
5. Pass the scored ARO through `scripts/application_resume_select_bullets.py` to set
   first-draft `render` flags by descending positive score buckets without splitting ties.
6. Store the first-draft ARO, rendered HTML, generated PDF, and ATS score for the job row
   with `scripts/application_resume_store_first_draft.py`.

Keep the master YAML neutral: empty `jod_matched_items`, zero count fields, and no
job-specific pruning.

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
ruby -ryaml -e "data=YAML.load_file('profile/MASTER-RESUME.yml'); inv=data.dig('core_technical_skills','bullet_points').to_h { |bp| [bp['category'], bp.dig('items','primary').to_a + bp.dig('items','additional').to_a] }; bad=[]; empty=[]; missing_counts=[]; data.dig('professional_experience','jobs').to_a.each { |j| j['bullet_points'].to_a.each { |b| empty << [j['order'], b['order']] if b['skills'].to_a.empty? || b.dig('categories','matched').to_a.empty?; missing_counts << [j['order'], b['order'], 'bullet_point_total_match_count'] unless b.key?('bullet_point_total_match_count'); b['skills'].to_a.each { |s| missing_counts << [j['order'], b['order'], s['category'], 'jod_match_count'] unless s.key?('jod_match_count'); s['matched'].to_a.each { |item| bad << [j['order'], b['order'], s['category'], item] unless inv.fetch(s['category'], []).include?(item) } } } }; puts \"empty matches=#{empty.size}\"; puts \"invalid matched skills=#{bad.size}\"; puts \"missing count fields=#{missing_counts.size}\"; exit 1 unless empty.empty? && bad.empty? && missing_counts.empty?"
```

## Handoff

When done, report:

- Source text path used.
- Target YAML path updated.
- Whether Core Technical Skills were changed.
- Number of professional-experience bullets checked.
- Whether `jod_match_count` and `bullet_point_total_match_count` placeholders were initialized or updated.
- Validation commands run and their result.

Leave search planning and tailored artifact generation for the next workflow phase.
