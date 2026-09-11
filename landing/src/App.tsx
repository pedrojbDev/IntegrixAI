import { useEffect, useRef, useState } from "react"
import {
  ArrowDown, ArrowRight, ArrowUpRight, AudioLines, Check,
  ChevronDown, FileText, Headphones, LayoutDashboard, LockKeyhole, Menu,
  MessageSquareText, Phone, PhoneIncoming, Route, ShieldCheck, X,
} from "lucide-react"
import ImpactCalculator from "./ImpactCalculator"

const contactHref = "mailto:contato@integrix.com.br?subject=Quero%20conhecer%20a%20Integrix%20AI&body=Ol%C3%A1%2C%20quero%20conversar%20sobre%20o%20atendimento%20da%20minha%20empresa."
const opsConsoleUrl = import.meta.env.VITE_OPS_CONSOLE_URL || "/dashboard"
const navLinks = [
  { label: "A solução", href: "#solucao" },
  { label: "Calculadora", href: "#calculadora" },
  { label: "Como funciona", href: "#como-funciona" },
  { label: "Dúvidas", href: "#duvidas" },
]

function Brand() {
  return (
    <a className="brand" href="#top" aria-label="Integrix AI — início">
      <svg className="brand-mark" viewBox="0 0 32 36" fill="none" aria-hidden="true">
        <path d="M2 9 16 1l14 8v8l-14 8L2 17V9Z" stroke="currentColor" strokeWidth="2.5" />
        <path d="m2 18 14 8 14-8M2 26l14 8 14-8M16 9v8" stroke="currentColor" strokeWidth="2.5" />
      </svg>
      <span>integrix<span className="brand-ai">AI</span></span>
    </a>
  )
}

function Header() {
  const [menuOpen, setMenuOpen] = useState(false)
  const menuButton = useRef<HTMLButtonElement>(null)
  const header = useRef<HTMLElement>(null)

  useEffect(() => {
    if (!menuOpen) return
    function dismiss(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setMenuOpen(false)
        menuButton.current?.focus()
      }
    }
    function clickOutside(event: PointerEvent) {
      if (event.target instanceof Node && !header.current?.contains(event.target)) setMenuOpen(false)
    }
    const desktop = window.matchMedia("(min-width: 1080px)")
    function closeOnDesktop(event: MediaQueryListEvent) {
      if (event.matches) setMenuOpen(false)
    }
    document.addEventListener("keydown", dismiss)
    document.addEventListener("pointerdown", clickOutside)
    desktop.addEventListener("change", closeOnDesktop)
    return () => {
      document.removeEventListener("keydown", dismiss)
      document.removeEventListener("pointerdown", clickOutside)
      desktop.removeEventListener("change", closeOnDesktop)
    }
  }, [menuOpen])

  return (
    <header className="site-header" ref={header}>
      <div className="container header-inner">
        <Brand />
        <nav className="desktop-nav" aria-label="Principal">
          {navLinks.map((link) => <a href={link.href} key={link.href}>{link.label}</a>)}
        </nav>
        <div className="header-actions">
          <a className="client-link" href={opsConsoleUrl}>Área do cliente<ArrowUpRight size={14} aria-hidden="true" /></a>
          <a className="button button-primary header-cta" href={contactHref}>Vamos conversar<ArrowUpRight size={15} aria-hidden="true" /></a>
          <button className="menu-toggle" ref={menuButton} type="button" aria-expanded={menuOpen} aria-controls="mobile-navigation" aria-label={menuOpen ? "Fechar menu" : "Abrir menu"} onClick={() => setMenuOpen((current) => !current)}>
            {menuOpen ? <X size={22} aria-hidden="true" /> : <Menu size={22} aria-hidden="true" />}
          </button>
        </div>
      </div>
      <nav className="mobile-nav" id="mobile-navigation" aria-label="Menu móvel" hidden={!menuOpen}>
        {navLinks.map((link) => <a href={link.href} key={link.href} onClick={() => setMenuOpen(false)}>{link.label}<ArrowUpRight size={16} aria-hidden="true" /></a>)}
        <a href={opsConsoleUrl}>Área do cliente<ArrowUpRight size={16} aria-hidden="true" /></a>
        <a className="button button-primary" href={contactHref} onClick={() => setMenuOpen(false)}>Conversar com a Integrix<ArrowRight size={16} aria-hidden="true" /></a>
      </nav>
    </header>
  )
}

