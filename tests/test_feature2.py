from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.tools.scraper import (
    FacultyInfo,
    _snippet_email,
    extract_email_from_html,
    find_faculty_info,
)


def test_extract_email_from_html_ignores_scripts_and_styles() -> None:
    html = """
    <script>hidden@example.edu</script>
    <style>.contact::after { content: "style@example.edu"; }</style>
    <p>Contact professor@university.edu for more information.</p>
    """

    assert extract_email_from_html(html) == "professor@university.edu"


@pytest.mark.parametrize(
    "html",
    [
        "<p>john.doe@example.com</p>",
        "<p>john.doe@example.org</p>",
        "<p>john.doe@example.net</p>",
        "<p>john.doe@test.com</p>",
        "<p>john.doe@localhost</p>",
        "<p>john.doe@department.localhost</p>",
        "<p>photo.png@university.edu</p>",
        "<p>photo.jpg@university.edu</p>",
        "<p>photo.jpeg@university.edu</p>",
        "<p>photo.svg@university.edu</p>",
        "<p>photo.gif@university.edu</p>",
        "<p>No email is published here.</p>",
    ],
)
def test_extract_email_from_html_filters_invalid_emails(html: str) -> None:
    assert extract_email_from_html(html) is None


def test_extract_email_from_html_skips_invalid_match_before_valid_match() -> None:
    html = "<p>image.png@university.edu, researcher@university.edu</p>"

    assert extract_email_from_html(html) == "researcher@university.edu"


def test_snippet_email_prefers_content_over_snippet() -> None:
    results = [
        {
            "content": "Reach researcher@university.edu",
            "snippet": "ignored@other.edu",
        }
    ]

    assert _snippet_email(results) == "researcher@university.edu"


def test_snippet_email_skips_placeholder_and_non_dict_values() -> None:
    results = [
        {"content": "admin@example.com"},
        {"snippet": "faculty@university.edu"},
        {"content": None},
    ]

    assert _snippet_email(results) == "faculty@university.edu"


@pytest.mark.asyncio
@pytest.mark.parametrize("api_key", [None, "", "   "])
async def test_find_faculty_info_returns_fallback_without_api_key(
    monkeypatch: pytest.MonkeyPatch, api_key: str | None
) -> None:
    if api_key is None:
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    else:
        monkeypatch.setenv("TAVILY_API_KEY", api_key)

    with patch("app.tools.scraper.AsyncTavilyClient") as tavily_client:
        result = await find_faculty_info("Ada Lovelace", "Analytical University")

    assert result == FacultyInfo(
        professor_name="Ada Lovelace",
        institution="Analytical University",
    )
    tavily_client.assert_not_called()


@pytest.mark.asyncio
async def test_find_faculty_info_returns_snippet_email_without_page_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    tavily_client = MagicMock()
    tavily_client.return_value.search = AsyncMock(
        return_value={
            "results": [
                {
                    "url": "https://university.edu/faculty/ada",
                    "content": "Email Ada at ada@university.edu",
                }
            ]
        }
    )

    with patch("app.tools.scraper.AsyncTavilyClient", tavily_client), patch(
        "app.tools.scraper.httpx.AsyncClient"
    ) as http_client:
        result = await find_faculty_info("Ada Lovelace", "Analytical University")

    assert result.email == "ada@university.edu"
    assert result.faculty_url == "https://university.edu/faculty/ada"
    http_client.assert_not_called()


@pytest.mark.asyncio
async def test_find_faculty_info_scrapes_html_when_snippet_has_no_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    tavily_client = MagicMock()
    tavily_client.return_value.search = AsyncMock(
        return_value={
            "results": [{"url": "https://university.edu/faculty/ada"}]
        }
    )

    response = httpx.Response(
        200,
        text="<p>Contact Ada at ada@university.edu</p>",
        request=httpx.Request("GET", "https://university.edu/faculty/ada"),
    )
    http_client = MagicMock()
    http_client.__aenter__ = AsyncMock(return_value=http_client)
    http_client.__aexit__ = AsyncMock(return_value=None)
    http_client.get = AsyncMock(return_value=response)

    with patch("app.tools.scraper.AsyncTavilyClient", tavily_client), patch(
        "app.tools.scraper.httpx.AsyncClient", return_value=http_client
    ):
        result = await find_faculty_info("Ada Lovelace", "Analytical University")

    assert result.email == "ada@university.edu"
    assert result.faculty_url == "https://university.edu/faculty/ada"
    http_client.get.assert_awaited_once_with("https://university.edu/faculty/ada")


@pytest.mark.asyncio
async def test_find_faculty_info_keeps_url_when_page_fetch_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    tavily_client = MagicMock()
    tavily_client.return_value.search = AsyncMock(
        return_value={"results": [{"url": "https://university.edu/faculty/ada"}]}
    )

    http_client = MagicMock()
    http_client.__aenter__ = AsyncMock(return_value=http_client)
    http_client.__aexit__ = AsyncMock(return_value=None)
    http_client.get = AsyncMock(
        side_effect=httpx.ConnectError(
            "connection failed",
            request=httpx.Request("GET", "https://university.edu/faculty/ada"),
        )
    )

    with patch("app.tools.scraper.AsyncTavilyClient", tavily_client), patch(
        "app.tools.scraper.httpx.AsyncClient", return_value=http_client
    ):
        result = await find_faculty_info("Ada Lovelace", "Analytical University")

    assert result.faculty_url == "https://university.edu/faculty/ada"
    assert result.email is None


@pytest.mark.asyncio
async def test_find_faculty_info_handles_tavily_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    tavily_client = MagicMock()
    tavily_client.return_value.search = AsyncMock(
        side_effect=RuntimeError("Tavily unavailable")
    )

    with patch("app.tools.scraper.AsyncTavilyClient", tavily_client):
        result = await find_faculty_info("Ada Lovelace", "Analytical University")

    assert result == FacultyInfo(
        professor_name="Ada Lovelace",
        institution="Analytical University",
    )