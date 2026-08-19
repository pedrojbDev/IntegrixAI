import { useMemo, useState } from "react"
import {
  ArrowDown,
  ArrowRight,
  AudioLines,
  BarChart3,
  Building2,
  CalendarCheck2,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleDollarSign,
  Clock3,
  Headphones,
  LineChart,
  LockKeyhole,
  Menu,
  MessageSquareText,
  PhoneCall,
  PhoneIncoming,
  Route,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  UserRoundCheck,
  WalletCards,
  X,
  type LucideIcon,
} from "lucide-react"

const contactHref =
  "mailto:contato@integrix.com.br?subject=Quero%20conhecer%20a%20Integrix%20AI&body=Ol%C3%A1%2C%20quero%20entender%20como%20a%20Integrix%20AI%20pode%20melhorar%20meu%20atendimento."
const opsConsoleUrl = import.meta.env.VITE_OPS_CONSOLE_URL || "/dashboard"

const navLinks = [
  { label: "Resultados", href: "#resultados" },
  { label: "Calculadora", href: "#calculadora" },
  { label: "Como funciona", href: "#como-funciona" },
  { label: "Segurança", href: "#seguranca" },
  { label: "Dúvidas", href: "#duvidas" },
]

const valuePillars: Array<{ icon: LucideIcon; title: string; description: string; accent: string }> = [
  {
    icon: PhoneIncoming,
    title: "Nenhuma oportunidade no toque de espera",
    description: "A IA atende ao mesmo tempo, inclusive fora do horário e nos picos de demanda.",
    accent: "bg-brand-lime",
  },
  {
    icon: WalletCards,
    title: "Crescimento sem folha inchada",
    description: "Automatize o volume repetitivo antes de transformar cada nova demanda em contratação.",
    accent: "bg-brand-coral text-white",
  },
  {
    icon: BarChart3,
    title: "Decisão com números, não impressão",
    description: "Veja volume, resolução, motivos de contato e pontos de atenção em um painel simples.",
    accent: "bg-brand-sky",
  },
]

const outcomes = [
  {
    label: "Disponibilidade",
    value: "24h",
    title: "Sua empresa disponível quando o cliente decide ligar.",
    description: "No almoço, à noite, no fim de semana ou durante um pico: a primeira resposta não precisa esperar.",
  },
  {
    label: "Escala",
    value: "∞",
    title: "Mais conversas sem multiplicar a estrutura no mesmo ritmo.",
    description: "A operação absorve variações de demanda e sua equipe humana cuida das situações de maior valor.",
  },
  {
    label: "Visibilidade",
    value: "1 painel",
    title: "Cada atendimento vira informação para melhorar o negócio.",
    description: "Acompanhe o que os clientes pedem, o que foi resolvido e onde ainda existe oportunidade.",
  },
]

const processSteps: Array<{ number: string; icon: LucideIcon; title: string; description: string }> = [
  {
    number: "01",
    icon: MessageSquareText,
    title: "A gente entende a sua operação",
    description: "Mapeamos os motivos de contato, as regras do negócio e o que deve continuar com pessoas.",
  },
  {
    number: "02",
    icon: Route,
    title: "A IA aprende o caminho certo",
    description: "Configuramos conversas, integrações e limites para que ela consulte, agende, registre ou encaminhe.",
  },
  {
    number: "03",
    icon: TrendingUp,
    title: "Você acompanha e melhora",
    description: "A operação entra no ar com indicadores claros. O aprendizado real orienta os próximos ganhos.",
  },
]

const useCases: Array<{ icon: LucideIcon; title: string; items: string[] }> = [
  {
    icon: CalendarCheck2,
    title: "Agendamentos",
    items: ["Marcar e confirmar horários", "Reagendar sem fila", "Lembrar o cliente automaticamente"],
  },
  {
    icon: Headphones,
    title: "Atendimento",
    items: ["Responder dúvidas frequentes", "Consultar status e solicitações", "Direcionar com todo o contexto"],
  },
  {
    icon: CircleDollarSign,
    title: "Comercial e cobrança",
    items: ["Qualificar oportunidades", "Recuperar contatos", "Fazer lembretes e negociações iniciais"],
  },
]

const faqs = [
  {
    question: "A voz parece robótica?",
    answer:
      "Não é uma URA de “digite 1 ou 2”. A conversa usa linguagem natural, entende a intenção do cliente e segue as regras definidas para a sua empresa.",
  },
  {
    question: "A IA substitui toda a minha equipe?",
    answer:
      "A proposta é retirar o trabalho repetitivo e dar escala ao primeiro atendimento. Situações sensíveis, negociações complexas e decisões humanas continuam com a equipe — agora com mais contexto e tempo.",
  },
  {
    question: "Preciso trocar os sistemas que já uso?",
    answer:
      "Na maioria dos projetos, não. A Integrix AI é desenhada para conversar com agendas, cadastros, CRMs e outros sistemas que já fazem parte da operação.",
  },
  {
    question: "Quanto tempo leva para começar?",
    answer:
      "O prazo depende do processo e das integrações necessárias. A demonstração serve justamente para mapear o primeiro caso de uso e propor uma implantação segura, com escopo e etapas claras.",
  },
  {
    question: "Como vocês cuidam da segurança?",
    answer:
      "Acessos, registros, permissões e dados sensíveis são tratados com controles próprios para operação empresarial. Você acompanha o que a IA fez e define até onde ela pode ir.",
  },
]

