"""Dashboard adapters for running outreach and reviewing persisted candidates."""

import asyncio
from collections.abc import Sequence
from typing import Any

from app.core.approval_queue import (
    approve_candidate,
    get_pending_candidates,
    reject_candidate,
)
from app.db.database import OutreachRecord, list_candidates
from app.graph.workflow import run_agent


HISTORY_HEADERS = [
    "Candidate ID",
    "Professor",
    "Institution",
    "Email",
    "Score",
    "Status",
    "Updated",
]

COUNTRY_OPTIONS = [
    ("United States", "US"),
    ("Canada", "CA"),
    ("United Kingdom", "GB"),
    ("Germany", "DE"),
    ("France", "FR"),
    ("Netherlands", "NL"),
    ("Switzerland", "CH"),
    ("Sweden", "SE"),
    ("Denmark", "DK"),
    ("Australia", "AU"),
    ("New Zealand", "NZ"),
    ("Japan", "JP"),
    ("Singapore", "SG"),
    ("South Korea", "KR"),
    ("India", "IN"),
    ("China", "CN"),
    ("Hong Kong", "HK"),
    ("Israel", "IL"),
    ("Brazil", "BR"),
]
COUNTRY_LABELS = {code: name for name, code in COUNTRY_OPTIONS}

_CSS = """
:root {
  --oa-ink: #202020;
  --oa-accent: #b83a2f;
  --oa-paper: #f4edda;
  --oa-border: #202020;
}
.gradio-container {
  max-width: 1180px !important;
  margin: 0 auto !important;
  color: var(--oa-ink) !important;
  background: var(--oa-paper) !important;
  font-family: "Courier New", Courier, monospace !important;
}
.oa-hero {
  padding: 24px 28px;
  border: 3px solid var(--oa-border);
  border-radius: 0;
  color: var(--oa-ink);
  background: var(--oa-paper);
  box-shadow: 5px 5px 0 var(--oa-border);
}
.oa-hero h1 {
  margin: 0 0 8px;
  font-size: 2rem;
  letter-spacing: .04em;
  text-transform: uppercase;
  color: var(--oa-ink) !important;
}
.oa-hero p { margin: 0; color: var(--oa-ink); font-size: .95rem; }
.oa-step {
  border: 0 !important;
  border-radius: 0 !important;
  padding: 18px 0 !important;
  background: var(--oa-paper);
}
.oa-step h2 {
  margin-top: 0;
  font-size: 1.15rem;
  text-transform: uppercase;
  letter-spacing: .05em;
  color: var(--oa-ink) !important;
}
.oa-help { color: var(--oa-ink) !important; font-size: .88rem; }
.oa-stat {
  border: 0 !important;
  border-bottom: 1px solid var(--oa-border) !important;
  border-radius: 0;
  padding: 12px 0 !important;
  background: var(--oa-paper);
}
.oa-stat p, .oa-stat strong { margin: 0; color: var(--oa-ink) !important; }
button, input, textarea, select {
  border-radius: 0 !important;
  font-family: "Courier New", Courier, monospace !important;
  color: var(--oa-ink) !important;
  background: var(--oa-paper) !important;
  border-color: var(--oa-border) !important;
}
button.primary {
  color: var(--oa-paper) !important;
  background: var(--oa-accent) !important;
  border: 2px solid var(--oa-border) !important;
}
button.primary:hover { background: var(--oa-ink) !important; }
button.secondary {
  border: 2px solid var(--oa-border) !important;
  background: var(--oa-paper) !important;
  color: var(--oa-ink) !important;
}
.tabs, .tabitem {
  border-radius: 0 !important;
}
.tab-nav button {
  border-bottom: 2px solid var(--oa-border) !important;
  border-radius: 0 !important;
  font-family: "Courier New", Courier, monospace !important;
  text-transform: uppercase;
  letter-spacing: .04em;
}
.tab-nav button.selected {
  color: var(--oa-accent) !important;
  border-bottom: 4px solid var(--oa-accent) !important;
}
label span {
  font-weight: 700 !important;
  letter-spacing: .02em;
  color: var(--oa-ink) !important;
}
.dataframe, .block {
  border-radius: 0 !important;
}
.prose, .markdown, .form, .wrap, .panel, .block {
  color: var(--oa-ink) !important;
  background: transparent !important;
}
.markdown *,
.prose *,
.oa-hero *,
.oa-step *,
.oa-stat * {
  color: var(--oa-ink) !important;
}
.markdown h1,
.markdown h2,
.markdown h3,
.markdown p,
.markdown strong {
  color: var(--oa-ink) !important;
}
.dataframe table, .dataframe th, .dataframe td {
  color: var(--oa-ink) !important;
  background: var(--oa-paper) !important;
  border-color: var(--oa-border) !important;
}
.dataframe th {
  background: var(--oa-ink) !important;
  color: var(--oa-paper) !important;
}
input::placeholder, textarea::placeholder {
  color: var(--oa-ink) !important;
  opacity: .65 !important;
}
"""


