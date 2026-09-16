# Copilot Instructions — Professor Outreach Agent

## What this project is
An AI agent that takes a research interest topic as input, finds matching
professors across universities, reads their recent papers, scores relevance,
writes personalized cold emails for MSc/PhD applications, and sends them
after manual verification. Every claim the agent writes in an email is
traceable to a real source with a clickable link.

## Tech stack
- **Agent framework:** LangGraph
- **Backend API:** FastAPI
- **LLM:** Claude API (anthropic SDK) or Gemini
- **Academic search:** Semantic Scholar API, OpenAlex API
- **Web search/scraping:** Tavily API, BeautifulSoup
- **UI:** Gradio
- **Email sending:** Resend API
- **Database:** SQLite
- **Observability:** LangSmith
- **Containerization:** Docker + docker-compose
- **Language:** Python 3.11+

## Folder structure

prof-outreach-agent/
├── app/
│ ├── agents/ # LangGraph graph definitions and node functions
│ ├── tools/ # Individual tools: search, scrape, email, score
│ ├── api/ # FastAPI route handlers
│ ├── ui/ # Gradio interface and components
│ ├── db/ # SQLite models, schema, and query functions
│ └── core/ # Config, constants, prompt templates
├── tests/ # One test file per feature
├── .github/
│ └── copilot-instructions.md
├── .env # API keys — never commit this
├── .gitignore
├── Dockerfile
├── docker-compose.yml
└── requirements.txt


## Coding conventions
- All code is Python 3.11+
- Use `async/await` for all FastAPI routes and LangGraph nodes
- Type hints on every function — no bare `def foo(x)`
- Pydantic models for all data shapes (API input/output, DB records, agent state)
- Environment variables via `python-dotenv` — never hardcode API keys
- One tool per file inside `app/tools/`
- One node per function inside `app/agents/`
- All prompts live in `app/core/prompts.py` — never inline prompt strings
- SQLite queries go in `app/db/` — no raw SQL outside that folder

## LangGraph conventions
- Agent state is always a typed `TypedDict`
- Every node receives `state` and returns updated `state`
- Conditional edges use explicit `should_continue` style functions
- Every node is individually testable without running the full graph

## What the agent does step by step
1. Takes research interest as input (e.g. "computer vision for medical imaging")
2. Searches Semantic Scholar + OpenAlex for authors publishing on that topic
3. For each author: finds university faculty page + email via Tavily + BeautifulSoup
4. Fetches top 3 recent papers, summarizes abstracts, scores relevance (0-10)
5. If score >= 7: generates personalized cold email with citation tags
6. Each claim in the email is tagged with: paper title, url, year
7. Auto quality checks: word count 100-200, prof name present, 1+ real citation, no clichés
8. Failed checks → regenerate. Passed → goes to approval queue
9. Approval UI: email shown with clickable highlighted claims → opens real source link
10. After approval: sends via Resend API with rate limiting
11. Everything logged to SQLite: prof name, university, email, score, status, date

## Agent state shape
```python
class AgentState(TypedDict):
    topic: str
    professors: list[dict]
    current_professor: dict
    papers: list[dict]
    relevance_score: float
    email_draft: str
    citations: list[dict]
    quality_checks: dict
    status: str  # pending | approved | sent | skipped
```

## Citation format (every email claim must have this)
```python
{
  "claim": "exact phrase from the email",
  "source_title": "paper title",
  "source_url": "https://semanticscholar.org/...",
  "year": 2023,
  "verified": True
}
```

## What to never do
- Never write a compliment in the email without a citation backing it up
- Never commit the `.env` file
- Never hardcode API keys or model names — use `core/config.py`
- Never write SQL outside `app/db/`
- Never write prompts inline — always use `app/core/prompts.py`
- Never skip type hints

## Current feature being built
Feature 1 — Find professors by research topic using Semantic Scholar + OpenAlex API
Feature 2 → Find university faculty page + email using Tavily + BeautifulSoup
Feature 3 → Fetch top 3 papers + summarize + score relevance using LLM
Feature 4 → Wire everything into LangGraph agent with conditional logic
Feature 5 → Personalized email writer with citation tags on every claim
Feature 6 → Verified approval UI with clickable claims showing real sources
Feature 7 → Auto quality checks before email reaches approval queue
Feature 8 → Send approved emails using Resend API with rate limiting
Feature 9 → Persistence layer — SQLite tracking all outreach and status
Feature 10 → Full Gradio dashboard with history, status, manual reply tracking