const currency = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  maximumFractionDigits: 0,
})

function Header() {
  const [menuOpen, setMenuOpen] = useState(false)

  return (
    <header className="fixed inset-x-0 top-0 z-50 border-b border-brand-ink/10 bg-brand-cream/90 backdrop-blur-xl">
      <div className="mx-auto flex h-[74px] max-w-[1440px] items-center justify-between px-5 sm:px-8 lg:px-12">
        <a className="group flex items-center gap-3" href="#top" aria-label="Integrix AI — início">
          <span className="logo-mark">
            <AudioLines className="h-5 w-5" aria-hidden="true" />
          </span>
          <span className="font-display text-xl font-bold tracking-[-0.04em] text-brand-ink">
            Integrix <span className="text-brand-green">AI</span>
          </span>
        </a>

        <nav className="hidden items-center gap-8 text-sm font-semibold text-brand-ink/70 lg:flex" aria-label="Principal">
          {navLinks.map((link) => (
            <a className="nav-link" href={link.href} key={link.href}>
              {link.label}
            </a>
          ))}
        </nav>

        <div className="flex items-center gap-2">
          <a className="button button-dark hidden sm:inline-flex" href={contactHref}>
            Agendar diagnóstico
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </a>
          <button
            aria-expanded={menuOpen}
            aria-label={menuOpen ? "Fechar menu" : "Abrir menu"}
            className="grid h-11 w-11 place-items-center rounded-full border border-brand-ink/15 text-brand-ink lg:hidden"
            onClick={() => setMenuOpen((current) => !current)}
            type="button"
          >
            {menuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </div>

      {menuOpen && (
        <nav className="border-t border-brand-ink/10 bg-brand-cream px-5 py-5 lg:hidden" aria-label="Menu móvel">
          <div className="mx-auto flex max-w-[1440px] flex-col">
            {navLinks.map((link) => (
              <a
                className="border-b border-brand-ink/10 py-4 font-semibold text-brand-ink"
                href={link.href}
                key={link.href}
                onClick={() => setMenuOpen(false)}
              >
                {link.label}
              </a>
            ))}
            <a className="button button-lime mt-5 justify-center" href={contactHref}>
              Agendar diagnóstico
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </a>
          </div>
        </nav>
      )}
    </header>
  )
}

function VoiceOperationVisual() {
  const bars = [28, 38, 48, 31, 58, 74, 44, 65, 86, 52, 68, 40, 58, 34, 46, 24]

  return (
    <div className="hero-visual reveal reveal-delay-2" aria-label="Exemplo ilustrativo do painel Integrix AI">
      <div className="hero-visual-grid" aria-hidden="true" />
      <div className="relative z-10 flex items-start justify-between gap-4">
        <div>
          <p className="eyebrow-light">Operação ao vivo</p>
          <p className="mt-2 font-display text-2xl font-bold tracking-[-0.04em] text-white">Atendimento inteligente</p>
        </div>
        <span className="live-badge">
          <span className="live-dot" />
          IA atendendo
        </span>
      </div>

      <div className="relative z-10 my-9 flex h-24 items-center justify-center gap-[6px] rounded-2xl border border-white/10 bg-white/[0.06] px-5">
        {bars.map((height, index) => (
          <span
            className="sound-bar"
            key={`${height}-${index}`}
            style={{ height: `${height}%`, animationDelay: `${index * 70}ms` }}
          />
        ))}
      </div>

      <div className="relative z-10 grid gap-3 sm:grid-cols-3">
        <div className="visual-metric visual-metric-highlight">
          <PhoneCall className="h-5 w-5" aria-hidden="true" />
          <strong>1.248</strong>
          <span>atendimentos</span>
        </div>
        <div className="visual-metric">
          <CheckCircle2 className="h-5 w-5" aria-hidden="true" />
          <strong>82%</strong>
          <span>resolvidos pela IA</span>
        </div>
        <div className="visual-metric">
          <Clock3 className="h-5 w-5" aria-hidden="true" />
          <strong>2m18s</strong>
          <span>tempo médio</span>
        </div>
      </div>

      <div className="relative z-10 mt-3 flex items-center justify-between gap-4 rounded-2xl border border-white/10 bg-white/[0.06] p-4">
        <div className="flex min-w-0 items-center gap-3">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-brand-lime text-brand-ink">
            <TrendingUp className="h-5 w-5" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-white">Demanda absorvida sem fila</p>
            <p className="mt-1 text-xs text-white/55">Exemplo de operação em um dia</p>
          </div>
        </div>
        <span className="font-display text-xl font-bold text-brand-lime">+37%</span>
      </div>

      <div className="floating-note hidden sm:flex">
        <UserRoundCheck className="h-5 w-5 text-brand-green" aria-hidden="true" />
        <div>
          <strong>Cliente encaminhado</strong>
          <span>com histórico completo</span>
        </div>
      </div>
    </div>
  )
}

function Hero() {
  return (
    <section className="page-shell relative overflow-hidden px-5 pb-20 pt-32 sm:px-8 sm:pb-28 sm:pt-40 lg:px-12" id="top">
      <div className="hero-orb hero-orb-one" aria-hidden="true" />
      <div className="hero-orb hero-orb-two" aria-hidden="true" />
      <div className="relative mx-auto grid max-w-[1440px] items-center gap-14 lg:grid-cols-[0.96fr_1.04fr] xl:gap-20">
        <div className="max-w-3xl">
          <div className="reveal inline-flex items-center gap-2 rounded-full border border-brand-ink/12 bg-white/55 px-4 py-2 text-xs font-bold uppercase tracking-[0.16em] text-brand-ink">
            <span className="h-2 w-2 rounded-full bg-brand-green" />
            Atendimento com IA que trabalha por resultado
          </div>
          <h1 className="reveal reveal-delay-1 mt-7 font-display text-[clamp(3.15rem,7vw,6.6rem)] font-extrabold leading-[0.97] tracking-[-0.055em] text-brand-ink">
            Atenda mais.
            <br />
            <span className="title-accent">Sem inflar</span>
            <br />
            a sua equipe.
          </h1>
          <p className="reveal reveal-delay-2 mt-8 max-w-2xl text-lg leading-8 text-brand-ink/70 sm:text-xl sm:leading-9">
            A Integrix AI atende chamadas, executa tarefas e registra cada conversa — 24 horas por dia. Sua empresa
            ganha escala, reduz trabalho repetitivo e deixa as pessoas focarem no que realmente precisa de pessoas.
          </p>
          <div className="reveal reveal-delay-3 mt-9 flex flex-col gap-3 sm:flex-row">
            <a className="button button-lime justify-center" href={contactHref}>
              Quero ver na minha empresa
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </a>
            <a className="button button-ghost justify-center" href="#calculadora">
              Calcular meu potencial
              <ArrowDown className="h-4 w-4" aria-hidden="true" />
            </a>
          </div>
          <p className="reveal reveal-delay-3 mt-5 flex items-center gap-2 text-sm font-medium text-brand-ink/55">
            <Check className="h-4 w-4 text-brand-green" aria-hidden="true" />
            Diagnóstico inicial sem compromisso e baseado na sua operação.
          </p>
        </div>

        <VoiceOperationVisual />
      </div>

      <div className="relative mx-auto mt-20 max-w-[1440px] border-y border-brand-ink/10 py-6 sm:mt-24">
        <p className="mb-5 text-center text-xs font-bold uppercase tracking-[0.2em] text-brand-ink/45 lg:hidden">
          Uma operação preparada para crescer
        </p>
        <div className="grid gap-5 text-sm font-semibold text-brand-ink/70 sm:grid-cols-2 lg:grid-cols-4">
          {[
            "Atendimento simultâneo",
            "Integração com seus sistemas",
            "Transferência com contexto",
            "Gestão em tempo real",
          ].map((item) => (
            <div className="flex items-center justify-center gap-3 lg:border-r lg:border-brand-ink/10 lg:last:border-r-0" key={item}>
              <CheckCircle2 className="h-5 w-5 text-brand-green" aria-hidden="true" />
              {item}
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

function ProblemSection() {
  return (
    <section className="bg-brand-ink px-5 py-24 text-white sm:px-8 sm:py-32 lg:px-12" id="resultados">
      <div className="mx-auto max-w-[1440px]">
        <div className="grid gap-10 lg:grid-cols-[1.1fr_0.9fr] lg:items-center lg:gap-20">
          <div>
            <p className="eyebrow-light">O custo que quase nunca aparece inteiro</p>
            <h2 className="section-title mt-5 max-w-3xl text-white">
              A ligação perdida custa uma venda. A rotina manual custa todos os meses.
            </h2>
          </div>
          <p className="max-w-2xl text-lg leading-8 text-white/65 lg:justify-self-end">
            Salário é só uma parte da conta. Encargos, benefícios, recrutamento, treinamento, faltas e rotatividade
            tornam caro manter pessoas presas a tarefas previsíveis. A IA muda essa matemática sem tirar o cuidado
            humano de onde ele importa.
          </p>
        </div>

        <div className="mt-16 grid gap-5 lg:grid-cols-3">
          {valuePillars.map((item) => {
            const IconComponent = item.icon
            return (
              <article className="value-card" key={item.title}>
                <span className={`grid h-12 w-12 place-items-center rounded-full text-brand-ink ${item.accent}`}>
                  <IconComponent className="h-5 w-5" aria-hidden="true" />
                </span>
                <h3 className="mt-8 font-display text-2xl font-bold leading-tight tracking-[-0.04em]">{item.title}</h3>
                <p className="mt-4 leading-7 text-white/60">{item.description}</p>
              </article>
            )
          })}
        </div>

        <div className="mt-20 grid divide-y divide-white/10 border-y border-white/10 md:grid-cols-3 md:divide-x md:divide-y-0">
          {outcomes.map((outcome) => (
            <article className="py-10 md:px-8 md:first:pl-0 md:last:pr-0" key={outcome.label}>
              <div className="flex items-end justify-between gap-5">
                <p className="text-xs font-bold uppercase tracking-[0.18em] text-white/40">{outcome.label}</p>
                <strong className="font-display text-4xl tracking-[-0.06em] text-brand-lime">{outcome.value}</strong>
              </div>
              <h3 className="mt-8 font-display text-2xl font-bold leading-tight tracking-[-0.04em]">{outcome.title}</h3>
              <p className="mt-4 leading-7 text-white/55">{outcome.description}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  )
}

function RangeControl({
  label,
  value,
  min,
  max,
  step,
  display,
  onChange,
}: {
  label: string
  value: number
  min: number
  max: number
  step: number
  display: string
  onChange: (value: number) => void
}) {
  const progress = ((value - min) / (max - min)) * 100

  return (
    <label className="block">
      <span className="flex items-center justify-between gap-4">
        <span className="text-sm font-semibold text-brand-ink/65">{label}</span>
        <strong className="rounded-full bg-brand-ink px-3 py-1 text-sm text-white">{display}</strong>
      </span>
      <input
        aria-label={label}
        className="range-control mt-5"
        max={max}
        min={min}
        onChange={(event) => onChange(Number(event.target.value))}
        step={step}
        style={{ "--range-progress": `${progress}%` } as React.CSSProperties}
        type="range"
        value={value}
      />
    </label>
  )
}

function ImpactCalculator() {
  const [people, setPeople] = useState(6)
  const [salary, setSalary] = useState(2500)
  const [overhead, setOverhead] = useState(70)
  const [routineShare, setRoutineShare] = useState(60)
  const [monthlyMinutes, setMonthlyMinutes] = useState(8000)
  const [exchangeRate, setExchangeRate] = useState(5.07)

  const estimate = useMemo(() => {
    const monthlyTeamCost = people * salary * (1 + overhead / 100)
    const routineCost = monthlyTeamCost * (routineShare / 100)
    const aiCostPerMinuteUsd = 0.16
    const monthlyAiCost = monthlyMinutes * aiCostPerMinuteUsd * exchangeRate
    const monthlySavings = Math.max(0, routineCost - monthlyAiCost)
    const annualSavings = monthlySavings * 12
    const savingsPercentage = routineCost > 0 ? (monthlySavings / routineCost) * 100 : 0

    return {
      monthlyTeamCost,
      routineCost,
      monthlyAiCost,
      monthlySavings,
      annualSavings,
      savingsPercentage,
      aiCostPerMinuteUsd,
    }
  }, [people, salary, overhead, routineShare, monthlyMinutes, exchangeRate])

  const hasEstimatedSavings = estimate.monthlySavings > 0

  return (
    <section className="bg-brand-cream px-5 py-24 sm:px-8 sm:py-32 lg:px-12" id="calculadora">
      <div className="mx-auto max-w-[1440px]">
        <div className="grid gap-8 lg:grid-cols-[0.78fr_1.22fr] lg:items-end">
          <div>
            <p className="eyebrow">Simule com os seus números</p>
            <h2 className="section-title mt-5">Quanto da sua estrutura está presa ao repetitivo?</h2>
          </div>
          <p className="max-w-2xl text-lg leading-8 text-brand-ink/65 lg:justify-self-end">
            Compare o custo da rotina atual com uma operação de voz por IA. Você pode ajustar equipe, volume de
            minutos e câmbio para entender, em valores aproximados, onde existe espaço real para economizar.
          </p>
        </div>

        <div className="calculator-shell mt-14">
          <div className="grid gap-10 p-6 sm:p-9 lg:grid-cols-[0.95fr_1.05fr] lg:gap-14 lg:p-12">
            <div className="space-y-9">
              <div className="calculator-input-group">
                <div className="calculator-group-heading">
                  <span>1</span>
                  <div>
                    <strong>Como funciona hoje</strong>
                    <p>Estime o custo da estrutura dedicada ao atendimento.</p>
                  </div>
                </div>
                <div className="mt-8 space-y-9">
                  <RangeControl
                    display={`${people} pessoas`}
                    label="Pessoas dedicadas ao atendimento"
                    max={30}
                    min={1}
                    onChange={setPeople}
                    step={1}
                    value={people}
                  />
                  <RangeControl
                    display={currency.format(salary)}
                    label="Salário médio mensal"
                    max={10000}
                    min={1500}
                    onChange={setSalary}
                    step={100}
                    value={salary}
                  />
                  <RangeControl
                    display={`${overhead}%`}
                    label="Encargos, benefícios e custos indiretos"
                    max={120}
                    min={30}
                    onChange={setOverhead}
                    step={5}
                    value={overhead}
                  />
                  <RangeControl
                    display={`${routineShare}%`}
                    label="Parcela do trabalho que é repetitiva"
                    max={90}
                    min={20}
                    onChange={setRoutineShare}
                    step={5}
                    value={routineShare}
                  />
                </div>
              </div>

              <div className="calculator-input-group">
                <div className="calculator-group-heading">
                  <span>2</span>
                  <div>
                    <strong>Quanto a IA atenderia</strong>
                    <p>Use seu volume de voz e uma cotação de referência.</p>
                  </div>
                </div>
                <div className="mt-8 space-y-9">
                  <RangeControl
                    display={`${monthlyMinutes.toLocaleString("pt-BR")} min`}
                    label="Minutos automatizáveis por mês"
                    max={50000}
                    min={1000}
                    onChange={setMonthlyMinutes}
                    step={500}
                    value={monthlyMinutes}
                  />
                  <RangeControl
                    display={`R$ ${exchangeRate.toFixed(2).replace(".", ",")}`}
                    label="Cotação de referência do dólar"
                    max={7}
                    min={4}
                    onChange={setExchangeRate}
                    step={0.01}
                    value={exchangeRate}
                  />
                </div>
                <p className="calculator-reference">
                  Cálculo usando <strong>US$ 0,16 por minuto</strong> como referência, não como preço contratado ou
                  garantia de custo.
                </p>
              </div>
            </div>

            <div className="calculator-result">
              <div className="calculator-result-heading">
                <span className="result-number">3</span>
                <div>
                  <p className="text-xs font-bold uppercase tracking-[0.18em] text-brand-ink/50">
                    Economia líquida estimada
                  </p>
                  <p className="mt-1 text-sm text-brand-ink/55">Custo atual menos o consumo estimado da IA</p>
                </div>
              </div>

              <div className="mt-8">
                <span className="text-sm font-semibold text-brand-ink/55">Por mês, aproximadamente</span>
                <strong className="mt-2 block font-display text-[clamp(3rem,6vw,5.5rem)] font-bold leading-none tracking-[-0.055em] text-brand-ink">
                  {hasEstimatedSavings ? currency.format(estimate.monthlySavings) : "R$ 0"}
                </strong>
                {hasEstimatedSavings ? (
                  <p className="mt-4 inline-flex rounded-full bg-brand-green px-3 py-1.5 text-xs font-bold text-white">
                    cerca de {Math.round(estimate.savingsPercentage)}% do custo repetitivo atual
                  </p>
                ) : (
                  <p className="mt-4 rounded-xl bg-brand-coral/15 p-3 text-sm font-semibold leading-6 text-brand-ink">
                    Com essas premissas, o custo estimado da IA supera o custo repetitivo informado. Ajuste o volume ou
                    solicite uma análise do processo.
                  </p>
                )}
              </div>

              <div className="calculation-breakdown mt-8">
                <div>
                  <span>
                    <small>1</small>
                    Custo mensal da equipe
                  </span>
                  <strong>{currency.format(estimate.monthlyTeamCost)}</strong>
                </div>
                <div>
                  <span>
                    <small>2</small>
                    Parte repetitiva desse custo
                  </span>
                  <strong>{currency.format(estimate.routineCost)}</strong>
                </div>
                <div>
                  <span>
                    <small>3</small>
                    Custo mensal estimado da IA
                  </span>
                  <strong className="text-brand-coral">− {currency.format(estimate.monthlyAiCost)}</strong>
                </div>
              </div>

              <div className="annual-result">
                <div>
                  <span>Em 12 meses</span>
                  <strong>{currency.format(estimate.annualSavings)}</strong>
                </div>
                <p>
                  {monthlyMinutes.toLocaleString("pt-BR")} min × US$ {estimate.aiCostPerMinuteUsd.toFixed(2)} × R${" "}
                  {exchangeRate.toFixed(2).replace(".", ",")}
                </p>
              </div>

              <p className="mt-5 text-xs leading-5 text-brand-ink/50">
                Este valor é a diferença entre o custo estimado da rotina repetitiva e o custo variável da IA. Não
                representa receita adicional nem economia garantida.
              </p>

              <a className="button button-dark mt-8 w-full justify-center" href={contactHref}>
                Validar esta estimativa
                <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </a>
            </div>
          </div>
          <p className="border-t border-brand-ink/10 px-6 py-5 text-xs leading-5 text-brand-ink/45 sm:px-9 lg:px-12">
            Simulação educativa, não promessa de economia. O preço por minuto, a cotação do dólar, impostos, telefonia,
            implantação e integrações podem alterar o resultado. Encargos e benefícios também variam por regime,
            convenção e empresa. Uma proposta real depende da análise do processo e do volume contratado.
          </p>
        </div>
      </div>
    </section>
  )
}

function HowItWorks() {
  return (
    <section className="bg-brand-paper px-5 py-24 sm:px-8 sm:py-32 lg:px-12" id="como-funciona">
      <div className="mx-auto max-w-[1440px]">
        <div className="max-w-4xl">
          <p className="eyebrow">Da primeira conversa ao resultado</p>
          <h2 className="section-title mt-5">
            Tecnologia robusta por trás.
            <br />
            <span className="text-brand-green">Uma experiência simples na frente.</span>
          </h2>
        </div>

        <div className="mt-16 grid gap-px overflow-hidden rounded-[2rem] border border-brand-ink/10 bg-brand-ink/10 lg:grid-cols-3">
          {processSteps.map((step) => {
            const IconComponent = step.icon
            return (
              <article className="process-card" key={step.number}>
                <div className="flex items-center justify-between">
                  <span className="font-display text-sm font-bold text-brand-green">{step.number}</span>
                  <IconComponent className="h-6 w-6 text-brand-ink/40" aria-hidden="true" />
                </div>
                <h3 className="mt-20 font-display text-2xl font-bold leading-tight tracking-[-0.04em] text-brand-ink">
                  {step.title}
                </h3>
                <p className="mt-4 leading-7 text-brand-ink/60">{step.description}</p>
              </article>
            )
          })}
        </div>

        <div className="human-handoff mt-16">
          <div className="max-w-xl">
            <p className="eyebrow-light">Quando precisa de gente, chega até gente</p>
            <h3 className="mt-5 font-display text-3xl font-bold leading-tight tracking-[-0.05em] text-white sm:text-4xl">
              Sem fazer o cliente começar tudo de novo.
            </h3>
            <p className="mt-5 text-lg leading-8 text-white/60">
              A IA identifica o limite, resume a conversa e entrega o atendimento com contexto. Sua equipe entra no
              momento certo, sabendo quem é o cliente e o que ele precisa.
            </p>
          </div>

          <div className="conversation-card">
            <div className="conversation-line">
              <span className="avatar avatar-ai">
                <AudioLines className="h-4 w-4" aria-hidden="true" />
              </span>
              <div>
                <p className="conversation-name">Integrix AI</p>
                <p className="conversation-bubble">Entendi. Vou chamar uma pessoa da equipe e já passar todo o contexto.</p>
              </div>
            </div>
            <div className="handoff-line">
              <span />
              <p>Histórico enviado em 2 segundos</p>
              <span />
            </div>
            <div className="conversation-line">
              <span className="avatar avatar-human">
                <UserRoundCheck className="h-4 w-4" aria-hidden="true" />
              </span>
              <div>
                <p className="conversation-name">Equipe humana</p>
                <p className="conversation-bubble conversation-bubble-light">
                  Olá! Já vi a sua solicitação e vou continuar daqui.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

function UseCases() {
  return (
    <section className="bg-brand-lime px-5 py-24 sm:px-8 sm:py-32 lg:px-12">
      <div className="mx-auto max-w-[1440px]">
        <div className="grid gap-8 lg:grid-cols-[0.8fr_1.2fr] lg:items-end">
          <div>
            <p className="eyebrow">Comece pelo que mais pesa hoje</p>
            <h2 className="section-title mt-5">Uma IA que resolve tarefas, não apenas conversa.</h2>
          </div>
          <p className="max-w-2xl text-lg leading-8 text-brand-ink/65 lg:justify-self-end">
            O primeiro projeto deve atacar um processo frequente, mensurável e valioso. A partir dele, a automação
            cresce junto com a confiança da sua operação.
          </p>
        </div>

        <div className="mt-14 grid gap-5 lg:grid-cols-3">
          {useCases.map((useCase) => {
            const IconComponent = useCase.icon
            return (
              <article className="use-case-card" key={useCase.title}>
                <IconComponent className="h-7 w-7 text-brand-green" aria-hidden="true" />
                <h3 className="mt-8 font-display text-3xl font-bold tracking-[-0.05em] text-brand-ink">{useCase.title}</h3>
                <ul className="mt-8 space-y-4">
                  {useCase.items.map((item) => (
                    <li className="flex items-start gap-3 text-brand-ink/70" key={item}>
                      <Check className="mt-0.5 h-5 w-5 shrink-0 text-brand-green" aria-hidden="true" />
                      {item}
                    </li>
                  ))}
                </ul>
              </article>
            )
          })}
        </div>

        <div className="mt-8 flex flex-wrap items-center justify-between gap-6 rounded-2xl border border-brand-ink/15 px-6 py-5">
          <div className="flex items-center gap-3">
            <Building2 className="h-5 w-5 text-brand-green" aria-hidden="true" />
            <p className="font-semibold text-brand-ink">
              Também desenhamos fluxos específicos para saúde, serviços e centrais de relacionamento.
            </p>
          </div>
          <a className="inline-flex items-center gap-2 text-sm font-bold text-brand-ink" href={contactHref}>
            Conversar sobre meu caso
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </a>
        </div>
      </div>
    </section>
  )
}

function SecuritySection() {
  const controls = [
    "Acessos administrativos protegidos",
    "Permissões definidas por operação",
    "Dados sensíveis tratados com cuidado",
    "Histórico consultável dos atendimentos",
    "Limites claros para cada ação da IA",
    "Indicadores e alertas para a gestão",
  ]

  return (
    <section className="bg-brand-cream px-5 py-24 sm:px-8 sm:py-32 lg:px-12" id="seguranca">
      <div className="mx-auto grid max-w-[1440px] gap-14 lg:grid-cols-[0.86fr_1.14fr] lg:items-center">
        <div>
          <div className="security-emblem">
            <ShieldCheck className="h-12 w-12" aria-hidden="true" />
            <span className="security-ring security-ring-one" />
            <span className="security-ring security-ring-two" />
          </div>
          <p className="eyebrow mt-10">Confiança para operar de verdade</p>
          <h2 className="section-title mt-5">Automação com controle. Não uma caixa-preta.</h2>
          <p className="mt-6 max-w-xl text-lg leading-8 text-brand-ink/65">
            Sua empresa define o que a IA pode fazer, quais informações pode consultar e quando deve chamar uma pessoa.
            Tudo o que importa fica visível para gestão e melhoria.
          </p>
        </div>

        <div className="overflow-hidden rounded-[2rem] border border-brand-ink/10 bg-white">
          {controls.map((control, index) => (
            <div className="flex items-center gap-4 border-b border-brand-ink/10 p-5 last:border-0 sm:p-6" key={control}>
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-brand-green/10 font-display text-xs font-bold text-brand-green">
                {String(index + 1).padStart(2, "0")}
              </span>
              <p className="font-semibold text-brand-ink">{control}</p>
              <LockKeyhole className="ml-auto hidden h-4 w-4 text-brand-ink/25 sm:block" aria-hidden="true" />
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

function ManagementSection() {
  return (
    <section className="bg-brand-paper px-5 py-24 sm:px-8 sm:py-32 lg:px-12">
      <div className="mx-auto max-w-[1440px] overflow-hidden rounded-[2.5rem] bg-brand-ink text-white">
        <div className="grid lg:grid-cols-[0.8fr_1.2fr]">
          <div className="p-8 sm:p-12 lg:p-16">
            <p className="eyebrow-light">Gestão que cabe na rotina</p>
            <h2 className="mt-5 font-display text-4xl font-bold leading-[1.02] tracking-[-0.06em] sm:text-5xl">
              Saiba o que está acontecendo sem ouvir ligação por ligação.
            </h2>
            <p className="mt-6 text-lg leading-8 text-white/60">
              O painel transforma conversas em visão de negócio: demanda, resolução, tempo, falhas e oportunidades de
              melhoria.
            </p>
            <a className="button button-lime mt-9" href={opsConsoleUrl}>
              Conhecer o painel
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </a>
          </div>

          <div className="management-panel">
            <div className="flex flex-wrap items-center justify-between gap-4 border-b border-brand-ink/10 pb-5">
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.16em] text-brand-green">Visão da operação</p>
                <p className="mt-2 font-display text-xl font-bold text-brand-ink">Resultados desta semana</p>
              </div>
              <span className="rounded-full bg-emerald-100 px-3 py-1.5 text-xs font-bold text-emerald-800">
                Operação saudável
              </span>
            </div>
            <div className="mt-5 grid gap-3 sm:grid-cols-3">
              {[
                ["Atendidos", "7.842", "+18%"],
                ["Resolvidos", "81%", "+6%"],
                ["Encaminhados", "14%", "-3%"],
              ].map(([label, value, delta]) => (
                <div className="rounded-xl border border-brand-ink/10 bg-white p-4" key={label}>
                  <span className="text-xs font-semibold text-brand-ink/45">{label}</span>
                  <strong className="mt-3 block font-display text-2xl text-brand-ink">{value}</strong>
                  <span className="mt-2 inline-block text-xs font-bold text-brand-green">{delta}</span>
                </div>
              ))}
            </div>
            <div className="mt-3 rounded-xl border border-brand-ink/10 bg-white p-5">
              <div className="flex items-center justify-between gap-4">
                <p className="text-sm font-bold text-brand-ink">Volume por dia</p>
                <LineChart className="h-5 w-5 text-brand-green" aria-hidden="true" />
              </div>
              <div className="mt-6 flex h-36 items-end gap-3">
                {[38, 62, 47, 75, 58, 88, 71].map((height, index) => (
                  <div className="flex flex-1 flex-col items-center gap-2" key={`${height}-${index}`}>
                    <span
                      className={`w-full rounded-t-md ${index === 5 ? "bg-brand-lime" : "bg-brand-green/20"}`}
                      style={{ height: `${height}%` }}
                    />
                    <span className="text-[10px] font-semibold uppercase text-brand-ink/35">
                      {["seg", "ter", "qua", "qui", "sex", "sáb", "dom"][index]}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

function FaqSection() {
  return (
    <section className="bg-brand-cream px-5 py-24 sm:px-8 sm:py-32 lg:px-12" id="duvidas">
      <div className="mx-auto grid max-w-[1440px] gap-14 lg:grid-cols-[0.7fr_1.3fr]">
        <div>
          <p className="eyebrow">Perguntas que importam</p>
          <h2 className="section-title mt-5">Sem palavras difíceis. Vamos ao ponto.</h2>
          <p className="mt-6 max-w-md text-lg leading-8 text-brand-ink/60">
            Se a sua dúvida não estiver aqui, conte como funciona sua operação. A conversa começa pelo problema, não
            pela tecnologia.
          </p>
        </div>

        <div className="border-t border-brand-ink/15">
          {faqs.map((faq, index) => (
            <details className="faq-item group" key={faq.question} open={index === 0}>
              <summary>
                <span>{faq.question}</span>
                <span className="faq-icon">
                  <ChevronRight className="h-5 w-5" aria-hidden="true" />
                </span>
              </summary>
              <p>{faq.answer}</p>
            </details>
          ))}
        </div>
      </div>
    </section>
  )
}

function FinalCta() {
  return (
    <section className="bg-brand-coral px-5 py-20 sm:px-8 sm:py-24 lg:px-12" id="contato">
      <div className="mx-auto max-w-[1440px] text-center">
        <Sparkles className="mx-auto h-10 w-10 text-brand-ink" aria-hidden="true" />
        <p className="eyebrow mt-7">O próximo atendimento pode custar menos e valer mais</p>
        <h2 className="mx-auto mt-5 max-w-5xl font-display text-[clamp(3rem,7vw,6.5rem)] font-extrabold leading-[0.97] tracking-[-0.055em] text-brand-ink">
          Descubra onde a IA gera retorno primeiro.
        </h2>
        <p className="mx-auto mt-7 max-w-2xl text-lg leading-8 text-brand-ink/70">
          Em uma conversa direta, mapeamos seu volume, seus custos e o melhor processo para começar — sem apresentação
          genérica e sem compromisso.
        </p>
        <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <a className="button button-dark justify-center" href={contactHref}>
            Agendar meu diagnóstico
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </a>
          <a className="button button-coral-ghost justify-center" href="mailto:contato@integrix.com.br">
            contato@integrix.com.br
          </a>
        </div>
      </div>
    </section>
  )
}

function Footer() {
  return (
    <footer className="bg-brand-ink px-5 py-12 text-white sm:px-8 lg:px-12">
      <div className="mx-auto max-w-[1440px]">
        <div className="flex flex-col gap-10 border-b border-white/10 pb-10 md:flex-row md:items-end md:justify-between">
          <div>
            <a className="flex items-center gap-3" href="#top" aria-label="Integrix AI — início">
              <span className="logo-mark logo-mark-light">
                <AudioLines className="h-5 w-5" aria-hidden="true" />
              </span>
              <span className="font-display text-xl font-bold tracking-[-0.04em]">
                Integrix <span className="text-brand-lime">AI</span>
              </span>
            </a>
            <p className="mt-5 max-w-md leading-7 text-white/50">
              Atendimento por voz com IA para empresas que querem crescer com eficiência, controle e uma experiência
              melhor para o cliente.
            </p>
          </div>
          <div className="flex flex-wrap gap-x-7 gap-y-3 text-sm font-semibold text-white/65">
            {navLinks.slice(0, 4).map((link) => (
              <a className="transition hover:text-brand-lime" href={link.href} key={link.href}>
                {link.label}
              </a>
            ))}
            <a className="transition hover:text-brand-lime" href={opsConsoleUrl}>
              Painel
            </a>
          </div>
        </div>
        <div className="flex flex-col gap-3 pt-8 text-xs text-white/35 sm:flex-row sm:items-center sm:justify-between">
          <p>© {new Date().getFullYear()} Integrix AI. Todos os direitos reservados.</p>
          <p>Feito para negócios que valorizam tempo, resultado e boas conversas.</p>
        </div>
      </div>
    </footer>
  )
}

export default function App() {
  return (
    <main className="min-h-screen overflow-hidden bg-brand-cream text-brand-ink">
      <Header />
      <Hero />
      <ProblemSection />
      <ImpactCalculator />
      <HowItWorks />
      <UseCases />
      <SecuritySection />
      <ManagementSection />
      <FaqSection />
      <FinalCta />
      <Footer />
    </main>
  )
}
