from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from math import ceil
from typing import Any
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
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
# SimpleDocTemplate also reserves six points of frame padding on each side.
CONTENT_WIDTH = A4[0] - 36 * mm - 12
CARD_GAP = 3 * mm
CARD_WIDTH = (CONTENT_WIDTH - 2 * CARD_GAP) / 3
REPORT_TZ = ZoneInfo("America/Sao_Paulo")


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
        title=f"Relatório operacional - {period_days} dias",
        author="Integrix AI",
    )
    styles = _styles()
    total_calls = int(overview["kpis"]["total_calls"])
    kpis = overview["kpis"]
    automatic_calls = int(kpis["automated_resolution_calls"])
    handoff_calls = int(kpis["successful_handoff_calls"])
    costs_summary = costs["summary"]
    generated_at = _date_time(datetime.now(timezone.utc).isoformat())

    scope = [
        f"Tenant: <b>{escape(tenant_id or 'Visão global autorizada')}</b>",
        f"Assistente: <b>{escape(assistant_id or 'Todos')}</b>",
    ]
    story: list[Any] = [
        Paragraph("Resumo executivo", styles["title"]),
        Paragraph(
            f"Últimos <b>{period_days} dias</b> | Emitido em {generated_at} (Brasília)",
            styles["subtitle"],
        ),
        Spacer(1, 5 * mm),
        Table(
            [[Paragraph(scope[0], styles["scope"]), Paragraph(scope[1], styles["scope"])]],
            colWidths=[CONTENT_WIDTH / 2] * 2,
            hAlign="LEFT",
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
        Spacer(1, 4 * mm),
        Paragraph("Resultado do atendimento", styles["section"]),
        Paragraph(_executive_summary(total_calls, automatic_calls, handoff_calls, health), styles["body"]),
        Spacer(1, 4 * mm),
        _metric_grid(
            [
                ("Chamadas analisadas", _number(total_calls), "com resultado operacional", NAVY),
                ("Sucesso do agente", _percent(int(kpis["successful_agent_calls"]), total_calls),
                 f"{_number(int(kpis['successful_agent_calls']))} resoluções ou transferências", TEAL),
                ("Resolução automática", _percent(automatic_calls, total_calls),
                 f"{_number(automatic_calls)} chamadas sem transferência", TEAL),
                ("Transferência humana", _percent(handoff_calls, total_calls),
                 f"{_number(handoff_calls)} transferências bem-sucedidas", AMBER),
                ("Não resolvidas pelo bot", _number(int(kpis["unresolved_calls"])),
                 "inclui transferências para humanos", AMBER),
                ("Falhas técnicas", _percent(int(kpis["technical_failure_events"]), int(kpis["tool_execution_count"])),
                 f"{_number(int(kpis['technical_failure_events']))} eventos em execuções de ferramentas", BLUE),
            ],
            styles,
        ),
        Spacer(1, 4 * mm),
        Paragraph("Evolução do atendimento", styles["section"]),
        Paragraph("Chamadas e transferências por intervalo com atividade; barras agrupadas em até 12 intervalos.", styles["section_note"]),
        Spacer(1, 2 * mm),
        _volume_chart(overview["series"]),
        Spacer(1, 4 * mm),
        Paragraph("Como ler os indicadores", styles["section"]),
        Paragraph(
            "Sucesso do agente soma resoluções automáticas e transferências bem-sucedidas. "
            "Uma transferência é um sucesso do agente, mas permanece não resolvida pelo bot. "
            "Encerramentos normais são incluídos na resolução automática. Falhas técnicas são medidas "
            "por execução de ferramenta e podem ocorrer em chamadas depois resolvidas.", styles["explanation"]),
        PageBreak(),
        Paragraph("Custos e consumo", styles["title"]),
        Paragraph("Custos oficiais Vapi em USD e conversão para reais pela PTAX de venda.", styles["subtitle"]),
        Spacer(1, 5 * mm),
        _metric_grid(_financial_metrics(costs_summary), styles),
        Spacer(1, 3 * mm),
        Paragraph("Composição dos custos", styles["section"]),
        Paragraph("Componentes sem discriminação aparecem zerados. Ajustes podem incluir diferenças de reconciliação; "
                  "o total oficial Vapi é a referência financeira.", styles["section_note"]),
        Spacer(1, 2 * mm),
        _cost_breakdown_table(costs["breakdown"] if costs_summary["calls_with_cost"] else [], styles),
        Spacer(1, 4 * mm),
        Paragraph("Cobertura e conversão", styles["section"]),
        _financial_quality_table(costs, styles),
        Spacer(1, 2 * mm),
        Paragraph("Bases distintas: o volume operacional usa eventos de atendimento; custos usam chamadas Vapi verificadas pela data de início. "
                  "As contagens podem diferir. Valores ausentes não representam custo ou duração zero.", styles["section_note"]),
        PageBreak(),
        Paragraph("Diagnóstico operacional", styles["title"]),
        Paragraph("Confiabilidade das execuções e desempenho por ferramenta.", styles["subtitle"]),
        Spacer(1, 5 * mm),
        _health_table(health, kpis, styles),
        Spacer(1, 5 * mm),
        Paragraph("Desempenho por ferramenta", styles["section"]),
        Paragraph("Contagens por execução concluída, não por chamada única. Uma chamada pode executar várias ferramentas. "
                  "Sucessos incluem transferências; a taxa técnica usa os códigos de erro das execuções. Custos não são atribuídos por ferramenta.", styles["section_note"]),
        Spacer(1, 2 * mm),
        _tools_table(tools["items"], styles),
        Spacer(1, 4 * mm),
        Paragraph("Fontes e critérios", styles["section"]),
        Paragraph(
            f"Mesmas agregações do painel operacional. Versão dos indicadores: {escape(str(overview['metric_version']))}. "
            f"Início da janela operacional: {_date_time(overview['since'])} (Brasília). "
            "A sincronização de custos reflete o processo global de ingestão; os indicadores do relatório respeitam os filtros selecionados.",
            styles["section_note"]),
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
            keepWithNext=True,
        ),
        "section_note": ParagraphStyle(
            "ReportSectionNote",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=11,
            textColor=MUTED,
            keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "ReportBody",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=14,
            textColor=SLATE,
        ),
        "explanation": ParagraphStyle(
            "ReportExplanation",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=12,
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
    rows = [cards[index:index + 3] + [""] * (3 - len(cards[index:index + 3]))
            for index in range(0, len(cards), 3)]
    grid = Table(rows, colWidths=[CARD_WIDTH + CARD_GAP, CARD_WIDTH + CARD_GAP, CARD_WIDTH],
                 hAlign="LEFT")
    grid.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), CARD_GAP),
                ("RIGHTPADDING", (-1, 0), (-1, -1), 0),
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
    value_width = CARD_WIDTH - 6.2 * mm
    font_size = min(18, max(9, 18 * value_width / max(1, stringWidth(value, "Helvetica-Bold", 18))))
    value_style = ParagraphStyle("FittedMetricValue", parent=styles["metric_value"],
                                 fontSize=font_size, leading=21)
    card = Table(
        [
            [Paragraph(escape(label), styles["metric_label"])],
            [Paragraph(escape(value), value_style)],
            [Paragraph(escape(detail), styles["metric_detail"])],
        ],
        colWidths=[CARD_WIDTH],
        minRowHeights=[24, 27, 30],
        splitByRow=0,
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
    width = CONTENT_WIDTH
    height = 53 * mm
    drawing = Drawing(width, height)
    drawing.add(Rect(0, 0, width, height, fillColor=PAPER, strokeColor=LINE, strokeWidth=0.5))
    groups = _group_series(series)
    if not groups:
        drawing.add(
            String(
                width / 2,
                height / 2,
                "Sem chamadas concluídas no período selecionado.",
                fontName="Helvetica",
                fontSize=9,
                fillColor=MUTED,
                textAnchor="middle",
            )
        )
        return drawing

    maximum = max(max(group["calls"], group["handoffs"]) for group in groups) or 1
    chart_left = max(12 * mm, stringWidth(_number(maximum), "Helvetica", 6.5) + 5 * mm)
    chart_bottom = 12 * mm
    chart_width = width - chart_left - 8 * mm
    chart_height = height - 22 * mm
    for step in range(1, 5):
        y = chart_bottom + chart_height * step / 4
        drawing.add(Line(chart_left, y, chart_left + chart_width, y, strokeColor=LINE, strokeWidth=0.35))
        drawing.add(
            String(
                chart_left - 2 * mm,
                y - 2,
                _number(round(maximum * step / 4)),
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
    drawing.add(String(chart_left, height - 4 * mm, "Chamadas", fontName="Helvetica-Bold", fontSize=7, fillColor=BLUE))
    drawing.add(String(chart_left + 22 * mm, height - 4 * mm, "Transferências", fontName="Helvetica-Bold", fontSize=7, fillColor=AMBER))
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


def _financial_metrics(summary: dict[str, Any]) -> list[tuple[str, str, str, colors.Color]]:
    has_cost = bool(summary["calls_with_cost"])
    has_duration = bool(summary["calls_with_duration"])
    return [
        ("Custo total em USD", _currency(float(summary["total_cost_usd"])) if has_cost else "Sem custos",
         f"{_number(int(summary['calls_with_cost']))} chamadas com custo reportado", BLUE),
        ("Custo convertido em BRL",
         _currency_brl(float(summary["total_cost_brl"])) if has_cost and summary["total_cost_brl"] is not None else "Indisponível",
         "PTAX de venda por data da chamada", BLUE),
        ("Custo médio por chamada", _currency(float(summary["avg_cost_per_call_usd"])) if has_cost else "Sem custos",
         "média das chamadas com custo em USD", BLUE),
        ("Cobertura de custos", _percent(int(summary["calls_with_cost"]), int(summary["vapi_calls"])) if summary["vapi_calls"] else "Sem chamadas",
         f"{_number(int(summary['calls_without_cost']))} chamadas Vapi sem custo", AMBER),
        ("Duração total", _duration_seconds(float(summary["total_duration_seconds"])) if has_duration else "Sem duração",
         f"{_number(int(summary['calls_with_duration']))} chamadas com duração", NAVY),
        ("Duração média", _duration_seconds(float(summary["avg_duration_seconds"])) if has_duration else "Sem duração",
         "média das chamadas com duração informada", NAVY),
    ]


def _data_table(headers: list[str], rows: list[list[str]], ratios: list[float],
                styles: dict[str, ParagraphStyle]) -> Table:
    data = [[Paragraph(escape(value), styles["table_header"]) for value in headers]]
    data += [[Paragraph(escape(value), styles["table_cell"]) for value in row] for row in rows]
    table = Table(data, colWidths=[CONTENT_WIDTH * ratio for ratio in ratios], hAlign="LEFT", repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PAPER]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.35, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 2 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm),
    ]))
    return table


