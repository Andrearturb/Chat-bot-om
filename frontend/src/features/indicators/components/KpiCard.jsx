export const KpiCard = ({ label, value, globalValue, globalLabel, unit, helper, progress, tone = 'teal' }) => (
  <article className={`kpi-card kpi-card--${tone}`}>
    <h3 className="kpi-label">{label}</h3>
    <div className="kpi-filtered">
      <strong className="kpi-value">
        <span className="kpi-value__filtered">{value}</span>
        <span className="kpi-value__separator">/</span>
        <span className="kpi-value__global">{globalValue}</span>
        {unit && <span className="kpi-value__unit"> {unit}</span>}
      </strong>
      <span className="kpi-context">Filtrado / {globalLabel}</span>
    </div>
    <span className="kpi-helper">{helper}</span>
    <div className="progress-track" aria-hidden="true">
      <div className="progress-fill" style={{ width: `${Math.max(0, Math.min(100, progress))}%` }} />
    </div>
  </article>
)
