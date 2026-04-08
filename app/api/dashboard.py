import json

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from ..config import Settings, get_settings
from .security import require_ops_token_with_query

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(
    _: str = Depends(require_ops_token_with_query),
    settings: Settings = Depends(get_settings),
):
    token_json = json.dumps(settings.ops_dashboard_token or "")
    header_name_json = json.dumps(settings.ops_token_header)

    return HTMLResponse(
        f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Integrix Ops Dashboard</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Sora:wght@400;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg: #0b0f14;
      --card: #101721;
      --card-soft: #172231;
      --line: #223247;
      --text: #f0f4f8;
      --muted: #9eb2c8;
      --accent: #2ec4b6;
      --accent-2: #ff9f1c;
      --danger: #ff5d73;
      --ok: #48d884;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Sora", sans-serif;
      background:
        radial-gradient(circle at 0% 0%, rgba(46, 196, 182, .22), transparent 42%),
        radial-gradient(circle at 100% 100%, rgba(255, 159, 28, .22), transparent 38%),
        var(--bg);
      color: var(--text);
      min-height: 100vh;
    }}
    .shell {{ max-width: 1200px; margin: 0 auto; padding: 28px 20px 36px; }}
    .topbar {{
      display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap;
      margin-bottom: 18px;
    }}
    .title {{
      margin: 0;
      font-size: clamp(1.3rem, 2vw, 1.8rem);
      letter-spacing: .02em;
    }}
    .subtitle {{
      margin: 6px 0 0;
      color: var(--muted);
      font-size: .92rem;
    }}
    .controls {{
      display: flex; gap: 10px; align-items: center; flex-wrap: wrap;
    }}
    .control, button {{
      border: 1px solid var(--line);
      background: var(--card);
      color: var(--text);
      padding: 10px 12px;
      border-radius: 12px;
      font: inherit;
    }}
    button {{
      cursor: pointer;
      transition: transform .15s ease, border-color .15s ease;
    }}
    button:hover {{ transform: translateY(-1px); border-color: var(--accent); }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 12px;
    }}
    .card {{
      background: linear-gradient(165deg, var(--card), var(--card-soft));
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 14px;
    }}
    .k-label {{ color: var(--muted); font-size: .82rem; margin-bottom: 8px; }}
    .k-value {{ font-size: 1.5rem; font-weight: 700; }}
    .k-value.mono {{ font-family: "IBM Plex Mono", monospace; font-size: 1.3rem; }}
    .panels {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      margin-bottom: 12px;
    }}
    .panel-title {{
      margin: 0 0 10px;
      font-size: .92rem;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: .06em;
    }}
    .bars {{ display: grid; gap: 7px; }}
    .bar-row {{
      display: grid;
      grid-template-columns: 110px 1fr 54px;
      align-items: center;
      gap: 10px;
      font-size: .82rem;
    }}
    .bar-wrap {{
      position: relative;
      height: 10px;
      border-radius: 999px;
      background: rgba(255,255,255,.06);
      overflow: hidden;
    }}
    .bar {{
      height: 100%;
      border-radius: 999px;
      background: linear-gradient(90deg, var(--accent), #66e2d5);
      width: 0%;
    }}
    .bar.cost {{ background: linear-gradient(90deg, var(--accent-2), #ffd37a); }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: .83rem;
      overflow: hidden;
      border-radius: 12px;
    }}
    th, td {{
      padding: 9px 8px;
      border-bottom: 1px solid rgba(255,255,255,.08);
      text-align: left;
    }}
    th {{ color: var(--muted); font-weight: 600; }}
    .muted {{ color: var(--muted); }}
    .status {{
      margin-top: 8px;
      font-size: .82rem;
      color: var(--muted);
      min-height: 18px;
    }}
    .badge {{
      display: inline-block;
      padding: 2px 8px;
      border-radius: 999px;
      font-size: .72rem;
      border: 1px solid var(--line);
      background: rgba(255,255,255,.02);
    }}
    .danger {{ color: var(--danger); }}
    .ok {{ color: var(--ok); }}
    @media (max-width: 980px) {{
      .grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .panels {{ grid-template-columns: 1fr; }}
      .bar-row {{ grid-template-columns: 80px 1fr 46px; }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <div class="topbar">
      <div>
        <h1 class="title">Integrix — Pilot Ops</h1>
        <p class="subtitle">Métricas de atendimento e custo real (USD) sincronizado da Vapi.</p>
      </div>
      <div class="controls">
        <select id="window" class="control">
          <option value="15m">15m</option>
          <option value="1h">1h</option>
          <option value="24h" selected>24h</option>
          <option value="7d">7d</option>
        </select>
        <input id="tenant" class="control" placeholder="tenant_id (opcional)" />
        <input id="assistant" class="control" placeholder="assistant_id (opcional)" />
        <button id="refreshBtn">Atualizar</button>
        <button id="syncBtn">Sync custo</button>
      </div>
    </div>

    <section class="grid">
      <article class="card"><div class="k-label">Total Calls</div><div id="k-total" class="k-value">0</div></article>
      <article class="card"><div class="k-label">Success</div><div id="k-success" class="k-value ok">0</div></article>
      <article class="card"><div class="k-label">Handoff</div><div id="k-handoff" class="k-value danger">0</div></article>
      <article class="card"><div class="k-label">Avg Duration</div><div id="k-duration" class="k-value mono">0 ms</div></article>
      <article class="card"><div class="k-label">Cost USD</div><div id="k-cost" class="k-value mono">$0.000000</div></article>
      <article class="card"><div class="k-label">Calls c/ Custo</div><div id="k-cost-calls" class="k-value">0</div></article>
      <article class="card"><div class="k-label">Avg Cost / Call</div><div id="k-cost-avg" class="k-value mono">$0.000000</div></article>
      <article class="card"><div class="k-label">Janela</div><div id="k-window" class="k-value"><span class="badge">24h</span></div></article>
    </section>

    <section class="panels">
      <article class="card">
        <h2 class="panel-title">Volume & Handoff</h2>
        <div id="calls-bars" class="bars"></div>
      </article>
      <article class="card">
        <h2 class="panel-title">Custo USD no tempo</h2>
        <div id="cost-bars" class="bars"></div>
      </article>
    </section>

    <section class="card">
      <h2 class="panel-title">Performance e Custo por Tool</h2>
      <div class="muted" style="margin-bottom:8px;">Join por call_id entre `call_events` e `vapi_call_costs`.</div>
      <table>
        <thead>
          <tr>
            <th>Tool</th>
            <th>Total</th>
            <th>Falhas %</th>
            <th>Handoff</th>
            <th>Avg ms</th>
            <th>Cost USD</th>
            <th>Avg Cost/Call</th>
          </tr>
        </thead>
        <tbody id="tools-table"></tbody>
      </table>
      <div id="status" class="status"></div>
    </section>
  </main>
  <script>
    const TOKEN = {token_json};
    const OPS_HEADER = {header_name_json};
    const statusEl = document.getElementById("status");
    const fmtMoney = (n) => `$${{Number(n || 0).toFixed(6)}}`;

    function withFilters(params) {{
      const tenant = document.getElementById("tenant").value.trim();
      if (tenant) params.set("tenant_id", tenant);
      const assistantId = document.getElementById("assistant").value.trim();
      if (assistantId) params.set("assistant_id", assistantId);
      return params;
    }}

    async function apiGet(path) {{
      const params = withFilters(new URLSearchParams({{ window: document.getElementById("window").value }}));
      const res = await fetch(`${{path}}?${{params.toString()}}`, {{
        headers: {{ [OPS_HEADER]: TOKEN }}
      }});
      if (!res.ok) throw new Error(`${{res.status}} ${{await res.text()}}`);
      return res.json();
    }}

    function renderBars(containerId, series, valueKey, cls) {{
      const container = document.getElementById(containerId);
      container.innerHTML = "";
      const last = series.slice(-16);
      const max = Math.max(1, ...last.map((x) => Number(x[valueKey] || 0)));
      for (const row of last) {{
        const v = Number(row[valueKey] || 0);
        const bar = Math.round((v / max) * 100);
        const time = new Date(row.timestamp).toLocaleTimeString("pt-BR", {{ hour: "2-digit", minute: "2-digit" }});
        const line = document.createElement("div");
        line.className = "bar-row";
        line.innerHTML = `
          <div class="muted">${{time}}</div>
          <div class="bar-wrap"><div class="bar ${{cls || ""}}" style="width:${{bar}}%"></div></div>
          <div>${{v.toFixed(valueKey === "cost_usd" ? 4 : 0)}}</div>
        `;
        container.appendChild(line);
      }}
    }}

    function renderTools(rows) {{
      const tbody = document.getElementById("tools-table");
      tbody.innerHTML = "";
      for (const row of rows) {{
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>${{row.tool_name}}</td>
          <td>${{row.total_calls}}</td>
          <td>${{row.failure_rate_pct}}%</td>
          <td>${{row.handoff_calls}}</td>
          <td>${{row.avg_duration_ms}}</td>
          <td>${{fmtMoney(row.total_cost_usd)}}</td>
          <td>${{fmtMoney(row.avg_cost_per_call_usd)}}</td>
        `;
        tbody.appendChild(tr);
      }}
    }}

    async function refreshAll() {{
      statusEl.textContent = "Atualizando...";
      try {{
        const [overview, costs, tools] = await Promise.all([
          apiGet("/ops/dashboard/overview"),
          apiGet("/ops/dashboard/costs"),
          apiGet("/ops/dashboard/tools"),
        ]);

        document.getElementById("k-total").textContent = overview.kpis.total_calls;
        document.getElementById("k-success").textContent = overview.kpis.success_calls;
        document.getElementById("k-handoff").textContent = overview.kpis.handoff_calls;
        document.getElementById("k-duration").textContent = `${{overview.kpis.avg_duration_ms}} ms`;
        document.getElementById("k-cost").textContent = fmtMoney(costs.summary.total_cost_usd);
        document.getElementById("k-cost-calls").textContent = costs.summary.calls_with_cost;
        document.getElementById("k-cost-avg").textContent = fmtMoney(costs.summary.avg_cost_per_call_usd);
        document.getElementById("k-window").innerHTML = `<span class="badge">${{overview.window}}</span>`;

        renderBars("calls-bars", overview.series, "calls", "");
        renderBars("cost-bars", costs.series, "cost_usd", "cost");
        renderTools(tools.items);
        const activeAssistant = document.getElementById("assistant").value.trim();
        const assistantInfo = activeAssistant ? ` | assistant: ${{activeAssistant}}` : "";
        statusEl.textContent = `Atualizado em ${{new Date().toLocaleTimeString("pt-BR")}}${{assistantInfo}}`;
      }} catch (err) {{
        statusEl.textContent = `Falha: ${{err.message}}`;
      }}
    }}

    async function syncCosts() {{
      statusEl.textContent = "Sincronizando custos...";
      const res = await fetch("/ops/costs/sync", {{
        method: "POST",
        headers: {{ [OPS_HEADER]: TOKEN }}
      }});
      if (!res.ok) {{
        statusEl.textContent = `Sync falhou: ${{res.status}}`;
        return;
      }}
      const payload = await res.json();
      statusEl.textContent = `Sync ok: processadas ${{payload.result.processed}}, novas ${{payload.result.created}}.`;
      await refreshAll();
    }}

    document.getElementById("refreshBtn").addEventListener("click", refreshAll);
    document.getElementById("syncBtn").addEventListener("click", syncCosts);
    document.getElementById("window").addEventListener("change", refreshAll);
    document.getElementById("assistant").addEventListener("change", refreshAll);
    document.getElementById("tenant").addEventListener("change", refreshAll);
    setInterval(refreshAll, 45000);
    refreshAll();
  </script>
</body>
</html>"""
    )
