import pytest

from app.tools.discovery import ProfessorCandidate, discover_professors


@pytest.mark.asyncio
async def test_discovery_keeps_multiple_universities_and_countries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    openalex = [
        ProfessorCandidate(
            name="Expert One",
            institution="University A",
            recent_paper="Paper A",
            source="OpenAlex",
            author_id="a1",
            country="US",
        ),
        ProfessorCandidate(
            name="Expert Two",
            institution="University B",
            recent_paper="Paper B",
            source="OpenAlex",
            author_id="a2",
            country="GB",
        ),
        ProfessorCandidate(
            name="Expert Three",
            institution="University C",
            recent_paper="Paper C",
            source="OpenAlex",
            author_id="a3",
            country="DE",
        ),
    ]

    async def openalex_candidates(
        topic: str, max_results: int = 30
    ) -> list[ProfessorCandidate]:
        return openalex

    async def semantic_candidates(
        topic: str, max_results: int = 30
    ) -> list[ProfessorCandidate]:
        return []

    monkeypatch.setattr(
        "app.tools.discovery.fetch_openalex_authors",
        openalex_candidates,
    )
    monkeypatch.setattr(
        "app.tools.discovery.fetch_semantic_scholar_authors",
        semantic_candidates,
    )

    candidates = await discover_professors("medical imaging", max_results=3)

    assert {candidate.institution for candidate in candidates} == {
        "University A",
        "University B",
        "University C",
    }
    assert {candidate.country for candidate in candidates} == {"US", "GB", "DE"}


@pytest.mark.asyncio
async def test_discovery_rejects_blank_topic() -> None:
    with pytest.raises(ValueError, match="research topic"):
        await discover_professors("  ")


@pytest.mark.asyncio
async def test_discovery_applies_include_and_exclude_country_filters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates = [
        ProfessorCandidate(
            name="US Expert",
            institution="US University",
            recent_paper="Paper",
            source="OpenAlex",
            author_id="us",
            country="US",
        ),
        ProfessorCandidate(
            name="GB Expert",
            institution="GB University",
            recent_paper="Paper",
            source="OpenAlex",
            author_id="gb",
            country="GB",
        ),
        ProfessorCandidate(
            name="DE Expert",
            institution="DE University",
            recent_paper="Paper",
            source="OpenAlex",
            author_id="de",
            country="DE",
        ),
    ]

    async def provider(
        topic: str, max_results: int = 30
    ) -> list[ProfessorCandidate]:
        return candidates

    monkeypatch.setattr("app.tools.discovery.fetch_openalex_authors", provider)
    monkeypatch.setattr(
        "app.tools.discovery.fetch_semantic_scholar_authors",
        lambda topic, max_results=30: provider(topic, max_results),
    )

    filtered = await discover_professors(
        "robotics",
        include_countries=["US", "GB"],
        exclude_countries=["GB"],
    )

    assert [candidate.country for candidate in filtered] == ["US"]
