import { CartesianGrid, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, } from 'recharts';
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
const ScatterTooltip = ({ active, payload, }) => {
    if (!active || !payload?.length || !payload[0]?.payload)
        return null;
    const d = payload[0].payload;
    return (<div className="chart-tooltip chart-tooltip--executive">
      <div className="chart-tooltip__title">{d.name}</div>
      <div className="chart-tooltip__row">
        <span className="chart-tooltip__label">Concluídos:</span>
        <strong className="chart-tooltip__value chart-tooltip__value--concluded">{d.concluded}</strong>
      </div>
      <div className="chart-tooltip__row">
        <span className="chart-tooltip__label">Tempo médio:</span>
        <strong className="chart-tooltip__value chart-tooltip__value--volume">
          {d.avgDays !== null ? `${d.avgDays.toFixed(1)} dias` : '–'}
        </strong>
      </div>
    </div>);
};
// ── main component ──────────────────────────────────────────────────────────
export const SupplierProductivityBlock = ({ suppliers }) => {
    if (suppliers.length === 0) {
        return (<section className="table-card supplier-productivity">
        <div className="chart-header">
          <p className="indicators-eyebrow">Fornecedores</p>
          <h3>Fornecedores por produtividade</h3>
          <p className="muted">Chamados concluídos e tempo médio de atendimento no período selecionado</p>
        </div>
        <p className="muted" style={{ padding: '24px 0' }}>Nenhum chamado concluído no período selecionado.</p>
      </section>);
    }
    // Averages for reference lines
    const avgConcluded = suppliers.reduce((s, r) => s + r.concluded, 0) / suppliers.length;
    const validDays = suppliers.filter((r) => r.avgDays !== null).map((r) => r.avgDays);
    const avgDays = validDays.length
        ? validDays.reduce((s, v) => s + v, 0) / validDays.length
        : 0;
    // Scatter data
    const scatterData = suppliers
        .filter((r) => r.avgDays !== null)
        .map((r) => ({ ...r, x: r.concluded, y: r.avgDays }));
    return (<section className="table-card supplier-productivity">
      <div className="chart-header">
        <div>
          <p className="indicators-eyebrow">Fornecedores</p>
          <h3>Fornecedores por produtividade</h3>
          <p className="muted">
            Chamados concluídos e tempo médio de atendimento no período selecionado
          </p>
        </div>
      </div>

      <div className="supplier-productivity__body">
        {/* ── left: executive table ── */}
        <div className="supplier-productivity__table-wrap">
          <p className="supplier-productivity__col-title">Tabela executiva</p>
          <p className="muted supplier-productivity__col-subtitle">Leitura rápida por fornecedor</p>
          <div className="table-wrap" style={{ marginTop: 12 }}>
            <table>
              <thead>
                <tr>
                  <th>Fornecedor</th>
                  <th style={{ textAlign: 'right' }}>Concluídos</th>
                  <th style={{ textAlign: 'right' }}>Tempo médio</th>
                  <th>Classificação</th>
                </tr>
              </thead>
              <tbody>
                {suppliers.map((row) => (<tr key={row.name}>
                    <td style={{ maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {row.name}
                    </td>
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
            </p>
          </div>
        </div>

        {/* ── right: scatter chart ── */}
        <div className="supplier-productivity__chart-wrap">
          <p className="supplier-productivity__col-title">Gráfico de dispersão</p>
          <p className="muted supplier-productivity__col-subtitle">Volume concluído × tempo médio</p>
          <ResponsiveContainer width="100%" height={360} style={{ marginTop: 12 }}>
            <ScatterChart margin={{ top: 16, right: 24, bottom: 24, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(5,56,98,0.08)"/>

              <XAxis type="number" dataKey="x" name="Concluídos" label={{ value: 'Concluídos', position: 'insideBottom', offset: -12, fontSize: 11, fill: '#5b6b7a' }} tickLine={false} axisLine={{ stroke: 'rgba(5,56,98,0.2)' }} tick={{ fill: '#0f172a', fontSize: 11 }}/>

              <YAxis type="number" dataKey="y" name="Tempo médio (dias)" label={{ value: 'Dias', angle: -90, position: 'insideLeft', offset: 10, fontSize: 11, fill: '#5b6b7a' }} tickLine={false} axisLine={{ stroke: 'rgba(5,56,98,0.2)' }} tick={{ fill: '#0f172a', fontSize: 11 }} width={44}/>

              {/* reference lines forming quadrants */}
              <ReferenceLine x={avgConcluded} stroke="rgba(8,43,91,0.28)" strokeDasharray="4 4" label={{ value: 'média', position: 'top', fontSize: 10, fill: '#5b6b7a' }}/>
              <ReferenceLine y={avgDays} stroke="rgba(12,116,112,0.28)" strokeDasharray="4 4" label={{ value: 'média', position: 'right', fontSize: 10, fill: '#5b6b7a' }}/>

              <Tooltip content={<ScatterTooltip />} cursor={{ strokeDasharray: '3 3' }}/>

              <Scatter data={scatterData} fill="#0C7A75" fillOpacity={0.82} stroke="#082B5B" strokeWidth={1} r={6}/>
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      </div>
    </section>);
};
