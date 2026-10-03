import { INDICATORS } from '../home/IndicatorsHome'

export default function IndicatorDashboardHeader({ activeIndicator, onChange, onBack }) {
  const current = INDICATORS.find((indicator) => indicator.id === activeIndicator) ?? INDICATORS[0]

  return (
    <section className="indicator-dashboard-header">
      <div className="indicator-dashboard-header__topline">
        <button type="button" className="indicator-dashboard-header__back" onClick={onBack}>
          <span aria-hidden="true">←</span> Central de Indicadores
        </button>
        <span className="indicator-dashboard-header__breadcrumb">Central de Indicadores <b aria-hidden="true">›</b> {current.title}</span>
      </div>

      <div className="indicator-dashboard-header__main">
        <div>
          <p>Indicador operacional</p>
          <h1>{current.title}</h1>
          <span>{current.description}</span>
        </div>

        <nav className="indicator-dashboard-nav" aria-label="Trocar indicador">
          {INDICATORS.map((indicator) => (
            <button
              key={indicator.id}
              type="button"
              className={indicator.id === activeIndicator ? 'is-active' : ''}
              onClick={() => onChange(indicator.id)}
              aria-pressed={indicator.id === activeIndicator}
            >
              {indicator.id === 'performance' ? 'Desempenho' : indicator.id === 'corrective' ? 'Corretivos' : indicator.id === 'preventive' ? 'Preventivos' : 'Custos'}
            </button>
          ))}
        </nav>
      </div>
    </section>
  )
}
