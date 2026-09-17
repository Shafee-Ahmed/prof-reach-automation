"""Quality and citation guardrails for outreach candidates."""

import re
from typing import Any

from pydantic import BaseModel, Field


class CitationIssue(BaseModel):
    """A citation or claim-verification problem."""

    issue_type: str
    description: str


class VerificationResult(BaseModel):
    """Quality verification outcome for a candidate email."""

    is_valid: bool
    quality_score: float
    citation_issues: list[CitationIssue] = Field(default_factory=list)
    contact_issues: list[str] = Field(default_factory=list)


_EMAIL_PATTERN = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)
_GENERIC_EMAIL_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "hotmail.com",
    "outlook.com",
    "icloud.com",
    "live.com",
    "mail.com",
    "proton.me",
    "protonmail.com",
    "yahoo.com",
}
_PLACEHOLDER_EMAIL_DOMAINS = {
    "example.com",
    "example.org",
    "example.net",
    "localhost",
    "test.com",
}


def _paper_lookup(candidate_data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    papers = candidate_data.get("papers", [])
    return {
        str(paper.get("title", "")).strip().casefold(): paper
        for paper in papers
        if isinstance(paper, dict) and str(paper.get("title", "")).strip()
    }


def _citation_issues(candidate_data: dict[str, Any]) -> list[CitationIssue]:
    draft = candidate_data.get("email_draft")
    if not isinstance(draft, dict):
        return [
            CitationIssue(
                issue_type="missing_draft",
                description="Candidate has no email draft to audit.",
            )
        ]

    papers = _paper_lookup(candidate_data)
    citations = draft.get("citations", [])
    if not isinstance(citations, list):
        return [
            CitationIssue(
                issue_type="invalid_citations",
                description="Email citations must be a list.",
            )
        ]

    issues: list[CitationIssue] = []
    body = str(draft.get("body", ""))
    markers = {int(number) for number in re.findall(r"\[(\d+)\]", body)}
    if citations and not markers and not any(
        citation.get("source_title", "").casefold() in body.casefold()
        for citation in citations
        if isinstance(citation, dict)
    ):
        issues.append(
            CitationIssue(
                issue_type="missing_inline_marker",
                description="Citations are present but the email has no inline citation marker or title.",
            )
        )

    for index, citation in enumerate(citations, start=1):
        if not isinstance(citation, dict):
            issues.append(
                CitationIssue(
                    issue_type="invalid_citation",
                    description=f"Citation {index} is not an object.",
                )
            )
            continue
        title = str(citation.get("source_title") or "").strip()
        paper = papers.get(title.casefold())
        if paper is None:
            issues.append(
                CitationIssue(
                    issue_type="unverified_source",
                    description=f"Citation {index} references a paper not present in candidate papers: {title or '<missing title>'}.",
                )
            )
            continue
        source_url = citation.get("source_url")
        if not isinstance(source_url, str) or not source_url.strip():
            issues.append(
                CitationIssue(
                    issue_type="missing_source_url",
                    description=f"Citation {index} is missing a source URL for: {title}.",
                )
            )
        elif source_url.strip() != str(paper.get("url") or "").strip():
            issues.append(
                CitationIssue(
                    issue_type="unverified_source_url",
                    description=f"Citation {index} URL does not match the verified paper URL for: {title}.",
                )
            )
        if index not in markers and title.casefold() not in body.casefold():
            issues.append(
                CitationIssue(
                    issue_type="uncited_claim",
                    description=f"Citation {index} is not referenced inline for: {title}.",
                )
            )

    for marker in sorted(markers):
        if marker < 1 or marker > len(citations):
            issues.append(
                CitationIssue(
                    issue_type="unknown_inline_marker",
                    description=f"Inline marker [{marker}] has no corresponding citation.",
                )
            )
    return issues


def _contact_issues(candidate_data: dict[str, Any]) -> list[str]:
    email = candidate_data.get("email")
    if not isinstance(email, str) or not email.strip():
        return ["Missing faculty email address."]
    normalized = email.strip().lower()
    if not _EMAIL_PATTERN.fullmatch(normalized):
        return ["Faculty email address is malformed."]
    domain = normalized.rsplit("@", 1)[1]
    if domain in _PLACEHOLDER_EMAIL_DOMAINS:
        return ["Faculty email address uses a placeholder domain."]
    if domain in _GENERIC_EMAIL_DOMAINS:
        return ["Faculty email address uses a generic email provider."]
    return []


def verify_candidate_quality(candidate_data: dict[str, Any]) -> VerificationResult:
    """Audit citations and contact details and return a bounded quality score."""
    citation_issues = _citation_issues(candidate_data)
    contact_issues = _contact_issues(candidate_data)
    papers = candidate_data.get("papers", [])
    draft = candidate_data.get("email_draft")
    metadata_valid = bool(
        candidate_data.get("name")
        and candidate_data.get("institution")
        and isinstance(papers, list)
        and isinstance(draft, dict)
        and draft.get("subject")
        and draft.get("body")
    )
    citation_count = len(draft.get("citations", [])) if isinstance(draft, dict) else 0
    verified_citations = max(0, citation_count - len(citation_issues))
    citation_score = (
        verified_citations / citation_count if citation_count else 0.0
    )
    metadata_score = 1.0 if metadata_valid else 0.0
    contact_score = 1.0 if not contact_issues else 0.0
    quality_score = round(
        max(0.0, min(1.0, (metadata_score + citation_score + contact_score) / 3)),
        3,
    )
    return VerificationResult(
        is_valid=metadata_valid and not citation_issues and not contact_issues,
        quality_score=quality_score,
        citation_issues=citation_issues,
        contact_issues=contact_issues,
    )
