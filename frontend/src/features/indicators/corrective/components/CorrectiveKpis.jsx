import { isConcluded, isOrderService, statusPredicates } from '../correctiveData'

const MOEDA = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 })
const NUMERO = new Intl.NumberFormat('pt-BR')

function BigKpi({ title, value, subtitle, onClick }) {
  return (
    <button type="button" className="corrective-kpi" onClick={onClick} disabled={!onClick}>
      <h3>{title}</h3>
      <strong>{value}</strong>
      {subtitle ? <small>{subtitle}</small> : null}
    </button>
  )
}

function MiniKpi({ title, value, emphasis, onClick }) {
  return (
    <button
      type="button"
      className={`corrective-mini${emphasis ? ' corrective-mini--emphasis' : ''}`}
      onClick={onClick}
      disabled={!onClick}
    >
      <h4>{title}</h4>
      <strong>{NUMERO.format(value)}</strong>
    </button>
  )
}

export default function CorrectiveKpis({
  kpis, counters, onOpenDetail, records,
  predicates = statusPredicates,
  labels = { emAberto: 'Em aberto', solicitacaoFinalizada: 'Solicitação Finalizada' },
  panelLabel = 'Indicadores dos chamados corretivos',
  slaPredicate = isConcluded,
}) {
  const abrir = (titulo, filtro) =>
    onOpenDetail ? () => onOpenDetail({ titulo, registros: records.filter(filtro) }) : undefined

  return (
    <>
      <section className="corrective-kpis" aria-label={panelLabel}>
        <BigKpi title="Total de Chamados" value={NUMERO.format(kpis.totalChamados)}
                onClick={abrir('Total de chamados', () => true)} />
        <BigKpi title="Total de O.S" value={NUMERO.format(kpis.totalOs)}
                onClick={abrir('Chamados com O.S', isOrderService)} />
        <BigKpi title="Custo Médio Serviço" value={MOEDA.format(kpis.custoMedio)}
                onClick={abrir('Chamados considerados no custo médio', isConcluded)} />
        <BigKpi
          title="SLA %"
          value={kpis.sla.percent === null ? 'Sem dados' : `${kpis.sla.percent}%`}
          subtitle={kpis.sla.percent === null
            ? 'A Tape não informa prazo verificável para este recorte'
            : `No prazo ${NUMERO.format(kpis.sla.noPrazo)} / ${NUMERO.format(kpis.sla.totalConsiderado)} considerados`}
          onClick={kpis.sla.percent === null ? undefined : abrir('Chamados considerados no SLA', slaPredicate)}
        />
      </section>

      <section className="corrective-status" aria-label="Chamados por status">
        <MiniKpi title={labels.emAberto} value={counters.emAberto}
                 onClick={abrir(labels.emAberto, predicates.emAberto)} />
        <MiniKpi title="Em atendimento" value={counters.emAtendimento}
                 onClick={abrir('Em atendimento', predicates.emAtendimento)} />
        <MiniKpi title="Não aprovado" value={counters.naoAprovado}
                 onClick={abrir('Não aprovado', predicates.naoAprovado)} />
        <MiniKpi title={labels.solicitacaoFinalizada} value={counters.solicitacaoFinalizada}
                 onClick={abrir(labels.solicitacaoFinalizada, predicates.solicitacaoFinalizada)} />
        <MiniKpi title="Concluídos" value={counters.concluidos} emphasis
                 onClick={abrir('Concluídos', predicates.concluidos)} />
      </section>
    </>
  )
}
