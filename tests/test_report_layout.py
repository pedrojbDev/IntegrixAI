import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.ops import report_service as report
from app.db import Base
from app.models.call_event import CallEvent
from app.models.vapi_call_cost import VapiCallCost


def story_text(items):
    for item in items:
        if isinstance(item, Paragraph):
            yield item.getPlainText()
        elif isinstance(item, Table):
            for row in item._cellvalues:
                for cell in row:
                    yield from story_text(cell if isinstance(cell, (list, tuple)) else [cell])


class ReportLayoutTests(unittest.TestCase):
    def test_metric_cards_fit_printable_width_for_any_number_of_metrics(self):
        width = A4[0] - 36 * mm - 12  # SimpleDocTemplate's frame padding.
        for count in (1, 6, 7, 8, 9, 12):
            with self.subTest(count=count):
                metrics = [(f"Indicador {i}", "123", "Detalhe", report.NAVY) for i in range(count)]
                grid = report._metric_grid(metrics, report._styles())
                actual_width, _ = grid.wrap(width, 700)
                self.assertLessEqual(actual_width, width + 0.01)
                self.assertEqual(3, grid._ncols)
                self.assertEqual((count + 2) // 3, grid._nrows)

    def test_large_currency_stays_on_one_line_inside_card(self):
        styles = report._styles()
        card = report._metric_card("Custo convertido", "R$ 1.234.567.890,12", "PTAX", report.BLUE, styles)
        card.wrap(160, 700)
        value = card._cellvalues[1][0][0]
        self.assertEqual(1, len(value.blPara.lines))

    def test_missing_costs_are_not_presented_as_zero_component_costs(self):
        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        Base.metadata.create_all(engine)
        captured = []
        build = SimpleDocTemplate.build

        def inspect_story(document, story, **kwargs):
            captured.extend(story_text(story))
            result = build(document, story, **kwargs)
            self.assertEqual(3, document.page)
            return result

        with Session(engine) as session, patch.object(SimpleDocTemplate, "build", inspect_story):
            report.build_operational_report_pdf(session, period_days=7, tenant_id="tenant_a", assistant_id=None)
        text = "\n".join(captured)
        self.assertIn("Sem componentes reportados", text)
        self.assertIn("Sem duração", text)
        self.assertNotIn("US$ 0,00", text)

    def test_report_explains_outcomes_and_financial_quality_with_tenant_scope(self):
        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        Base.metadata.create_all(engine)
        now = datetime.now(timezone.utc) - timedelta(hours=1)
        captured = []
        build = SimpleDocTemplate.build

        def inspect_story(document, story, **kwargs):
            captured.extend(story_text(story))
            return build(document, story, **kwargs)

        with Session(engine) as session:
            for tenant, assistant, call_id, tool, state in (
                ("tenant_a", "assistant_a", "automatic", "search_providers", "RESOLVIDA_AUTOMATICO"),
                ("tenant_a", "assistant_a", "handoff", "handoff_human", "TRANSFERIDA_HUMANO"),
                ("tenant_b", "assistant_a", "private", "PRIVATE_OTHER_TENANT", "RESOLVIDA_AUTOMATICO"),
                ("tenant_a", "assistant_b", "private_assistant", "PRIVATE_OTHER_ASSISTANT", "RESOLVIDA_AUTOMATICO"),
            ):
                session.add(CallEvent(tenant_id=tenant, call_id=call_id, tool_call_id=call_id,
                                      tool_name=tool, event_type="tool_completed", ok=True,
                                      final_state=state, duration_ms=1200, created_at=now))
                session.add(VapiCallCost(tenant_id=tenant, call_id=call_id, started_at=now,
                                         assistant_id=assistant, is_verified=True,
                                         duration_seconds=120, cost_total_usd=1.5,
                                         cost_total_brl=None, fx_is_provisional=False))
            session.commit()
            with patch.object(SimpleDocTemplate, "build", inspect_story):
                pdf = report.build_operational_report_pdf(
                    session, period_days=7, tenant_id="tenant_a", assistant_id="assistant_a")

        text = "\n".join(captured)
        self.assertTrue(pdf.startswith(b"%PDF-"))
        for expected in ("Sucesso do agente", "Resolução automática", "50,0%", "100,0%",
                         "Duração média", "2 min 00 s", "US$ 3,00", "PTAX",
                         "Chamadas sem conversão", "Sem conversão completa",
                         "Falhas técnicas", "Como ler os indicadores"):
            self.assertIn(expected, text)
        self.assertNotIn("PRIVATE_OTHER_TENANT", text)
        self.assertNotIn("PRIVATE_OTHER_ASSISTANT", text)
        self.assertNotIn("R$ 0,00", text)


if __name__ == "__main__":
    unittest.main()
