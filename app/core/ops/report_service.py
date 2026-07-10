from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from math import ceil
from typing import Any
from xml.sax.saxutils import escape

from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from .dashboard_service import get_costs, get_health, get_overview, get_tools

REPORT_WINDOWS = {7: "7d", 15: "15d", 30: "30d", 90: "90d"}

NAVY = HexColor("#102A43")
BLUE = HexColor("#146C94")
TEAL = HexColor("#0F9D8A")
AMBER = HexColor("#D97706")
SLATE = HexColor("#52616B")
MUTED = HexColor("#7B8794")
PAPER = HexColor("#F7FAFC")
LINE = HexColor("#D9E2EC")


def build_operational_report_pdf(
    session: Session,
    *,
    period_days: int,
    tenant_id: str | None,
    assistant_id: str | None,
) -> bytes:
    """Build a tenant-aware operational PDF from the same aggregates as the dashboard."""
    try:
        window = REPORT_WINDOWS[period_days]
    except KeyError as exc:
        raise ValueError("period_days deve ser 7, 15, 30 ou 90") from exc

    overview = get_overview(
        session,
        window=window,
        tenant_id=tenant_id,
        assistant_id=assistant_id,
    )
    costs = get_costs(
        session,
        window=window,
        tenant_id=tenant_id,
        assistant_id=assistant_id,
    )
    tools = get_tools(
        session,
        window=window,
        tenant_id=tenant_id,
        assistant_id=assistant_id,
    )
    health = get_health(
        session,
        window=window,
        tenant_id=tenant_id,
        assistant_id=assistant_id,
    )

    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=34 * mm,
        bottomMargin=20 * mm,
        title=f"Relatorio operacional - {period_days} dias",
        author="Integrix AI",
    )
    styles = _styles()
    total_calls = int(overview["kpis"]["total_calls"])
    success_calls = int(overview["kpis"]["success_calls"])
    handoff_calls = int(overview["kpis"]["handoff_calls"])
    costs_summary = costs["summary"]
    generated_at = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

    scope = [
        f"Tenant: <b>{escape(tenant_id or 'Visao global autorizada')}</b>",
        f"Assistant: <b>{escape(assistant_id or 'Todos')}</b>",
    ]
    story: list[Any] = [
        Paragraph("Relatorio operacional", styles["title"]),
        Paragraph(
            f"Periodo analisado: <b>ultimos {period_days} dias</b> &nbsp;|&nbsp; Gerado em {generated_at}",
            styles["subtitle"],
        ),
        Spacer(1, 5 * mm),
        Table(
            [[Paragraph(scope[0], styles["scope"]), Paragraph(scope[1], styles["scope"])]],
            colWidths=[85 * mm, 85 * mm],
            style=TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), PAPER),
                    ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4 * mm),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4 * mm),
                    ("TOPPADDING", (0, 0), (-1, -1), 3.5 * mm),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5 * mm),
                ]
            ),
        ),
        Spacer(1, 6 * mm),
        Paragraph("Visao executiva", styles["section"]),
        Paragraph(_executive_summary(total_calls, success_calls, handoff_calls, health), styles["body"]),
        Spacer(1, 4 * mm),
        _metric_grid(
            [
                ("Calls analisadas", _number(total_calls), "volume no periodo", NAVY),
                ("Resolucao automatica", _percent(success_calls, total_calls), f"{_number(success_calls)} calls", TEAL),
                ("Handoff", _percent(handoff_calls, total_calls), f"{_number(handoff_calls)} transferencias", AMBER),
                ("Custo total", _currency(float(costs_summary["total_cost_usd"])), "custos Vapi sincronizados", BLUE),
                (
                    "Custo medio por call",
                    _currency(float(costs_summary["avg_cost_per_call_usd"])),
                    f"{_number(int(costs_summary['calls_with_cost']))} calls com custo",
                    BLUE,
                ),
                (
                    "Tempo medio da tool",
                    _duration_ms(float(overview["kpis"]["avg_duration_ms"])),
                    "ultima tool concluida por call",
                    NAVY,
                ),
            ],
            styles,
        ),
        Spacer(1, 6 * mm),
        Paragraph("Evolucao do periodo", styles["section"]),
        Paragraph("Volume de chamadas e transferencias agrupado para leitura executiva.", styles["section_note"]),
        Spacer(1, 2 * mm),
        _volume_chart(overview["series"]),
        Spacer(1, 5 * mm),
        KeepTogether(
            [
                Paragraph("Saude operacional", styles["section"]),
                _health_table(health, costs_summary, total_calls, styles),
            ]
        ),
        Spacer(1, 6 * mm),
        Paragraph("Desempenho por tool", styles["section"]),
        Paragraph("Chamadas concluidas, resultado, tempo e custo atribuido por ferramenta.", styles["section_note"]),
        Spacer(1, 2 * mm),
        _tools_table(tools["items"], styles),
    ]
    document.build(story, onFirstPage=_draw_page_chrome, onLaterPages=_draw_page_chrome)
    return output.getvalue()


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "ReportTitle",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=27,
            textColor=NAVY,
            spaceAfter=2 * mm,
        ),
        "subtitle": ParagraphStyle(
            "ReportSubtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=14,
            textColor=SLATE,
        ),
        "scope": ParagraphStyle(
            "ReportScope",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=NAVY,
        ),
        "section": ParagraphStyle(
            "ReportSection",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=17,
            textColor=NAVY,
            spaceAfter=1 * mm,
        ),
        "section_note": ParagraphStyle(
            "ReportSectionNote",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=11,
            textColor=MUTED,
        ),
        "body": ParagraphStyle(
            "ReportBody",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=14,
            textColor=SLATE,
        ),
        "metric_label": ParagraphStyle(
            "MetricLabel",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.5,
            leading=10,
            textColor=MUTED,
        ),
        "metric_value": ParagraphStyle(
            "MetricValue",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=19,
            textColor=NAVY,
        ),
        "metric_detail": ParagraphStyle(
            "MetricDetail",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7.2,
            leading=9,
            textColor=SLATE,
        ),
        "table_header": ParagraphStyle(
            "TableHeader",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7,
            leading=8.5,
            textColor=colors.white,
        ),
        "table_cell": ParagraphStyle(
            "TableCell",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7.4,
            leading=9,
            textColor=NAVY,
        ),
    }


