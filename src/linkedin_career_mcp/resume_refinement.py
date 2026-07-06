from __future__ import annotations

import copy
import html
import json
import re
from collections.abc import Iterable, Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from linkedin_career_mcp.application_resume import job_opening_description_target_texts
from linkedin_career_mcp.ats import AtsDiagnostics, AtsWeightedTerm
from linkedin_career_mcp.errors import WorkflowError

SECOND_PASS_RESUME_CRITIQUE_SCHEMA_VERSION = "second_pass_resume_critique.v1"
SECOND_PASS_RESUME_EVIDENCE_SCHEMA_VERSION = "second_pass_resume_evidence.v1"
EXTERNAL_RESUME_CRITIQUE_SCHEMA_VERSION = "external_resume_critique.v1"

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_METRIC_RE = re.compile(r"(?<![A-Za-z0-9])\d[\d,]*(?:\.\d+)?(?:%|\+)?(?![A-Za-z0-9])")
_WHITESPACE_RE = re.compile(r"\s+")

_SUPPORTED_FACT_ALIAS_GROUPS: tuple[tuple[str, ...], ...] = (
    ("rest api", "rest apis", "restful api", "restful apis"),
    ("ci/cd", "cicd", "continuous integration", "continuous deployment"),
    ("observability", "monitoring"),
)

_CONTROLLED_FACT_PHRASES = frozenset(
    {
        "ai",
        "audit",
        "aws",
        "azure",
        "compliance",
        "docker",
        "gpu",
        "hipaa",
        "java",
        "kafka",
        "kubernetes",
        "oracle",
        "pci",
        "python",
        "regulated",
        "soc 2",
        "terraform",
    }
)

_CONTROLLED_RESPONSIBILITY_PHRASES = frozenset(
    {
        "administered",
        "architected",
        "audited",
        "complied",
        "deployed",
        "governed",
        "implemented",
        "led",
        "managed",
        "migrated",
        "owned",
        "secured",
    }
)

_EXTERNAL_CRITIQUE_FACT_PHRASES = frozenset(
    {
        *_CONTROLLED_FACT_PHRASES,
        "authentication",
        "gpu infrastructure",
        "long term maintenance",
        "long term support",
        "lts",
        "maintenance ownership",
        "observability",
        "platform reliability",
        "rest api",
        "rest apis",
        "restful api",
        "restful apis",
        "scheduling",
    }
)

_KNOWN_ROLE_MISMATCH_TERMS = frozenset(
    {
        "long term maintenance",
        "long term support",
        "lts",
        "maintenance ownership",
    }
)

_ACTIONABLE_CRITIQUE_TERMS = frozenset(
    {
        "add",
        "address",
        "clarify",
        "could",
        "de emphasize",
        "deemphasize",
        "emphasize",
        "gap",
        "highlight",
        "include",
        "mention",
        "missing",
        "move",
        "prioritize",
        "remove",
        "replace",
        "rewrite",
        "reword",
        "should",
    }
)


class ResumeRefinementError(WorkflowError):
    """Raised when second-pass resume refinement data cannot be parsed."""


class ResumeEvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    source: Literal["mro", "aro", "jod", "ats"]
    label: str
    text: str


class ResumeCritiqueEvidencePacket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["second_pass_resume_evidence.v1"] = (
        SECOND_PASS_RESUME_EVIDENCE_SCHEMA_VERSION
    )
    jod_targets: list[ResumeEvidenceItem] = Field(default_factory=list)
    source_evidence: list[ResumeEvidenceItem] = Field(default_factory=list)
    ats_evidence: list[ResumeEvidenceItem] = Field(default_factory=list)


class ResumeCritiqueTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section: Literal[
        "professional_summary",
        "core_technical_skills",
        "professional_experience",
        "education",
        "certifications",
        "portfolio",
    ]
    field: str
    job_order: str | None = None
    bullet_order: str | None = None


class ProposedResumeChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    change_id: str
    change_type: Literal[
        "rewrite_summary",
        "rewrite_bullet",
        "reorder_skills",
        "emphasize_supported_term",
        "remove_or_deemphasize_text",
        "other",
    ]
    target: ResumeCritiqueTarget
    current_text: str
    proposed_text: str
    rationale: str
    evidence_refs: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)


class SecondPassResumeCritique(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["second_pass_resume_critique.v1"] = (
        SECOND_PASS_RESUME_CRITIQUE_SCHEMA_VERSION
    )
    proposed_changes: list[ProposedResumeChange] = Field(default_factory=list)


class UnsupportedCritiqueChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    change_id: str
    reasons: list[str]
    unknown_evidence_refs: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)


class ResumeCritiqueSupportAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_fully_supported: bool
    unsupported_changes: list[UnsupportedCritiqueChange] = Field(default_factory=list)


class ResumePatchValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str
    detail: str
    unsupported_terms: list[str] = Field(default_factory=list)


class RejectedResumePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    change_id: str
    issues: list[ResumePatchValidationIssue]


class ResumePatchValidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accepted_change_ids: list[str] = Field(default_factory=list)
    rejected_changes: list[RejectedResumePatch] = Field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.rejected_changes


class ResumePatchApplyResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    updated_resume: dict[str, Any]
    validation: ResumePatchValidationReport


class ExternalCritiqueSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suggestion_id: str
    text: str
    classification: Literal[
        "supported",
        "needs_user_evidence",
        "noisy_or_role_mismatch",
        "rejected",
    ]
    reasons: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    extracted_terms: list[str] = Field(default_factory=list)


class ExternalCritiqueClassificationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["external_resume_critique.v1"] = (
        EXTERNAL_RESUME_CRITIQUE_SCHEMA_VERSION
    )
    suggestions: list[ExternalCritiqueSuggestion] = Field(default_factory=list)

    @property
    def supported_suggestions(self) -> list[ExternalCritiqueSuggestion]:
        return [
            suggestion
            for suggestion in self.suggestions
            if suggestion.classification == "supported"
        ]


def build_second_pass_resume_critique_prompt(
    *,
    job_id: str,
    company: str,
    job_title: str,
    application_resume: Mapping[str, Any],
    master_resume: Mapping[str, Any],
    ats_diagnostics: AtsDiagnostics,
    external_critique_suggestions: Iterable[ExternalCritiqueSuggestion] | None = None,
) -> str:
    evidence_packet = build_resume_critique_evidence_packet(
        application_resume=application_resume,
        master_resume=master_resume,
        ats_diagnostics=ats_diagnostics,
    )
    payload = {
        "job": {
            "job_id": job_id,
            "company": company,
            "job_title": job_title,
        },
        "current_resume": _current_resume_payload(application_resume),
        "evidence_packet": evidence_packet.model_dump(),
    }
    supported_external_suggestions = [
        suggestion.model_dump()
        for suggestion in external_critique_suggestions or []
        if suggestion.classification == "supported"
    ]
    if supported_external_suggestions:
        payload["external_critique"] = {
            "supported_suggestions": supported_external_suggestions,
        }
    return (
        "You are a second-pass resume critique workflow. Return only valid JSON.\n"
        "Your job is to propose small, evidence-backed improvements to an existing "
        "Application Resume Object (ARO). Do not apply changes.\n\n"
        "Hard rules:\n"
        "- Every proposed change must reference evidence_refs from the payload.\n"
        "- Do not add a new skill, metric, employer, tool, domain, compliance claim, "
        "credential, or responsibility unless the evidence refs directly support it.\n"
        "- If a useful suggestion is not fully supported, keep it in proposed_changes "
        "but list the unsupported words or claims in unsupported_claims.\n"
        "- Prefer rewording, reordering, emphasis, and supported aliases over new facts.\n"
        "- Treat ATS noisy phrase evidence as diagnostic context, not resume content to add.\n\n"
        "Optional external critique suggestions, when present, have already been "
        "classified. Use only external_critique.supported_suggestions and still cite "
        "the payload evidence refs for every proposed change.\n\n"
        "Return this JSON shape:\n"
        "{\n"
        f'  "schema_version": "{SECOND_PASS_RESUME_CRITIQUE_SCHEMA_VERSION}",\n'
        '  "proposed_changes": [\n'
        "    {\n"
        '      "change_id": "change-1",\n'
        '      "change_type": "rewrite_bullet",\n'
        '      "target": {\n'
        '        "section": "professional_experience",\n'
        '        "field": "text",\n'
        '        "job_order": "1",\n'
        '        "bullet_order": "2"\n'
        "      },\n"
        '      "current_text": "Existing bullet text.",\n'
        '      "proposed_text": "Evidence-backed replacement text.",\n'
        '      "rationale": "Why this improves role alignment.",\n'
        '      "evidence_refs": ["mro:job:1:bullet:2", "jod:target:1"],\n'
        '      "unsupported_claims": []\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        "Payload:\n"
        f"{json.dumps(payload, indent=2, ensure_ascii=True)}\n"
    )


def build_resume_critique_evidence_packet(
    *,
    application_resume: Mapping[str, Any],
    master_resume: Mapping[str, Any],
    ats_diagnostics: AtsDiagnostics,
) -> ResumeCritiqueEvidencePacket:
    return ResumeCritiqueEvidencePacket(
        jod_targets=_jod_target_evidence_items(application_resume),
        source_evidence=[
            *_resume_source_evidence(master_resume, source="mro"),
            *_resume_source_evidence(application_resume, source="aro", rendered_only=True),
        ],
        ats_evidence=_ats_evidence_items(ats_diagnostics),
    )


