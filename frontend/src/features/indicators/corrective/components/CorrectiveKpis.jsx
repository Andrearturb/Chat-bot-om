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

export default function CorrectiveKpis({ kpis, counters, onOpenDetail, records }) {
  const abrir = (titulo, filtro) =>
    onOpenDetail ? () => onOpenDetail({ titulo, registros: records.filter(filtro) }) : undefined

  return (
    <>
      <section className="corrective-kpis" aria-label="Indicadores dos chamados corretivos">
        <BigKpi title="Total de Chamados" value={NUMERO.format(kpis.totalChamados)}
                onClick={abrir('Total de chamados', () => true)} />
        <BigKpi title="Total de O.S" value={NUMERO.format(kpis.totalOs)}
                onClick={abrir('Chamados com O.S', isOrderService)} />
        <BigKpi title="Custo Médio Serviço" value={MOEDA.format(kpis.custoMedio)}
                onClick={abrir('Chamados considerados no custo médio', isConcluded)} />
        <BigKpi
          title="SLA %"
          value={`${kpis.sla.percent}%`}
          subtitle={`No prazo ${NUMERO.format(kpis.sla.noPrazo)} / ${NUMERO.format(kpis.sla.totalConsiderado)} considerados`}
          onClick={abrir('Chamados considerados no SLA', isConcluded)}
        />
      </section>

      <section className="corrective-status" aria-label="Chamados por status">
        <MiniKpi title="Em aberto" value={counters.emAberto}
                 onClick={abrir('Em aberto', statusPredicates.emAberto)} />
        <MiniKpi title="Em atendimento" value={counters.emAtendimento}
                 onClick={abrir('Em atendimento', statusPredicates.emAtendimento)} />
        <MiniKpi title="Não aprovado" value={counters.naoAprovado}
                 onClick={abrir('Não aprovado', statusPredicates.naoAprovado)} />
        <MiniKpi title="Solicitação Finalizada" value={counters.solicitacaoFinalizada}
                 onClick={abrir('Solicitação Finalizada', statusPredicates.solicitacaoFinalizada)} />
        <MiniKpi title="Concluídos" value={counters.concluidos} emphasis
                 onClick={abrir('Concluídos', statusPredicates.concluidos)} />
      </section>
    </>
  )
}
