"""In-memory human review queue for generated outreach emails."""

from copy import deepcopy
from enum import StrEnum
from hashlib import sha256
from typing import Any

from pydantic import BaseModel, Field

from app.db.database import save_candidate, update_candidate_status

class ApprovalStatus(StrEnum):
    """Available reviewer decisions."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EDITED = "edited"


class CitationTag(BaseModel):
    """A source supporting a research claim in an email."""

    claim: str
    source_title: str
    source_url: str | None = None


class ApprovedCandidate(BaseModel):
    """Candidate and final email state after human review."""

    candidate_id: str
    candidate_metadata: dict[str, Any] = Field(default_factory=dict)
    final_subject: str
    final_body: str
    citations: list[CitationTag] = Field(default_factory=list)
    status: ApprovalStatus
    reviewer_notes: str | None = None


_QUEUE: dict[str, ApprovedCandidate] = {}


def _candidate_record_data(candidate: ApprovedCandidate) -> dict[str, Any]:
    """Build the database candidate shape from the review representation."""
    return {
        **deepcopy(candidate.candidate_metadata),
        "candidate_id": candidate.candidate_id,
        "status": candidate.status.value,
        "email_draft": {
            "subject": candidate.final_subject,
            "body": candidate.final_body,
            "citations": [citation.model_dump() for citation in candidate.citations],
        },
        "reviewer_notes": candidate.reviewer_notes,
    }


def _candidate_id(candidate: dict[str, Any]) -> str:
    identity = (
        str(candidate.get("author_id") or "")
        or str(candidate.get("email") or "")
        or str(candidate.get("name") or candidate.get("professor_name") or "")
    )
    if not identity:
        raise ValueError("A candidate needs author_id, email, or name")
    return sha256(identity.casefold().encode("utf-8")).hexdigest()[:16]


def _load_candidate(candidate: dict[str, Any]) -> ApprovedCandidate:
    draft = candidate.get("email_draft")
    if not isinstance(draft, dict):
        raise ValueError("Pending candidate is missing an email_draft")
    subject = draft.get("subject")
    body = draft.get("body")
    if not isinstance(subject, str) or not isinstance(body, str):
        raise ValueError("Email draft must contain string subject and body")
    citations = [
        CitationTag.model_validate(citation)
        for citation in draft.get("citations", [])
    ]
    candidate_id = str(candidate.get("candidate_id") or _candidate_id(candidate))
    metadata = {
        key: deepcopy(value)
        for key, value in candidate.items()
        if key not in {"candidate_id", "email_draft"}
    }
    return ApprovedCandidate(
        candidate_id=candidate_id,
        candidate_metadata=metadata,
        final_subject=subject,
        final_body=body,
        citations=citations,
        status=ApprovalStatus.PENDING,
    )


def get_pending_candidates(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Load and return candidates whose graph status is pending."""
    _QUEUE.clear()
    pending: list[dict[str, Any]] = []
    for result in results:
        if result.get("status") != ApprovalStatus.PENDING.value:
            continue
        candidate = _load_candidate(result)
        _QUEUE[candidate.candidate_id] = candidate
        pending.append(
            {
                **deepcopy(result),
                "candidate_id": candidate.candidate_id,
            }
        )
    return pending


def _require_pending(candidate_id: str) -> ApprovedCandidate:
    candidate = _QUEUE.get(candidate_id)
    if candidate is None:
        raise KeyError(f"Unknown approval candidate: {candidate_id}")
    if candidate.status not in {ApprovalStatus.PENDING, ApprovalStatus.EDITED}:
        raise ValueError(
            f"Candidate {candidate_id} is already {candidate.status.value}"
        )
    return candidate


def approve_candidate(
    candidate_id: str,
    edited_subject: str | None = None,
    edited_body: str | None = None,
) -> ApprovedCandidate:
    """Approve a pending candidate, optionally preserving reviewer edits."""
    candidate = _require_pending(candidate_id)
    if edited_subject is not None:
        candidate.final_subject = edited_subject
    if edited_body is not None:
        candidate.final_body = edited_body
    candidate.status = (
        ApprovalStatus.EDITED
        if edited_subject is not None or edited_body is not None
        else ApprovalStatus.APPROVED
    )
    save_candidate(_candidate_record_data(candidate))
    update_candidate_status(
        candidate.candidate_id,
        candidate.status.value,
        subject=candidate.final_subject if edited_subject is not None else None,
        body=candidate.final_body if edited_body is not None else None,
    )
    return candidate


def reject_candidate(
    candidate_id: str,
    reason: str | None = None,
) -> ApprovedCandidate:
    """Reject a pending candidate and retain the review reason."""
    candidate = _require_pending(candidate_id)
    candidate.status = ApprovalStatus.REJECTED
    candidate.reviewer_notes = reason
    save_candidate(_candidate_record_data(candidate))
    update_candidate_status(
        candidate.candidate_id,
        candidate.status.value,
        reviewer_notes=reason,
    )
    return candidate
