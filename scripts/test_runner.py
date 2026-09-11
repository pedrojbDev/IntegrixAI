"""Local unittest entrypoint with deterministic async execution.

The production code intentionally uses ``asyncio.to_thread`` for blocking
provider calls.  In the restricted environments used by coding agents, the
interpreter can leave that worker pool waiting during interpreter shutdown.
Unit tests already mock provider work where timing matters, so the local
runner executes those calls inline and keeps the process short-lived.
"""

from __future__ import annotations

import asyncio
import inspect
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar


_ResultT = TypeVar("_ResultT")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


async def _run_inline(
    func: Callable[..., _ResultT],
    /,
    *args: Any,
    **kwargs: Any,
) -> _ResultT:
    result = func(*args, **kwargs)
    if inspect.isawaitable(result):
        return await result  # type: ignore[return-value]
    return result


def main() -> None:
    if os.environ.get("ALLOW_EXTERNAL_TESTS") != "1":
        asyncio.to_thread = _run_inline  # type: ignore[assignment]

    from unittest import __main__ as unittest_main

    unittest_main.main()


if __name__ == "__main__":
    main()
