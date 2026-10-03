import { Fragment, useState } from 'react'

const NUMERO = new Intl.NumberFormat('pt-BR')

function RankTable({ title, columnLabel, rows, onOpenRow }) {
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
                <td>
                  <button type="button" className="corrective-rank__link" onClick={() => onOpenRow(row.label)}>
                    {row.label}
                  </button>
                </td>
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

function CategoryRankTable({ rows, subcategoriesByCategory, onOpenSubcategory }) {
  const [expandedCategory, setExpandedCategory] = useState(null)

  return (
    <article className="corrective-rank">
      <h3>Categoria</h3>
      {rows.length === 0 ? (
        <p className="corrective-empty">Sem dados para o filtro atual.</p>
      ) : (
        <table>
          <thead>
            <tr><th>Categoria</th><th style={{ textAlign: 'right' }}>Qtd.</th><th style={{ textAlign: 'right' }}>%</th></tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const expanded = expandedCategory === row.label
              const subcategories = subcategoriesByCategory.get(row.label) ?? []

              return (
                <Fragment key={row.label}>
                  <tr>
                    <td>
                      <button
                        type="button"
                        className="corrective-rank__link corrective-rank__category"
                        aria-expanded={expanded}
                        onClick={() => setExpandedCategory(expanded ? null : row.label)}
                      >
                        <span aria-hidden="true">{expanded ? '▾' : '▸'}</span>
                        {row.label}
                      </button>
                    </td>
                    <td style={{ textAlign: 'right' }}>{NUMERO.format(row.total)}</td>
                    <td style={{ textAlign: 'right' }}>{row.percent}%</td>
                  </tr>
                  {expanded && subcategories.map((sub) => (
                    <tr key={`${row.label}-${sub.label}`} className="corrective-rank__subcategory">
                      <td>
                        <button
                          type="button"
                          className="corrective-rank__link"
                          onClick={() => onOpenSubcategory(row.label, sub.label)}
                        >
                          {sub.label}
                        </button>
                      </td>
                      <td style={{ textAlign: 'right' }}>{NUMERO.format(sub.total)}</td>
                      <td />
                    </tr>
                  ))}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      )}
    </article>
  )
}

export default function CorrectiveRankTables({
  lojaRank, categoryRank, subcategoriesByCategory, onOpenStore, onOpenSubcategory,
  periodicityRank, onOpenPeriodicity,
}) {
  return (
    <section className="corrective-ranks">
      <RankTable title="Loja" columnLabel="Loja" rows={lojaRank} onOpenRow={onOpenStore} />
      <CategoryRankTable
        rows={categoryRank}
        subcategoriesByCategory={subcategoriesByCategory}
        onOpenSubcategory={onOpenSubcategory}
      />
      {periodicityRank && (
        <RankTable title="Periodicidade" columnLabel="Periodicidade" rows={periodicityRank}
                   onOpenRow={onOpenPeriodicity} />
      )}
    </section>
  )
}
