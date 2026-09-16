"""Async professor discovery using OpenAlex and Semantic Scholar."""

import asyncio
import logging
import os
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict


OPENALEX_WORKS_URL = "https://api.openalex.org/works"
SEMANTIC_SCHOLAR_PAPERS_URL = (
    "https://api.semanticscholar.org/graph/v1/paper/search"
)
CONTACT_EMAIL = os.getenv(
    "PROFESSOR_OUTREACH_CONTACT_EMAIL",
    "contact@example.com",
)
USER_AGENT = f"ProfessorOutreachAgent/1.0 (mailto:{CONTACT_EMAIL})"
logger = logging.getLogger(__name__)


class ProfessorCandidate(BaseModel):
    """A professor candidate returned by an academic search provider."""

    model_config = ConfigDict(extra="ignore")

    name: str
    institution: str = "Unknown"
    recent_paper: str
    source: str
    author_id: str | None = None


def _semantic_scholar_candidates(
    paper: dict[str, Any],
) -> list[ProfessorCandidate]:
    title = str(paper.get("title") or "Unknown")
    candidates: list[ProfessorCandidate] = []
    for author in paper.get("authors") or []:
        if not isinstance(author, dict) or not author.get("name"):
            continue
        author_id = author.get("authorId") or author.get("author_id")
        candidates.append(
            ProfessorCandidate(
                name=str(author["name"]),
                recent_paper=title,
                source="Semantic Scholar",
                author_id=str(author_id) if author_id else None,
            )
        )
    return candidates


async def fetch_openalex_authors(
    topic: str, max_results: int = 10
) -> list[ProfessorCandidate]:
    """Fetch topic-matching authors from OpenAlex."""
    params = {
        "search": topic,
        "per_page": max_results,
        "sort": "cited_by_count:desc",
    }
    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        timeout=30.0,
    ) as client:
        response = await client.get(OPENALEX_WORKS_URL, params=params)
        response.raise_for_status()
        payload = response.json()

    candidates: list[ProfessorCandidate] = []
    for work in payload.get("results", []):
        if not isinstance(work, dict):
            continue
        title = str(work.get("title") or "Unknown")
        for authorship in work.get("authorships") or []:
            if not isinstance(authorship, dict):
                continue
            author = authorship.get("author")
            if not isinstance(author, dict) or not author.get("display_name"):
                continue
            institutions = authorship.get("institutions") or []
            institution = "Unknown"
            if isinstance(institutions, list) and institutions:
                first_institution = institutions[0]
                if isinstance(first_institution, dict):
                    institution = str(
                        first_institution.get("display_name") or "Unknown"
                    )
            author_id = author.get("id")
            candidates.append(
                ProfessorCandidate(
                    name=str(author["display_name"]),
                    institution=institution,
                    recent_paper=title,
                    source="OpenAlex",
                    author_id=str(author_id) if author_id else None,
                )
            )
    return candidates[:max_results]


async def fetch_semantic_scholar_authors(
    topic: str, max_results: int = 10
) -> list[ProfessorCandidate]:
    """Fetch topic-matching paper authors from Semantic Scholar."""
    params = {
        "query": topic,
        "limit": max_results,
        "fields": "title,authors",
    }
    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        timeout=30.0,
    ) as client:
        response = await client.get(
            SEMANTIC_SCHOLAR_PAPERS_URL,
            params=params,
        )
        if response.status_code == 429:
            logger.warning("Semantic Scholar rate limit reached for topic %r", topic)
            return []
        response.raise_for_status()
        payload = response.json()

    candidates: list[ProfessorCandidate] = []
    for paper in payload.get("data", []):
        if isinstance(paper, dict):
            candidates.extend(_semantic_scholar_candidates(paper))
    return candidates[:max_results]


async def discover_professors(topic: str) -> list[ProfessorCandidate]:
    """Fetch, merge, and deduplicate candidates from both providers."""
    results = await asyncio.gather(
        fetch_openalex_authors(topic),
        fetch_semantic_scholar_authors(topic),
        return_exceptions=True,
    )

    candidates: list[ProfessorCandidate] = []
    seen_names: set[str] = set()
    for result in results:
        if isinstance(result, Exception):
            logger.warning("Professor provider failed: %s", result)
            continue
        for candidate in result:
            normalized_name = candidate.name.casefold()
            if normalized_name not in seen_names:
                seen_names.add(normalized_name)
                candidates.append(candidate)
    return candidates