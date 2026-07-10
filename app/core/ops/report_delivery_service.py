from __future__ import annotations

import smtplib
import ssl
from collections.abc import Callable
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...config import Settings
from ...db import SessionLocal
from ...logging import get_logger
from ...models.ops_sync_state import OpsSyncState
from .report_service import build_operational_report_pdf

BRASILIA_TIMEZONE = ZoneInfo("America/Sao_Paulo")
DAILY_REPORT_STATE_KEY = "daily_operational_report_email"
DAILY_REPORT_ADVISORY_LOCK_ID = 732_118_407

log = get_logger()

EmailSender = Callable[[Settings, bytes, str], None]
SessionFactory = Callable[[], Session]


def run_daily_operational_report_if_due(
    settings: Settings,
    *,
    now: datetime | None = None,
    session_factory: SessionFactory = SessionLocal,
    email_sender: EmailSender | None = None,
) -> bool:
    """Send one scheduled report per Brasilia calendar day across all app workers."""
    if not settings.daily_report_enabled:
        return False

    reference_time = _as_utc(now or datetime.now(timezone.utc))
    brasilia_now = reference_time.astimezone(BRASILIA_TIMEZONE)
    if brasilia_now.hour < settings.daily_report_hour_brasilia:
        return False

    session = session_factory()
    try:
        if not _try_acquire_delivery_lock(session):
            return False

        state = session.get(OpsSyncState, DAILY_REPORT_STATE_KEY)
        if state and state.last_synced_at:
            last_delivery = _as_utc(state.last_synced_at).astimezone(BRASILIA_TIMEZONE)
            if last_delivery.date() == brasilia_now.date():
                return False

        report_pdf = build_operational_report_pdf(
            session,
            period_days=settings.daily_report_period_days,
            tenant_id=settings.daily_report_tenant_id,
            assistant_id=settings.daily_report_assistant_id,
        )
        filename = f"relatorio-operacional-{brasilia_now.date().isoformat()}.pdf"
        (email_sender or send_operational_report_email)(settings, report_pdf, filename)

        if state is None:
            state = OpsSyncState(provider=DAILY_REPORT_STATE_KEY)
            session.add(state)
        state.last_synced_at = reference_time
        state.updated_at = reference_time
        session.commit()
        log.info(
            "daily_operational_report_sent",
            event_type="ops_report_delivery",
            tenant_id=settings.daily_report_tenant_id,
            assistant_id=settings.daily_report_assistant_id,
            period_days=settings.daily_report_period_days,
            recipient_count=len(settings.daily_report_recipient_list),
            scheduled_hour_brasilia=settings.daily_report_hour_brasilia,
        )
        return True
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def send_operational_report_email(settings: Settings, report_pdf: bytes, filename: str) -> None:
    """Deliver an operational report through the configured SMTP provider."""
    message = EmailMessage()
    message["Subject"] = "Integrix AI - Relatorio operacional diario"
    message["From"] = settings.smtp_from_email or ""
    message["To"] = ", ".join(settings.daily_report_recipient_list)
    message.set_content(
        "Em anexo esta o relatorio operacional diario gerado pela Integrix AI."
    )
    message.add_attachment(
        report_pdf,
        maintype="application",
        subtype="pdf",
        filename=filename,
    )

    context = ssl.create_default_context()
    if settings.smtp_use_ssl:
        smtp_client: Any = smtplib.SMTP_SSL(
            settings.smtp_host,
            settings.smtp_port,
            timeout=30,
            context=context,
        )
    else:
        smtp_client = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30)

    with smtp_client as client:
        client.ehlo()
        if settings.smtp_use_starttls:
            client.starttls(context=context)
            client.ehlo()
        if settings.smtp_username and settings.smtp_password:
            client.login(settings.smtp_username, settings.smtp_password)
        client.send_message(message)


def _try_acquire_delivery_lock(session: Session) -> bool:
    bind = session.get_bind()
    if bind.dialect.name != "postgresql":
        return True
    return bool(
        session.execute(select(func.pg_try_advisory_xact_lock(DAILY_REPORT_ADVISORY_LOCK_ID))).scalar()
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