def parse_second_pass_resume_critique_response(response_text: str) -> SecondPassResumeCritique:
    try:
        payload = json.loads(_extract_json_object(response_text))
    except json.JSONDecodeError as exc:
        raise ResumeRefinementError(f"Second-pass critique returned invalid JSON: {exc}") from exc

    payload = _normalize_second_pass_critique_payload(payload)
    try:
        return SecondPassResumeCritique.model_validate(payload)
    except ValueError as exc:
        raise ResumeRefinementError(f"Second-pass critique did not match schema: {exc}") from exc


def _normalize_second_pass_critique_payload(payload: object) -> object:
    if not isinstance(payload, dict):
        return payload
    changes = payload.get("proposed_changes")
    if not isinstance(changes, list):
        return payload
    section_aliases = {
        "summary": "professional_summary",
        "professional-summary": "professional_summary",
        "professional summary": "professional_summary",
        "skills": "core_technical_skills",
        "core skills": "core_technical_skills",
        "technical skills": "core_technical_skills",
        "core_technical_skill": "core_technical_skills",
        "experience": "professional_experience",
        "professional experience": "professional_experience",
    }
    change_type_aliases = {
        "add_skill": "emphasize_supported_term",
        "add_supported_skill": "emphasize_supported_term",
        "add_supported_alias": "emphasize_supported_term",
        "reorder_bullets": "other",
        "rewrite_skills": "reorder_skills",
    }
    for change in changes:
        if not isinstance(change, dict):
            continue
        change_type = str(change.get("change_type") or "").strip().casefold()
        if change_type in change_type_aliases:
            change["change_type"] = change_type_aliases[change_type]
        target = change.get("target")
        if not isinstance(target, dict):
            continue
        section = str(target.get("section") or "").strip().casefold().replace("_", " ")
        if section in section_aliases:
            target["section"] = section_aliases[section]
    return payload


def assess_second_pass_critique_support(
    *,
    critique: SecondPassResumeCritique,
    evidence_packet: ResumeCritiqueEvidencePacket,
) -> ResumeCritiqueSupportAssessment:
    known_refs = _known_evidence_refs(evidence_packet)
    unsupported_changes: list[UnsupportedCritiqueChange] = []
    for change in critique.proposed_changes:
        reasons: list[str] = []
        unknown_refs = [ref for ref in change.evidence_refs if ref not in known_refs]
        if not change.evidence_refs:
            reasons.append("missing_evidence_refs")
        if unknown_refs:
            reasons.append("unknown_evidence_refs")
        if change.unsupported_claims:
            reasons.append("unsupported_claims_declared")
        if reasons:
            unsupported_changes.append(
                UnsupportedCritiqueChange(
                    change_id=change.change_id,
                    reasons=reasons,
                    unknown_evidence_refs=unknown_refs,
                    unsupported_claims=change.unsupported_claims,
                )
            )
    return ResumeCritiqueSupportAssessment(
        is_fully_supported=not unsupported_changes,
        unsupported_changes=unsupported_changes,
    )


