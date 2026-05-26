import {
  Activity,
  ArrowRight,
  BarChart3,
  Bot,
  Building2,
  CheckCircle2,
  ClipboardCheck,
  Headphones,
  HeartPulse,
  KeyRound,
  Layers3,
  LineChart,
  LockKeyhole,
  Network,
  PhoneCall,
  Radar,
  Route,
  ShieldCheck,
  Sparkles,
  UserCheck,
  type LucideIcon,
} from "lucide-react"

const contactHref = "mailto:contato@integrix.com.br?subject=Demonstra%C3%A7%C3%A3o%20Integrix%20AI"
const opsConsoleUrl = import.meta.env.VITE_OPS_CONSOLE_URL || "/dashboard"

type IconCard = {
  title: string
  description: string
  icon: LucideIcon
}

const navLinks = [
  { label: "Produto", href: "#produto" },
  { label: "Segurança", href: "#seguranca" },
  { label: "Operação", href: "#operacao" },
  { label: "Como funciona", href: "#como-funciona" },
  { label: "Contato", href: "#contato" },
]

const painPoints = [
  "Clientes repetem informações porque os canais não conversam entre si.",
  "Gestores têm pouca visibilidade do que acontece nos atendimentos.",
  "Equipes perdem tempo conferindo processos manualmente.",
  "A empresa quer usar IA, mas precisa manter controle e segurança.",
  "A passagem para humano precisa ser registrada e organizada.",
  "Crescer a operação sem acompanhamento vira risco.",
]

const features: IconCard[] = [
  {
    title: "Direcionamento inteligente de chamadas",
    description: "A ligação segue o caminho certo por unidade, cliente, canal ou regra de atendimento.",
    icon: Route,
  },
  {
    title: "Integração segura com sistemas internos",
    description: "A IA consulta e registra informações nos sistemas da empresa com limites bem definidos.",
    icon: Network,
  },
  {
    title: "Registro e auditoria de atendimentos",
    description: "Cada interação importante fica documentada para suporte, qualidade e gestão.",
    icon: ClipboardCheck,
  },
  {
    title: "Painel de gestão operacional",
    description: "Acompanhe volume, resolução, qualidade, falhas e evolução da operação em um só lugar.",
    icon: BarChart3,
  },
  {
    title: "Controle por cliente, unidade ou operação",
    description: "Diferentes áreas podem seguir regras próprias sem perder padronização de gestão.",
    icon: Layers3,
  },
  {
    title: "Indicadores de qualidade e custos",
    description: "Acompanhe sinais de desempenho e uso para tomar decisões com mais previsibilidade.",
    icon: LineChart,
  },
  {
    title: "Diagnóstico de falhas",
    description: "Identifique gargalos e exceções antes que eles prejudiquem o atendimento.",
    icon: Radar,
  },
  {
    title: "Passagem organizada para atendimento humano",
    description: "Quando a IA não deve resolver sozinha, a equipe recebe contexto para continuar o atendimento.",
    icon: UserCheck,
  },
]

const solutionFlow = [
  "A IA atende e entende a solicitação do cliente.",
  "A Integrix AI conecta a conversa aos sistemas internos autorizados.",
  "O atendimento fica registrado com segurança para consulta e auditoria.",
  "A gestão acompanha indicadores, qualidade e exceções no painel.",
]

const securityItems: IconCard[] = [
  {
    title: "Acesso administrativo protegido",
    description: "O painel de gestão é reservado a pessoas autorizadas da operação.",
    icon: LockKeyhole,
  },
  {
    title: "Dados sensíveis mascarados",
    description: "Registros podem ocultar informações delicadas sem perder rastreabilidade.",
    icon: ShieldCheck,
  },
  {
    title: "Permissões por cliente ou unidade",
    description: "Cada operação pode ter acessos, regras e limites adequados ao seu contexto.",
    icon: KeyRound,
  },
  {
    title: "Histórico consultável de atendimentos",
    description: "A empresa pode revisar conversas, decisões e encaminhamentos com clareza.",
    icon: ClipboardCheck,
  },
  {
    title: "Integrações validadas",
    description: "As conexões seguem regras definidas antes de acionar sistemas corporativos.",
    icon: Network,
  },
  {
    title: "Controles para produção",
    description: "A solução foi pensada para operação contínua, não apenas para demonstrações isoladas.",
    icon: Building2,
  },
]

