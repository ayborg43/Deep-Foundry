"""
Milestone 0 no-op task: proves the worker entrypoint boots against the same
codebase as the ASGI app and can import Core and AI modules directly, in
process, per ARCHITECTURE.md §3.2 (no network hop between worker and app).
"""

from ai.main import app as ai_app  # noqa: F401  (import-only proof, per Epic 0.1)
from config.celery import app
from core.interface import write_audit_log


@app.task(name="worker.ping")
def ping() -> str:
    write_audit_log(
        actor_type="system",
        actor_id="worker",
        action="ping",
        resource_type="system",
        resource_id="worker",
    )
    return "pong"
