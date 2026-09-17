from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.agents.paper_evaluator import _request_evaluation
from app.tools.discovery import ProfessorCandidate
from app.tools.paper_fetcher import PaperSummary


@pytest.mark.asyncio
async def test_request_evaluation_uses_gemini_generate_content() -> None:
    candidate = ProfessorCandidate(
        name="Ada Lovelace",
        institution="Analytical University",
        recent_paper="Computing Engines",
        source="OpenAlex",
    )
    papers = [PaperSummary(title="Computing Engines", publication_year=1843)]
    response = httpx.Response(
        200,
        json={
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": (
                                    '{"summary":"Relevant work","relevance_score":8,'
                                    '"rationale":"The topic aligns."}'
                                )
                            }
                        ]
                    }
                }
            ]
        },
        request=httpx.Request(
            "POST",
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-2.5-flash:generateContent",
        ),
    )
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.post = AsyncMock(return_value=response)

    with (
        patch("app.agents.paper_evaluator.GEMINI_API_KEY", "test-key"),
        patch("app.agents.paper_evaluator.GEMINI_MODEL", "gemini-2.5-flash"),
        patch("app.agents.paper_evaluator.httpx.AsyncClient", return_value=client),
    ):
        result = await _request_evaluation(candidate, "computer science", papers)

    assert result["relevance_score"] == 8
    request_url = client.post.await_args.args[0]
    params = client.post.await_args.kwargs["params"]
    payload = client.post.await_args.kwargs["json"]
    assert request_url.endswith(":generateContent")
    assert params == {"key": "test-key"}
    assert payload["generationConfig"]["responseMimeType"] == "application/json"
