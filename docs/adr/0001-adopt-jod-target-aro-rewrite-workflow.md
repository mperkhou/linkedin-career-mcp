# ADR 0001: Adopt JOD-Target ARO Rewrite Workflow

Status: accepted

Date: 2026-06-21

## Context

The previous ARO workflow used local scoring and selection to choose existing
master-resume bullets for each job. Follow-up experiments made that selector
more sophisticated with requirement coverage, skill diversity, ATS aliases,
embedding similarity, exact-term preservation, and tuning thresholds.

The extra selection logic did not improve the final resumes. It often improved
internal proxy signals while lowering ATS results or losing important evidence.

The new workflow needs to:

- preserve truthful source evidence
- generate role-specific bullets
- keep the Flask tracker as the manual review surface
- avoid runtime dependencies on temporary local evidence files
- remain understandable enough to debug from cached prompts and AROs

## Decision

Use JOD-targeted generative rewriting as the default production workflow.

The workflow:

1. Builds or reads a cleaned JOD.
2. Distills that JOD into compact requirement targets.
3. Deep-copies the MRO into a per-job ARO.
4. Matches Core Technical Skills only for the rendered skills section.
5. Rewrites rendered experience bullets from ARO source evidence and JOD targets.
6. Stores the resulting ARO, rendered HTML/PDF, and ATS proxy scores in SQLite.

Current-role paragraph evidence is stored in the canonical master resume files,
not in `tmp/master-paragraphs.md`.

## Consequences

Positive:

- Better final bullet quality than selector-based variants.
- Fewer proxy objectives competing with the real output.
- Easier cached prompt/response inspection.
- No production dependency on a temporary paragraph file.
- Clearer split between source evidence, generated ARO content, rendering, and
  manual review.

Tradeoffs:

- Generation costs more than the cheapest selection experiment.
- The workflow depends more directly on LLM output quality.
- Manual review remains essential because generated bullets are final prose, not
  selected source snippets.

## Alternatives Considered

### Keep Legacy Bullet Selection

Rejected. Selector V2 improved source-linkage proxies but lowered average ATS
from 77.8 to 74.0 across the eight-job refreshed-MRO comparison.

### Add Embedding-Based Selection

Rejected. Tuned Selector V3 was still down 4.8 points against old Selector V2 and
down 1.0 point against refreshed-MRO Selector V2.

### Split Current-Role Paragraph Routing Before Generation

Rejected for production. The plain split was cheaper, but lower quality. The
enhanced split was more expensive and still filtered out key evidence.

### Direct Generation From All Relevant Evidence

Accepted. This produced the strongest current-role bullets in the comparison and
became the v3.0.0 Method 2 production path.

## References

- [3.0.0 release notes](../release-notes/3.0.0.md)
- [JOD-target ARO redesign experiment](../experiments/2026-06-21-jod-target-aro-redesign.md)

