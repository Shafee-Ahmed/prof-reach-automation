"""Async professor discovery using OpenAlex and Semantic Scholar."""

import asyncio
import logging
import os
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict

OPENALEX_WORKS_URL = "https://api.openalex.org/works"
SEMANTIC_SCHOLAR_PAPERS_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
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


def _semantic_scholar_candidates(raw_paper_json: dict) -> list[ProfessorCandidate]:
    if not isinstance(raw_paper_json, dict):
        return []

    title = raw_paper_json.get("title") or ""
    authors = raw_paper_json.get("authors") or []

    return [
        ProfessorCandidate(
            name=author["name"],
            author_id=author["authorId"],
            paper_title=title,
        )
        for author in authors
        if isinstance(author, dict) and author.get("authorId") and author.get("name")
    ]


async def fetch_openalex_authors(
    topic: str, max_results: int = 10
) -> list[ProfessorCandidate]:
    params = {
        "search": topic,
        "per_page": max_results,
        "sort": "cited_by_count:desc",  #  i will need to sort it based on recent years , todo : just keep update the prf who has worked on the topic in last 2 to 4 yrs
    }

    # Step 1: Execute non-blocking HTTP request
    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT}, timeout=30.0
    ) as client:
        response = await client.get(OPENALEX_WORKS_URL, params=params)
        response.raise_for_status()
        payload = response.json()

    candidates: list[ProfessorCandidate] = []

    # Step 2: Process returned works
    for work in payload.get("results", []):
        if not isinstance(work, dict):
            continue
        title = str(work.get("title") or "Unknown")

        # Step 3: Extract authors from each work
        for authorship in work.get("authorships") or []:
            if not isinstance(authorship, dict):
                continue

            # 1. Get the nested author dict
            author = authorship.get("author")
            if not isinstance(author, dict) or not author.get("display_name"):
                continue

            # 2. Extract institution name defensively
            institutions = authorship.get("institutions") or []
            institution = "Unknown"
            if isinstance(institutions, list) and institutions:
                first_inst = institutions[0]
                if isinstance(first_inst, dict):
                    institution = str(first_inst.get("display_name") or "Unknown")

            # 3. Pull author_id from the author variable above
            author_id = author.get("id")

            # 4. Instantiate ProfessorCandidate
            candidate = ProfessorCandidate(
                name=str(author["display_name"]),
                institution=institution,
                recent_paper=title,
                source="OpenAlex",
                author_id=str(author_id) if author_id else None,
            )
            candidates.append(candidate)

    return candidates[:max_results]


async def fetch_semantic_scholar_authors(
    topic: str, max_results: int = 10
) -> list[ProfessorCandidate]:
    params = {
        "query": topic,
        "limit": max_results,
        "fields": "title,authors",
    }
    
    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=30.0) as client:
        response = await client.get(SEMANTIC_SCHOLAR_PAPERS_URL, params=params)
        # If response.status_code == 429, log a warning and return []
        if response.status_code == 429:
            logger.warning("Semantic Scholar rate limit reached for topic: %s", topic)
            return []
        response.raise_for_status()
        payload = response.json()

    candidates: list[ProfessorCandidate] = []
    
    # For each paper dict, extend candidates using _semantic_scholar_candidates(paper)
    for paper in payload.get("data", []):
            if isinstance (paper , dict):
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
