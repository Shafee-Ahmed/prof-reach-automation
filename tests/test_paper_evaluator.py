from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.agents.paper_evaluator import _request_evaluation
from app.tools.discovery import ProfessorCandidate
from app.tools.paper_fetcher import PaperSummary


@pytest.mark.asyncio
async def test_request_evaluation_uses_openai_chat_completions() -> None:
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
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"summary":"Relevant work","relevance_score":8,'
                            '"rationale":"The topic aligns."}'
                        )
                    }
                }
            ]
        },
        request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
    )
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.post = AsyncMock(return_value=response)

    with (
        patch("app.agents.paper_evaluator.OPENAI_API_KEY", "test-key"),
        patch("app.agents.paper_evaluator.OPENAI_MODEL", "gpt-4o-mini"),
        patch("app.agents.paper_evaluator.httpx.AsyncClient", return_value=client),
    ):
        result = await _request_evaluation(candidate, "computer science", papers)

    assert result["relevance_score"] == 8
    headers = client.post.await_args.kwargs["headers"]
    payload = client.post.await_args.kwargs["json"]
    assert headers["Authorization"] == "Bearer test-key"
    assert payload["model"] == "gpt-4o-mini"
    assert payload["response_format"] == {"type": "json_object"}
