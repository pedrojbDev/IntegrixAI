import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.core.ops.fx_service import PtaxService
from app.db import Base
from app.models.exchange_rate import ExchangeRate


class PtaxServiceTests(unittest.TestCase):
    def _session_local(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        return sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def test_weekend_or_holiday_uses_previous_available_close(self) -> None:
        session_local = self._session_local()
        service = PtaxService(Settings(_env_file=None))
        with session_local() as session:
            session.add(
                ExchangeRate(
                    rate_date=datetime(2026, 7, 3).date(),
                    base_currency="USD",
                    quote_currency="BRL",
                    sale_rate=Decimal("5.40"),
                    source="BCB_PTAX",
                    is_provisional=False,
                )
            )
            session.commit()

            rate_date, rate, provisional = service.rate_for_call(
                session,
                datetime(2026, 7, 5, 15, tzinfo=timezone.utc),
            )

        self.assertEqual(datetime(2026, 7, 3).date(), rate_date)
        self.assertEqual(Decimal("5.40000000"), rate)
        self.assertFalse(provisional)

    def test_missing_history_keeps_brl_unavailable(self) -> None:
        service = PtaxService(Settings(_env_file=None))
        with self._session_local()() as session:
            rate_date, rate, provisional = service.rate_for_call(
                session,
                datetime(2026, 7, 5, 15, tzinfo=timezone.utc),
            )

        self.assertIsNone(rate_date)
        self.assertIsNone(rate)
        self.assertFalse(provisional)

    def test_current_business_day_fallback_is_provisional(self) -> None:
        session_local = self._session_local()
        service = PtaxService(Settings(_env_file=None))
        brasilia_today = datetime.now(timezone.utc).astimezone(
            ZoneInfo("America/Sao_Paulo")
        ).date()
        previous = brasilia_today - timedelta(days=1)
        while previous.weekday() >= 5:
            previous -= timedelta(days=1)
        with session_local() as session:
            session.add(
                ExchangeRate(
                    rate_date=previous,
                    base_currency="USD",
                    quote_currency="BRL",
                    sale_rate=Decimal("5.30"),
                    source="BCB_PTAX",
                    is_provisional=False,
                )
            )
            session.commit()
            _, _, provisional = service.rate_for_call(
                session,
                datetime.now(timezone.utc),
            )

        if brasilia_today.weekday() < 5:
            self.assertTrue(provisional)
        else:
            self.assertFalse(provisional)

    def test_provisional_rate_is_replaced_by_closing_rate(self) -> None:
        session_local = self._session_local()
        service = PtaxService(Settings(_env_file=None))
        rate_date = datetime(2026, 7, 6).date()
        with session_local() as session:
            service._upsert_rates(
                session,
                [(rate_date, Decimal("5.10"), True)],
            )
            session.commit()
            service._upsert_rates(
                session,
                [(rate_date, Decimal("5.20"), False)],
            )
            session.commit()
            row = session.get(ExchangeRate, (rate_date, "USD", "BRL"))

        self.assertEqual(Decimal("5.20000000"), row.sale_rate)
        self.assertFalse(row.is_provisional)


if __name__ == "__main__":
    unittest.main()
