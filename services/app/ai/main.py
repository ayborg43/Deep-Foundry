"""
AI modules — FastAPI sub-app, mounted at /ai/* by config/asgi.py.

Owns the Model Router, Memory, Knowledge ingestion, and Task/Workflow
orchestration per ARCHITECTURE.md §3.1. Milestone 0 scope is a health check
only; real endpoints land starting Milestone 2 (Model Router).
"""

from fastapi import FastAPI

app = FastAPI(title="Agentarium AI Modules")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
