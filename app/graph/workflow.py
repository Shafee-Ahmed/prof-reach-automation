"""LangGraph workflow for professor discovery and relevance evaluation."""

from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from app.agents.email_writer import generate_email_draft
from app.agents.paper_evaluator import evaluate_candidate
from app.agents.quality_checker import verify_candidate_quality
from app.db.database import save_graph_results
from app.graph.state import AgentState, candidate_from_state
from app.tools.discovery import discover_professors
from app.tools.scraper import FacultyInfo, find_faculty_info

RELEVANCE_THRESHOLD = 7.0


def _faculty_update(faculty: FacultyInfo) -> dict[str, Any]:
    return faculty.model_dump(exclude_none=True)


async def discover_node(state: AgentState) -> dict[str, Any]:
    """Discover professors matching the requested topic."""
    topic = state.get("topic", "").strip()
    if not topic:
        raise ValueError("A research topic is required")

    candidates = await discover_professors(topic)
    professors = [candidate.model_dump() for candidate in candidates]
    return {
        "professors": professors,
        "current_index": 0,
        "status": "pending" if professors else "skipped",
        "results": [],
    }


async def enrich_faculty_node(state: AgentState) -> dict[str, Any]:
    """Find the current professor's faculty page and contact information."""
    index = state.get("current_index", 0)
    professors = state.get("professors", [])
    if index >= len(professors):
        raise IndexError("Current professor index is outside the candidate list")

    candidate_data = professors[index]
    faculty = await find_faculty_info(
        str(candidate_data["name"]),
        str(candidate_data.get("institution", "Unknown")),
    )
    enriched = {**candidate_data, **_faculty_update(faculty)}
    updated_professors = [*professors]
    updated_professors[index] = enriched
    return {
        "professors": updated_professors,
        "current_professor": enriched,
        "status": "pending",
    }


async def evaluate_node(state: AgentState) -> dict[str, Any]:
    """Evaluate the current professor's recent papers against the topic."""
    candidate = candidate_from_state(state["current_professor"])
    evaluation = await evaluate_candidate(candidate, state["topic"])
    papers = [paper.model_dump() for paper in evaluation.top_papers]
    email_draft: dict[str, Any] | None = None
    if evaluation.relevance_score >= RELEVANCE_THRESHOLD:
        draft = await generate_email_draft(
            candidate_name=candidate.name,
            institution=candidate.institution,
            student_interests=state["topic"],
            top_papers=evaluation.top_papers,
        )
        email_draft = draft.model_dump()
    return {
        "papers": papers,
        "relevance_score": evaluation.relevance_score,
        "email_draft": email_draft,
        "current_professor": {
            **state["current_professor"],
            "summary": evaluation.summary,
            "rationale": evaluation.rationale,
            "papers": papers,
            "relevance_score": evaluation.relevance_score,
            "email_draft": email_draft,
        },
    }


def _result_from_state(state: AgentState, result_status: str) -> dict[str, Any]:
    return {
        **state["current_professor"],
        "papers": state.get("papers", []),
        "relevance_score": state.get("relevance_score", 0.0),
        "email_draft": (
            state.get("email_draft")
            if result_status == "pending"
            else None
        ),
        "quality_checks": state.get("quality_checks", {}),
        "status": result_status,
    }


async def queue_candidate_node(state: AgentState) -> dict[str, Any]:
    """Keep a qualified candidate in the manual approval queue."""
    candidate = _result_from_state(state, "pending")
    verification = verify_candidate_quality(candidate)
    candidate["quality_checks"] = verification.model_dump()
    return {
        "status": "pending",
        "quality_checks": verification.model_dump(),
        "results": [*state.get("results", []), candidate],
    }


async def skip_candidate_node(state: AgentState) -> dict[str, Any]:
    """Mark a candidate below the relevance threshold as skipped."""
    return {
        "status": "skipped",
        "results": [*state.get("results", []), _result_from_state(state, "skipped")],
    }


def should_queue_candidate(
    state: AgentState,
) -> Literal["queue_candidate", "skip_candidate"]:
    """Route candidates based on the configured relevance threshold."""
    if state.get("relevance_score", 0.0) >= RELEVANCE_THRESHOLD:
        return "queue_candidate"
    return "skip_candidate"


async def advance_node(state: AgentState) -> dict[str, Any]:
    """Move the workflow cursor to the next discovered professor."""
    return {
        "current_index": state.get("current_index", 0) + 1,
        "current_professor": {},
        "papers": [],
        "relevance_score": 0.0,
        "email_draft": None,
    }


def should_process_next(
    state: AgentState,
) -> Literal["enrich_faculty", "finish"]:
    """Continue the loop while undispatched professors remain."""
    if state.get("current_index", 0) < len(state.get("professors", [])):
        return "enrich_faculty"
    return "finish"


async def finish_node(state: AgentState) -> dict[str, Any]:
    """Set the final workflow status after all candidates are processed."""
    results = state.get("results", [])
    final_status = "pending" if any(
        result.get("status") == "pending" for result in results
    ) else "skipped"
    save_graph_results(results)
    return {"status": final_status}


def build_graph() -> StateGraph:
    """Build the uncompiled outreach workflow."""
    graph = StateGraph(AgentState)
    graph.add_node("discover", discover_node)
    graph.add_node("enrich_faculty", enrich_faculty_node)
    graph.add_node("evaluate", evaluate_node)
    graph.add_node("queue_candidate", queue_candidate_node)
    graph.add_node("skip_candidate", skip_candidate_node)
    graph.add_node("advance", advance_node)
    graph.add_node("finish", finish_node)

    graph.add_edge(START, "discover")
    graph.add_conditional_edges(
        "discover",
        should_process_next,
        {"enrich_faculty": "enrich_faculty", "finish": "finish"},
    )
    graph.add_edge("enrich_faculty", "evaluate")
    graph.add_conditional_edges(
        "evaluate",
        should_queue_candidate,
        {
            "queue_candidate": "queue_candidate",
            "skip_candidate": "skip_candidate",
        },
    )
    graph.add_edge("queue_candidate", "advance")
    graph.add_edge("skip_candidate", "advance")
    graph.add_conditional_edges(
        "advance",
        should_process_next,
        {"enrich_faculty": "enrich_faculty", "finish": "finish"},
    )
    graph.add_edge("finish", END)
    return graph


def compile_graph() -> Any:
    """Compile and return the outreach workflow ready for invocation."""
    return build_graph().compile()


async def run_agent(topic: str) -> AgentState:
    """Run the complete discovery, enrichment, and evaluation workflow."""
    return await compile_graph().ainvoke({"topic": topic})
