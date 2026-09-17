import pytest

from app.core.approval_queue import (
    ApprovalStatus,
    approve_candidate,
    get_pending_candidates,
    reject_candidate,
)


def _results() -> list[dict]:
    return [
        {
            "name": "Ada Lovelace",
            "institution": "Analytical University",
            "email": "ada@university.edu",
            "relevance_score": 8.0,
            "status": "pending",
            "papers": [{"title": "Computing Engines", "url": "https://paper.test"}],
            "email_draft": {
                "subject": "Research discussion",
                "body": "Dear Professor Lovelace, I would value a conversation [1].",
                "citations": [
                    {
                        "claim": "A research claim",
                        "source_title": "Computing Engines",
                        "source_url": "https://paper.test",
                    }
                ],
            },
        },
        {
            "name": "Grace Hopper",
            "status": "skipped",
            "email_draft": None,
        },
    ]


def test_loading_pending_candidates_from_graph_output() -> None:
    pending = get_pending_candidates(_results())

    assert len(pending) == 1
    assert pending[0]["name"] == "Ada Lovelace"
    assert pending[0]["candidate_id"]


def test_manual_edits_preserve_citation_tags() -> None:
    pending = get_pending_candidates(_results())

    approved = approve_candidate(
        pending[0]["candidate_id"],
        edited_subject="Updated subject",
        edited_body="Updated body [1].",
    )

    assert approved.status is ApprovalStatus.EDITED
    assert approved.final_subject == "Updated subject"
    assert approved.final_body == "Updated body [1]."
    assert approved.citations[0].source_title == "Computing Engines"


def test_approval_and_rejection_state_transitions() -> None:
    pending = get_pending_candidates(_results())
    approved = approve_candidate(pending[0]["candidate_id"])
    assert approved.status is ApprovalStatus.APPROVED

    get_pending_candidates(_results())
    rejected = reject_candidate(pending[0]["candidate_id"], "Not a current fit")
    assert rejected.status is ApprovalStatus.REJECTED
    assert rejected.reviewer_notes == "Not a current fit"


def test_unknown_candidate_is_rejected() -> None:
    get_pending_candidates(_results())

    with pytest.raises(KeyError):
        approve_candidate("missing")