const useCases: IconCard[] = [
  {
    title: "Operadoras de saúde",
    description: "Apoio em consultas sobre rede credenciada, status de solicitações e orientação de atendimento.",
    icon: HeartPulse,
  },
  {
    title: "Centrais de atendimento",
    description: "Automação de perguntas frequentes e processos repetitivos com controle de qualidade.",
    icon: Headphones,
  },
  {
    title: "Empresas com sistemas legados",
    description: "Conexão entre IA de voz e sistemas já existentes, sem troca imediata da base operacional.",
    icon: Building2,
  },
  {
    title: "Gestão de qualidade",
    description: "Registros e indicadores para revisar gargalos, melhorar scripts e apoiar decisões.",
    icon: Activity,
  },
]

const dashboardRows = [
  { client: "Maria A.", channel: "Telefone", status: "Resolvido", time: "09:42" },
  { client: "João P.", channel: "URA", status: "Em análise", time: "09:36" },
  { client: "Clínica Norte", channel: "Retorno", status: "Humano", time: "09:28" },
]

const integrationStatus = ["CRM conectado", "Agenda ativa", "Base de clientes OK"]

function Header() {
  return (
    <header className="fixed inset-x-0 top-0 z-50 border-b border-slate-200/80 bg-white/82 backdrop-blur-xl">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4 sm:px-6 lg:px-8">
        <a className="flex items-center gap-3" href="#top" aria-label="Integrix AI">
          <span className="grid h-10 w-10 place-items-center rounded-xl bg-corporate-700 text-white shadow-sm">
            <Bot className="h-5 w-5" aria-hidden="true" />
          </span>
          <span className="font-display text-lg font-bold tracking-normal text-slate-950">Integrix AI</span>
        </a>
        <nav className="hidden items-center gap-7 text-sm font-semibold text-slate-600 lg:flex" aria-label="Principal">
          {navLinks.map((link) => (
            <a className="transition hover:text-corporate-700" href={link.href} key={link.href}>
              {link.label}
            </a>
          ))}
        </nav>
        <div className="flex items-center gap-3">
          <a
            className="hidden rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-bold text-slate-700 shadow-sm transition hover:border-corporate-200 hover:text-corporate-700 sm:inline-flex"
            href={opsConsoleUrl}
          >
            Ver painel
          </a>
          <a
            className="rounded-lg bg-corporate-700 px-4 py-2 text-sm font-bold text-white shadow-sm transition hover:bg-corporate-800"
            href={contactHref}
          >
            Solicitar demonstração
          </a>
        </div>
      </div>
    </header>
  )
}

function SectionHeader({ eyebrow, title, description }: { eyebrow: string; title: string; description: string }) {
  return (
    <div className="mx-auto mb-12 max-w-3xl text-center">
      <p className="mb-4 text-sm font-extrabold uppercase tracking-[0.2em] text-corporate-700">{eyebrow}</p>
      <h2 className="font-display text-3xl font-bold text-slate-950 sm:text-4xl">{title}</h2>
      <p className="mt-5 text-base leading-8 text-slate-600 sm:text-lg">{description}</p>
    </div>
  )
}

function MetricCard({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="min-w-0 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">{label}</p>
      <p className="mt-2 break-words font-display text-xl font-bold leading-tight text-slate-950 sm:text-[1.35rem]">
        {value}
      </p>
      <p className="mt-1 text-xs text-slate-500">{detail}</p>
    </div>
  )
}

