"""LLM-based paper summarization and relevance evaluation."""

import json
import logging
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import GEMINI_API_KEY, GEMINI_API_URL, GEMINI_MODEL
from app.tools.discovery import ProfessorCandidate
from app.tools.paper_fetcher import PaperSummary, fetch_top_papers

logger = logging.getLogger(__name__)


class CandidateEvaluation(BaseModel):
    """A candidate's recent work and its relevance to a student's interests."""

    candidate_name: str
    top_papers: list[PaperSummary]
    summary: str
    relevance_score: float
    rationale: str


def _fallback(candidate: ProfessorCandidate, papers: list[PaperSummary]) -> CandidateEvaluation:
    summary = (
        f"{candidate.name} has {len(papers)} recent paper(s) available for review."
        if papers
        else f"No recent papers were found for {candidate.name}."
    )
    return CandidateEvaluation(
        candidate_name=candidate.name,
        top_papers=papers,
        summary=summary,
        relevance_score=0.0,
        rationale="An LLM evaluation could not be completed.",
    )


def _prompt(
    candidate: ProfessorCandidate,
    interests: str,
    papers: list[PaperSummary],
) -> str:
    paper_data = json.dumps([paper.model_dump() for paper in papers], ensure_ascii=True)
    return (
        "Evaluate a professor's recent papers against a student's research interests. "
        "Return only valid JSON with keys: summary, relevance_score, rationale. "
        "relevance_score must be a number from 0.0 to 10.0. "
        f"Candidate: {candidate.name}; institution: {candidate.institution}. "
        f"Student interests: {interests}. Papers: {paper_data}"
    )


async def _request_evaluation(
    candidate: ProfessorCandidate,
    interests: str,
    papers: list[PaperSummary],
) -> dict[str, Any]:
    if not GEMINI_API_KEY or not GEMINI_MODEL:
        raise RuntimeError("GEMINI_API_KEY or GEMINI_MODEL is not configured")
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": _prompt(candidate, interests, papers)},
                ],
            },
        ],
        "generationConfig": {
            "temperature": 0,
            "maxOutputTokens": 700,
            "responseMimeType": "application/json",
        },
    }
    url = f"{GEMINI_API_URL}/{GEMINI_MODEL}:generateContent"
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            url,
            params={"key": GEMINI_API_KEY},
            headers={"content-type": "application/json"},
            json=payload,
        )
        response.raise_for_status()
        content = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        if not isinstance(content, str):
            raise TypeError("Gemini returned a non-text message")
    return json.loads(content)


async def evaluate_candidate(
    candidate: ProfessorCandidate,
    student_interests: str,
) -> CandidateEvaluation:
    """Fetch papers and evaluate their relevance, with a safe fallback."""
    papers = await fetch_top_papers(
        candidate.name,
        candidate.institution,
        limit=3,
        author_id=candidate.author_id,
        topic=student_interests,
    )
    try:
        result = await _request_evaluation(candidate, student_interests, papers)
        score = max(0.0, min(10.0, float(result["relevance_score"])))
        return CandidateEvaluation(
            candidate_name=candidate.name,
            top_papers=papers,
            summary=str(result["summary"]),
            relevance_score=score,
            rationale=str(result["rationale"]),
        )
    except (
        httpx.HTTPError,
        KeyError,
        TypeError,
        ValueError,
        RuntimeError,
        json.JSONDecodeError,
        ValidationError,
    ) as exc:
        logger.warning("Candidate evaluation failed for %s: %s", candidate.name, exc)
        return _fallback(candidate, papers)