function OperationPreview() {
  return (
    <figure className="operation-preview">
      <div className="preview-caption"><span>DA CONVERSA À AÇÃO</span><span>01 — PROCESSO CONECTADO</span></div>
      <div className="operation-window">
        <div className="window-heading"><span><AudioLines size={17} aria-hidden="true" />Integrix / Atendimento</span><span className="demo-label">Demonstração</span></div>
        <div className="operation-body">
          <div className="call-heading">
            <span className="call-icon"><PhoneIncoming size={21} strokeWidth={1.6} aria-hidden="true" /></span>
            <div><h3>Uma ligação. Tudo conectado.</h3><p>Voz, sistemas e próximos passos no mesmo fluxo.</p></div>
          </div>
          <div className="voice-signal" aria-hidden="true">
            <span>VOZ CONECTADA</span>
            <div>{[9, 15, 23, 12, 29, 19, 34, 24, 14, 28, 18, 32, 22, 11, 26, 16, 31, 20, 13, 25, 17, 10].map((height, index) => (
              <i key={index} style={{ height, animationDelay: `${index * 35}ms` }} />
            ))}</div>
          </div>
          <div className="transcript">
            <div className="transcript-line"><span>CLIENTE</span><p>“Quero saber o status da minha solicitação.”</p></div>
            <div className="transcript-line"><span>INTEGRIX</span><p>“Vou consultar agora e registrar o próximo passo para você.”</p></div>
          </div>
          <div className="workflow-path">
            <div><span className="workflow-node"><Check size={13} aria-hidden="true" /></span><span>Solicitação compreendida</span><span className="workflow-detail">Voz</span></div>
            <div><span className="workflow-node"><Check size={13} aria-hidden="true" /></span><span>Sistema consultado</span><span className="workflow-detail">Integração</span></div>
            <div><span className="workflow-node"><Check size={13} aria-hidden="true" /></span><span>Próximo passo registrado</span><span className="workflow-detail">Ação</span></div>
          </div>
          <div className="action-receipt">
            <Route size={22} strokeWidth={1.5} aria-hidden="true" />
            <div><strong>Solicitação encaminhada</strong><span>Contexto registrado para a equipe responsável</span></div>
          </div>
        </div>
        <div className="window-footer"><span><FileText size={13} aria-hidden="true" />Histórico disponível para a equipe</span><LockKeyhole size={13} aria-hidden="true" /></div>
      </div>
      <figcaption><span className="caption-line" />Dados ilustrativos. O fluxo é configurado para cada operação.</figcaption>
    </figure>
  )
}

function Hero() {
  return (
    <section className="hero" aria-labelledby="hero-title">
      <div className="container">
        <div className="hero-grid">
          <div className="hero-copy entrance">
            <p className="eyebrow"><span className="eyebrow-square" />Atendimento por voz com IA</p>
            <h1 id="hero-title">Menos espera.<br />Mais processos <em>resolvidos.</em></h1>
            <p className="hero-description">Substitua ligações demoradas e processos repetitivos por atendimento com IA: rápido, eficiente e disponível 24 horas por dia.</p>
            <div className="hero-actions">
              <a className="button button-primary" href={contactHref}>Conhecer a solução<ArrowUpRight size={17} aria-hidden="true" /></a>
              <a className="button button-secondary" href="#calculadora">Simular custos<ArrowDown size={16} aria-hidden="true" /></a>
            </div>
            <p className="hero-note">Uma conversa sobre o seu negócio. Sem compromisso.</p>
          </div>
          <div className="entrance entrance-delayed"><OperationPreview /></div>
        </div>
        <div className="capability-strip">
          <p>Tecnologia que se encaixa<br /><strong>na rotina da sua empresa.</strong></p>
          <span><Phone size={19} strokeWidth={1.5} aria-hidden="true" />Atendimento 24 horas</span>
          <span><Route size={19} strokeWidth={1.5} aria-hidden="true" />Integração com seus sistemas</span>
          <span><Headphones size={19} strokeWidth={1.5} aria-hidden="true" />Equipe humana no controle</span>
        </div>
      </div>
    </section>
  )
}

