# AGENTS.md instructions for AIHR

## Project

AIHR is an AI hiring recommendation effectiveness and monitoring system. It uses FastAPI for the analytics API, Streamlit for the dashboard, SQLAlchemy for database access, and pytest/ruff for feedback.

## Agent Skills

Use the installed Codex skills from `~/.codex/skills` when the task fits.

### Recommended flow

- Use `/ask-matt` when it is unclear which skill should guide the work.
- Use `/grill-with-docs` before non-trivial product or architecture changes so project vocabulary and decisions stay captured.
- Use `/tdd` for behavior changes and bug fixes where a testable seam exists.
- Use `/diagnosing-bugs` for failures that need reproduction, minimization, instrumentation, and a regression test.
- Use `/to-spec`, `/to-tickets`, and `/implement` for larger work that should be split into traceable tickets.
- Use `/code-review` before finishing a meaningful code change.

### Issue tracker

Issues are tracked in GitHub Issues for `miamai456/AI-Hiring-Monitor`. See `docs/agents/issue-tracker.md`.

### Triage labels

The default triage label vocabulary is used. See `docs/agents/triage-labels.md`.

### Domain docs

This repo uses a single-context domain documentation layout: root `CONTEXT.md` plus ADRs in `docs/adr/`. See `docs/agents/domain.md`.

## Local commands

Use these commands from the repo root:

```powershell
python -m pip install -e ".[dev]"
pytest
ruff check .
```

Run the application locally with:

```powershell
uvicorn aihr.api.main:app --reload
$env:AIHR_API_URL="http://localhost:8000/api/v1"
streamlit run app/Home.py
```

Docker flow:

```powershell
Copy-Item .env.example .env
docker compose up --build
docker compose down
```

## Working conventions

- Prefer changes through public seams: API endpoints, service functions, repository/database boundaries, and Streamlit page behavior.
- Keep tests focused on behavior rather than implementation details.
- Update `CONTEXT.md` when new domain terms become important.
- Add an ADR under `docs/adr/` for decisions that are hard to reverse.
