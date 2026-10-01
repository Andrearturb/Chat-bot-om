const INDICATORS = [
  {
    id: 'performance',
    title: 'Indicador de Desempenho',
    description: 'Visão geral da operação, produtividade, regiões, fornecedores e analistas.',
    tone: 'blue',
    icon: 'performance',
    visual: 'performance',
  },
  {
    id: 'corrective',
    title: 'Chamados Corretivos',
    description: 'Acompanhe fila, status, criticidade, aging e volume dos corretivos.',
    tone: 'amber',
    icon: 'corrective',
    visual: 'corrective',
  },
  {
    id: 'preventive',
    title: 'Chamados Preventivos',
    description: 'Visualize preventivas, periodicidade, execução e cobertura por praça.',
    tone: 'green',
    icon: 'preventive',
    visual: 'preventive',
  },
  {
    id: 'financial',
    title: 'Indicadores Financeiros',
    description: 'Monitore custos, CAPEX, savings, rateios e desempenho financeiro.',
    tone: 'violet',
    icon: 'financial',
    visual: 'financial',
  },
]

function IndicatorIcon({ type }) {
  const props = {
    width: 34,
    height: 34,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.9,
    strokeLinecap: 'round',
    strokeLinejoin: 'round',
    'aria-hidden': 'true',
  }

  if (type === 'corrective') {
    return (
      <svg {...props}>
        <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
      </svg>
    )
  }

  if (type === 'preventive') {
    return (
      <svg {...props}>
        <rect x="3" y="5" width="18" height="16" rx="3" />
        <path d="M16 3v4M8 3v4M3 10h18" />
        <path d="m8.5 15 2 2 4-4" />
      </svg>
    )
  }

  if (type === 'financial') {
    return (
      <svg {...props}>
        <ellipse cx="12" cy="5" rx="6.5" ry="2.5" />
        <path d="M5.5 5v5c0 1.4 2.9 2.5 6.5 2.5s6.5-1.1 6.5-2.5V5" />
        <path d="M5.5 10v5c0 1.4 2.9 2.5 6.5 2.5s6.5-1.1 6.5-2.5v-5" />
        <path d="M5.5 15v4c0 1.4 2.9 2.5 6.5 2.5s6.5-1.1 6.5-2.5v-4" />
      </svg>
    )
  }

  return (
    <svg {...props}>
      <path d="M4 20V12M10 20V7M16 20V4M22 20V9" />
      <path d="M2 20h22" />
    </svg>
  )
}

function IndicatorVisual({ type }) {
  if (type === 'corrective') {
    return (
      <div className="indicator-card-visual indicator-card-visual--tickets" aria-hidden="true">
        <span className="ticket-dot ticket-dot--red" /><span className="ticket-line ticket-line--long" />
        <span className="ticket-dot ticket-dot--amber" /><span className="ticket-line" />
        <span className="ticket-dot ticket-dot--green" /><span className="ticket-line ticket-line--long" />
        <span className="ticket-dot ticket-dot--teal" /><span className="ticket-line" />
      </div>
    )
  }

  if (type === 'preventive') {
    return (
      <div className="indicator-card-visual indicator-card-visual--calendar" aria-hidden="true">
        <span className="calendar-bar" />
        <span /><span /><span /><span />
        <span className="calendar-check">✓</span><span /><span className="calendar-check">✓</span><span />
        <span /><span /><span /><span className="calendar-check calendar-check--large">✓</span>
      </div>
    )
  }

  if (type === 'financial') {
    return (
      <div className="indicator-card-visual indicator-card-visual--financial" aria-hidden="true">
        <div className="financial-bars"><span /><span /><span /><span /><span /></div>
        <svg viewBox="0 0 120 54" preserveAspectRatio="xMidYMid meet">
          <polyline points="4,44 30,28 52,34 76,15 96,23 116,5" fill="none" stroke="currentColor" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
          <circle cx="30" cy="28" r="3" fill="currentColor" />
          <circle cx="76" cy="15" r="3" fill="currentColor" />
          <circle cx="116" cy="5" r="3" fill="currentColor" />
        </svg>
        <span className="financial-coin">$</span>
      </div>
    )
  }

  return (
    <div className="indicator-card-visual indicator-card-visual--performance" aria-hidden="true">
      <div className="performance-bars"><span /><span /><span /><span /><span /></div>
      <div className="performance-ring" />
      <div className="performance-lines"><span /><span /><span /></div>
    </div>
  )
}

export default function IndicatorsHome({ onOpenIndicator, error, onRetry }) {
  return (
    <section className="indicators-home" aria-labelledby="indicators-home-title">
      <div className="indicators-home__heading">
        <div>
          <h2 id="indicators-home-title">Indicadores disponíveis</h2>
          <p>Explore os principais indicadores da operação de Obras &amp; Manutenções.</p>
        </div>
        <span className="indicators-home__ready"><span aria-hidden="true">✦</span> Preparado para novos indicadores <span aria-hidden="true">ⓘ</span></span>
      </div>

      {error && (
        <div className="indicators-home__warning" role="status">
          <span>Os painéis estão disponíveis, mas a atualização da base falhou.</span>
          <button type="button" onClick={onRetry}>Tentar novamente</button>
        </div>
      )}

      <div className="indicators-home__grid">
        {INDICATORS.map((indicator) => (
          <button
            key={indicator.id}
            type="button"
            className={`indicator-home-card indicator-home-card--${indicator.tone}`}
            onClick={() => onOpenIndicator(indicator.id)}
          >
            <span className="indicator-home-card__icon"><IndicatorIcon type={indicator.icon} /></span>
            <span className="indicator-home-card__copy">
              <strong>{indicator.title}</strong>
              <small>{indicator.description}</small>
              <span className="indicator-home-card__action">Abrir indicador <b aria-hidden="true">→</b></span>
            </span>
            <IndicatorVisual type={indicator.visual} />
          </button>
        ))}
      </div>
    </section>
  )
}

export { INDICATORS }
