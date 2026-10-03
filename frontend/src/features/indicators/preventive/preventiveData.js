import {
  applyCorrectiveFilters,
  buildFilterOptions,
  defaultCorrectiveFilters,
  isConcluded,
  isOrderService,
} from '../corrective/correctiveData.js'

const TODOS = 'todos'

export const defaultPreventiveFilters = { ...defaultCorrectiveFilters, periodicidade: TODOS }

export function applyPreventiveFilters(records, filters = defaultPreventiveFilters) {
  return applyCorrectiveFilters(records, filters).filter((record) =>
    filters.periodicidade === TODOS || record.periodicity === filters.periodicidade,
  )
}

export function buildPreventiveFilterOptions(records) {
  const options = buildFilterOptions(records)
  options.periodicidade = [...new Set(records.map((record) => record.periodicity).filter(Boolean))]
    .sort((a, b) => a.localeCompare(b, 'pt-BR'))
  return options
}

const norm = (value) => String(value ?? '').normalize('NFD')
  .replace(/[\u0300-\u036f]/g, '').toLowerCase().trim()

export const preventiveStatusPredicates = {
  emAberto: (record) => norm(record.rawStatus) === 'backlog',
  emAtendimento: (record) => norm(record.rawStatus) === 'em atendimento',
  naoAprovado: (record) => norm(record.rawStatus) === 'nao aprovado',
  solicitacaoFinalizada: (record) => ['servico finalizado', 'servico concluido'].includes(norm(record.rawStatus)),
  concluidos: isConcluded,
}

export function buildPreventiveStatusCounters(records) {
  return Object.fromEntries(Object.entries(preventiveStatusPredicates).map(([key, predicate]) => [
    key, records.filter(predicate).length,
  ]))
}

export function buildPreventiveKpis(records) {
  const completed = records.filter(isConcluded)
  const eligible = completed.filter((record) => record.slaKnown)
  const atrasado = eligible.filter((record) => record.slaLate).length
  const noPrazo = eligible.length - atrasado
  const approvedTotal = completed.reduce((sum, record) =>
    sum + (Number.isFinite(record.approvedValue) ? record.approvedValue : 0), 0)

  return {
    totalChamados: records.length,
    totalOs: records.filter(isOrderService).length,
    custoMedio: completed.length ? Math.round(approvedTotal / completed.length) : 0,
    sla: {
      percent: eligible.length ? Math.round((noPrazo / eligible.length) * 100) : null,
      noPrazo, atrasado, totalConsiderado: eligible.length,
    },
  }
}
