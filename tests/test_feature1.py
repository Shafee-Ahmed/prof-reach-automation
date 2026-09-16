import pytest
from app.tools.discovery import discover_professors, ProfessorCandidate

@pytest.mark.asyncio
async def test_discover_professors():
    candidates = await discover_professors("computer vision for medical imaging")
    assert isinstance(candidates, list)
    assert len(candidates) > 0
    assert isinstance(candidates[0], ProfessorCandidate)
    assert candidates[0].name != ""