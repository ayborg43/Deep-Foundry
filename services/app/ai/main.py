"""
AI modules — FastAPI sub-app, mounted at /ai/* by config/asgi.py.

Owns the Model Router, Memory, Knowledge ingestion, and Task/Workflow
orchestration per ARCHITECTURE.md §3.1.
"""

from fastapi import FastAPI

from ai.internal_routes import router as internal_router

app = FastAPI(title="Deep-Foundry AI Modules")
app.include_router(internal_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
