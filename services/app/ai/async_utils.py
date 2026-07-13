"""
Bridges a synchronous generator (ModelRouter.generate_stream — sync because
it also has to work unmodified from a Celery worker, not just FastAPI) into
an async generator FastAPI's StreamingResponse can consume, without blocking
the event loop. Each `next()` call runs in a worker thread via
asyncio.to_thread, which is also why Django ORM calls inside the sync
generator (the model_calls write on completion) are safe here — that thread
has no event loop of its own for Django's SynchronousOnlyOperation check to
trip on.
"""

import asyncio
from collections.abc import AsyncIterator, Iterator
from typing import TypeVar

from asgiref.sync import sync_to_async
from django.db import close_old_connections

T = TypeVar("T")

_SENTINEL = object()


def _next_and_close_connections(iterator: Iterator[T]) -> T | object:
    # close_old_connections() only closes connections opened on the thread
    # it runs on. asyncio.to_thread's default executor reuses a small pool
    # of threads across unrelated calls, not necessarily the same one each
    # time — so the only reliable place to close a connection this next()
    # call might have opened (e.g. the model_calls write in
    # ModelRouter.generate_stream) is right here, on that same thread,
    # before control returns to the event loop.
    try:
        return next(iterator, _SENTINEL)
    finally:
        close_old_connections()


async def async_iter_from_sync(sync_iter: Iterator[T]) -> AsyncIterator[T]:
    iterator = iter(sync_iter)
    while True:
        item = await asyncio.to_thread(_next_and_close_connections, iterator)
        if item is _SENTINEL:
            return
        yield item


async def close_django_connections() -> None:
    """Django's request-cycle signals close connections opened by ORM calls
    automatically — but they only fire for Django's own request/response
    cycle, never for the FastAPI sub-app mounted alongside it. Every AI
    module endpoint that touches the ORM (directly or via core.interface)
    must call this when it's done, or the connection a background thread
    opened just leaks for the life of the process."""
    await sync_to_async(close_old_connections)()