def records_to_rows(records: Sequence[OutreachRecord]) -> list[list[Any]]:
    """Convert persisted records into rows suitable for a Gradio dataframe."""
    return [
        [
            record.candidate_id,
            record.name,
            record.institution,
            record.email or "",
            record.relevance_score,
            record.status,
            record.updated_at or "",
        ]
        for record in records
    ]


def history_rows(status: str = "all") -> list[list[Any]]:
    """Return persisted outreach history, optionally filtered by status."""
    records = list_candidates(None if status == "all" else status)
    return records_to_rows(records)


def _record_candidate_data(record: OutreachRecord) -> dict[str, Any]:
    return {
        "candidate_id": record.candidate_id,
        "name": record.name,
        "institution": record.institution,
        "email": record.email,
        "faculty_url": record.faculty_url,
        "relevance_score": record.relevance_score,
        "papers": record.papers,
        "status": record.status,
        "email_draft": {
            "subject": record.subject,
            "body": record.body,
            "citations": record.citations,
        }
        if record.subject is not None and record.body is not None
        else None,
        "quality_checks": record.quality_checks,
    }


def pending_rows() -> list[list[Any]]:
    """Return pending candidates and load them into the approval queue."""
    records = list_candidates("pending")
    get_pending_candidates(
        [
            data
            for record in records
            if (data := _record_candidate_data(record))["email_draft"] is not None
        ]
    )
    return records_to_rows(records)


def pending_choices() -> list[tuple[str, str]]:
    """Return human-readable choices while keeping candidate IDs internal."""
    return [
        (
            f"{record.name} — {record.institution} "
            f"(score {record.relevance_score:.1f})",
            record.candidate_id,
        )
        for record in list_candidates("pending")
        if record.subject is not None and record.body is not None
    ]


def candidate_preview(candidate_id: str | None) -> str:
    """Render the selected candidate and draft for the review panel."""
    if not candidate_id:
        return (
            "### Select a candidate\n"
            "Refresh the queue, then choose a candidate to inspect the draft."
        )
    record = next(
        (item for item in list_candidates() if item.candidate_id == candidate_id),
        None,
    )
    if record is None:
        return "### Candidate not found\nRefresh the queue and try again."
    citations = "\n".join(
        f"- **{citation.get('source_title', 'Source')}**: "
        f"{citation.get('source_url') or 'URL unavailable'}"
        for citation in record.citations
    ) or "- No citation tags found"
    return (
        f"### {record.name}\n"
        f"**{record.institution}**  \n"
        f"Relevance score: **{record.relevance_score:.1f}/10**  \n"
        f"Recipient: `{record.email or 'not found'}`\n\n"
        f"**Subject**  \n{record.subject or 'No subject'}\n\n"
        f"**Draft**  \n{record.body or 'No draft body'}\n\n"
        f"**Citation sources**\n{citations}"
    )


