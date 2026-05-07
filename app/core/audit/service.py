from __future__ import annotations

from dataclasses import dataclass
from queue import Empty, Full, Queue
from threading import Event, Lock, Thread
import time
from typing import Any

from ...config import Settings
from ...db import SessionLocal
from ...logging import get_logger
from ...models.call_event import CallEvent
from ..metrics.service import metrics_store

log = get_logger()

SENSITIVE_KEYS = {"cpf", "token", "secret", "authorization", "password"}


@dataclass(frozen=True)
class AuditEventPayload:
    tenant_id: str
    call_id: str
    tool_call_id: str | None
    tool_name: str
    event_type: str
    final_state: str | None
    ok: bool | None
    duration_ms: float | None
    error_code: str | None
    payload_masked: dict


class AuditQueueWorker:
    def __init__(self, settings: Settings):
        self.batch_size = settings.audit_batch_size
        self.flush_interval_seconds = settings.audit_flush_interval_seconds
        self.queue: Queue[AuditEventPayload] = Queue(maxsize=settings.audit_queue_max_size)
        self._stop_event = Event()
        self._thread = Thread(target=self._run, name="audit-event-writer", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self, *, drain: bool = True, timeout_seconds: float = 2.0) -> None:
        if drain:
            self.wait_until_idle(timeout_seconds=timeout_seconds)
        self._stop_event.set()
        self._thread.join(timeout=timeout_seconds)

    def wait_until_idle(self, *, timeout_seconds: float = 2.0) -> bool:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if self.queue.unfinished_tasks == 0:
                return True
            time.sleep(0.01)
        return self.queue.unfinished_tasks == 0

    def _run(self) -> None:
        while not self._stop_event.is_set():
            batch = self._collect_batch()
            if not batch:
                continue
            _write_audit_events(batch)
            for _ in batch:
                self.queue.task_done()

    def _collect_batch(self) -> list[AuditEventPayload]:
        try:
            first = self.queue.get(timeout=self.flush_interval_seconds)
        except Empty:
            return []

        batch = [first]
        deadline = time.monotonic() + self.flush_interval_seconds
        while len(batch) < self.batch_size:
            remaining = max(0.0, deadline - time.monotonic())
            if remaining <= 0:
                break
            try:
                batch.append(self.queue.get(timeout=remaining))
            except Empty:
                break
        return batch


_worker_lock = Lock()
_worker: AuditQueueWorker | None = None
_worker_signature: tuple[int, int, float] | None = None


def mask_payload(value: Any) -> Any:
    """Mask sensitive fields before persisting payload snapshots."""
    if isinstance(value, dict):
        masked: dict[str, Any] = {}
        for key, item in value.items():
            key_lower = str(key).lower()
            if key_lower in SENSITIVE_KEYS:
                masked[key] = "***"
                continue
            if key_lower == "cpf" and isinstance(item, str):
                digits = "".join(ch for ch in item if ch.isdigit())
                masked[key] = f"***{digits[-4:]}" if digits else "***"
                continue
            masked[key] = mask_payload(item)
        return masked
    if isinstance(value, list):
        return [mask_payload(item) for item in value]
    return value


def _build_event_payload(
    *,
    tenant_id: str | None,
    call_id: str | None,
    tool_call_id: str | None = None,
    tool_name: str,
    event_type: str,
    final_state: str | None,
    ok: bool | None,
    duration_ms: float | None,
    error_code: str | None,
    payload: dict | None,
) -> AuditEventPayload:
    return AuditEventPayload(
        tenant_id=tenant_id or "unknown",
        call_id=call_id or "unknown",
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        event_type=event_type,
        final_state=final_state,
        ok=ok,
        duration_ms=duration_ms,
        error_code=error_code,
        payload_masked=mask_payload(payload or {}),
    )


def _write_audit_events(events: list[AuditEventPayload]) -> None:
    if not events:
        return

    session = SessionLocal()
    try:
        session.add_all(
            [
                CallEvent(
                    tenant_id=event.tenant_id,
                    call_id=event.call_id,
                    tool_call_id=event.tool_call_id,
                    tool_name=event.tool_name,
                    event_type=event.event_type,
                    final_state=event.final_state,
                    ok=event.ok,
                    duration_ms=event.duration_ms,
                    error_code=event.error_code,
                    payload_masked=event.payload_masked,
                )
                for event in events
            ]
        )
        session.commit()
        metrics_store.increment_counter("audit_events_written", len(events))
    except Exception as exc:
        session.rollback()
        metrics_store.increment_counter("audit_events_failed", len(events))
        sample = events[0]
        log.warning(
            "audit_store_failed",
            event_type="audit_error",
            tenant_id=sample.tenant_id,
            call_id=sample.call_id,
            tool_name=sample.tool_name,
            batch_size=len(events),
            reason=str(exc),
        )
    finally:
        session.close()


def _get_audit_worker(settings: Settings) -> AuditQueueWorker:
    global _worker, _worker_signature

    signature = (
        settings.audit_queue_max_size,
        settings.audit_batch_size,
        settings.audit_flush_interval_seconds,
    )
    with _worker_lock:
        if _worker is not None and _worker_signature == signature:
            return _worker
        if _worker is not None:
            _worker.stop(drain=True)
        _worker = AuditQueueWorker(settings)
        _worker_signature = signature
        _worker.start()
        return _worker


def stop_audit_worker() -> None:
    global _worker, _worker_signature

    with _worker_lock:
        if _worker is not None:
            _worker.stop(drain=True)
        _worker = None
        _worker_signature = None


def wait_for_audit_queue(timeout_seconds: float = 2.0) -> bool:
    with _worker_lock:
        worker = _worker
    if worker is None:
        return True
    return worker.wait_until_idle(timeout_seconds=timeout_seconds)


def record_call_event(
    *,
    settings: Settings,
    tenant_id: str | None,
    call_id: str | None,
    tool_call_id: str | None = None,
    tool_name: str,
    event_type: str,
    final_state: str | None,
    ok: bool | None,
    duration_ms: float | None,
    error_code: str | None,
    payload: dict | None,
) -> None:
    """Persist a call event when DB auditing is enabled."""
    if not settings.db_enabled:
        return

    event = _build_event_payload(
        tenant_id=tenant_id,
        call_id=call_id,
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        event_type=event_type,
        final_state=final_state,
        ok=ok,
        duration_ms=duration_ms,
        error_code=error_code,
        payload=payload,
    )

    if settings.audit_write_mode == "async":
        worker = _get_audit_worker(settings)
        try:
            worker.queue.put_nowait(event)
            metrics_store.increment_counter("audit_events_enqueued")
        except Full:
            metrics_store.increment_counter("audit_events_dropped")
            log.warning(
                "audit_queue_full",
                event_type="audit_error",
                tenant_id=event.tenant_id,
                call_id=event.call_id,
                tool_name=event.tool_name,
                queue_max_size=settings.audit_queue_max_size,
            )
        return

    _write_audit_events([event])