def _cost_breakdown_table(items: list[dict[str, Any]], styles: dict[str, ParagraphStyle]) -> Table:
    labels = {"transport": "Telefonia e transporte", "stt": "Transcrição de áudio (STT)",
              "llm": "Modelo de linguagem (LLM)", "tts": "Síntese de voz (TTS)",
              "vapi": "Plataforma Vapi", "analysis": "Análise pós-chamada",
              "adjustment_and_other": "Ajustes e outros"}
    rows = [[labels.get(str(item["category"]), str(item["category"])),
             _currency(float(item["cost_usd"])), f"{float(item['share_pct']):.1f}%".replace(".", ",")]
            for item in items]
    if not rows:
        rows = [["Sem componentes reportados", "-", "-"]]
    return _data_table(["COMPONENTE", "CUSTO USD", "PARTICIPAÇÃO"], rows, [0.52, 0.26, 0.22], styles)


def _financial_quality_table(costs: dict[str, Any], styles: dict[str, ParagraphStyle]) -> Table:
    summary, fx = costs["summary"], costs["fx"]
    rows = [
        ["Chamadas Vapi verificadas", _number(int(summary["vapi_calls"]))],
        ["Conversão PTAX", "Sem custos reportados" if not summary["calls_with_cost"] else
         ("Completa" if fx["complete"] else "Sem conversão completa")],
        ["Chamadas sem conversão", _number(int(fx["missing_rate_calls"]))],
        ["Chamadas com câmbio provisório", _number(int(fx["provisional_calls"]))],
        ["Última data PTAX aplicada", datetime.fromisoformat(fx["last_rate_date"]).strftime("%d/%m/%Y")
         if fx["last_rate_date"] else "Sem cotação aplicada"],
    ]
    return _data_table(["INDICADOR", "LEITURA"], rows, [0.52, 0.48], styles)


