const INDICATORS = [
  {
    id: 'performance',
    title: 'Indicador de desempenho',
    description: 'Visão geral de chamados, produtividade, SLA, praças e fornecedores.',
    icon: 'chart',
  },
  {
    id: 'corrective',
    title: 'Chamados corretivos',
    description: 'Acompanhamento operacional dos chamados de manutenção corretiva.',
    icon: 'tools',
  },
  {
    id: 'preventive',
    title: 'Chamados preventivos',
    description: 'Controle e acompanhamento das manutenções preventivas programadas.',
    icon: 'calendar-check',
  },
  {
    id: 'financial',
    title: 'Indicadores financeiros',
    description: 'Visão financeira de custos, investimentos, budget e saving.',
    icon: 'finance',
  },
]

function IndicatorIcon({ type }) {
  const props = {
    width: 28,
    height: 28,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.8,
    strokeLinecap: 'round',
    strokeLinejoin: 'round',
    'aria-hidden': 'true',
  }

  if (type === 'tools') {
    return (
      <svg {...props}>
        <path d="M14.7 6.3a4 4 0 0 0-5-5l2.1 2.1-2.8 2.8-2.1-2.1a4 4 0 0 0 5 5L20 17.2a2 2 0 1 1-2.8 2.8l-8.1-8.1a4 4 0 0 0-5-5L6.2 9 9 6.2 6.9 4.1" />
      </svg>
    )
  }

  if (type === 'calendar-check') {
    return (
      <svg {...props}>
        <rect x="3" y="5" width="18" height="16" rx="3" />
        <path d="M16 3v4M8 3v4M3 10h18" />
        <path d="m8.5 15 2 2 4-4" />
      </svg>
    )
  }

  if (type === 'finance') {
    return (
      <svg {...props}>
        <path d="M4 19V9M10 19V5M16 19v-7M22 19H2" />
        <path d="m4 6 5-3 5 3 6-4" />
      </svg>
    )
  }

  return (
    <svg {...props}>
      <path d="M4 20V11M10 20V5M16 20v-8M22 20V3" />
      <path d="M2 20h22" />
    </svg>
  )
}

export default function IndicatorSwitcher({ activeIndicator, onChange }) {
  return (
    <nav className="indicator-switcher" aria-label="Indicadores disponíveis">
      {INDICATORS.map((indicator) => {
        const active = indicator.id === activeIndicator
        return (
          <button
            key={indicator.id}
            type="button"
            className={`indicator-switcher__item${active ? ' indicator-switcher__item--active' : ''}`}
            onClick={() => onChange(indicator.id)}
            aria-pressed={active}
          >
            <span className="indicator-switcher__icon"><IndicatorIcon type={indicator.icon} /></span>
            <span className="indicator-switcher__copy">
              <strong>{indicator.title}</strong>
              <small>{indicator.description}</small>
            </span>
            <span className="indicator-switcher__arrow" aria-hidden="true">→</span>
          </button>
        )
      })}
    </nav>
  )
}

export { INDICATORS }
