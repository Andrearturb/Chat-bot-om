const TODOS = 'todos'

export const defaultCorrectiveFilters = {
  status: TODOS,
  loja: TODOS,
  praca: TODOS,
  categoria: TODOS,
  mes: TODOS,
  ano: TODOS,
}

function normalize(value) {
  return String(value ?? '')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .trim()
    .toLowerCase()
}

/** Devolve {ano, mes} da data de criação, ou null quando a data não existe ou é inválida. */
function dateParts(value) {
  if (!value) return null
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return null
  return {
    ano: String(parsed.getFullYear()),
    mes: String(parsed.getMonth() + 1).padStart(2, '0'),
  }
}

export function applyCorrectiveFilters(records, filters = defaultCorrectiveFilters) {
  return records.filter((record) => {
    if (filters.status !== TODOS && normalize(record.rawStatus) !== normalize(filters.status)) return false
    if (filters.loja !== TODOS && normalize(record.location) !== normalize(filters.loja)) return false
    if (filters.praca !== TODOS && normalize(record.region) !== normalize(filters.praca)) return false
    if (filters.categoria !== TODOS && normalize(record.category) !== normalize(filters.categoria)) return false

    if (filters.mes !== TODOS || filters.ano !== TODOS) {
      const parts = dateParts(record.createdOn)
      if (parts === null) return false
      if (filters.mes !== TODOS && parts.mes !== filters.mes) return false
      if (filters.ano !== TODOS && parts.ano !== filters.ano) return false
    }

    return true
  })
}

export function buildFilterOptions(records) {
  const status = new Set()
  const loja = new Set()
  const praca = new Set()
  const categoria = new Set()
  const mes = new Set()
  const ano = new Set()

  for (const record of records) {
    if (record.rawStatus) status.add(record.rawStatus)
    if (record.location) loja.add(record.location)
    if (record.region) praca.add(record.region)
    if (record.category) categoria.add(record.category)

    const parts = dateParts(record.createdOn)
    if (parts !== null) {
      mes.add(parts.mes)
      ano.add(parts.ano)
    }
  }

  const ordenar = (conjunto) => [...conjunto].sort((a, b) => a.localeCompare(b, 'pt-BR'))

  return {
    status: ordenar(status),
    loja: ordenar(loja),
    praca: ordenar(praca),
    categoria: ordenar(categoria),
    mes: [...mes].sort(),
    ano: [...ano].sort(),
  }
}

/** Verdadeiro para o conjunto de concluídos: o status canônico do chatbot-om. */
export function isConcluded(record) {
  return normalize(record.canonicalStatus) === 'concluido'
}

const cru = (record) => normalize(record.rawStatus)

/**
 * Um predicado por card de status, em um só lugar.
 *
 * Os contadores e o modal de drill-down usam exatamente estes predicados, para
 * que o número do card e a lista por trás dele nunca possam divergir.
 */
export const statusPredicates = {
  emAberto: (record) => cru(record) === 'em aberto',
  emAtendimento: (record) => cru(record) === 'em atendimento',
  naoAprovado: (record) => cru(record) === 'nao aprovado',
  solicitacaoFinalizada: (record) =>
    cru(record) === 'solicitacao finalizada' || cru(record) === 'servico finalizado',
  concluidos: isConcluded,
}

export function buildStatusCounters(records) {
  return Object.fromEntries(
    Object.entries(statusPredicates).map(([chave, predicado]) => [
      chave,
      records.filter(predicado).length,
    ]),
  )
}
