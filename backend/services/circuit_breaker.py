"""
backend/services/circuit_breaker.py
Type-Safe Generic Circuit Breaker (`@with_demo_circuit_breaker`).
Guarantees that both live Gemini API calls and offline fallbacks from
`data/fallback_cache/` return validated instances of the exact same Pydantic model (`T`),
and explicitly stamps `result.served_from_fallback = True` whenever served from fallback.
"""
import asyncio
import functools
import logging
from pathlib import Path
from typing import Type, TypeVar, Callable, Awaitable
from pydantic import BaseModel
from config.settings import settings

logger = logging.getLogger("vinyas_ai.circuit_breaker")
T = TypeVar("T", bound=BaseModel)


def _load_validated_fallback(fallback_path: Path, response_model: Type[T]) -> T:
    instance = response_model.model_validate_json(fallback_path.read_text(encoding="utf-8"))
    if hasattr(instance, "served_from_fallback"):
        setattr(instance, "served_from_fallback", True)
    return instance


def with_demo_circuit_breaker(
    fallback_filename: str,
    response_model: Type[T],
    timeout_sec: float = 3.2,
):
    """
    Type-safe async circuit breaker. Always returns an instance of `response_model` (Pydantic BaseModel)
    whether served live from Vertex AI / Gemini or loaded from `data/fallback_cache/`.
    Explicitly sets `served_from_fallback = True` on all cached fallback returns.
    """
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            fallback_path = Path("data/fallback_cache") / fallback_filename
            if not fallback_path.exists():
                fallback_path = settings.FALLBACK_CACHE_DIR / fallback_filename

            if settings.DEMO_SAFE_MODE:
                logger.info(
                    "DEMO_SAFE_MODE active: serving validated %s from %s (served_from_fallback=True)",
                    response_model.__name__,
                    fallback_filename,
                )
                await asyncio.sleep(0.15)
                return _load_validated_fallback(fallback_path, response_model)

            try:
                result = await asyncio.wait_for(
                    func(*args, **kwargs), timeout=timeout_sec
                )
                if isinstance(result, dict):
                    validated = response_model.model_validate(result)
                else:
                    validated = result
                if hasattr(validated, "served_from_fallback"):
                    setattr(validated, "served_from_fallback", False)
                return validated
            except (asyncio.TimeoutError, Exception) as exc:
                logger.warning(
                    "Circuit breaker tripped on %s (%s). Returning validated %s from %s (served_from_fallback=True)",
                    func.__name__,
                    type(exc).__name__,
                    response_model.__name__,
                    fallback_filename,
                )
                return _load_validated_fallback(fallback_path, response_model)

        return wrapper

    return decorator