def _metric_grid(metrics: list[tuple[str, str, str, colors.Color]], styles: dict[str, ParagraphStyle]) -> Table:
    cards = [_metric_card(label, value, detail, accent, styles) for label, value, detail, accent in metrics]
    grid = Table([cards[:3], cards[3:]], colWidths=[57 * mm, 57 * mm, 57 * mm], hAlign="LEFT")
    grid.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2.5 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5 * mm),
            ]
        )
    )
    return grid


def _metric_card(
    label: str,
    value: str,
    detail: str,
    accent: colors.Color,
    styles: dict[str, ParagraphStyle],
) -> Table:
    card = Table(
        [
            [Paragraph(escape(label.upper()), styles["metric_label"])],
            [Paragraph(escape(value), styles["metric_value"])],
            [Paragraph(escape(detail), styles["metric_detail"])],
        ],
        colWidths=[54.5 * mm],
    )
    card.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PAPER),
                ("LINEBEFORE", (0, 0), (0, -1), 2.5, accent),
                ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 3.2 * mm),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm),
                ("TOPPADDING", (0, 0), (-1, 0), 3 * mm),
                ("BOTTOMPADDING", (0, -1), (-1, -1), 3.2 * mm),
            ]
        )
    )
    return card


def _volume_chart(series: list[dict[str, Any]]) -> Drawing:
    width = 174 * mm
    height = 57 * mm
    drawing = Drawing(width, height)
    drawing.add(Rect(0, 0, width, height, fillColor=PAPER, strokeColor=LINE, strokeWidth=0.5))
    groups = _group_series(series)
    if not groups:
        drawing.add(
            String(
                width / 2,
                height / 2,
                "Sem chamadas concluidas no periodo selecionado.",
                fontName="Helvetica",
                fontSize=9,
                fillColor=MUTED,
                textAnchor="middle",
            )
        )
        return drawing

    chart_left = 12 * mm
    chart_bottom = 12 * mm
    chart_width = width - 20 * mm
    chart_height = height - 22 * mm
    maximum = max(max(group["calls"], group["handoffs"]) for group in groups) or 1
    for step in range(1, 5):
        y = chart_bottom + chart_height * step / 4
        drawing.add(Line(chart_left, y, chart_left + chart_width, y, strokeColor=LINE, strokeWidth=0.35))
        drawing.add(
            String(
                chart_left - 2 * mm,
                y - 2,
                str(round(maximum * step / 4)),
                fontName="Helvetica",
                fontSize=6.5,
                fillColor=MUTED,
                textAnchor="end",
            )
        )

    step_width = chart_width / len(groups)
    for index, group in enumerate(groups):
        origin_x = chart_left + index * step_width
        call_width = max(2, step_width * 0.35)
        handoff_width = max(2, step_width * 0.2)
        call_height = chart_height * group["calls"] / maximum
        handoff_height = chart_height * group["handoffs"] / maximum
        drawing.add(Rect(origin_x + step_width * 0.18, chart_bottom, call_width, call_height, fillColor=BLUE, strokeColor=None))
        drawing.add(
            Rect(
                origin_x + step_width * 0.58,
                chart_bottom,
                handoff_width,
                handoff_height,
                fillColor=AMBER,
                strokeColor=None,
            )
        )
        drawing.add(
            String(
                origin_x + step_width / 2,
                4 * mm,
                group["label"],
                fontName="Helvetica",
                fontSize=6.2,
                fillColor=MUTED,
                textAnchor="middle",
            )
        )
    drawing.add(String(chart_left, height - 4 * mm, "Calls", fontName="Helvetica-Bold", fontSize=7, fillColor=BLUE))
    drawing.add(String(chart_left + 14 * mm, height - 4 * mm, "Handoff", fontName="Helvetica-Bold", fontSize=7, fillColor=AMBER))
    return drawing