def classify_external_resume_critique(
    *,
    external_critique_text: str,
    evidence_packet: ResumeCritiqueEvidencePacket,
) -> ExternalCritiqueClassificationReport:
    source_items = [
        item
        for item in evidence_packet.source_evidence
        if item.source in {"mro", "aro"}
    ]
    role_items = [
        *evidence_packet.jod_targets,
        *evidence_packet.ats_evidence,
    ]
    source_text = _source_evidence_text(evidence_packet)
    role_text = "\n".join(item.text for item in role_items if item.text)
    source_normalized = _claim_normalized(source_text)
    role_normalized = _claim_normalized(role_text)
    suggestions: list[ExternalCritiqueSuggestion] = []

    for index, suggestion_text in enumerate(
        _split_external_critique_suggestions(external_critique_text),
        start=1,
    ):
        suggestion_id = f"external-{index}"
        extracted_terms = _external_critique_terms(suggestion_text)
        source_supported_terms = [
            term for term in extracted_terms if _claim_phrase_supported(term, source_normalized)
        ]
        role_supported_terms = [
            term for term in extracted_terms if _claim_phrase_supported(term, role_normalized)
        ]
        evidence_refs = _evidence_refs_supporting_terms(
            terms=source_supported_terms,
            evidence_items=source_items,
        )
        unsupported_terms = [
            term for term in extracted_terms if term not in source_supported_terms
        ]

        if not _looks_actionable_external_suggestion(suggestion_text):
            suggestions.append(
                ExternalCritiqueSuggestion(
                    suggestion_id=suggestion_id,
                    text=suggestion_text,
                    classification="rejected",
                    reasons=["non_actionable_external_text"],
                    extracted_terms=extracted_terms,
                )
            )
            continue

        if not extracted_terms:
            suggestions.append(
                ExternalCritiqueSuggestion(
                    suggestion_id=suggestion_id,
                    text=suggestion_text,
                    classification="rejected",
                    reasons=["no_evidence_bearing_terms"],
                )
            )
            continue

        if unsupported_terms:
            unsupported_role_terms = [
                term for term in unsupported_terms if term not in role_supported_terms
            ]
            if unsupported_role_terms or any(
                term in _KNOWN_ROLE_MISMATCH_TERMS for term in unsupported_terms
            ):
                suggestions.append(
                    ExternalCritiqueSuggestion(
                        suggestion_id=suggestion_id,
                        text=suggestion_text,
                        classification="noisy_or_role_mismatch",
                        reasons=["not_supported_by_resume_or_role_evidence"],
                        evidence_refs=evidence_refs,
                        extracted_terms=extracted_terms,
                    )
                )
            else:
                suggestions.append(
                    ExternalCritiqueSuggestion(
                        suggestion_id=suggestion_id,
                        text=suggestion_text,
                        classification="needs_user_evidence",
                        reasons=["job_relevant_but_not_supported_by_mro_or_aro"],
                        evidence_refs=evidence_refs,
                        extracted_terms=extracted_terms,
                    )
                )
            continue

        if evidence_refs:
            suggestions.append(
                ExternalCritiqueSuggestion(
                    suggestion_id=suggestion_id,
                    text=suggestion_text,
                    classification="supported",
                    reasons=["supported_by_mro_or_aro"],
                    evidence_refs=evidence_refs,
                    extracted_terms=extracted_terms,
                )
            )
        else:
            suggestions.append(
                ExternalCritiqueSuggestion(
                    suggestion_id=suggestion_id,
                    text=suggestion_text,
                    classification="rejected",
                    reasons=["no_matching_source_evidence_ref"],
                    extracted_terms=extracted_terms,
                )
            )

    return ExternalCritiqueClassificationReport(suggestions=suggestions)


def validate_second_pass_resume_patches(
    *,
    application_resume: Mapping[str, Any],
    critique: SecondPassResumeCritique,
    evidence_packet: ResumeCritiqueEvidencePacket,
) -> ResumePatchValidationReport:
    support_assessment = assess_second_pass_critique_support(
        critique=critique,
        evidence_packet=evidence_packet,
    )
    support_by_change_id = {
        change.change_id: change
        for change in support_assessment.unsupported_changes
    }
    source_evidence_text = _source_evidence_text(evidence_packet)
    accepted_change_ids: list[str] = []
    rejected_changes: list[RejectedResumePatch] = []
    seen_targets: dict[str, str] = {}

    for change in critique.proposed_changes:
        issues: list[ResumePatchValidationIssue] = []
        target_key = _target_key(change.target)
        previous_change_id = seen_targets.get(target_key)
        if previous_change_id:
            issues.append(
                ResumePatchValidationIssue(
                    reason="duplicate_target",
                    detail=(
                        f"Change targets the same resume field as {previous_change_id}; "
                        "apply one patch per target."
                    ),
                )
            )
        else:
            seen_targets[target_key] = change.change_id

        unsupported = support_by_change_id.get(change.change_id)
        if unsupported:
            issues.extend(_support_assessment_issues(unsupported))

        actual_text = _target_current_text(application_resume, change.target)
        if actual_text is None:
            issues.append(
                ResumePatchValidationIssue(
                    reason="unsupported_target",
                    detail="The target section/field cannot be located in the ARO.",
                )
            )
        elif _plain_compare(actual_text) != _plain_compare(change.current_text):
            issues.append(
                ResumePatchValidationIssue(
                    reason="current_text_mismatch",
                    detail="The patch current_text does not match the current ARO target.",
                )
            )

        unsupported_terms = _unsupported_new_factual_terms(
            current_text=change.current_text,
            proposed_text=change.proposed_text,
            source_evidence_text=source_evidence_text,
        )
        if unsupported_terms:
            issues.append(
                ResumePatchValidationIssue(
                    reason="unsupported_factual_terms",
                    detail=(
                        "The patch introduces facts that are not supported by existing "
                        "MRO/ARO evidence."
                    ),
                    unsupported_terms=unsupported_terms,
                )
            )

        if issues:
            rejected_changes.append(
                RejectedResumePatch(
                    change_id=change.change_id,
                    issues=issues,
                )
            )
        else:
            accepted_change_ids.append(change.change_id)

    return ResumePatchValidationReport(
        accepted_change_ids=accepted_change_ids,
        rejected_changes=rejected_changes,
    )


