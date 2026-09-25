// ── classification badge ────────────────────────────────────────────────────
const classConfig = {
    high: { label: 'Alta produtividade', bg: 'rgba(12,122,117,0.14)', color: '#0c7a75' },
    volume: { label: 'Alto volume', bg: 'rgba(8,43,91,0.12)', color: '#082b5b' },
    fast: { label: 'Rápido / baixo volume', bg: 'rgba(217,142,20,0.14)', color: '#b87c10' },
    slow: { label: 'Tempo elevado', bg: 'rgba(171,55,73,0.12)', color: '#ab3749' },
};
const classLegend = [
    { cls: 'high', desc: 'Volume acima da média e tempo médio abaixo ou igual à média.' },
    { cls: 'volume', desc: 'Volume acima da média e tempo médio acima da média.' },
    { cls: 'fast', desc: 'Volume abaixo da média e tempo médio abaixo ou igual à média.' },
    { cls: 'slow', desc: 'Volume abaixo da média e tempo médio acima da média.' },
];
const Badge = ({ cls }) => {
    const cfg = classConfig[cls];
    return (<span style={{
            display: 'inline-block',
            padding: '3px 10px',
            borderRadius: 999,
            fontSize: '0.76rem',
            fontWeight: 700,
            background: cfg.bg,
            color: cfg.color,
            whiteSpace: 'nowrap',
        }}>
      {cfg.label}
    </span>);
};
// ── main component ──────────────────────────────────────────────────────────
export const AnalystProductivityBlock = ({ analysts }) => {
    if (analysts.length === 0) {
        return (<section className="table-card">
        <div className="chart-header">
          <p className="indicators-eyebrow">Analistas</p>
          <h3>Analistas por produtividade</h3>
          <p className="muted">Chamados concluídos e tempo médio de atendimento no período selecionado</p>
        </div>
        <p className="muted" style={{ padding: '24px 0' }}>Nenhum chamado concluído no período selecionado.</p>
      </section>);
    }
    return (<section className="table-card">
      <div className="chart-header">
        <div>
          <p className="indicators-eyebrow">Analistas</p>
          <h3>Analistas por produtividade</h3>
          <p className="muted">
            Chamados concluídos e tempo médio desde a criação até a conclusão no período selecionado
          </p>
        </div>
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Analista</th>
              <th style={{ textAlign: 'right' }}>Concluídos</th>
              <th style={{ textAlign: 'right' }}>Tempo médio</th>
              <th>Classificação</th>
            </tr>
          </thead>
          <tbody>
            {analysts.map((row) => (<tr key={row.name}>
                <td>{row.name}</td>
                <td style={{ textAlign: 'right', fontWeight: 700 }}>{row.concluded}</td>
                <td style={{ textAlign: 'right' }}>
                  {row.avgDays !== null ? `${row.avgDays.toFixed(1)} dias` : '–'}
                </td>
                <td>
                  <Badge cls={row.classification}/>
                </td>
              </tr>))}
          </tbody>
        </table>
      </div>

      {/* ── classification legend ── */}
      <div className="supplier-legend">
        <p className="supplier-legend__title">Como interpretar a classificação</p>
        <ul className="supplier-legend__list">
          {classLegend.map(({ cls, desc }) => (<li key={cls} className="supplier-legend__item">
              <Badge cls={cls}/>
              <span className="supplier-legend__desc">{desc}</span>
            </li>))}
        </ul>
        <p className="supplier-legend__note">
          As médias são recalculadas conforme os filtros aplicados na tela.
          Tempo médio calculado desde a criação do chamado até a conclusão.
        </p>
      </div>
    </section>);
};
