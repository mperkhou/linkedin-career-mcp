# JOD-Target ARO Redesign Experiment

Date: 2026-06-21

Status: adopted in v3.0.0

Decision: use JOD-targeted generative rewriting from ARO source evidence as the
production resume-generation workflow.

## Hypothesis

The resume workflow should improve if it stops asking local code to pick the
best existing bullets and instead asks an LLM to generate truthful, role-specific
bullets from a bounded evidence set.

The core framing became:

> Let generative LLMs generate, not pick.

## Background: Earlier Selector Experiments

The earlier experiment branch in `~/dev/codex/linkedin-career-mcp-experiment`
tested whether a more sophisticated selector could produce better first-draft
AROs without changing the underlying bullet text.

Reference session: `019ec7db-63c5-7771-8763-3dfff10fcca4`

Reference reports:

- `~/dev/codex/linkedin-career-mcp-experiment/output/experiments/selector_v2_mro_comparison/selector_v2_mro_compare_20260615T235710Z/selector_v2_mro_comparison_report.md`
- `~/dev/codex/linkedin-career-mcp-experiment/output/experiments/selector_v3_embeddings/selector_v3_embeddings_tuned_20260616T021244Z/selector_v3_embedding_comparison_report.md`

### Selector V2

Selector V2 added deterministic bullet candidate extraction, explainable
bullet-to-JOD scoring, requirement coverage, skill diversity, ATS aliases,
existing-match counts, and coverage penalties.

The refreshed-MRO comparison processed eight jobs:

| Metric | Result |
| --- | ---: |
| Jobs processed | 8 |
| Overall ATS average | 77.8 -> 74.0 |
| Average overall delta | -3.8 |
| Job-level deltas | 0 positive, 1 unchanged, 7 negative |
| Keyword/Semantic average deltas | -8.2 / -3.1 |
| Missing terms removed/added | 0 / 14 |
| DevOps-linked selected bullets average | 0.0 -> 7.2 |

The counter-intuitive result was the important part: the selector became much
better at selecting bullets that matched its own DevOps linkage proxy, but the
actual rendered resumes got worse.

### Selector V3

Selector V3 tried to repair that by using OpenRouter embeddings
(`openai/text-embedding-3-small`), exact-term preservation, selection caps, and
threshold tuning.

The tuned V3 run still processed eight jobs and reported:

| Metric | Result |
| --- | ---: |
| V3 vs old Selector V2 overall delta average | -4.8 |
| V3 vs refreshed-MRO Selector V2 overall delta average | -1.0 |
| Exact-term selected coverage average | 0.44 |

Increasing selector complexity did not recover quality. It made the system
harder to reason about while still producing weaker final resumes.

## Current Repo Experiments

The v3.0.0 branch moved from selection to generation in stages.

Primary test job: `url-9823c4455364`

The first experimental workflow:

1. Initialized each ARO from the MRO.
2. Preserved Core Technical Skills matching.
3. Generated JOD targets with GLM 5.2 through OpenRouter.
4. Rewrote rendered prior-role experience bullets from each role's ARO source
   evidence and the JOD targets.
5. Held the current role aside for focused comparison.

Cached first workflow:

- `output/experimental_jod/url-9823c4455364-20260620T225448Z/`

Final smoke-run cache after promoting the architecture:

- `tmp/final_jod_workflow_smoke_20260621T043327Z/`

## Current-Role Evidence Experiments

The current role needed separate treatment because it carries the strongest and
most recent evidence. We tested four variants.

| Variant | Cache | Tokens | Cost | Qualitative result |
| --- | --- | ---: | ---: | --- |
| Existing selected bullets plus JOD targets | `output/oracle_bullet_trials/url-9823c4455364-20260621T011136Z/` | 5,414 | $0.0146776 | Good, but constrained by the inherited selected-bullet list. |
| All current-role evidence paragraphs plus JOD targets | `output/oracle_bullet_trials/url-9823c4455364-20260621T011136Z/` | 7,995 | $0.0198840 | Best output. Preserved the strongest metrics, including 11,000+ device evidence. |
| Prompt A target-category routing, then Prompt B selected paragraphs | `output/oracle_category_split_trials/url-9823c4455364-20260621T032128Z/` | 5,358 | $0.0104022 | Cheaper, but lost quality and specificity. |
| Enhanced Prompt A/B split from rebuilt master-resume evidence, skills, and categories | `output/oracle_v2_enhanced_split_trials/url-9823c4455364-20260621T040817Z/` | 17,597 | $0.0339568 | Better grounded than the plain split, but more expensive and still filtered out key evidence. |

The three-way comparison cache summarized the final result:

- Method 2 preserved the strongest 11,000+ device metric and read as the best
  all-around output.
- Plain split was cheapest but lost quality and specificity.
- Enhanced split improved grounding and selected paragraph-level evidence with
  skills/categories, but Prompt A still missed key evidence.

## Why Method 2 Won

Method 2 sends all relevant current-role evidence paragraphs plus the JOD targets
to GLM 5.2. It costs more than the cheapest split, but it keeps the model's
attention on the full source record and lets the model synthesize the final
bullets directly.

The selection-style variants failed in a familiar way:

- They reduced context before generation.
- They filtered out evidence that later proved important.
- They introduced another model judgment step that could not be fully evaluated
  until after final bullets were generated.
- They made the workflow more complicated without producing better bullets.

Method 2 is simpler and better aligned with the actual task: produce truthful,
high-signal resume bullets from bounded evidence.

## Adopted Architecture

The production v3.0.0 workflow now:

1. Parses and trims the JOD.
2. Creates compact JOD targets with GLM 5.2.
3. Initializes the ARO from the MRO.
4. Runs Core Technical Skills matching for the rendered skills section.
5. Rewrites rendered professional-experience bullets from ARO evidence and JOD
   targets.
6. Stores the ARO, rendered HTML/PDF, and ATS values in the tracker database.

The current-role paragraph evidence now lives in:

- `profile/MP-MASTER-RESUME.txt`
- `profile/MASTER-RESUME.yml`

This keeps the production workflow independent of `tmp/master-paragraphs.md`.

## Guardrails

- Do not rewrite source evidence creatively inside the master resume.
- Do not inflate Core Technical Skills unless source evidence directly supports
  the skill.
- Preserve exact metrics and outcomes from the source evidence.
- Ignore unsupported JOD targets instead of inventing coverage.
- Treat future selection experiments as opt-in research, not production
  fallbacks.

## Conclusion

Both experiment lines reached the same conclusion. The more we tried to make the
system pick the right source material, the more the workflow optimized proxy
signals instead of final resume quality. The adopted v3.0.0 design keeps source
evidence bounded and truthful, then lets the LLM do the generative work it is
actually good at.