function LineChartMockup() {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <p className="text-sm font-bold text-slate-900">Atendimentos nos últimos dias</p>
        <span className="rounded-full bg-cyan-50 px-3 py-1 text-xs font-bold text-corporate-700">+18%</span>
      </div>
      <svg className="h-32 w-full" viewBox="0 0 420 128" role="img" aria-label="Gráfico de atendimentos">
        <defs>
          <linearGradient id="lineFill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#2563eb" stopOpacity="0.22" />
            <stop offset="100%" stopColor="#2563eb" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d="M0 96 C48 82 64 70 105 76 C148 82 155 44 202 50 C250 56 260 26 306 34 C356 43 366 18 420 24 L420 128 L0 128 Z" fill="url(#lineFill)" />
        <path d="M0 96 C48 82 64 70 105 76 C148 82 155 44 202 50 C250 56 260 26 306 34 C356 43 366 18 420 24" fill="none" stroke="#2563eb" strokeLinecap="round" strokeWidth="4" />
      </svg>
    </div>
  )
}

function BarChartMockup() {
  const bars = [
    { label: "Matriz", value: 78 },
    { label: "Sul", value: 54 },
    { label: "Norte", value: 42 },
    { label: "Digital", value: 66 },
  ]

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="mb-4 text-sm font-bold text-slate-900">Chamadas por unidade</p>
      <div className="space-y-3">
        {bars.map((bar) => (
          <div className="grid grid-cols-[64px_1fr] items-center gap-3" key={bar.label}>
            <span className="text-xs font-semibold text-slate-500">{bar.label}</span>
            <span className="h-3 overflow-hidden rounded-full bg-slate-100">
              <span className="block h-full rounded-full bg-gradient-to-r from-corporate-600 to-cyan-400" style={{ width: `${bar.value}%` }} />
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

function DashboardMockup() {
  return (
    <div className="relative rounded-3xl border border-slate-200 bg-white/92 p-4 shadow-[0_28px_90px_rgba(15,23,42,0.16)] backdrop-blur md:p-5">
      <div className="absolute -inset-4 -z-10 rounded-[2rem] bg-gradient-to-br from-corporate-200/55 via-cyan-100/50 to-violet-100/60 blur-2xl" />
      <div className="mb-5 flex flex-col gap-4 border-b border-slate-200 pb-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-corporate-700">Painel de gestão</p>
          <h2 className="mt-1 font-display text-xl font-bold text-slate-950">Operação de atendimento</h2>
        </div>
        <div className="flex flex-wrap gap-2">
          {["Operação normal", "Auditoria ativa", "Integrações OK"].map((badge) => (
            <span className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-bold text-emerald-700" key={badge}>
              {badge}
            </span>
          ))}
        </div>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Atendimentos hoje" value="1.248" detail="volume acompanhado" />
        <MetricCard label="Taxa de resolução" value="82%" detail="sem nova transferência" />
        <MetricCard label="Tempo médio" value="2m18s" detail="por atendimento" />
        <MetricCard label="Custo estimado" value="Em controle" detail="uso sob acompanhamento" />
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-[1.25fr_0.75fr]">
        <LineChartMockup />
        <BarChartMockup />
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <p className="mb-4 text-sm font-bold text-slate-900">Últimos atendimentos</p>
          <div className="space-y-3">
            {dashboardRows.map((row) => (
              <div className="grid grid-cols-[1fr_auto] gap-3 rounded-lg bg-slate-50 p-3 sm:grid-cols-[1fr_90px_90px_54px]" key={`${row.client}-${row.time}`}>
                <span className="text-sm font-semibold text-slate-800">{row.client}</span>
                <span className="hidden text-sm text-slate-500 sm:inline">{row.channel}</span>
                <span className="text-sm font-semibold text-corporate-700">{row.status}</span>
                <span className="hidden text-sm text-slate-500 sm:inline">{row.time}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <p className="mb-4 text-sm font-bold text-slate-900">Status das integrações</p>
          <div className="space-y-3">
            {integrationStatus.map((item) => (
              <div className="flex items-center gap-3 rounded-lg bg-slate-50 p-3" key={item}>
                <CheckCircle2 className="h-5 w-5 text-emerald-600" aria-hidden="true" />
                <span className="text-sm font-semibold text-slate-700">{item}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function Hero() {
  return (
    <section className="relative overflow-hidden bg-[linear-gradient(135deg,#f8fbff_0%,#eef6ff_46%,#f7f3ff_100%)] px-4 pb-20 pt-32 sm:px-6 lg:px-8" id="top">
      <div className="absolute inset-x-0 top-20 h-64 bg-[radial-gradient(circle_at_20%_20%,rgba(37,99,235,0.14),transparent_28rem),radial-gradient(circle_at_80%_10%,rgba(124,58,237,0.12),transparent_30rem)]" aria-hidden="true" />
      <div className="relative mx-auto grid max-w-7xl gap-12 lg:grid-cols-[0.88fr_1.12fr] lg:items-center">
        <div>
          <div className="reveal inline-flex rounded-full border border-corporate-200 bg-white/80 px-4 py-2 text-xs font-bold uppercase tracking-[0.16em] text-corporate-700 shadow-sm">
            Plataforma para operações de atendimento
          </div>
          <h1 className="reveal reveal-delay-1 mt-7 font-display text-4xl font-bold leading-tight text-slate-950 sm:text-5xl lg:text-6xl">
            IA de voz para operações de atendimento que exigem controle, integração e rastreabilidade.
          </h1>
          <p className="reveal reveal-delay-2 mt-7 max-w-2xl text-lg leading-9 text-slate-600">
            A Integrix AI ajuda empresas a automatizar atendimentos por voz, conectar a IA aos sistemas internos e
            acompanhar a operação com segurança, auditoria e indicadores claros.
          </p>
          <div className="reveal reveal-delay-3 mt-9 flex flex-col gap-3 sm:flex-row">
            <a
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-corporate-700 px-6 py-3 text-sm font-bold text-white shadow-sm transition hover:bg-corporate-800"
              href={contactHref}
            >
              Solicitar demonstração
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </a>
            <a
              className="inline-flex items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-6 py-3 text-sm font-bold text-slate-700 shadow-sm transition hover:border-corporate-200 hover:text-corporate-700"
              href="#como-funciona"
            >
              Ver como funciona
            </a>
          </div>
        </div>
        <DashboardMockup />
      </div>
    </section>
  )
}

function ProblemSection() {
  return (
    <section className="px-4 py-24 sm:px-6 lg:px-8" id="produto">
      <div className="mx-auto max-w-7xl">
        <SectionHeader
          eyebrow="Desafio"
          title="A IA precisa resolver o atendimento sem desorganizar a operação."
          description="O ganho real aparece quando atendimento, sistemas internos, registros e gestão passam a trabalhar juntos."
        />
        <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
          {painPoints.map((item) => (
            <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm transition hover:-translate-y-1 hover:shadow-lg" key={item}>
              <div className="mb-4 h-1 w-12 rounded-full bg-gradient-to-r from-corporate-600 to-cyan-400" />
              <p className="leading-7 text-slate-700">{item}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

function SolutionSection() {
  return (
    <section className="border-y border-slate-200 bg-white px-4 py-24 sm:px-6 lg:px-8">
      <div className="mx-auto grid max-w-7xl gap-10 lg:grid-cols-[0.9fr_1.1fr] lg:items-center">
        <div>
          <p className="mb-4 text-xs font-bold uppercase tracking-[0.18em] text-corporate-700">Solução</p>
          <h2 className="font-display text-3xl font-bold text-slate-950 sm:text-4xl">
            A IA atende. A Integrix AI conecta, registra, protege e mostra o que está acontecendo.
          </h2>
          <p className="mt-5 text-lg leading-8 text-slate-600">
            A plataforma organiza a camada operacional por trás do atendimento com IA, para que gestores tenham
            previsibilidade, dados confiáveis e menos retrabalho.
          </p>
        </div>
        <div className="rounded-3xl border border-slate-200 bg-slate-50 p-5 shadow-sm">
          {solutionFlow.map((item, index) => (
            <div className="flex gap-4 border-b border-slate-200 py-4 last:border-b-0" key={item}>
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-corporate-700 text-sm font-bold text-white">
                {index + 1}
              </span>
              <p className="self-center leading-7 text-slate-700">{item}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

function FeatureCard({ item }: { item: IconCard }) {
  const Icon = item.icon

  return (
    <article className="group rounded-2xl border border-slate-200 bg-white p-6 shadow-sm transition hover:-translate-y-1 hover:border-corporate-200 hover:shadow-lg">
      <div className="mb-5 grid h-11 w-11 place-items-center rounded-xl bg-corporate-50 text-corporate-700 transition group-hover:bg-corporate-700 group-hover:text-white">
        <Icon className="h-5 w-5" aria-hidden="true" />
      </div>
      <h3 className="font-display text-lg font-bold text-slate-950">{item.title}</h3>
      <p className="mt-3 leading-7 text-slate-600">{item.description}</p>
    </article>
  )
}

function FeaturesSection() {
  return (
    <section className="px-4 py-24 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-7xl">
        <SectionHeader
          eyebrow="Funcionalidades"
          title="Recursos para atendimento, gestão e qualidade."
          description="Uma camada de automação para conectar conversas, sistemas e acompanhamento operacional em linguagem simples para a gestão."
        />
        <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-4">
          {features.map((item) => (
            <FeatureCard item={item} key={item.title} />
          ))}
        </div>
      </div>
    </section>
  )
}

function HowItWorksSection() {
  return (
    <section className="border-y border-slate-200 bg-slate-50 px-4 py-24 sm:px-6 lg:px-8" id="como-funciona">
      <div className="mx-auto max-w-7xl">
        <SectionHeader
          eyebrow="Como funciona"
          title="Um fluxo claro entre cliente, IA, sistemas e gestão."
          description="A arquitetura continua robusta, mas a experiência para o negócio é simples: atender, consultar, registrar e acompanhar."
        />
        <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-4">
          {[
            { title: "Atende", description: "O cliente conversa com a IA por voz, como em um atendimento comum.", icon: PhoneCall },
            { title: "Integra", description: "A plataforma conecta a conversa aos sistemas internos autorizados.", icon: Network },
            { title: "Registra", description: "O que importa fica documentado para auditoria, suporte e qualidade.", icon: ClipboardCheck },
            { title: "Acompanha", description: "A gestão visualiza indicadores, exceções e oportunidades de melhoria.", icon: LineChart },
          ].map((item) => {
            const Icon = item.icon
            return (
              <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm" key={item.title}>
                <Icon className="mb-5 h-7 w-7 text-corporate-700" aria-hidden="true" />
                <h3 className="font-display text-xl font-bold text-slate-950">{item.title}</h3>
                <p className="mt-3 leading-7 text-slate-600">{item.description}</p>
              </article>
            )
          })}
        </div>
      </div>
    </section>
  )
}

function SecuritySection() {
  return (
    <section className="px-4 py-24 sm:px-6 lg:px-8" id="seguranca">
      <div className="mx-auto max-w-7xl">
        <SectionHeader
          eyebrow="Segurança"
          title="Controle para operar IA em ambientes corporativos."
          description="A proposta é automatizar atendimentos mantendo acesso protegido, registros confiáveis e regras claras por operação."
        />
        <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
          {securityItems.map((item) => (
            <FeatureCard item={item} key={item.title} />
          ))}
        </div>
      </div>
    </section>
  )
}

function UseCasesSection() {
  return (
    <section className="border-y border-slate-200 bg-white px-4 py-24 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-7xl">
        <SectionHeader
          eyebrow="Aplicações"
          title="Para operações que precisam atender melhor sem perder controle."
          description="A Integrix AI é indicada para empresas que querem usar voz com IA em processos reais, com registro, integração e acompanhamento."
        />
        <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-4">
          {useCases.map((item) => (
            <FeatureCard item={item} key={item.title} />
          ))}
        </div>
      </div>
    </section>
  )
}

function OpsConsoleSection() {
  return (
    <section className="px-4 py-24 sm:px-6 lg:px-8" id="operacao">
      <div className="mx-auto grid max-w-7xl gap-10 rounded-3xl border border-corporate-100 bg-gradient-to-br from-white via-corporate-50 to-violet-50 p-6 shadow-[0_22px_70px_rgba(15,23,42,0.10)] md:p-10 lg:grid-cols-[0.9fr_1.1fr] lg:items-center">
        <div>
          <p className="mb-4 text-xs font-bold uppercase tracking-[0.18em] text-corporate-700">Painel de gestão</p>
          <h2 className="font-display text-3xl font-bold text-slate-950 sm:text-4xl">
            Sua equipe acompanha a operação em um só lugar.
          </h2>
          <p className="mt-5 text-lg leading-8 text-slate-600">
            O painel administrativo ajuda a entender atendimentos, revisar registros, acompanhar indicadores e agir quando
            algum processo precisa de atenção.
          </p>
          <a
            className="mt-8 inline-flex items-center justify-center gap-2 rounded-lg bg-corporate-700 px-6 py-3 text-sm font-bold text-white shadow-sm transition hover:bg-corporate-800"
            href={opsConsoleUrl}
          >
            Entrar no painel
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </a>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="grid gap-3 sm:grid-cols-2">
            {[
              "Visão geral da operação",
              "Histórico por atendimento",
              "Indicadores de qualidade",
              "Diagnóstico de falhas",
              "Filtros por unidade ou assistente",
              "Ações de suporte administrativo",
            ].map((item) => (
              <div className="flex items-center gap-3 rounded-xl bg-slate-50 p-4" key={item}>
                <CheckCircle2 className="h-5 w-5 text-emerald-600" aria-hidden="true" />
                <span className="text-sm font-semibold text-slate-700">{item}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}

function FinalCta() {
  return (
    <section className="px-4 py-24 sm:px-6 lg:px-8" id="contato">
      <div className="mx-auto max-w-5xl rounded-3xl bg-slate-950 px-6 py-16 text-center shadow-[0_24px_80px_rgba(15,23,42,0.20)] sm:px-10">
        <Sparkles className="mx-auto mb-8 h-12 w-12 text-cyan-300" aria-hidden="true" />
        <h2 className="font-display text-3xl font-bold text-white sm:text-5xl">
          Automatize atendimentos por voz com segurança, integração e gestão.
        </h2>
        <p className="mx-auto mt-6 max-w-2xl text-lg leading-8 text-slate-300">
          Converse com a Integrix AI para entender como a IA pode apoiar sua operação com mais clareza e controle.
        </p>
        <div className="mt-9 flex flex-col justify-center gap-3 sm:flex-row">
          <a className="rounded-lg bg-white px-6 py-3 text-sm font-bold text-slate-950 transition hover:bg-cyan-50" href={contactHref}>
            Solicitar demonstração
          </a>
          <a
            className="rounded-lg border border-white/20 px-6 py-3 text-sm font-bold text-white transition hover:border-cyan-300 hover:text-cyan-200"
            href={contactHref}
          >
            Falar com especialista
          </a>
        </div>
      </div>
    </section>
  )
}

function Footer() {
  return (
    <footer className="border-t border-slate-200 bg-white px-4 py-10 sm:px-6 lg:px-8">
      <div className="mx-auto flex max-w-7xl flex-col gap-8 md:flex-row md:items-center md:justify-between">
        <div>
          <p className="font-display text-lg font-bold text-slate-950">Integrix AI</p>
          <p className="mt-2 max-w-xl text-sm leading-6 text-slate-500">
            IA de voz para call centers que precisam de automação, integração e gestão confiável.
          </p>
        </div>
        <div className="flex flex-wrap gap-5 text-sm font-semibold text-slate-600">
          <a className="hover:text-corporate-700" href="#produto">
            Produto
          </a>
          <a className="hover:text-corporate-700" href="#seguranca">
            Segurança
          </a>
          <a className="hover:text-corporate-700" href="#como-funciona">
            Como funciona
          </a>
          <a className="hover:text-corporate-700" href={opsConsoleUrl}>
            Painel
          </a>
        </div>
      </div>
      <p className="mx-auto mt-8 max-w-7xl text-sm text-slate-500">© {new Date().getFullYear()} Integrix AI. Todos os direitos reservados.</p>
    </footer>
  )
}

export default function App() {
  return (
    <main className="min-h-screen overflow-hidden bg-[#f8fbff] text-slate-900">
      <Header />
      <Hero />
      <ProblemSection />
      <SolutionSection />
      <FeaturesSection />
      <HowItWorksSection />
      <SecuritySection />
      <UseCasesSection />
      <OpsConsoleSection />
      <FinalCta />
      <Footer />
    </main>
  )
}
