import { useId, useState, type CSSProperties } from "react"
import { ArrowRight, ArrowUpRight, Info, RotateCcw } from "lucide-react"
import { calculateEstimate, costPerMinuteUsd, currency, defaultAssumptions, type Assumptions } from "./estimate"

type RangeControlProps = {
  label: string
  value: number
  min: number
  max: number
  unit: string
  decimal?: boolean
  onChange: (value: number) => void
}

function RangeControl({ label, value, min, max, unit, decimal = false, onChange }: RangeControlProps) {
  const id = useId()
  const [draft, setDraft] = useState<string | null>(null)
  const format = (number: number) => number.toLocaleString("pt-BR", { minimumFractionDigits: decimal ? 2 : 0 })

  function commitDraft() {
    if (draft !== null && draft.trim() !== "" && Number.isFinite(Number(draft))) {
      const precision = decimal ? 100 : 1
      const next = Math.round(Number(draft) * precision) / precision
      onChange(Math.min(max, Math.max(min, next)))
    }
    setDraft(null)
  }

  return (
    <div className="range-field">
      <label className="field-label" htmlFor={`${id}-number`} id={`${id}-label`}>{label}</label>
      <div className="numeric-entry">
        <input
          id={`${id}-number`}
          type="number"
          inputMode={decimal ? "decimal" : "numeric"}
          min={min}
          max={max}
          step={decimal ? 0.01 : 1}
          value={draft ?? value}
          aria-describedby={`${id}-unit`}
          onChange={(event) => {
            const raw = event.target.value
            setDraft(raw)
            if (raw !== "" && event.target.validity.valid) onChange(Number(raw))
          }}
          onBlur={commitDraft}
          onKeyDown={(event) => {
            if (event.key === "Enter") event.currentTarget.blur()
          }}
        />
        <span id={`${id}-unit`}>{unit}</span>
      </div>
      <input
        className="range-control"
        type="range"
        aria-labelledby={`${id}-label`}
        aria-valuetext={`${format(value)} ${unit}`}
        min={min}
        max={max}
        step={decimal ? 0.01 : 1}
        value={value}
        style={{ "--range-progress": `${((value - min) / (max - min)) * 100}%` } as CSSProperties}
        onChange={(event) => {
          setDraft(null)
          onChange(Number(event.target.value))
        }}
      />
      <div className="range-limits" aria-hidden="true"><span>{format(min)}</span><span>{format(max)}</span></div>
    </div>
  )
}