def validate_and_apply_second_pass_resume_patches(
    *,
    application_resume: Mapping[str, Any],
    critique: SecondPassResumeCritique,
    evidence_packet: ResumeCritiqueEvidencePacket,
) -> ResumePatchApplyResult:
    validation = validate_second_pass_resume_patches(
        application_resume=application_resume,
        critique=critique,
        evidence_packet=evidence_packet,
    )
    updated_resume = copy.deepcopy(dict(application_resume))
    accepted_change_ids = set(validation.accepted_change_ids)
    for change in critique.proposed_changes:
        if change.change_id in accepted_change_ids:
            _apply_resume_patch(updated_resume, change)
    return ResumePatchApplyResult(
        updated_resume=updated_resume,
        validation=validation,
    )


def _support_assessment_issues(
    unsupported: UnsupportedCritiqueChange,
) -> list[ResumePatchValidationIssue]:
    issues: list[ResumePatchValidationIssue] = []
    for reason in unsupported.reasons:
        if reason == "missing_evidence_refs":
            detail = "The patch does not cite any evidence refs."
        elif reason == "unknown_evidence_refs":
            detail = (
                "The patch cites evidence refs that are not present in the evidence "
                f"packet: {', '.join(unsupported.unknown_evidence_refs)}."
            )
        elif reason == "unsupported_claims_declared":
            detail = (
                "The critique declared unsupported claims: "
                f"{', '.join(unsupported.unsupported_claims)}."
            )
        else:
            detail = reason
        issues.append(
            ResumePatchValidationIssue(
                reason=reason,
                detail=detail,
                unsupported_terms=unsupported.unsupported_claims,
            )
        )
    return issues


def _source_evidence_text(evidence_packet: ResumeCritiqueEvidencePacket) -> str:
    return "\n".join(
        item.text
        for item in evidence_packet.source_evidence
        if item.source in {"mro", "aro"} and item.text
    )


def _split_external_critique_suggestions(external_critique_text: str) -> list[str]:
    suggestions: list[str] = []
    for raw_line in external_critique_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line = re.sub(r"^(?:[-*]|\d+[.)])\s+", "", line).strip()
        if _looks_external_critique_heading(line):
            continue
        if line:
            suggestions.append(line)

    if suggestions:
        return _dedupe(suggestions)

    text = _string(external_critique_text)
    if not text:
        return []
    return _dedupe(
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
        if sentence.strip() and not _looks_external_critique_heading(sentence.strip())
    )


def _looks_external_critique_heading(line: str) -> bool:
    normalized = _claim_normalized(line)
    return (
        line.endswith(":")
        and len(line) <= 100
        and not any(
            _claim_phrase_present(normalized, term)
            for term in _ACTIONABLE_CRITIQUE_TERMS
        )
    )


def _looks_actionable_external_suggestion(suggestion_text: str) -> bool:
    normalized = _claim_normalized(suggestion_text)
    if (
        _claim_phrase_present(normalized, "score")
        and _metric_claims(suggestion_text)
        and not any(
            _claim_phrase_present(normalized, term)
            for term in _ACTIONABLE_CRITIQUE_TERMS
        )
    ):
        return False
    return any(
        _claim_phrase_present(normalized, term)
        for term in _ACTIONABLE_CRITIQUE_TERMS
    )


def _external_critique_terms(suggestion_text: str) -> list[str]:
    normalized = _claim_normalized(suggestion_text)
    terms: list[str] = []
    terms.extend(display for display, _ in _metric_claims_with_display(suggestion_text))
    for aliases in _SUPPORTED_FACT_ALIAS_GROUPS:
        alias = _present_alias(normalized, aliases)
        if alias:
            terms.append(alias)
    for phrase in sorted(_EXTERNAL_CRITIQUE_FACT_PHRASES):
        if _claim_phrase_present(normalized, phrase):
            terms.append(_claim_normalized(phrase))
    for acronym in re.findall(r"\b[A-Z]{2,}\b", _plain_text(suggestion_text)):
        terms.append(acronym.casefold())
    return _dedupe(terms)


def _evidence_refs_supporting_terms(
    *,
    terms: Iterable[str],
    evidence_items: Iterable[ResumeEvidenceItem],
) -> list[str]:
    refs: list[str] = []
    term_list = list(terms)
    for item in evidence_items:
        normalized_text = _claim_normalized(item.text)
        if any(_claim_phrase_supported(term, normalized_text) for term in term_list):
            refs.append(item.id)
    return _dedupe(refs)


