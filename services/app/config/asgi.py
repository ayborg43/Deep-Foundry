"""
ASGI entrypoint for the Deep-Foundry modular monolith.

Per ARCHITECTURE.md ADR-006, this mounts the AI modules' FastAPI app at /ai/*
inside the same ASGI process Django serves everything else from — one image,
one deploy pipeline, no network hop for internal calls. The /ai mount MUST be
registered before the catch-all Django mount, since Starlette matches routes
in declaration order.
"""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.core.asgi import get_asgi_application  # noqa: E402
from starlette.applications import Starlette  # noqa: E402
from starlette.routing import Mount  # noqa: E402

from ai.main import app as ai_app  # noqa: E402

django_asgi_app = get_asgi_application()

application = Starlette(
    routes=[
        Mount("/ai", app=ai_app),
        Mount("/", app=django_asgi_app),
    ]
)
