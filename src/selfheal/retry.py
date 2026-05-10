from __future__ import annotations

import asyncio
import functools
import time
from collections.abc import Awaitable, Callable
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")


def _validate_retry_config(max_attempts: int, base_delay: float, max_delay: float) -> None:
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    if base_delay < 0:
        raise ValueError("base_delay must be non-negative")
    if max_delay < 0:
        raise ValueError("max_delay must be non-negative")


def _backoff_delay(attempt: int, base_delay: float, max_delay: float) -> float:
    return min(base_delay * 2**attempt, max_delay)


def retry_sync(
    max_attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 30.0,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    _validate_retry_config(max_attempts, base_delay, max_delay)

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception:
                    if attempt == max_attempts - 1:
                        raise
                    delay = _backoff_delay(attempt, base_delay, max_delay)
                    if delay > 0:
                        time.sleep(delay)
            raise RuntimeError("retry attempts exhausted")

        return wrapper

    return decorator


def retry_async(
    max_attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 30.0,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    _validate_retry_config(max_attempts, base_delay, max_delay)

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception:
                    if attempt == max_attempts - 1:
                        raise
                    delay = _backoff_delay(attempt, base_delay, max_delay)
                    if delay > 0:
                        await asyncio.sleep(delay)
            raise RuntimeError("retry attempts exhausted")

        return wrapper

    return decorator