def _target_key(target: ResumeCritiqueTarget) -> str:
    return "|".join(
        [
            target.section,
            target.field,
            target.job_order or "",
            target.bullet_order or "",
        ]
    )


def _target_current_text(
    resume: Mapping[str, Any],
    target: ResumeCritiqueTarget,
) -> str | None:
    if target.section == "professional_summary":
        if target.field not in {"paragraph", "text"}:
            return None
        summary = resume.get("professional_summary")
        if not isinstance(summary, Mapping):
            return None
        return _string(summary.get(target.field))

    if target.section == "professional_experience":
        if target.field != "text":
            return None
        bullet = _find_experience_bullet(resume, target)
        if not isinstance(bullet, Mapping):
            return None
        return _string(bullet.get("text"))

    return None


def _find_experience_bullet(
    resume: Mapping[str, Any],
    target: ResumeCritiqueTarget,
) -> Mapping[str, Any] | None:
    if not target.job_order or not target.bullet_order:
        return None
    experience = resume.get("professional_experience")
    jobs = experience.get("jobs") if isinstance(experience, Mapping) else []
    if not isinstance(jobs, list):
        return None
    for job_index, job in enumerate(jobs, start=1):
        if not isinstance(job, Mapping) or not _renders(job):
            continue
        job_order = _order_value(job.get("order"), fallback=job_index)
        if job_order != target.job_order:
            continue
        bullets = job.get("bullet_points")
        if not isinstance(bullets, list):
            return None
        for bullet_index, bullet in enumerate(bullets, start=1):
            if not isinstance(bullet, Mapping) or not _renders(bullet):
                continue
            bullet_order = _order_value(bullet.get("order"), fallback=bullet_index)
            if bullet_order == target.bullet_order:
                return bullet
    return None


def _apply_resume_patch(
    resume: dict[str, Any],
    change: ProposedResumeChange,
) -> None:
    target = change.target
    if target.section == "professional_summary" and target.field in {"paragraph", "text"}:
        summary = resume.get("professional_summary")
        if isinstance(summary, dict):
            summary[target.field] = change.proposed_text
        return

    if target.section == "professional_experience" and target.field == "text":
        bullet = _find_experience_bullet(resume, target)
        if isinstance(bullet, dict):
            bullet["text"] = change.proposed_text


def _unsupported_new_factual_terms(
    *,
    current_text: str,
    proposed_text: str,
    source_evidence_text: str,
) -> list[str]:
    unsupported: list[str] = []
    current_normalized = _claim_normalized(current_text)
    proposed_normalized = _claim_normalized(proposed_text)
    source_normalized = _claim_normalized(source_evidence_text)

    current_metrics = _metric_claims(current_text)
    source_metrics = _metric_claims(source_evidence_text)
    for display, metric in _metric_claims_with_display(proposed_text):
        if metric not in current_metrics and metric not in source_metrics:
            unsupported.append(display)

    for aliases in _SUPPORTED_FACT_ALIAS_GROUPS:
        proposed_alias = _present_alias(proposed_normalized, aliases)
        if not proposed_alias:
            continue
        if _any_claim_phrase_present(current_normalized, aliases):
            continue
        if not _any_claim_phrase_present(source_normalized, aliases):
            unsupported.append(proposed_alias)

    for phrase in sorted(_CONTROLLED_FACT_PHRASES):
        if not _claim_phrase_present(proposed_normalized, phrase):
            continue
        if _claim_phrase_present(current_normalized, phrase):
            continue
        if not _claim_phrase_supported(phrase, source_normalized):
            unsupported.append(phrase)

    for phrase in sorted(_CONTROLLED_RESPONSIBILITY_PHRASES):
        if not _claim_phrase_present(proposed_normalized, phrase):
            continue
        if _claim_phrase_present(current_normalized, phrase):
            continue
        if not _claim_phrase_present(source_normalized, phrase):
            unsupported.append(phrase)

    return _dedupe(unsupported)


def _claim_phrase_supported(phrase: str, source_normalized: str) -> bool:
    if _claim_phrase_present(source_normalized, phrase):
        return True
    for aliases in _SUPPORTED_FACT_ALIAS_GROUPS:
        if phrase in aliases and _any_claim_phrase_present(source_normalized, aliases):
            return True
    return False


def _present_alias(text_normalized: str, aliases: tuple[str, ...]) -> str | None:
    for alias in aliases:
        if _claim_phrase_present(text_normalized, alias):
            return alias
    return None


def _any_claim_phrase_present(text_normalized: str, phrases: Iterable[str]) -> bool:
    return any(_claim_phrase_present(text_normalized, phrase) for phrase in phrases)


