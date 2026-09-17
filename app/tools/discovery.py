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
    country: str | None = None


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
    topic: str, max_results: int = 30
) -> list[ProfessorCandidate]:
    params = {
        "search": topic,
        # Search a broad recent sample, then diversify by institution/country
        # below instead of returning authors from only the first few works.
        "per_page": min(max_results * 4, 100),
        "sort": "publication_date:desc",
        "filter": "from_publication_date:2021-01-01",
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
                    country = first_inst.get("country_code")
                else:
                    country = None
            else:
                country = None

            # 3. Pull author_id from the author variable above
            author_id = author.get("id")

            # 4. Instantiate ProfessorCandidate
            candidate = ProfessorCandidate(
                name=str(author["display_name"]),
                institution=institution,
                recent_paper=title,
                source="OpenAlex",
                author_id=str(author_id) if author_id else None,
                country=str(country).upper() if country else None,
            )
            candidates.append(candidate)

    return _diversify_candidates(candidates, max_results)


async def fetch_semantic_scholar_authors(
    topic: str, max_results: int = 30
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
    
    return _diversify_candidates(candidates, max_results)


def _diversify_candidates(
    candidates: list[ProfessorCandidate],
    max_results: int,
    max_per_institution: int = 2,
) -> list[ProfessorCandidate]:
    """Prefer several universities and countries over one prolific institution."""
    selected: list[ProfessorCandidate] = []
    seen_authors: set[str] = set()
    institution_counts: dict[str, int] = {}

    # First pass maximizes geographic and university coverage.
    for candidate in candidates:
        author_key = (candidate.author_id or candidate.name).casefold()
        institution_key = candidate.institution.casefold()
        if author_key in seen_authors:
            continue
        if institution_counts.get(institution_key, 0) >= max_per_institution:
            continue
        seen_authors.add(author_key)
        institution_counts[institution_key] = (
            institution_counts.get(institution_key, 0) + 1
        )
        selected.append(candidate)
        if len(selected) >= max_results:
            return selected

    # Keep the result useful when a provider returns incomplete institution data.
    for candidate in candidates:
        author_key = (candidate.author_id or candidate.name).casefold()
        if author_key not in seen_authors:
            seen_authors.add(author_key)
            selected.append(candidate)
            if len(selected) >= max_results:
                break
    return selected



async def discover_professors(
    topic: str,
    max_results: int = 30,
    include_countries: list[str] | None = None,
    exclude_countries: list[str] | None = None,
) -> list[ProfessorCandidate]:
    """Find topic experts across many universities and countries."""
    if not topic.strip():
        raise ValueError("A research topic is required")
    included = {country.strip().upper() for country in include_countries or []}
    excluded = {country.strip().upper() for country in exclude_countries or []}
    results = await asyncio.gather(
        fetch_openalex_authors(topic, max_results),
        fetch_semantic_scholar_authors(topic, max_results),
        return_exceptions=True,
    )

    candidates: list[ProfessorCandidate] = []
    seen_authors: set[str] = set()
    for result in results:
        if isinstance(result, Exception):
            logger.warning("Professor provider failed: %s", result)
            continue
        for candidate in result:
            normalized_author = (
                candidate.author_id or f"{candidate.name}|{candidate.institution}"
            ).casefold()
            if normalized_author not in seen_authors:
                seen_authors.add(normalized_author)
                candidates.append(candidate)
    candidates = [
        candidate
        for candidate in candidates
        if (not included or candidate.country in included)
        and candidate.country not in excluded
    ]
    return _diversify_candidates(candidates, max_results)
