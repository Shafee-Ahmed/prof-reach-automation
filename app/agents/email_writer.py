"""Personalized, citation-backed outreach email generation."""

import json
import logging
from typing import Any

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.core.config import GEMINI_API_KEY, GEMINI_API_URL, GEMINI_MODEL
from app.core.prompts import email_writer_prompt
from app.tools.paper_fetcher import PaperSummary

logger = logging.getLogger(__name__)


class CitationTag(BaseModel):
    """A source attached to a research claim in an email body."""

    claim: str
    source_title: str
    source_url: str | None = None


class EmailDraft(BaseModel):
    """A personalized email and the sources supporting its claims."""

    subject: str
    body: str
    citations: list[CitationTag] = Field(default_factory=list)


def _fallback_email(
    candidate_name: str,
    institution: str,
    student_interests: str,
    papers: list[PaperSummary],
) -> EmailDraft:
    citations = [
        CitationTag(
            claim=f"I read your paper, {paper.title}.",
            source_title=paper.title,
            source_url=paper.url,
        )
        for paper in papers[:1]
    ]
    citation_marker = " [1]" if citations else ""
    body = (
        f"Dear Professor {candidate_name},\n\n"
        f"I am a prospective graduate student interested in {student_interests}. "
        f"I am reaching out because I would value learning more about research "
        f"opportunities in your group at {institution}. "
        + (
            f"I recently read your work, “{papers[0].title},” and would appreciate "
            f"the opportunity to understand how its research direction relates to "
            f"my interests{citation_marker}."
            if papers
            else "I would appreciate the opportunity to learn whether your group "
            "has research directions related to my interests."
        )
        + " I can share my CV and a brief research summary if helpful. "
        "I would be glad to prepare any additional information that would help "
        "you assess whether my background could fit your group. "
        "Would you be open to a short conversation about possible supervision "
        "or research opportunities? Thank you for your time and consideration.\n\n"
        "Best regards,\nProspective graduate student"
    )
    return EmailDraft(
        subject=f"Prospective graduate student interested in {student_interests}",
        body=body,
        citations=citations,
    )


def _gemini_payload(
    candidate_name: str,
    institution: str,
    student_interests: str,
    papers: list[PaperSummary],
) -> dict[str, Any]:
    return {
        "contents": [
            {
                "parts": [
                    {
                        "text": email_writer_prompt(
                            candidate_name,
                            institution,
                            student_interests,
                            papers,
                        )
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 900,
            "responseMimeType": "application/json",
        },
    }


async def generate_email_draft(
    candidate_name: str,
    institution: str,
    student_interests: str,
    top_papers: list[PaperSummary],
) -> EmailDraft:
    """Generate a citation-backed email, with a safe local fallback."""
    fallback = _fallback_email(
        candidate_name,
        institution,
        student_interests,
        top_papers,
    )
    if not GEMINI_API_KEY or not GEMINI_MODEL:
        logger.warning("Gemini credentials are missing; using email fallback")
        return fallback

    try:
        response_payload = _gemini_payload(
            candidate_name,
            institution,
            student_interests,
            top_papers,
        )
        url = f"{GEMINI_API_URL}/{GEMINI_MODEL}:generateContent"
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                url,
                params={"key": GEMINI_API_KEY},
                headers={"content-type": "application/json"},
                json=response_payload,
            )
            response.raise_for_status()
            content = response.json()["candidates"][0]["content"]["parts"][0]["text"]
            if not isinstance(content, str):
                raise TypeError("Gemini returned a non-text email draft")
        return EmailDraft.model_validate(json.loads(content))
    except (
        httpx.HTTPError,
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        ValidationError,
    ) as exc:
        logger.warning(
            "Personalized email generation failed for %s: %s",
            candidate_name,
            exc,
        )
        return fallback
