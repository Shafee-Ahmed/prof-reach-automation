"""Safe delivery of approved outreach emails through Resend."""

import logging
import re
from enum import StrEnum
from typing import Any

import httpx
from pydantic import BaseModel

from app.core.approval_queue import ApprovedCandidate, ApprovalStatus
from app.core.config import (
    EMAIL_SEND_MODE,
    RESEND_API_KEY,
    RESEND_API_URL,
    RESEND_FROM_EMAIL,
)
from app.db.database import record_delivery, save_candidate

logger = logging.getLogger(__name__)


class DeliveryStatus(StrEnum):
    """Email delivery outcome."""

    SIMULATED = "simulated"
    SENT = "sent"


class SentEmailResult(BaseModel):
    """Result returned by the email delivery tool."""

    candidate_id: str
    recipient: str
    status: DeliveryStatus
    provider_id: str | None = None


_EMAIL_PATTERN = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)


def _recipient(candidate: ApprovedCandidate) -> str:
    email = candidate.candidate_metadata.get("email")
    if not isinstance(email, str) or not _EMAIL_PATTERN.fullmatch(email.strip()):
        raise ValueError("Approved candidate has no valid recipient email")
    return email.strip()


async def send_approved_email(
    candidate: ApprovedCandidate,
) -> SentEmailResult:
    """Send an approved email, or simulate delivery in test mode."""
    if candidate.status not in {ApprovalStatus.APPROVED, ApprovalStatus.EDITED}:
        raise ValueError("Only approved or edited candidates can be sent")

    recipient = _recipient(candidate)
    save_candidate(
        {
            **candidate.candidate_metadata,
            "candidate_id": candidate.candidate_id,
            "status": candidate.status.value,
            "email": recipient,
            "email_draft": {
                "subject": candidate.final_subject,
                "body": candidate.final_body,
                "citations": [citation.model_dump() for citation in candidate.citations],
            },
        }
    )
    if EMAIL_SEND_MODE != "live":
        logger.info(
            "Email delivery simulated for candidate %s to %s",
            candidate.candidate_id,
            recipient,
        )
        result = SentEmailResult(
            candidate_id=candidate.candidate_id,
            recipient=recipient,
            status=DeliveryStatus.SIMULATED,
        )
        record_delivery(candidate.candidate_id, result.status.value)
        return result

    if not RESEND_API_KEY or not RESEND_FROM_EMAIL:
        raise RuntimeError(
            "RESEND_API_KEY and RESEND_FROM_EMAIL are required in live mode"
        )

    payload: dict[str, Any] = {
        "from": RESEND_FROM_EMAIL,
        "to": [recipient],
        "subject": candidate.final_subject,
        "text": candidate.final_body,
    }
    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "content-type": "application/json",
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            RESEND_API_URL,
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        response_data = response.json()

    provider_id = response_data.get("id")
    if not isinstance(provider_id, str) or not provider_id:
        raise ValueError("Resend response did not include an email id")
    result = SentEmailResult(
        candidate_id=candidate.candidate_id,
        recipient=recipient,
        status=DeliveryStatus.SENT,
        provider_id=provider_id,
    )
    record_delivery(
        candidate.candidate_id,
        result.status.value,
        provider_id=result.provider_id,
    )
    return result
