"""Synchronous ASGI client for tests.

Starlette's ``TestClient`` uses an AnyIO blocking portal and therefore needs a
second thread.  That makes the suite unnecessarily sensitive to the host
runtime.  This adapter keeps the tests synchronous while executing each
request through HTTPX's in-process ASGI transport on the current thread.
"""

from __future__ import annotations

import asyncio
from contextlib import ExitStack
from typing import Any
from unittest.mock import patch

import httpx


class LocalASGIClient:
    """Small ``TestClient``-compatible surface backed by ``ASGITransport``."""

    def __init__(
        self,
        app: Any,
        *,
        base_url: str = "http://testserver",
        follow_redirects: bool = True,
        raise_app_exceptions: bool = True,
    ) -> None:
        self._app = app
        self._base_url = base_url
        self._follow_redirects = follow_redirects
        self._raise_app_exceptions = raise_app_exceptions
        self.cookies = httpx.Cookies()

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Send one request and keep the cookie jar between requests."""

        async def run_inline(func: Any, *args: Any, **inner_kwargs: Any) -> Any:
            """Avoid a worker-thread portal in constrained local runners.

            The application has synchronous route/dependency functions.  The
            normal Starlette path sends those functions to AnyIO's worker
            thread pool, which can deadlock in restricted agent sandboxes.
            Running them inline keeps this in-process harness deterministic;
            production workers still use Starlette's normal thread pool.
            """

            for control_kwarg in ("abandon_on_cancel", "cancellable", "limiter"):
                inner_kwargs.pop(control_kwarg, None)
            return func(*args, **inner_kwargs)

        async def send() -> httpx.Response:
            with ExitStack() as stack:
                for target in (
                    "fastapi.routing.run_in_threadpool",
                    "fastapi.dependencies.utils.run_in_threadpool",
                    "fastapi.concurrency.run_in_threadpool",
                    "starlette.routing.run_in_threadpool",
                    "starlette.datastructures.run_in_threadpool",
                    "starlette.background.run_in_threadpool",
                    "starlette._exception_handler.run_in_threadpool",
                    "anyio.to_thread.run_sync",
                ):
                    stack.enter_context(patch(target, run_inline))

                transport = httpx.ASGITransport(
                    app=self._app,
                    raise_app_exceptions=self._raise_app_exceptions,
                )
                async with httpx.AsyncClient(
                    transport=transport,
                    base_url=self._base_url,
                    cookies=self.cookies,
                    follow_redirects=self._follow_redirects,
                ) as client:
                    response = await client.request(method, url, **kwargs)
                    self.cookies = client.cookies
                    return response

        return asyncio.run(send())

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("PUT", url, **kwargs)

    def patch(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("PATCH", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("DELETE", url, **kwargs)
