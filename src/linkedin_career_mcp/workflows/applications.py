from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ApplicationWorkflowStage = Literal[
    "not_started",
    "draft_ready",
    "awaiting_user_review",
    "approved_for_submission",
    "submitted",
]


@dataclass(frozen=True)
class ApplicationWorkflowPolicy:
    require_user_approval_before_submit: bool = True
    record_audit_events: bool = True


DEFAULT_APPLICATION_POLICY = ApplicationWorkflowPolicy()
