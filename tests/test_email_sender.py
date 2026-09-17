from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.core.approval_queue import ApprovedCandidate, ApprovalStatus, CitationTag
from app.db.database import list_candidates
from app.tools.email_sender import DeliveryStatus, send_approved_email


def _candidate(status: ApprovalStatus = ApprovalStatus.APPROVED) -> ApprovedCandidate:
    return ApprovedCandidate(
        candidate_id="candidate-1",
        candidate_metadata={"email": "professor@university.edu"},
        final_subject="Research discussion",
        final_body="Dear Professor, I would value a conversation.",
        citations=[
            CitationTag(
                claim="A claim",
                source_title="A paper",
                source_url="https://university.edu/paper",
            )
        ],
        status=status,
    )


@pytest.mark.asyncio
async def test_test_mode_simulates_approved_email(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr("app.db.database.DATABASE_PATH", tmp_path / "simulated.db")
    with patch("app.tools.email_sender.EMAIL_SEND_MODE", "test"):
        result = await send_approved_email(_candidate())

    assert result.status is DeliveryStatus.SIMULATED
    assert result.recipient == "professor@university.edu"
    assert list_candidates()[0].status == "simulated"


@pytest.mark.asyncio
async def test_live_mode_sends_through_resend(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr("app.db.database.DATABASE_PATH", tmp_path / "live.db")
    response = httpx.Response(
        200,
        json={"id": "resend-message-1"},
        request=httpx.Request("POST", "https://api.resend.com/emails"),
    )
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.post = AsyncMock(return_value=response)

    with (
        patch("app.tools.email_sender.EMAIL_SEND_MODE", "live"),
        patch("app.tools.email_sender.RESEND_API_KEY", "test-key"),
        patch("app.tools.email_sender.RESEND_FROM_EMAIL", "me@mydomain.com"),
        patch("app.tools.email_sender.httpx.AsyncClient", return_value=client),
    ):
        result = await send_approved_email(_candidate(ApprovalStatus.EDITED))

    assert result.status is DeliveryStatus.SENT
    assert result.provider_id == "resend-message-1"
    assert client.post.await_args.kwargs["json"]["to"] == ["professor@university.edu"]
    assert list_candidates()[0].provider_id == "resend-message-1"


@pytest.mark.asyncio
async def test_unapproved_candidate_cannot_be_sent() -> None:
    with pytest.raises(ValueError, match="Only approved"):
        await send_approved_email(_candidate(ApprovalStatus.PENDING))
