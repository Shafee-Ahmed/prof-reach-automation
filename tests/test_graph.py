from unittest.mock import AsyncMock, patch

import pytest

from app.graph import compile_graph
from app.agents.email_writer import CitationTag, EmailDraft
from app.agents.paper_evaluator import CandidateEvaluation
from app.tools.paper_fetcher import PaperSummary
from app.tools.discovery import ProfessorCandidate
from app.tools.scraper import FacultyInfo


def _candidate(name: str) -> ProfessorCandidate:
    return ProfessorCandidate(
        name=name,
        institution="Analytical University",
        recent_paper="Computing Engines",
        source="OpenAlex",
    )


@pytest.mark.asyncio
async def test_graph_queues_high_relevance_and_skips_low_relevance() -> None:
    candidates = [_candidate("Ada Lovelace"), _candidate("Grace Hopper")]
    faculty = FacultyInfo(
        professor_name="Ada Lovelace",
        institution="Analytical University",
        faculty_url="https://university.edu/ada",
        email="ada@university.edu",
    )
    second_faculty = faculty.model_copy(
        update={"professor_name": "Grace Hopper", "email": "grace@university.edu"}
    )

    async def faculty_lookup(name: str, _: str) -> FacultyInfo:
        return faculty if name == "Ada Lovelace" else second_faculty

    evaluations = iter(
        [
            CandidateEvaluation(
                candidate_name="Ada Lovelace",
                top_papers=[PaperSummary(title="Medical Vision")],
                relevance_score=8.0,
                summary="Strong match",
                rationale="Aligned",
            ),
            CandidateEvaluation(
                candidate_name="Grace Hopper",
                top_papers=[],
                relevance_score=4.0,
                summary="Weak match",
                rationale="Not aligned",
            ),
        ]
    )
    email_draft = EmailDraft(
        subject="Research discussion",
        body="I would value discussing your research.",
        citations=[
            CitationTag(
                claim="Your research is relevant.",
                source_title="Medical Vision",
                source_url="https://university.edu/paper",
            )
        ],
    )

    with (
        patch("app.graph.workflow.discover_professors", AsyncMock(return_value=candidates)),
        patch("app.graph.workflow.find_faculty_info", side_effect=faculty_lookup),
        patch("app.graph.workflow.evaluate_candidate", side_effect=evaluations),
        patch(
            "app.graph.workflow.generate_email_draft",
            AsyncMock(return_value=email_draft),
        ) as generate_email,
    ):
        result = await compile_graph().ainvoke({"topic": "computer vision"})

    assert result["status"] == "pending"
    assert [item["status"] for item in result["results"]] == ["pending", "skipped"]
    assert result["results"][0]["email"] == "ada@university.edu"
    assert result["results"][1]["email"] == "grace@university.edu"
    assert result["results"][0]["email_draft"] == email_draft.model_dump()
    assert result["results"][1]["email_draft"] is None
    generate_email.assert_awaited_once_with(
        candidate_name="Ada Lovelace",
        institution="Analytical University",
        student_interests="computer vision",
        top_papers=[PaperSummary(title="Medical Vision")],
    )


@pytest.mark.asyncio
async def test_graph_skips_when_discovery_returns_no_candidates() -> None:
    with patch("app.graph.workflow.discover_professors", AsyncMock(return_value=[])):
        result = await compile_graph().ainvoke({"topic": "unknown topic"})

    assert result["status"] == "skipped"
    assert result["results"] == []