def _group_series(series: list[dict[str, Any]], max_groups: int = 12) -> list[dict[str, Any]]:
    if not series:
        return []
    group_size = max(1, ceil(len(series) / max_groups))
    grouped: list[dict[str, Any]] = []
    for index in range(0, len(series), group_size):
        items = series[index : index + group_size]
        first_timestamp = str(items[0].get("timestamp") or "")
        try:
            label = datetime.fromisoformat(first_timestamp).strftime("%d/%m")
        except ValueError:
            label = str(index + 1)
        grouped.append(
            {
                "label": label,
                "calls": sum(int(item.get("calls") or 0) for item in items),
                "handoffs": sum(int(item.get("handoffs") or 0) for item in items),
            }
        )
    return grouped


def _health_table(
    health: dict[str, Any],
    costs_summary: dict[str, Any],
    total_calls: int,
    styles: dict[str, ParagraphStyle],
) -> Table:
    counters = health["counters"]
    rows = [
        ["Estado", _health_label(str(health["health_state"]))],
        ["Atualizacao de custos", str(health["sync"]["freshness_state"]).capitalize()],
        ["Cobertura de custo", _percent(int(costs_summary["calls_with_cost"]), total_calls)],
        ["Erros de negocio repetidos", _number(int(counters["repeated_business_errors"]))],
        ["Reentregas idempotentes", _number(int(counters["idempotency_hits"]))],
    ]
    data = [
        [
            Paragraph("INDICADOR", styles["table_header"]),
            Paragraph("LEITURA", styles["table_header"]),
        ]
    ] + [
        [Paragraph(escape(label), styles["table_cell"]), Paragraph(escape(value), styles["table_cell"])]
        for label, value in rows
    ]
    table = Table(data, colWidths=[72 * mm, 102 * mm], hAlign="LEFT", repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("BACKGROUND", (0, 1), (-1, -1), PAPER),
                ("GRID", (0, 0), (-1, -1), 0.35, LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 2.5 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5 * mm),
            ]
        )
    )
    return table