def _date_time(value: str | None) -> str:
    if not value:
        return "Não registrada"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(REPORT_TZ).strftime("%d/%m/%Y %H:%M")


def _duration_seconds(value: float) -> str:
    seconds = max(0, round(value))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{_number(hours)} h {minutes:02d} min" if hours else f"{minutes} min {seconds:02d} s"


def _health_table(
    health: dict[str, Any],
    kpis: dict[str, Any],
    styles: dict[str, ParagraphStyle],
) -> Table:
    counters = health["counters"]
    rows = [
        ["Estado", _health_label(str(health["health_state"]))],
        ["Atualização de custos (processo global)", {"fresh": "Em dia", "delayed": "Atrasada", "stale": "Desatualizada", "unknown": "Sem sincronização registrada"}.get(str(health["sync"]["freshness_state"]), "Indisponível")],
        ["Última sincronização (Brasília)", _date_time(health["sync"]["last_synced_at"])],
        ["Execuções de ferramentas", _number(int(kpis["tool_execution_count"]))],
        ["Tempo médio por execução", _duration_ms(float(kpis["avg_duration_ms"])) if kpis["tool_execution_count"] else "Sem execuções"],
        ["Falhas técnicas / execuções", f"{_number(int(counters['technical_failure_events']))} / {_number(int(counters['tool_execution_count']))} "
         f"({_percent(int(counters['technical_failure_events']), int(counters['tool_execution_count']))})"],
        ["Erros de negócio repetidos", _number(int(counters["repeated_business_errors"]))],
        ["Reentregas idempotentes", _number(int(counters["idempotency_hits"]))],
    ]
    return _data_table(["INDICADOR", "LEITURA"], rows, [0.46, 0.54], styles)


