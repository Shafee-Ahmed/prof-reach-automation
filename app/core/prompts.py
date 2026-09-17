"""Prompt templates used by outreach agent features."""

import json

from app.tools.paper_fetcher import PaperSummary


def email_writer_prompt(
    candidate_name: str,
    institution: str,
    student_interests: str,
    papers: list[PaperSummary],
) -> str:
    """Build the structured prompt for personalized email generation."""
    paper_data = json.dumps(
        [paper.model_dump() for paper in papers],
        ensure_ascii=True,
    )
    return (
        "Write a concise, respectful cold email for a prospective graduate student. "
        "Return only valid JSON with exactly these keys: subject, body, citations. "
        "The body must be 100 to 150 words, mention the professor and institution, "
        "connect the student's interests to the supplied papers, and end with a "
        "polite request to discuss possible supervision or research opportunities. "
        "Every research claim must have an inline citation marker such as [1]. "
        "The citations array must contain one object per marker with keys "
        "claim, source_title, source_url. Use only the supplied papers and never "
        "invent facts, titles, URLs, methods, results, or affiliations. "
        "If a paper has no URL, use null for source_url. "
        f"Professor: {candidate_name}; institution: {institution}; "
        f"Student interests: {student_interests}; Papers: {paper_data}"
    )
