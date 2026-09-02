"""Provider transcript normalization, privacy primitives and scoped coordination.

Business interpretation is supplied by the registered tenant implementation.
Never persist the text emitted by ``conversation_turns``.
"""
from __future__ import annotations

import hashlib
import hmac
import math
import re
import unicodedata
from collections.abc import Callable, Mapping
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from ...config import Settings
from .tenant_config_service import TenantConfigService

ConversationPolicy = Callable[[Session, Settings, str, str, Mapping], None]
_policies: dict[str, ConversationPolicy] = {}


def register_conversation_policy(implementation: str, policy: ConversationPolicy) -> None:
    _policies[implementation] = policy


def capture_conversation(session: Session, settings: Settings, tenant_id: str,
                         call_id: str, message: Mapping) -> None:
    if not settings.vapi_slot_guard_enabled:
        return
    key = TenantConfigService(settings).get_implementation_key(tenant_id)
    policy = _policies.get(key)
    if policy is not None:
        policy(session, settings, tenant_id, call_id, message)


def lock_call(session: Session, tenant_id: str, call_id: str) -> None:
    """Transaction-scoped lock also covers creation of a previously absent row."""
    if session.get_bind().dialect.name == "postgresql":
        digest = hashlib.sha256(f"vapi-state:{tenant_id}:{call_id}".encode()).digest()
        key = int.from_bytes(digest[:8], "big", signed=True)
        session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(c for c in value if not unicodedata.combining(c))
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def keyed_hmac(secret: str, value: str) -> str:
    return hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()


def term_hmacs(secret: str, value: str) -> set[str]:
    words = normalize_text(value).split()[:64]
    return {keyed_hmac(secret, " ".join(words[i:j]))
            for i in range(len(words)) for j in range(i + 1, min(len(words), i + 6) + 1)}


def event_time(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value) if math.isfinite(value) else None
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp() * 1000
        except ValueError:
            return None
    return None


def conversation_turns(message: Mapping) -> list[dict]:
    artifact = message.get("artifact") or {}
    if not isinstance(artifact, Mapping):
        artifact = {}
    for candidate in (message.get("messages"), artifact.get("messages"), message.get("conversation")):
        if isinstance(candidate, Mapping):
            candidate = candidate.get("messages")
        if not isinstance(candidate, list) or not candidate:
            continue
        turns = []
        for index, item in enumerate(candidate):
            if not isinstance(item, Mapping):
                continue
            role = item.get("role")
            role = {"bot": "assistant", "customer": "user"}.get(role, role)
            content = item.get("message") or item.get("content") or item.get("text")
            if role not in {"user", "assistant"} or not isinstance(content, str) or not content.strip():
                continue
            stamp = event_time(item.get("time"))
            # Raw Vapi messages have absolute millisecond timestamps. Index is
            # reserved for complete OpenAI-style snapshots that lack timestamps.
            order = stamp if stamp is not None else float(index)
            identity = str(item.get("id") or f"{role}:{order}")
            turns.append({"id": identity, "order": order, "role": role, "text": content})
        return turns
    return []