export default function ImpactCalculator({ contactHref }: { contactHref: string }) {
  const [assumptions, setAssumptions] = useState(defaultAssumptions)
  const [resetCount, setResetCount] = useState(0)
  const estimate = calculateEstimate(assumptions)
  const hasSavings = estimate.monthlyDifference > 0
  const comparisonMax = Math.max(estimate.routineCost, estimate.monthlyAiCost)

  function update(name: keyof Assumptions, value: number) {
    setAssumptions((current) => ({ ...current, [name]: value }))
  }

  return (
    <section className="section calculator-section" id="calculadora" aria-labelledby="calculator-title">
      <div className="container">
        <div className="section-heading">
          <div>
            <p className="eyebrow">02 / Uma decisão com números</p>
            <h2 id="calculator-title">O que muda<br />na <em>sua conta.</em></h2>
          </div>
          <p>Uma boa conversa começa com uma estimativa transparente. Compare o custo do trabalho repetitivo com o consumo de voz por IA.</p>
        </div>

        <div className="calculator-shell">
          <div className="calculator-inputs">
            <div className="calculator-toolbar">
              <span>Monte seu cenário</span>
              <button className="text-button" type="button" onClick={() => {
                setAssumptions(defaultAssumptions)
                setResetCount((current) => current + 1)
              }}><RotateCcw size={14} aria-hidden="true" />Restaurar valores</button>
            </div>
            <div key={resetCount}>
              <fieldset className="calculator-group">
                <legend><span>01</span> Sua estrutura atual</legend>
                <div className="fields-grid">
                  <RangeControl label="Pessoas no atendimento" unit="pessoas" min={1} max={30} value={assumptions.people} onChange={(value) => update("people", value)} />
                  <RangeControl label="Salário médio mensal" unit="R$ / mês" min={1500} max={10000} value={assumptions.salary} onChange={(value) => update("salary", value)} />
                  <RangeControl label="Encargos e custos indiretos" unit="% do salário" min={30} max={120} value={assumptions.overhead} onChange={(value) => update("overhead", value)} />
                  <RangeControl label="Parcela de trabalho repetitivo" unit="% do trabalho" min={20} max={90} value={assumptions.routineShare} onChange={(value) => update("routineShare", value)} />
                </div>
              </fieldset>
              <fieldset className="calculator-group">
                <legend><span>02</span> O volume a automatizar</legend>
                <div className="fields-grid">
                  <RangeControl label="Minutos automatizáveis por mês" unit="min / mês" min={1000} max={50000} value={assumptions.monthlyMinutes} onChange={(value) => update("monthlyMinutes", value)} />
                  <RangeControl label="Cotação de referência do dólar" unit="R$ / US$" min={4} max={7} decimal value={assumptions.exchangeRate} onChange={(value) => update("exchangeRate", value)} />
                </div>
              </fieldset>
            </div>
            <p className="calculator-reference"><Info size={15} aria-hidden="true" /><span>Referência de consumo: <strong>US$ 0,16 por minuto.</strong> Ajuste pelos controles ou digite seus valores.</span></p>
          </div>

          <div className="calculator-result">
            <div className="result-topline"><span>Seu cenário</span><span className="estimate-badge">Estimativa</span></div>
            <div className="result-summary" role="status" aria-live="polite" aria-atomic="true">
              <p>Economia líquida potencial / mês</p>
              <strong className="result-amount">{currency.format(estimate.monthlySavings)}</strong>
              {hasSavings ? (
                <p className="result-insight"><ArrowUpRight size={16} aria-hidden="true" />{Math.round(estimate.savingsPercentage)}% do custo repetitivo estimado</p>
              ) : (
                <p className="result-insight no-savings">{estimate.monthlyDifference < 0
                  ? `O consumo estimado da IA supera o custo repetitivo em ${currency.format(-estimate.monthlyDifference)} por mês.`
                  : "Neste cenário, o consumo estimado da IA equivale ao custo repetitivo."}</p>
              )}
            </div>

            <div className="cost-comparison">
              <div className="comparison-row">
                <div><span>Trabalho repetitivo hoje</span><strong>{currency.format(estimate.routineCost)}</strong></div>
                <div className="comparison-track" aria-hidden="true"><span style={{ width: `${(estimate.routineCost / comparisonMax) * 100}%` }} /></div>
              </div>
              <div className="comparison-row comparison-ai">
                <div><span>Consumo estimado da IA</span><strong>{currency.format(estimate.monthlyAiCost)}</strong></div>
                <div className="comparison-track" aria-hidden="true"><span style={{ width: `${(estimate.monthlyAiCost / comparisonMax) * 100}%` }} /></div>
              </div>
            </div>

            <dl className="result-breakdown">
              <div><dt>Custo total da equipe / mês</dt><dd>{currency.format(estimate.monthlyTeamCost)}</dd></div>
              <div><dt>Parcela repetitiva informada</dt><dd>{assumptions.routineShare}%</dd></div>
              <div className="annual-result"><dt>Potencial em 12 meses</dt><dd>{currency.format(estimate.annualSavings)}</dd></div>
            </dl>
            <a className="button button-primary" href={contactHref}>Conversar sobre este cenário<ArrowRight size={16} aria-hidden="true" /></a>
            <p className="result-footnote">Não representa receita adicional nem economia garantida. A redução efetiva depende de como sua operação é reorganizada.</p>
          </div>
          <details className="calculator-method">
            <summary>Entenda o cálculo e o que está incluído<span aria-hidden="true">+</span></summary>
            <div>
              <p><strong>Estrutura atual:</strong> pessoas × salário × (1 + encargos). Aplicamos a parcela repetitiva informada a esse custo.</p>
              <p><strong>Consumo de IA:</strong> {assumptions.monthlyMinutes.toLocaleString("pt-BR")} minutos × US$ {costPerMinuteUsd.toFixed(2).replace(".", ",")} × R$ {assumptions.exchangeRate.toFixed(2).replace(".", ",")}.</p>
              <p>Simulação educativa, não proposta comercial. Impostos, telefonia, implantação e integrações não estão incluídos no consumo estimado. Preços, encargos e cotação variam. O valor anual considera o mesmo cenário por 12 meses.</p>
            </div>
          </details>
        </div>
      </div>
    </section>
  )
}
