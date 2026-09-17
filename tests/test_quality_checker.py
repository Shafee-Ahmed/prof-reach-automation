from app.agents.quality_checker import verify_candidate_quality


def _candidate() -> dict:
    return {
        "name": "Ada Lovelace",
        "institution": "Analytical University",
        "email": "ada@analytical.edu",
        "papers": [
            {
                "title": "Computing Engines",
                "url": "https://analytical.edu/papers/engines",
            }
        ],
        "email_draft": {
            "subject": "Research discussion",
            "body": "I read your work on Computing Engines [1].",
            "citations": [
                {
                    "claim": "I read your work on Computing Engines.",
                    "source_title": "Computing Engines",
                    "source_url": "https://analytical.edu/papers/engines",
                }
            ],
        },
    }


def test_clean_candidate_passes_verification() -> None:
    result = verify_candidate_quality(_candidate())

    assert result.is_valid is True
    assert result.quality_score == 1.0
    assert result.citation_issues == []
    assert result.contact_issues == []


def test_hallucinated_title_and_missing_url_are_flagged() -> None:
    candidate = _candidate()
    candidate["email_draft"]["citations"] = [
        {
            "claim": "An unsupported claim.",
            "source_title": "Hallucinated Paper",
            "source_url": "https://analytical.edu/papers/hallucinated",
        },
        {
            "claim": "A claim with no source URL.",
            "source_title": "Computing Engines",
            "source_url": None,
        },
    ]
    candidate["email_draft"]["body"] = "I read Hallucinated Paper [1] and Computing Engines [2]."

    result = verify_candidate_quality(candidate)

    issue_types = {issue.issue_type for issue in result.citation_issues}
    assert result.is_valid is False
    assert "unverified_source" in issue_types
    assert "missing_source_url" in issue_types


def test_invalid_email_is_flagged() -> None:
    candidate = _candidate()
    candidate["email"] = "professor@gmail.com"

    result = verify_candidate_quality(candidate)

    assert result.is_valid is False
    assert result.contact_issues == ["Faculty email address uses a generic email provider."]
