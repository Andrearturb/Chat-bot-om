const toneIcons = {
    teal: 'summary-tone--teal',
    cyan: 'summary-tone--cyan',
    amber: 'summary-tone--amber',
    violet: 'summary-tone--violet',
    rose: 'summary-tone--rose',
};
export const ExecutiveSummary = ({ summary }) => (<section className="summary-card">
    <div className="summary-card__header">
      <div>
        <p className="indicators-eyebrow">Resumo executivo</p>
        <h3>Leitura dinâmica do cenário atual</h3>
      </div>
      <div className="summary-concentration">
          <div className="summary-concentration__ring" style={{ background: `conic-gradient(#0c7a75 ${summary.concentration}%, rgba(5,56,98,0.1) 0)` }}>
            <strong>{summary.concentration.toFixed(1)}%</strong>
          </div>
          <div className="summary-concentration__label">CONCENTRAÇÃO</div>
      </div>
    </div>

    <section className="summary-stats">
      <article className="summary-stat">
        <span className="summary-stat__icon">▦</span>
        <div>
          <p>Total de chamados</p>
          <strong>{summary.total.toLocaleString('pt-BR')}</strong>
        </div>
      </article>
      <article className="summary-stat">
        <span className="summary-stat__icon">◫</span>
        <div>
          <p>Categorias</p>
          <strong>{summary.categoryCount}</strong>
        </div>
      </article>
      <article className="summary-stat">
        <span className="summary-stat__icon">▣</span>
        <div>
          <p>Subcategorias</p>
          <strong>{summary.subcategoryCount}</strong>
        </div>
      </article>
    </section>

    <section className="summary-insights">
      {summary.insights.map((insight) => (<article key={insight.title} className={`summary-insight ${toneIcons[insight.tone]}`}>
          <span className="summary-insight__icon">{insight.icon}</span>
          <div>
            <h4>{insight.title}</h4>
            <p>{insight.description}</p>
          </div>
        </article>))}
    </section>
  </section>);
