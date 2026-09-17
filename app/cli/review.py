"""Interactive command-line review for the human approval queue."""

from collections.abc import Callable
from typing import Any

from app.core.approval_queue import (
    ApprovedCandidate,
    approve_candidate,
    get_pending_candidates,
    reject_candidate,
)


def _display_candidate(candidate: dict[str, Any], output: Callable[[str], None]) -> None:
    output(f"\nCandidate: {candidate.get('name', candidate.get('professor_name', 'Unknown'))}")
    output(f"Institution: {candidate.get('institution', 'Unknown')}")
    output(f"Relevance score: {candidate.get('relevance_score', 0)}")
    output("Papers and citations:")
    for paper in candidate.get("papers", []):
        output(f"- {paper.get('title', 'Untitled')}: {paper.get('url') or 'no URL'}")
    draft = candidate["email_draft"]
    output(f"\nSubject: {draft['subject']}")
    output(f"Body:\n{draft['body']}")
    output("Citation tags:")
    for citation in draft.get("citations", []):
        output(
            f"- {citation['claim']} -> {citation['source_title']} "
            f"({citation.get('source_url') or 'no URL'})"
        )


def review_pending_candidates(
    results: list[dict[str, Any]],
    input_fn: Callable[[str], str] = input,
    output: Callable[[str], None] = print,
) -> list[ApprovedCandidate]:
    """Review pending graph results and return approved/edited candidates."""
    pending = get_pending_candidates(results)
    ready: list[ApprovedCandidate] = []
    for candidate in pending:
        _display_candidate(candidate, output)
        while True:
            choice = input_fn("\n(A)pprove, (E)dit, (R)eject, or (S)kip? ").strip().lower()
            if choice == "a":
                ready.append(approve_candidate(candidate["candidate_id"]))
                break
            if choice == "e":
                subject = input_fn("New subject (blank keeps current): ")
                body = input_fn("New body (blank keeps current): ")
                ready.append(
                    approve_candidate(
                        candidate["candidate_id"],
                        edited_subject=subject or None,
                        edited_body=body or None,
                    )
                )
                break
            if choice == "r":
                reason = input_fn("Rejection reason (optional): ")
                reject_candidate(candidate["candidate_id"], reason or None)
                break
            if choice == "s":
                break
            output("Please choose A, E, R, or S.")
    return ready
