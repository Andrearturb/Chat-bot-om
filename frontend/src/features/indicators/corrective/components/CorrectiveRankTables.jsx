const NUMERO = new Intl.NumberFormat('pt-BR')

function RankTable({ title, columnLabel, rows }) {
  return (
    <article className="corrective-rank">
      <h3>{title}</h3>
      {rows.length === 0 ? (
        <p className="corrective-empty">Sem dados para o filtro atual.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>{columnLabel}</th>
              <th style={{ textAlign: 'right' }}>Qtd.</th>
              <th style={{ textAlign: 'right' }}>%</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.label}>
                <td>{row.label}</td>
                <td style={{ textAlign: 'right' }}>{NUMERO.format(row.total)}</td>
                <td style={{ textAlign: 'right' }}>{row.percent}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </article>
  )
}

export default function CorrectiveRankTables({ lojaRank, categoryRank }) {
  return (
    <section className="corrective-ranks">
      <RankTable title="Loja" columnLabel="Loja" rows={lojaRank} />
      <RankTable title="Categoria" columnLabel="Categoria" rows={categoryRank} />
    </section>
  )
}
