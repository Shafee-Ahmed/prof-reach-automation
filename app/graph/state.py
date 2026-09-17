"""State definitions and validation helpers for the outreach graph."""

from typing import Any, TypedDict

from app.tools.discovery import ProfessorCandidate


class AgentState(TypedDict, total=False):
    """State passed between outreach workflow nodes."""

    topic: str
    include_countries: list[str]
    exclude_countries: list[str]
    professors: list[dict[str, Any]]
    current_professor: dict[str, Any]
    current_index: int
    papers: list[dict[str, Any]]
    relevance_score: float
    email_draft: dict[str, Any] | None
    citations: list[dict[str, Any]]
    quality_checks: dict[str, Any]
    status: str
    results: list[dict[str, Any]]
    error: str


def candidate_from_state(professor: dict[str, Any]) -> ProfessorCandidate:
    """Validate a serialized professor candidate from graph state."""
    return ProfessorCandidate.model_validate(professor)
