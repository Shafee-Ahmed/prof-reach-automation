from pathlib import Path

import pytest

from app.db.database import (
    OutreachRecord,
    initialize_database,
    list_candidates,
    record_delivery,
    save_candidate,
    update_candidate_status,
)


def test_save_and_list_candidate(tmp_path: Path) -> None:
    database = tmp_path / "outreach.db"
    initialize_database(database)
    saved = save_candidate(
        OutreachRecord(
            candidate_id="candidate-1",
            name="Ada Lovelace",
            institution="Analytical University",
            email="ada@university.edu",
            status="pending",
            subject="Research discussion",
            body="Dear Professor Lovelace.",
            papers=[{"title": "Computing Engines"}],
            citations=[{"claim": "A claim", "source_title": "Computing Engines"}],
            quality_checks={"is_valid": True, "quality_score": 1.0},
        ),
        database,
    )

    records = list_candidates(path=database)

    assert saved.created_at is not None
    assert records[0].candidate_id == "candidate-1"
    assert records[0].papers[0]["title"] == "Computing Engines"
    assert records[0].quality_checks["is_valid"] is True


def test_update_review_and_delivery_status(tmp_path: Path) -> None:
    database = tmp_path / "outreach.db"
    save_candidate(
        OutreachRecord(
            candidate_id="candidate-2",
            name="Grace Hopper",
            institution="Analytical University",
        ),
        database,
    )

    approved = update_candidate_status(
        "candidate-2",
        "approved",
        reviewer_notes="Reviewed",
        path=database,
    )
    sent = record_delivery(
        "candidate-2",
        "sent",
        provider_id="resend-1",
        path=database,
    )

    assert approved.status == "approved"
    assert approved.reviewer_notes == "Reviewed"
    assert sent.status == "sent"
    assert sent.provider_id == "resend-1"


def test_unknown_candidate_update_fails(tmp_path: Path) -> None:
    with pytest.raises(KeyError):
        update_candidate_status("missing", "approved", path=tmp_path / "outreach.db")
