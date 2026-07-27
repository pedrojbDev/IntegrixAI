from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ...config import Settings
from ...models.exchange_rate import ExchangeRate

BRASILIA_TIMEZONE = ZoneInfo("America/Sao_Paulo")


class PtaxService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def ensure_rates(self, session: Session, dates: set[date]) -> int:
        if not dates:
            return 0
        start = min(dates) - timedelta(days=7)
        end = max(dates)
        existing_rows = session.execute(
            select(ExchangeRate.rate_date, ExchangeRate.is_provisional).where(
                ExchangeRate.base_currency == "USD",
                ExchangeRate.quote_currency == "BRL",
                ExchangeRate.rate_date >= start,
                ExchangeRate.rate_date <= end,
            )
        ).all()
        existing = {row.rate_date for row in existing_rows if not row.is_provisional}
        requested_business_dates = {
            current
            for current in _date_range(start, end)
            if current.weekday() < 5
        }
        missing = requested_business_dates - existing
        if not missing:
            return 0
        rates = self._fetch_period(min(missing), max(missing))
        self._upsert_rates(session, rates)
        return len(rates)

    def rate_for_call(
        self,
        session: Session,
        call_started_at: datetime | None,
    ) -> tuple[date | None, Decimal | None, bool]:
        if call_started_at is None:
            return None, None, False
        call_date = _as_utc(call_started_at).astimezone(BRASILIA_TIMEZONE).date()
        row = session.execute(
            select(ExchangeRate)
            .where(
                ExchangeRate.base_currency == "USD",
                ExchangeRate.quote_currency == "BRL",
                ExchangeRate.rate_date <= call_date,
            )
            .order_by(ExchangeRate.rate_date.desc())
            .limit(1)
        ).scalar_one_or_none()
        if row is None:
            return None, None, False
        today = datetime.now(timezone.utc).astimezone(BRASILIA_TIMEZONE).date()
        provisional = bool(row.is_provisional) or (
            call_date == today and call_date.weekday() < 5 and row.rate_date < call_date
        )
        return row.rate_date, Decimal(row.sale_rate), provisional

    def _fetch_period(self, start: date, end: date) -> list[tuple[date, Decimal, bool]]:
        start_text = start.strftime("%m-%d-%Y")
        end_text = end.strftime("%m-%d-%Y")
        endpoint = (
            "CotacaoDolarPeriodo(dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)"
        )
        params = {
            "@dataInicial": f"'{start_text}'",
            "@dataFinalCotacao": f"'{end_text}'",
            "$format": "json",
            "$select": "cotacaoVenda,dataHoraCotacao,tipoBoletim",
        }
        url = f"{self.settings.ptax_base_url.rstrip('/')}/{endpoint}"
        try:
            response = httpx.get(url, params=params, timeout=15.0)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise RuntimeError("BCB PTAX request failed") from exc
        items = payload.get("value", []) if isinstance(payload, dict) else []
        latest_by_date: dict[date, tuple[datetime, Decimal, bool]] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            parsed_at = _parse_ptax_datetime(item.get("dataHoraCotacao"))
            try:
                rate = Decimal(str(item.get("cotacaoVenda")))
            except (InvalidOperation, TypeError):
                continue
            if parsed_at is None or rate <= 0:
                continue
            current = latest_by_date.get(parsed_at.date())
            is_close = str(item.get("tipoBoletim", "")).lower() == "fechamento"
            sort_time = parsed_at + (timedelta(days=1) if is_close else timedelta())
            if current is None or sort_time > current[0]:
                latest_by_date[parsed_at.date()] = (sort_time, rate, not is_close)
        return sorted(
            (rate_date, value[1], value[2])
            for rate_date, value in latest_by_date.items()
        )

    @staticmethod
    def _upsert_rates(session: Session, rates: list[tuple[date, Decimal, bool]]) -> None:
        if not rates:
            return
        now = datetime.now(timezone.utc)
        rows = [
            {
                "rate_date": rate_date,
                "base_currency": "USD",
                "quote_currency": "BRL",
                "sale_rate": rate,
                "source": "BCB_PTAX",
                "is_provisional": provisional,
                "fetched_at": now,
            }
            for rate_date, rate, provisional in rates
        ]
        if session.bind and session.bind.dialect.name == "postgresql":
            insert_stmt = pg_insert(ExchangeRate).values(rows)
            excluded = insert_stmt.excluded
            session.execute(
                insert_stmt.on_conflict_do_update(
                    index_elements=[
                        ExchangeRate.rate_date,
                        ExchangeRate.base_currency,
                        ExchangeRate.quote_currency,
                    ],
                    set_={
                        "sale_rate": excluded.sale_rate,
                        "source": excluded.source,
                        "is_provisional": excluded.is_provisional,
                        "fetched_at": excluded.fetched_at,
                    },
                )
            )
            return
        for row in rows:
            key = (row["rate_date"], row["base_currency"], row["quote_currency"])
            existing = session.get(ExchangeRate, key)
            if existing is None:
                session.add(ExchangeRate(**row))
            else:
                existing.sale_rate = row["sale_rate"]
                existing.source = row["source"]
                existing.is_provisional = row["is_provisional"]
                existing.fetched_at = now


def _date_range(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_ptax_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=BRASILIA_TIMEZONE)
    return parsed.astimezone(BRASILIA_TIMEZONE)
