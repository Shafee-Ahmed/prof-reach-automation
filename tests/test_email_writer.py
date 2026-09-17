from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.agents.email_writer import EmailDraft, generate_email_draft
from app.agents.email_writer import _fallback_email
from app.tools.paper_fetcher import PaperSummary


@pytest.mark.asyncio
async def test_generate_email_draft_parses_gemini_response() -> None:
    response = httpx.Response(
        200,
        json={
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": (
                                    '{"subject":"Research discussion",'
                                    '"body":"Dear Professor Ada, I would value a '
                                    'conversation about your work [1].",'
                                    '"citations":[{"claim":"your work",'
                                    '"source_title":"Computing Engines",'
                                    '"source_url":"https://example.edu/paper"}]}'
                                )
                            }
                        ]
                    }
                }
            ]
        },
        request=httpx.Request("POST", "https://example.test/generateContent"),
    )
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.post = AsyncMock(return_value=response)

    with (
        patch("app.agents.email_writer.GEMINI_API_KEY", "test-key"),
        patch("app.agents.email_writer.GEMINI_MODEL", "gemini-test"),
        patch("app.agents.email_writer.httpx.AsyncClient", return_value=client),
    ):
        result = await generate_email_draft(
            "Ada Lovelace",
            "Analytical University",
            "computer science",
            [PaperSummary(title="Computing Engines")],
        )

    assert isinstance(result, EmailDraft)
    assert result.subject == "Research discussion"
    assert result.citations[0].source_title == "Computing Engines"


@pytest.mark.asyncio
async def test_generate_email_draft_uses_fallback_without_credentials() -> None:
    with patch("app.agents.email_writer.GEMINI_API_KEY", ""):
        result = await generate_email_draft(
            "Ada Lovelace",
            "Analytical University",
            "computer science",
            [],
        )

    assert "Ada Lovelace" in result.body
    assert result.citations == []


def test_fallback_email_is_concise() -> None:
    draft = _fallback_email(
        "Ada Lovelace",
        "Analytical University",
        "computer vision for medical imaging",
        [PaperSummary(title="Medical Vision")],
    )

    assert 100 <= len(draft.body.split()) <= 150
