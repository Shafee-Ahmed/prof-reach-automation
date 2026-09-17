from app.tools.paper_fetcher import PaperSummary, _filter_by_topic


def test_filter_by_topic_excludes_unrelated_papers() -> None:
    papers = [
        PaperSummary(title="Deep learning for medical image segmentation"),
        PaperSummary(title="Women and travel in ancient history"),
    ]

    filtered = _filter_by_topic(papers, "computer vision for medical imaging")

    assert [paper.title for paper in filtered] == [
        "Deep learning for medical image segmentation"
    ]


def test_filter_by_topic_keeps_all_papers_without_topic() -> None:
    papers = [PaperSummary(title="Any paper")]

    assert _filter_by_topic(papers, None) == papers
