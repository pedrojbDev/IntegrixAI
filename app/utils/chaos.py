import random
import time

from fastapi import HTTPException, status

from ..config import Settings


def maybe_introduce_chaos(settings: Settings) -> None:
    """Inject optional latency or 503s to simulate upstream instability."""
    if settings.chaos_error_rate and random.random() < settings.chaos_error_rate:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Transient upstream error (chaos mode)",
        )

    if settings.chaos_latency_ms and settings.chaos_latency_ms > 0:
        delay = random.randint(0, settings.chaos_latency_ms) / 1000
        if delay:
            time.sleep(delay)