def dashboard_stats() -> str:
    """Render compact counts for the dashboard overview."""
    records = list_candidates()
    counts = {
        "pending": sum(record.status == "pending" for record in records),
        "approved": sum(record.status in {"approved", "edited"} for record in records),
        "sent": sum(record.status in {"sent", "simulated"} for record in records),
        "rejected": sum(record.status == "rejected" for record in records),
    }
    return (
        f"**{counts['pending']}** pending &nbsp;&nbsp; "
        f"**{counts['approved']}** approved &nbsp;&nbsp; "
        f"**{counts['sent']}** sent &nbsp;&nbsp; "
        f"**{counts['rejected']}** rejected"
    )


def review_candidate(
    candidate_id: str,
    decision: str,
    subject: str = "",
    body: str = "",
    reason: str = "",
) -> str:
    """Apply an approval-queue decision and return a user-facing result."""
    normalized = decision.strip().lower()
    if normalized not in {"approve", "edit", "reject"}:
        raise ValueError("Decision must be approve, edit, or reject")
    if normalized == "reject":
        reject_candidate(candidate_id, reason.strip() or None)
        return f"Rejected {candidate_id}"
    candidate = approve_candidate(
        candidate_id,
        edited_subject=subject.strip() or None if normalized == "edit" else None,
        edited_body=body.strip() or None if normalized == "edit" else None,
    )
    return f"{candidate.status.value.title()} {candidate_id}"


def refresh_review_panel() -> tuple[Any, str]:
    """Reload the queue and select its first candidate for quick review."""
    pending_rows()
    choices = pending_choices()
    selected = choices[0][1] if choices else ""
    return (
        gradio_dropdown(choices=choices, value=selected),
        candidate_preview(selected),
    )


def gradio_dropdown(**kwargs: Any) -> Any:
    """Create a dropdown update lazily without importing Gradio in core tests."""
    import gradio as gr

    return gr.Dropdown(**kwargs)


def run_topic(
    topic: str,
    include_countries: list[str] | None,
    exclude_countries: list[str] | None,
) -> tuple[str, list[list[Any]]]:
    """Run the async graph from a synchronous Gradio callback."""
    cleaned_topic = topic.strip()
    if not cleaned_topic:
        raise ValueError("Enter a research topic before searching")
    result = asyncio.run(
        run_agent(
            cleaned_topic,
            include_countries=include_countries or [],
            exclude_countries=exclude_countries or [],
        )
    )
    filter_summary = _country_filter_summary(include_countries, exclude_countries)
    return (
        f"Workflow finished with status: {result.get('status', 'unknown')}. "
        f"{filter_summary}",
        history_rows(),
    )


def _country_filter_summary(
    include_countries: list[str] | None,
    exclude_countries: list[str] | None,
) -> str:
    included = [COUNTRY_LABELS.get(code, code) for code in include_countries or []]
    excluded = [COUNTRY_LABELS.get(code, code) for code in exclude_countries or []]
    parts: list[str] = []
    if included:
        parts.append(f"Included: {', '.join(included)}")
    if excluded:
        parts.append(f"Excluded: {', '.join(excluded)}")
    return " ".join(parts) if parts else "No country filter applied."