function SolutionSection() {
  const solutions = [
    { icon: MessageSquareText, number: "01", title: "Responder e orientar", text: "Entenda o motivo da ligação e responda dúvidas com clareza, sem fazer o cliente repetir a história.", tag: "Respostas mais rápidas" },
    { icon: Route, number: "02", title: "Consultar e executar", text: "Conecte a IA aos sistemas da operação para consultar informações e concluir tarefas durante a conversa.", tag: "Menos retrabalho" },
    { icon: Headphones, number: "03", title: "Encaminhar com contexto", text: "Defina os casos que precisam de uma pessoa e encaminhe a solicitação com o histórico do atendimento.", tag: "Continuidade para o cliente" },
  ]
  return (
    <section className="section solution-section" id="solucao" aria-labelledby="solution-title">
      <div className="container">
        <div className="section-heading">
          <div><p className="eyebrow">01 / Atendimento que avança</p><h2 id="solution-title">A conversa é só<br /><em>o começo.</em></h2></div>
          <p>O valor está no que acontece depois do “alô”. A Integrix conecta a conversa aos processos que fazem sua empresa funcionar.</p>
        </div>
        <div className="solution-grid">
          {solutions.map(({ icon: Icon, number, title, text, tag }) => (
            <article className="solution-item" key={number}>
              <div className="solution-item-top"><Icon size={26} strokeWidth={1.4} aria-hidden="true" /><span>{number}</span></div>
              <h3>{title}</h3><p>{text}</p><span className="solution-tag"><span />{tag}</span>
            </article>
          ))}
        </div>
        <p className="scope-note">Cada projeto tem seu escopo. Os fluxos e as integrações são definidos a partir dos seus sistemas e da sua operação.</p>
      </div>
    </section>
  )
}

function HowItWorks() {
  const steps = [
    { title: "Entendemos sua rotina", text: "Mapeamos os motivos de contato, o volume e os sistemas utilizados. Juntos, escolhemos um processo para começar.", deliverable: "Escopo e prioridades" },
    { title: "Configuramos e validamos", text: "Desenhamos as conversas, conectamos os sistemas previstos e testamos as regras e os encaminhamentos com sua equipe.", deliverable: "Fluxo validado com você" },
    { title: "Acompanhamos a operação", text: "Com o atendimento em uso, os registros e indicadores ajudam a identificar ajustes e decidir os próximos passos.", deliverable: "Visibilidade para evoluir" },
  ]
  return (
    <section className="section implementation-section" id="como-funciona" aria-labelledby="implementation-title">
      <div className="container">
        <div className="section-heading">
          <div><p className="eyebrow">03 / Da primeira conversa à operação</p><h2 id="implementation-title">Tecnologia próxima.<br /><em>Implantação acompanhada.</em></h2></div>
          <p>Você conhece o seu negócio. Nós cuidamos de conectar a tecnologia a ele, com etapas claras e validação em conjunto.</p>
        </div>
        <ol className="steps-grid">
          {steps.map((step, index) => <li key={step.title}><div className="step-number">0{index + 1}<span /></div><h3>{step.title}</h3><p>{step.text}</p><span className="step-deliverable"><Check size={15} aria-hidden="true" />{step.deliverable}</span></li>)}
        </ol>
        <div className="control-panel" id="seguranca">
          <div className="control-intro"><ShieldCheck size={29} strokeWidth={1.4} aria-hidden="true" /><p className="eyebrow">Controle faz parte da entrega</p><h3>Automação com limites.<br />Gestão com visibilidade.</h3><p>Sua empresa define o que a IA pode consultar, quais ações pode executar e quando a equipe precisa assumir.</p><a className="inline-link" href={opsConsoleUrl}>Acessar o painel de gestão<ArrowUpRight size={16} aria-hidden="true" /></a></div>
          <div className="control-list">
            <div><LockKeyhole size={19} strokeWidth={1.5} aria-hidden="true" /><div><h4>Acessos e permissões</h4><p>Controles para restringir o acesso administrativo e as ações de cada operação.</p></div></div>
            <div><FileText size={19} strokeWidth={1.5} aria-hidden="true" /><div><h4>Histórico dos atendimentos</h4><p>Registros para consultar o que aconteceu e dar continuidade às solicitações.</p></div></div>
            <div><LayoutDashboard size={19} strokeWidth={1.5} aria-hidden="true" /><div><h4>Acompanhamento em um painel</h4><p>Volume, custos e informações dos atendimentos para orientar a gestão.</p></div></div>
          </div>
        </div>
      </div>
    </section>
  )
}

