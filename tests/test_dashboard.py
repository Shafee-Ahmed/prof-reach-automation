from pathlib import Path

import pytest

from app.db.database import OutreachRecord
from app.ui.dashboard import history_rows, records_to_rows


def test_records_to_rows_contains_review_and_delivery_fields() -> None:
    rows = records_to_rows(
        [
            OutreachRecord(
                candidate_id="candidate-1",
                name="Ada Lovelace",
                institution="Analytical University",
                email="ada@university.edu",
                relevance_score=8.5,
                status="pending",
                updated_at="2026-09-18T00:00:00+00:00",
            )
        ]
    )

    assert rows == [
        [
            "candidate-1",
            "Ada Lovelace",
            "Analytical University",
            "ada@university.edu",
            8.5,
            "pending",
            "2026-09-18T00:00:00+00:00",
        ]
    ]


def test_history_rows_filters_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app.db.database import save_candidate

    database = tmp_path / "dashboard.db"
    monkeypatch.setattr("app.db.database.DATABASE_PATH", database)
    save_candidate(
        OutreachRecord(
            candidate_id="pending-1",
            name="Ada Lovelace",
            institution="Analytical University",
            status="pending",
        )
    )
    save_candidate(
        OutreachRecord(
            candidate_id="sent-1",
            name="Grace Hopper",
            institution="Analytical University",
            status="sent",
        )
    )

    assert history_rows("sent")[0][0] == "sent-1"