def build_dashboard() -> Any:
    """Construct the Gradio dashboard lazily so core imports need no Gradio."""
    import gradio as gr

    with gr.Blocks(title="Professor Outreach Agent") as dashboard:
        gr.Markdown(
            """
            <div class="oa-hero">
              <h1>PROFESSOR OUTREACH // CONTROL DESK</h1>
              <p>Find experts. Verify sources. Send thoughtful outreach.</p>
            </div>
            """,
        )
        stats = gr.Markdown(dashboard_stats, elem_classes="oa-stat")

        with gr.Tab("1 · Discover"):
            gr.Markdown("## Find experts by research interest")
            gr.Markdown(
                "Search recent research across universities and countries. "
                "Results are saved automatically for review.",
                elem_classes="oa-help",
            )
            topic = gr.Textbox(
                label="Research interest",
                placeholder="computer vision for medical imaging",
                info="Use a focused topic for more relevant matches.",
            )
            with gr.Row():
                include_countries = gr.Dropdown(
                    choices=COUNTRY_OPTIONS,
                    label="Include countries",
                    multiselect=True,
                    info="Only keep experts from these countries. Leave empty for all.",
                )
                exclude_countries = gr.Dropdown(
                    choices=COUNTRY_OPTIONS,
                    label="Exclude countries",
                    multiselect=True,
                    info="Excluded countries are removed from the results.",
                )
            search_button = gr.Button("Find professors", variant="primary")
            search_status = gr.Markdown()
            search_history = gr.Dataframe(
                headers=HISTORY_HEADERS,
                datatype=["str", "str", "str", "str", "number", "str", "str"],
                interactive=False,
            )
            search_button.click(
                run_topic,
                inputs=[topic, include_countries, exclude_countries],
                outputs=[search_status, search_history],
            ).then(dashboard_stats, outputs=stats)

        with gr.Tab("2 · Review"):
            gr.Markdown("## Review the approval queue")
            gr.Markdown(
                "Select a candidate to inspect their profile, score, draft, and sources. "
                "Only approved drafts can be sent.",
                elem_classes="oa-help",
            )
            refresh_button = gr.Button("Refresh queue")
            candidate_selector = gr.Dropdown(
                label="Candidate to review",
                choices=[],
                interactive=True,
                info="Candidates are sorted by most recently updated.",
            )
            candidate_preview_output = gr.Markdown()
            pending_table = gr.Dataframe(
                headers=HISTORY_HEADERS,
                datatype=["str", "str", "str", "str", "number", "str", "str"],
                interactive=False,
                visible=False,
            )
            decision = gr.Radio(
                ["approve", "edit", "reject"],
                value="approve",
                label="Decision",
                info="Choose edit to replace the subject or body before approval.",
            )
            with gr.Group(visible=True):
                edited_subject = gr.Textbox(
                    label="New subject (optional)",
                    placeholder="Leave blank to keep the generated subject",
                )
                edited_body = gr.Textbox(
                    label="New body (optional)",
                    placeholder="Leave blank to keep the generated body",
                    lines=6,
                )
                rejection_reason = gr.Textbox(
                    label="Rejection reason (optional)",
                    placeholder="Why is this not a fit?",
                )
            review_button = gr.Button("Apply decision", variant="primary")
            review_status = gr.Markdown()
            refresh_button.click(
                refresh_review_panel,
                outputs=[candidate_selector, candidate_preview_output],
            )
            dashboard.load(
                refresh_review_panel,
                outputs=[candidate_selector, candidate_preview_output],
            )
            candidate_selector.change(
                candidate_preview,
                inputs=candidate_selector,
                outputs=candidate_preview_output,
            )
            review_button.click(
                review_candidate,
                inputs=[
                    candidate_selector,
                    decision,
                    edited_subject,
                    edited_body,
                    rejection_reason,
                ],
                outputs=review_status,
            ).then(
                refresh_review_panel,
                outputs=[candidate_selector, candidate_preview_output],
            ).then(dashboard_stats, outputs=stats)

        with gr.Tab("3 · History"):
            gr.Markdown("## Outreach history")
            gr.Markdown(
                "Track every candidate from discovery through delivery.",
                elem_classes="oa-help",
            )
            status_filter = gr.Dropdown(
                ["all", "pending", "approved", "edited", "rejected", "simulated", "sent"],
                value="all",
                label="Status",
            )
            history_table = gr.Dataframe(
                headers=HISTORY_HEADERS,
                datatype=["str", "str", "str", "str", "number", "str", "str"],
                value=history_rows(),
                interactive=False,
            )
            status_filter.change(history_rows, inputs=status_filter, outputs=history_table)
            gr.Button("Refresh history").click(
                history_rows,
                inputs=status_filter,
                outputs=history_table,
            ).then(dashboard_stats, outputs=stats)

    return dashboard


def launch_dashboard() -> None:
    """Launch the local Gradio dashboard."""
    build_dashboard().launch(css=_CSS)


if __name__ == "__main__":
    launch_dashboard()
