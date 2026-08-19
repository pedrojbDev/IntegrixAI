import hmac

from fastapi import Request

from ...config import Settings


def is_webhook_authorized(http_request: Request, settings: Settings) -> bool:
    """Validate optional webhook secret; production fails closed when missing."""
    if not settings.webhook_secret:
        return not settings.is_production
    received_secret = http_request.headers.get(settings.webhook_secret_header)
    if not received_secret:
        return False
    return hmac.compare_digest(received_secret, settings.webhook_secret)
