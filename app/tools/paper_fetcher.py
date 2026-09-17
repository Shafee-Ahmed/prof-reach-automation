"""Fetch recent papers for a professor from academic APIs."""

import logging
import re
from typing import Any

import httpx
from pydantic import BaseModel

from app.core.config import PROFESSOR_OUTREACH_CONTACT_EMAIL

SEMANTIC_SCHOLAR_AUTHOR_SEARCH_URL = (
    "https://api.semanticscholar.org/graph/v1/author/search"
)
SEMANTIC_SCHOLAR_WORKS_URL = "https://api.semanticscholar.org/graph/v1/author/{author_id}/papers"
OPENALEX_WORKS_URL = "https://api.openalex.org/works"
REQUEST_TIMEOUT = 30.0
logger = logging.getLogger(__name__)
USER_AGENT = (
    "ProfessorOutreachAgent/1.0 "
    f"(mailto:{PROFESSOR_OUTREACH_CONTACT_EMAIL})"
)


class PaperSummary(BaseModel):
    """The paper fields needed by the evaluator and later email stages."""

    title: str
    abstract: str | None = None
    publication_year: int | None = None
    url: str | None = None


_TOPIC_STOP_WORDS = {
    "about",
    "and",
    "for",
    "from",
    "into",
    "of",
    "on",
    "the",
    "using",
    "with",
}


def _year(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _semantic_paper(paper: dict[str, Any]) -> PaperSummary | None:
    title = str(paper.get("title") or "").strip()
    if not title:
        return None
    url = paper.get("url")
    return PaperSummary(
        title=title,
        abstract=paper.get("abstract") or None,
        publication_year=_year(paper.get("year")),
        url=str(url) if url else None,
    )


def _openalex_paper(work: dict[str, Any]) -> PaperSummary | None:
    title = str(work.get("title") or "").strip()
    if not title:
        return None
    primary_location = work.get("primary_location") or {}
    landing_page_url = (
        primary_location.get("landing_page_url")
        if isinstance(primary_location, dict)
        else None
    )
    abstract = None
    inverted_index = work.get("abstract_inverted_index")
    if isinstance(inverted_index, dict):
        words: list[tuple[int, str]] = []
        for word, positions in inverted_index.items():
            if isinstance(positions, list):
                words.extend(
                    (position, str(word))
                    for position in positions
                    if isinstance(position, int)
                )
        abstract = " ".join(word for _, word in sorted(words)) or None
    return PaperSummary(
        title=title,
        abstract=abstract,
        publication_year=_year(work.get("publication_year")),
        url=str(landing_page_url) if landing_page_url else None,
    )


def _sort_and_limit(papers: list[PaperSummary], limit: int) -> list[PaperSummary]:
    unique: dict[tuple[str, str | None], PaperSummary] = {}
    for paper in papers:
        unique.setdefault((paper.title.casefold(), paper.url), paper)
    return sorted(
        unique.values(),
        key=lambda paper: paper.publication_year or 0,
        reverse=True,
    )[:limit]


def _topic_tokens(topic: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", topic.casefold())
        if len(token) >= 4 and token not in _TOPIC_STOP_WORDS
    }


def _filter_by_topic(
    papers: list[PaperSummary],
    topic: str | None,
) -> list[PaperSummary]:
    """Keep papers with at least one meaningful topic term in title/abstract."""
    if not topic:
        return papers
    topic_terms = _topic_tokens(topic)
    if not topic_terms:
        return papers
    return [
        paper
        for paper in papers
        if topic_terms
        & set(re.findall(r"[a-z0-9]+", f"{paper.title} {paper.abstract or ''}".casefold()))
    ]


async def _fetch_semantic_scholar(
    client: httpx.AsyncClient,
    author_name: str,
    institution: str,
    limit: int,
) -> list[PaperSummary]:
    response = await client.get(
        SEMANTIC_SCHOLAR_AUTHOR_SEARCH_URL,
        params={"query": author_name, "limit": 5},
    )
    response.raise_for_status()
    authors = response.json().get("data", [])
    author_id = next(
        (
            author.get("authorId")
            for author in authors
            if isinstance(author, dict)
            and author.get("authorId")
            and author_name.casefold() in str(author.get("name", "")).casefold()
        ),
        None,
    )
    if not author_id:
        return []
    response = await client.get(
        SEMANTIC_SCHOLAR_WORKS_URL.format(author_id=author_id),
        params={
            "limit": max(limit, 10),
            "sort": "year:desc",
            "fields": "title,abstract,year,url,authors",
        },
    )
    response.raise_for_status()
    papers = []
    for paper in response.json().get("data", []):
        if not isinstance(paper, dict):
            continue
        authors = paper.get("authors") or []
        author_names = " ".join(
            str(author.get("name", ""))
            for author in authors
            if isinstance(author, dict)
        )
        if institution and author_names and author_name.casefold() not in author_names.casefold():
            continue
        parsed = _semantic_paper(paper)
        if parsed:
            papers.append(parsed)
    return papers


async def _fetch_openalex(
    client: httpx.AsyncClient,
    author_name: str,
    institution: str,
    limit: int,
    author_id: str | None = None,
) -> list[PaperSummary]:
    params: dict[str, Any] = {
        "per-page": max(limit, 10),
        "sort": "publication_date:desc",
    }
    if author_id and author_id.startswith("https://openalex.org/"):
        params["filter"] = f"author.id:{author_id.rsplit('/', 1)[-1]}"
    else:
        params["search"] = f"{author_name} {institution}"
    response = await client.get(
        OPENALEX_WORKS_URL,
        params=params,
    )
    response.raise_for_status()
    papers = []
    for work in response.json().get("results", []):
        if isinstance(work, dict):
            parsed = _openalex_paper(work)
            if parsed:
                papers.append(parsed)
    return papers


async def fetch_top_papers(
    author_name: str,
    institution: str,
    limit: int = 3,
    author_id: str | None = None,
    topic: str | None = None,
) -> list[PaperSummary]:
    """Fetch up to ``limit`` recent papers, returning an empty list on failure."""
    if limit <= 0 or not author_name.strip():
        return []
    headers = {"User-Agent": USER_AGENT}
    try:
        async with httpx.AsyncClient(
            headers=headers, timeout=REQUEST_TIMEOUT
        ) as client:
            try:
                papers = await _fetch_semantic_scholar(
                    client, author_name, institution, limit
                )
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                logger.warning("Semantic Scholar paper fetch failed: %s", exc)
                papers = []
            if not papers:
                try:
                    papers = await _fetch_openalex(
                        client, author_name, institution, limit, author_id
                    )
                except (httpx.HTTPError, ValueError, KeyError) as exc:
                    logger.warning("OpenAlex paper fetch failed: %s", exc)
                    return []
    except httpx.HTTPError as exc:
        logger.warning("Academic paper client failed: %s", exc)
        return []
    return _sort_and_limit(_filter_by_topic(papers, topic), limit)
