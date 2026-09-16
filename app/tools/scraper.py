"""Faculty profile and email discovery helpers."""

import logging
import os
import re
from typing import Any

import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel
from tavily import AsyncTavilyClient


logger = logging.getLogger(__name__)
EMAIL_REGEX = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)
_PLACEHOLDER_DOMAINS = {
    "example.com",
    "example.net",
    "example.org",
    "localhost",
    "test.com",
}
_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".svg", ".gif")


class FacultyInfo(BaseModel):
    """Faculty contact and profile information."""

    professor_name: str
    institution: str
    faculty_url: str | None = None
    email: str | None = None
    source: str = "Tavily + Scraper"


def extract_email_from_html(html_text: str) -> str | None:
    """Extract the first non-placeholder, non-image email from HTML."""
    soup = BeautifulSoup(html_text, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()

    for email in re.findall(EMAIL_REGEX, soup.get_text(" ", strip=True)):
        normalized_email = email.lower()
        local_part, domain = normalized_email.rsplit("@", 1)
        if (
            domain in _PLACEHOLDER_DOMAINS
            or domain.endswith(".localhost")
            or local_part.endswith(_IMAGE_SUFFIXES)
        ):
            continue
        return email
    return None


def _snippet_email(results: list[dict[str, Any]]) -> str | None:
    for result in results:
        snippet = result.get("content") or result.get("snippet") or ""
        match = re.search(EMAIL_REGEX, str(snippet))
        if match:
            email = match.group(0)
            domain = email.rsplit("@", 1)[1].lower()
            if domain not in _PLACEHOLDER_DOMAINS:
                return email
    return None


async def find_faculty_info(
    professor_name: str, institution: str
) -> FacultyInfo:
    """Find a faculty webpage and email, returning a safe fallback on failure."""
    fallback = FacultyInfo(
        professor_name=professor_name,
        institution=institution,
    )
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key or not api_key.strip():
        logger.warning("TAVILY_API_KEY is missing; returning faculty fallback")
        return fallback

    query = f"{professor_name} {institution} faculty profile email webpage"
    try:
        client = AsyncTavilyClient(api_key=api_key)
        response = await client.search(
            query=query,
            max_results=5,
            include_raw_content=False,
        )
    except Exception as exc:
        logger.warning("Tavily faculty search failed: %s", exc)
        return fallback

    raw_results = response.get("results", []) if isinstance(response, dict) else []
    results = [result for result in raw_results if isinstance(result, dict)]
    faculty_url = next(
        (
            str(result["url"])
            for result in results
            if result.get("url")
        ),
        None,
    )
    email = _snippet_email(results)
    if email or not faculty_url:
        return fallback.model_copy(update={"faculty_url": faculty_url, "email": email})

    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": _BROWSER_USER_AGENT},
            timeout=30.0,
            follow_redirects=True,
        ) as http_client:
            page_response = await http_client.get(faculty_url)
            page_response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Faculty webpage fetch failed for %s: %s", faculty_url, exc)
        return fallback.model_copy(update={"faculty_url": faculty_url})

    email = extract_email_from_html(page_response.text)
    return fallback.model_copy(update={"faculty_url": faculty_url, "email": email})