def _tools_table(items: list[dict[str, Any]], styles: dict[str, ParagraphStyle]) -> Table:
    headers = ["TOOL", "CALLS", "RESOLVIDAS", "FALHAS", "HANDOFF", "TEMPO", "CUSTO", "CUSTO/CALL"]
    data: list[list[Paragraph]] = [[Paragraph(header, styles["table_header"]) for header in headers]]
    if not items:
        data.append(
            [Paragraph("Nenhuma tool concluida no periodo selecionado.", styles["table_cell"])]
            + [Paragraph("", styles["table_cell"]) for _ in range(7)]
        )
    else:
        for item in items:
            data.append(
                [
                    Paragraph(escape(str(item["tool_name"])), styles["table_cell"]),
                    Paragraph(_number(int(item["total_calls"])), styles["table_cell"]),
                    Paragraph(_number(int(item["success_calls"])), styles["table_cell"]),
                    Paragraph(_number(int(item["failed_calls"])), styles["table_cell"]),
                    Paragraph(_number(int(item["handoff_calls"])), styles["table_cell"]),
                    Paragraph(_duration_ms(float(item["avg_duration_ms"])), styles["table_cell"]),
                    Paragraph(_currency(float(item["total_cost_usd"])), styles["table_cell"]),
                    Paragraph(_currency(float(item["avg_cost_per_call_usd"])), styles["table_cell"]),
                ]
            )
    table = Table(
        data,
        colWidths=[43 * mm, 14 * mm, 18 * mm, 15 * mm, 17 * mm, 20 * mm, 23 * mm, 24 * mm],
        hAlign="LEFT",
        repeatRows=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PAPER]),
                ("GRID", (0, 0), (-1, -1), 0.3, LINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 2 * mm),
                ("RIGHTPADDING", (0, 0), (-1, -1), 1.5 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 2.2 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2 * mm),
            ]
        )
    )
    return table


def _draw_page_chrome(canvas, document) -> None:
    canvas.saveState()
    page_width, page_height = A4
    canvas.setFillColor(colors.white)
    canvas.rect(0, 0, page_width, page_height, fill=1, stroke=0)
    canvas.setFillColor(NAVY)
    canvas.rect(0, page_height - 22 * mm, page_width, 22 * mm, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 10)
    canvas.drawString(18 * mm, page_height - 13 * mm, "INTEGRIX AI")
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(page_width - 18 * mm, page_height - 13 * mm, "RELATORIO OPERACIONAL")
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.5)
    canvas.line(18 * mm, 13 * mm, page_width - 18 * mm, 13 * mm)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(18 * mm, 8 * mm, "Integrix Ops Console - dados operacionais agregados")
    canvas.drawRightString(page_width - 18 * mm, 8 * mm, f"Pagina {canvas.getPageNumber()}")
    canvas.restoreState()


def _executive_summary(
    total_calls: int,
    success_calls: int,
    handoff_calls: int,
    health: dict[str, Any],
) -> str:
    if total_calls == 0:
        return "Nao ha calls concluidas para os filtros e periodo selecionados."
    return (
        f"Foram analisadas <b>{_number(total_calls)} calls</b>, com <b>{_percent(success_calls, total_calls)}</b> "
        f"de resolucao automatica e <b>{_percent(handoff_calls, total_calls)}</b> de handoff. "
        f"A saude operacional calculada para o periodo esta em <b>{_health_label(str(health['health_state']))}</b>."
    )


def _health_label(value: str) -> str:
    return {
        "stable": "Estavel",
        "warning": "Atencao",
        "critical": "Critico",
        "no_data": "Sem dados",
    }.get(value, value.capitalize())


def _number(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def _percent(part: int, total: int) -> str:
    rate = (part / total * 100) if total else 0.0
    return f"{rate:.1f}%".replace(".", ",")


def _currency(value: float) -> str:
    return f"US$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _duration_ms(value: float) -> str:
    if value < 1000:
        return f"{value:.0f} ms"
    return f"{value / 1000:.1f} s".replace(".", ",")
