"""Coordinate searches across requests and processes without holding a state transaction.

The synchronous worker owns the session advisory lock until the actual provider
call ends, even if its asyncio caller times out or disconnects. SQLite locks are
only a local test/development fallback; PostgreSQL is the production authority.
"""
from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from threading import Lock
from weakref import WeakValueDictionary

from sqlalchemy import text
from sqlalchemy.orm import Session

from ...logging import get_logger
from ...models.vapi_call_slot_state import VapiCallSlotState
from ...models.vapi_search_execution import VapiSearchExecution
from ...platform.services.vapi_conversation import keyed_hmac, lock_call
from . import slot_guard
from .integration.client import BusinessRuleError

log = get_logger()
_local_locks = WeakValueDictionary()
_local_guard = Lock()


def _blocked(code, action, message, *, retryable=False):
    return BusinessRuleError(code=code, field=None, message=message, attempt=0,
                             retryable=retryable, handoff_after_retry=False,
                             details={'recovery_action': action})


@contextmanager
def _call_lock(sessions, tenant_id, call_id):
    namespace = f'vapi-search:{tenant_id}:{call_id}'
    with sessions() as session:
        engine = session.get_bind()
    if engine.dialect.name != 'postgresql':
        with _local_guard:
            lock = _local_locks.setdefault(namespace, Lock())
        acquired = lock.acquire(blocking=False)
        try:
            if acquired:
                with engine.connect() as connection:
                    yield connection
            else:
                yield None
        finally:
            if acquired:
                lock.release()
        return
    key = int.from_bytes(hashlib.sha256(namespace.encode()).digest()[:8], 'big', signed=True)
    with engine.connect() as connection:
        acquired = bool(connection.scalar(text('SELECT pg_try_advisory_lock(:key)'), {'key': key}))
        connection.commit()  # The session lock survives; no transaction spans HTTP.
        try:
            yield connection if acquired else None
        finally:
            if acquired:
                try:
                    connection.rollback()
                    released = connection.scalar(text('SELECT pg_advisory_unlock(:key)'), {'key': key})
                    connection.commit()
                    if not released:
                        connection.invalidate()
                except BaseException:
                    connection.invalidate()
                    raise


def _evidence(session, tenant_id, call_id):
    state = session.get(VapiCallSlotState, (tenant_id, call_id))
    if state is None or slot_guard._is_expired(state.expires_at):
        raise slot_guard._unconfirmed('cpf')
    meta = state.conversation_meta or {}
    if meta.get('terminal'):
        raise _blocked('CALL_TERMINAL', 'stop', 'Ligacao encerrada')
    # Changes unrelated to fields (e.g. tool delivery) must not stale a result.
    return json.dumps({'fields': meta.get('field_turns'), 'pending': meta.get('pending'),
                       'refresh': meta.get('refresh_turn'), 'cpf': state.cpf_hmac,
                       'city': state.city_term_hmacs, 'specialty': state.specialty_term_hmacs},
                      sort_keys=True), meta.get('refresh_turn') or ''


def execute_search(*, settings, tenant_id, call_id, signature, validate, execute,
                   complete=None, recover=None, emit=None):
    sessions = slot_guard.SessionLocal
    # Use the lock-owning connection for every short transaction: workers must
    # never need a second pooled connection to release their first one.
    with _call_lock(sessions, tenant_id, call_id) as connection:
        if connection is None:
            log.info('provider_search_inflight_blocked', tenant_id=tenant_id, call_id=call_id)
            raise _blocked('BATCH_DEFERRED', 'wait_current_search',
                           'Aguarde a busca atual antes da proxima', retryable=True)
        with Session(bind=connection) as session, session.begin():
            lock_call(session, tenant_id, call_id)
            validate(session)
            evidence, refresh = _evidence(session, tenant_id, call_id)
            key = (tenant_id, call_id, keyed_hmac(settings.vapi_slot_state_hmac_secret, signature),
                   keyed_hmac(settings.vapi_slot_state_hmac_secret, 'refresh:' + refresh))
            row = session.get(VapiSearchExecution, key)
            if row is not None:
                if row.status == 'succeeded' and not slot_guard._is_expired(row.expires_at):
                    if complete:
                        complete(session)
                    if emit:
                        emit(session, 'provider_search_result_reused', ok=True,
                             final_state=row.final_state,
                             payload={'reused_result': True,
                                      'provider_count': len((row.result_payload or {}).get('providers', []))})
                    log.info('provider_search_result_reused', tenant_id=tenant_id, call_id=call_id)
                    return {**row.result_payload, 'reused_result': True}, row.final_state
                # A running row whose session lock is gone is indeterminate.
                raise _blocked('SEARCH_ALREADY_ATTEMPTED', 'offer_handoff',
                               'Busca ja tentada; ofereca atendimento humano ou aguarde nova solicitacao')
            session.add(VapiSearchExecution(tenant_id=key[0], call_id=key[1], query_hmac=key[2],
                refresh_hmac=key[3], status='running',
                expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.vapi_slot_state_retention_hours)))
            if emit:
                emit(session, 'provider_search_upstream_started')
        failure = None
        try:
            result, final_state = execute()
        except BaseException as exc:
            failure = exc
        with Session(bind=connection) as session, session.begin():
            lock_call(session, tenant_id, call_id)
            discarded = False
            try:
                validate(session)
                if _evidence(session, tenant_id, call_id)[0] != evidence:
                    raise _blocked('SEARCH_STATE_CHANGED', 'wait_current_search',
                                   'Dados alterados durante a busca; utilize os dados atuais', retryable=True)
            except BusinessRuleError as exc:
                failure = exc
                discarded = True
            row = session.get(VapiSearchExecution, key)
            if row is None:
                raise _blocked('SEARCH_STATE_CHANGED', 'stop', 'Busca expirada')
            if failure is not None:
                if recover and isinstance(failure, BusinessRuleError):
                    failure = recover(failure, session, discarded)
                row.status = 'discarded' if discarded else 'failed'
            else:
                if complete:
                    complete(session)
                row.status = 'succeeded'
                row.result_payload = result
                row.final_state = final_state
                if emit:
                    emit(session, 'provider_search_completed', ok=True,
                         final_state=final_state,
                         payload={'provider_count': len((result or {}).get('providers', []))})
        if failure is not None:
            log.info('provider_search_result_discarded' if discarded else 'provider_search_failed',
                     tenant_id=tenant_id, call_id=call_id)
            raise failure
        return result, final_state
