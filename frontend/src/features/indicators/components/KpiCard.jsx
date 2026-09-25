const tones = {
    teal: 'linear-gradient(135deg, rgba(12,116,112,0.18), rgba(12,116,112,0.02))',
    cyan: 'linear-gradient(135deg, rgba(7,56,98,0.18), rgba(7,56,98,0.02))',
    amber: 'linear-gradient(135deg, rgba(181,126,28,0.18), rgba(181,126,28,0.02))',
    rose: 'linear-gradient(135deg, rgba(171,55,73,0.18), rgba(171,55,73,0.02))',
};
export const KpiCard = ({ label, value, globalValue, helper, progress, tone = 'teal' }) => (<article className="kpi-card" style={{ background: tones[tone] }}>
    <span className="kpi-label">{label}</span>
    <strong className="kpi-value">
      {globalValue !== undefined ? (<>
          {value}
          <span className="kpi-value__separator"> / </span>
          <span className="kpi-value__global">{globalValue}</span>
        </>) : (value)}
    </strong>
    <span className="kpi-helper">{helper}</span>
    <div className="progress-track" aria-hidden="true">
      <div className="progress-fill" style={{ width: `${Math.max(0, Math.min(100, progress))}%` }}/>
    </div>
  </article>);
