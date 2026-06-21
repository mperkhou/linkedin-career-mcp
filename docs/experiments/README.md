# Experiment Notes

This directory records workflow experiments that influence production behavior.
It is meant to answer three future questions quickly:

- What did we try?
- What happened?
- Why did we keep or reject it?

Each experiment note should include:

- hypothesis
- input data and cache locations
- variants tested
- token and cost metrics when API calls are involved
- qualitative review notes
- final decision
- follow-up constraints or guardrails

## Index

| Date | Experiment | Decision |
| --- | --- | --- |
| 2026-06-21 | [JOD-target ARO redesign](2026-06-21-jod-target-aro-redesign.md) | Adopt direct JOD-targeted generation from ARO evidence. Reject increasingly complex bullet/paragraph selection as the production path. |