def _tools_table(items: list[dict[str, Any]], styles: dict[str, ParagraphStyle]) -> Table:
    headers = ["FERRAMENTA", "EXECUÇÕES", "SUCESSOS", "FALHAS", "FALHAS TÉCNICAS", "TEMPO MÉDIO"]
    data: list[list[Paragraph]] = [[Paragraph(header, styles["table_header"]) for header in headers]]
    if not items:
        data.append(
            [Paragraph("Nenhuma ferramenta concluída no período selecionado.", styles["table_cell"])]
            + [Paragraph("", styles["table_cell"]) for _ in range(5)]
        )
    else:
        for item in items:
            data.append(
                [
                    Paragraph(escape(str(item["tool_name"])), styles["table_cell"]),
                    Paragraph(_number(int(item["total_calls"])), styles["table_cell"]),
                    Paragraph(_number(int(item["success_calls"])), styles["table_cell"]),
                    Paragraph(_number(int(item["failed_calls"])), styles["table_cell"]),
                    Paragraph(_percent(int(item["technical_failure_events"]), int(item["total_calls"])), styles["table_cell"]),
                    Paragraph(_duration_ms(float(item["avg_duration_ms"])), styles["table_cell"]),
                ]
            )
    table = Table(
        data,
        colWidths=[CONTENT_WIDTH * ratio for ratio in (0.34, 0.13, 0.13, 0.10, 0.16, 0.14)],
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
    if not items:
        table.setStyle(TableStyle([("SPAN", (0, 1), (-1, 1))]))
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
    canvas.drawRightString(page_width - 18 * mm, page_height - 13 * mm, "RELATÓRIO OPERACIONAL")
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
    automatic_calls: int,
    handoff_calls: int,
    health: dict[str, Any],
) -> str:
    if total_calls == 0:
        return "Não há chamadas concluídas para os filtros e período selecionados."
    return (
        f"Foram analisadas <b>{_number(total_calls)} chamadas</b>, com <b>{_percent(automatic_calls, total_calls)}</b> "
        f"de resolução automática e <b>{_percent(handoff_calls, total_calls)}</b> de transferência humana. "
        f"A saúde operacional do período está em <b>{escape(_health_label(str(health['health_state'])))}</b>."
    )


def _health_label(value: str) -> str:
    return {
        "stable": "Estável",
        "warning": "Atenção",
        "critical": "Crítico",
        "no_data": "Sem dados",
    }.get(value, value.capitalize())


def _number(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def _percent(part: int, total: int) -> str:
    rate = (part / total * 100) if total else 0.0
    return f"{rate:.1f}%".replace(".", ",")


def _currency(value: float) -> str:
    return f"US$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _currency_brl(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _duration_ms(value: float) -> str:
    if value < 1000:
        return f"{value:.0f} ms"
    return f"{value / 1000:.1f} s".replace(".", ",")