def _claim_phrase_present(text_normalized: str, phrase: str) -> bool:
    normalized_phrase = _claim_normalized(phrase)
    if not normalized_phrase:
        return False
    return (
        re.search(
            rf"(?<![a-z0-9]){re.escape(normalized_phrase)}(?![a-z0-9])",
            text_normalized,
        )
        is not None
    )


def _metric_claims(text: str) -> set[str]:
    return {metric for _, metric in _metric_claims_with_display(text)}


def _metric_claims_with_display(text: str) -> list[tuple[str, str]]:
    claims: list[tuple[str, str]] = []
    for match in _METRIC_RE.finditer(_plain_text(text)):
        display = match.group(0)
        claims.append((display, _normalize_metric(display)))
    return claims


def _normalize_metric(value: str) -> str:
    return value.casefold().replace(",", "")


def _plain_compare(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", _plain_text(value)).strip().casefold()


def _claim_normalized(value: str) -> str:
    text = _plain_text(value).casefold().replace("&", " and ")
    text = re.sub(r"[^a-z0-9+#/%]+", " ", text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def _plain_text(value: str) -> str:
    return html.unescape(_HTML_TAG_RE.sub("", str(value or "")))


def _jod_target_evidence_items(
    application_resume: Mapping[str, Any],
) -> list[ResumeEvidenceItem]:
    job_opening_description = application_resume.get("job_opening_description")
    if not isinstance(job_opening_description, Mapping):
        return []
    return [
        ResumeEvidenceItem(
            id=f"jod:target:{index}",
            source="jod",
            label=f"JOD target {index}",
            text=target,
        )
        for index, target in enumerate(
            job_opening_description_target_texts(job_opening_description),
            start=1,
        )
    ]


def _resume_source_evidence(
    resume: Mapping[str, Any],
    *,
    source: Literal["mro", "aro"],
    rendered_only: bool = False,
) -> list[ResumeEvidenceItem]:
    items: list[ResumeEvidenceItem] = []
    summary = resume.get("professional_summary")
    if isinstance(summary, Mapping):
        summary_text = _string(summary.get("paragraph") or summary.get("text"))
        if summary_text:
            items.append(
                ResumeEvidenceItem(
                    id=f"{source}:summary",
                    source=source,
                    label=f"{source.upper()} professional summary",
                    text=summary_text,
                )
            )
    items.extend(_skill_evidence_items(resume, source=source))
    items.extend(
        _experience_evidence_items(
            resume,
            source=source,
            rendered_only=rendered_only,
        )
    )
    return items


def _skill_evidence_items(
    resume: Mapping[str, Any],
    *,
    source: Literal["mro", "aro"],
) -> list[ResumeEvidenceItem]:
    core_skills = resume.get("core_technical_skills")
    buckets = core_skills.get("bullet_points") if isinstance(core_skills, Mapping) else []
    if not isinstance(buckets, list):
        return []
    items: list[ResumeEvidenceItem] = []
    for bucket in buckets:
        if not isinstance(bucket, Mapping):
            continue
        category = _string(bucket.get("category")) or "Skills"
        for skill in _skill_bucket_items(bucket):
            items.append(
                ResumeEvidenceItem(
                    id=f"{source}:skill:{_slug(category)}:{_slug(skill)}",
                    source=source,
                    label=f"{source.upper()} skill: {category}",
                    text=f"{category}: {skill}",
                )
            )
    return items


def _experience_evidence_items(
    resume: Mapping[str, Any],
    *,
    source: Literal["mro", "aro"],
    rendered_only: bool,
) -> list[ResumeEvidenceItem]:
    experience = resume.get("professional_experience")
    jobs = experience.get("jobs") if isinstance(experience, Mapping) else []
    if not isinstance(jobs, list):
        return []
    items: list[ResumeEvidenceItem] = []
    for job_index, job in enumerate(jobs, start=1):
        if not isinstance(job, Mapping):
            continue
        if rendered_only and not _renders(job):
            continue
        job_order = _order_value(job.get("order"), fallback=job_index)
        header_text = _job_header_text(job)
        if header_text:
            items.append(
                ResumeEvidenceItem(
                    id=f"{source}:job:{job_order}:header",
                    source=source,
                    label=f"{source.upper()} job {job_order} header",
                    text=header_text,
                )
            )
        raw_bullets = job.get("bullet_points")
        if not isinstance(raw_bullets, list):
            continue
        for bullet_index, bullet in enumerate(raw_bullets, start=1):
            if not isinstance(bullet, Mapping):
                continue
            if rendered_only and not _renders(bullet):
                continue
            text = _string(bullet.get("text"))
            if not text:
                continue
            bullet_order = _order_value(bullet.get("order"), fallback=bullet_index)
            items.append(
                ResumeEvidenceItem(
                    id=f"{source}:job:{job_order}:bullet:{bullet_order}",
                    source=source,
                    label=f"{source.upper()} job {job_order} bullet {bullet_order}",
                    text=text,
                )
            )
    return items


def _job_header_text(job: Mapping[str, Any]) -> str:
    parts: list[str] = []
    for key in ("line_1", "line_2"):
        line = job.get(key)
        if not isinstance(line, Mapping):
            continue
        parts.extend(
            _string(line.get(field))
            for field in (
                "company_name_text",
                "position_name_text",
                "position_dates_text",
                "position_intro_text",
            )
            if _string(line.get(field))
        )
    return " | ".join(parts)


def _ats_evidence_items(diagnostics: AtsDiagnostics) -> list[ResumeEvidenceItem]:
    score = diagnostics.component_scores
    return [
        ResumeEvidenceItem(
            id="ats:score",
            source="ats",
            label="ATS component scores",
            text=(
                f"overall={score.overall_score}, parsing={score.parsing_score}, "
                f"keyword={score.keyword_match_score}, semantic={score.semantic_match_score}, "
                f"formatting_risk={score.formatting_risk}"
            ),
        ),
        *_term_evidence_items("ats:matched", "ATS matched term", diagnostics.matched_terms),
        *_term_evidence_items(
            "ats:unmatched",
            "ATS unmatched weighted term",
            diagnostics.unmatched_weighted_terms,
        ),
        *_term_evidence_items(
            "ats:noisy",
            "ATS likely noisy phrase",
            diagnostics.likely_noisy_phrase_matches,
        ),
    ]


def _term_evidence_items(
    prefix: str,
    label: str,
    terms: Iterable[AtsWeightedTerm],
) -> list[ResumeEvidenceItem]:
    return [
        ResumeEvidenceItem(
            id=f"{prefix}:{_slug(term.term)}",
            source="ats",
            label=label,
            text=f"{term.term} (weight={term.weight:g})",
        )
        for term in terms
    ]


def _current_resume_payload(application_resume: Mapping[str, Any]) -> dict[str, object]:
    return {
        "summary": _current_summary(application_resume),
        "rendered_skills": [
            item.text
            for item in _skill_evidence_items(application_resume, source="aro")
        ],
        "rendered_experience_bullets": [
            item.model_dump()
            for item in _experience_evidence_items(
                application_resume,
                source="aro",
                rendered_only=True,
            )
        ],
    }


def _current_summary(application_resume: Mapping[str, Any]) -> str:
    summary = application_resume.get("professional_summary")
    if not isinstance(summary, Mapping):
        return ""
    return _string(summary.get("paragraph") or summary.get("text"))


def _skill_bucket_items(bucket: Mapping[str, Any]) -> list[str]:
    raw_items = bucket.get("items")
    if isinstance(raw_items, list):
        return _dedupe(_string(item) for item in raw_items)
    if not isinstance(raw_items, Mapping):
        return []
    primary = _string_list(raw_items.get("primary"))
    additional = _string_list(raw_items.get("additional"))
    matched = _string_list(bucket.get("jod_matched_items"))
    return _dedupe([*primary, *additional, *matched])


def _known_evidence_refs(evidence_packet: ResumeCritiqueEvidencePacket) -> set[str]:
    return {
        item.id
        for item in [
            *evidence_packet.jod_targets,
            *evidence_packet.source_evidence,
            *evidence_packet.ats_evidence,
        ]
    }


def _extract_json_object(response_text: str) -> str:
    text = response_text.strip()
    if text.startswith("```"):
        lines = [
            line
            for line in text.splitlines()
            if not line.strip().startswith("```")
        ]
        text = "\n".join(lines).strip()
    if text.startswith("{") and text.endswith("}"):
        return text
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ResumeRefinementError("Second-pass critique did not contain a JSON object.")
    return text[start : end + 1]


def _renders(value: Mapping[str, Any]) -> bool:
    raw = value.get("render")
    if raw is None:
        return True
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().casefold() not in {"false", "no", "0", "off"}
    return bool(raw)


def _order_value(value: Any, *, fallback: int | None = None) -> str:
    if isinstance(value, bool):
        value = None
    if value is None:
        return "" if fallback is None else str(fallback)
    if isinstance(value, int):
        return str(value)
    text = str(value).strip()
    return text or ("" if fallback is None else str(fallback))


def _string(value: Any) -> str:
    return str(value or "").strip()


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_string(item) for item in value if _string(item)]


def _dedupe(items: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        key = _slug(item)
        if key and key not in seen:
            result.append(item)
            seen.add(key)
    return result


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug or "item"