function FaqSection() {
  const faqs = [
    { question: "Como é uma conversa com a Integrix?", answer: "O cliente fala com um agente de voz em linguagem natural. A conversa segue o fluxo definido para sua empresa e pode consultar informações ou executar as tarefas previstas nas integrações. Na demonstração, apresentamos como isso se aplica ao seu caso." },
    { question: "Preciso trocar os sistemas que já utilizo?", answer: "A proposta é trabalhar com os sistemas da sua operação. Antes da implantação, avaliamos as possibilidades de integração com cadastro, CRM, financeiro ou outras ferramentas e definimos o que pode ser conectado no primeiro projeto." },
    { question: "O que acontece quando o cliente precisa de uma pessoa?", answer: "Definimos com sua equipe os casos que exigem atendimento humano e o caminho de encaminhamento. A solicitação segue com o contexto registrado, respeitando a disponibilidade e as regras da operação." },
    { question: "Quanto custa e como funciona a contratação?", answer: "A proposta considera o processo, o volume de voz e as integrações necessárias. A calculadora oferece uma referência de consumo para iniciar a análise; o valor contratado e os custos de implantação são definidos na proposta comercial." },
    { question: "Quanto tempo leva para colocar em funcionamento?", answer: "O prazo depende do escopo e das integrações. Após entender sua operação, apresentamos as etapas de configuração, testes e entrada em uso. Começar por um processo bem definido ajuda a validar o projeto antes de expandir." },
  ]
  return (
    <section className="section faq-section" id="duvidas" aria-labelledby="faq-title">
      <div className="container faq-grid">
        <div><p className="eyebrow">04 / Antes de começar</p><h2 id="faq-title">Boas perguntas.<br /><em>Respostas diretas.</em></h2><p className="faq-intro">Tem um cenário específico em mente?<br />Vamos entender juntos.</p><a className="inline-link" href={contactHref}>Falar com a Integrix<ArrowUpRight size={16} aria-hidden="true" /></a></div>
        <div className="faq-list">{faqs.map((faq, index) => <details className="faq-item" key={faq.question} open={index === 0}><summary>{faq.question}<ChevronDown size={18} aria-hidden="true" /></summary><p>{faq.answer}</p></details>)}</div>
      </div>
    </section>
  )
}

function Footer() {
  return (
    <>
      <section className="contact-section" id="contato" aria-labelledby="contact-title">
        <div className="container contact-inner"><div><p className="eyebrow">O próximo passo é uma conversa</p><h2 id="contact-title">Vamos olhar para<br /><em>a sua operação?</em></h2></div><div className="contact-actions"><p>Conte o que ocupa o tempo da sua equipe.<br />Vamos identificar por onde começar.</p><a className="button button-light" href={contactHref}>Falar sobre minha operação<ArrowUpRight size={18} aria-hidden="true" /></a><a className="contact-email" href="mailto:contato@integrix.com.br">contato@integrix.com.br</a></div></div>
      </section>
      <footer className="site-footer"><div className="container"><div className="footer-top"><div><Brand /><p>Voz, processos e pessoas.<br />Uma operação mais conectada.</p></div><nav aria-label="Rodapé"><a href="#solucao">A solução</a><a href="#calculadora">Simular custos</a><a href="#seguranca">Segurança e controle</a><a href={opsConsoleUrl}>Área do cliente<ArrowUpRight size={13} aria-hidden="true" /></a></nav></div><div className="footer-bottom"><p>© {new Date().getFullYear()} Integrix AI. Todos os direitos reservados.</p><span>Inteligência aplicada. Relações humanas.</span></div></div></footer>
    </>
  )
}

export default function App() {
  return (
    <div id="top">
      <a className="skip-link" href="#conteudo">Pular para o conteúdo</a>
      <Header />
      <main id="conteudo">
        <Hero />
        <SolutionSection />
        <ImpactCalculator contactHref={contactHref} />
        <HowItWorks />
        <FaqSection />
      </main>
      <Footer />
    </div>
  )
}
