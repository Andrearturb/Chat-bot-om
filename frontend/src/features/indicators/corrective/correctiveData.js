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

/** Normaliza o status de assinatura para o vocabulário do painel. */
function signatureBucket(value) {
  const texto = normalize(value)
  if (!texto) return ''
  if (texto.includes('conclu') || texto.includes('complet')) return 'concluido'
  if (texto.includes('pend') || texto.includes('aguard')) return 'pendente'
  return ''
}

export function isOrderService(record) {
  const bucket = signatureBucket(record.signatureStatus)
  return bucket === 'pendente' || bucket === 'concluido'
}

export function isCompletedOrderService(record) {
  return signatureBucket(record.signatureStatus) === 'concluido'
}

export function orderServiceStatusLabel(record) {
  const bucket = signatureBucket(record.signatureStatus)
  if (bucket === 'concluido') return 'Concluída'
  if (bucket === 'pendente') return 'Pendente'
  return record.signatureStatus || '—'
}

export function buildCorrectiveKpis(records) {
  const concluidos = records.filter(isConcluded)

  let atrasado = 0
  for (const record of concluidos) {
    if (record.slaLate === true) atrasado += 1
  }
  const noPrazo = concluidos.length - atrasado
  const totalConsiderado = concluidos.length
  const percent = totalConsiderado === 0 ? 0 : Math.round((noPrazo / totalConsiderado) * 100)

  // Concluído sem valor aprovado entra no denominador como zero: regra do BI.
  const soma = concluidos.reduce(
    (acc, record) => acc + (typeof record.approvedValue === 'number' ? record.approvedValue : 0),
    0,
  )
  const custoMedio = concluidos.length === 0 ? 0 : Math.round(soma / concluidos.length)

  const totalOs = records.filter(isOrderService).length

  return {
    totalChamados: records.length,
    totalOs,
    custoMedio,
    sla: { percent, noPrazo, atrasado, totalConsiderado },
  }
}

const RANK_FALLBACK = {
  location: 'Sem loja',
  category: 'Sem categoria',
  subcategory: 'Sem subcategoria',
  periodicity: 'Sem periodicidade',
  region: 'Sem praça',
  analyst: 'Sem analista',
}

export function rankLabel(record, field) {
  const value = String(record[field] ?? '').trim()
  return value && value !== 'Não informado' ? value : (RANK_FALLBACK[field] ?? 'Não informado')
}

export function filterByRank(records, field, label) {
  return records.filter((record) => rankLabel(record, field) === label)
}

const TICKET_ORDER = new Intl.Collator('pt-BR', { numeric: true, sensitivity: 'base' })

export function sortDetailRecords(records) {
  const timestamp = (record) => {
    const parsed = Date.parse(record.createdOn ?? '')
    return Number.isNaN(parsed) ? -Infinity : parsed
  }

  return [...records].sort((a, b) =>
    timestamp(b) - timestamp(a) || TICKET_ORDER.compare(String(b.ticketId ?? ''), String(a.ticketId ?? '')),
  )
}

const MESES_PT = [
  'jan', 'fev', 'mar', 'abr', 'mai', 'jun',
  'jul', 'ago', 'set', 'out', 'nov', 'dez',
]

function contarPor(records, campo) {
  const contagem = new Map()

  for (const record of records) {
    const label = rankLabel(record, campo)
    contagem.set(label, (contagem.get(label) ?? 0) + 1)
  }

  return [...contagem.entries()]
    .map(([label, total]) => ({ label, total }))
    .sort((a, b) => b.total - a.total || a.label.localeCompare(b.label, 'pt-BR'))
}

export function buildSubcategoryRanks(records) {
  const byCategory = new Map()

  for (const record of records) {
    const category = rankLabel(record, 'category')
    const subcategory = rankLabel(record, 'subcategory')
    const counts = byCategory.get(category) ?? new Map()
    counts.set(subcategory, (counts.get(subcategory) ?? 0) + 1)
    byCategory.set(category, counts)
  }

  return new Map([...byCategory].map(([category, counts]) => [
    category,
    [...counts].map(([label, total]) => ({ label, total }))
      .sort((a, b) => b.total - a.total || a.label.localeCompare(b.label, 'pt-BR')),
  ]))
}

export function buildRank(records, campo, limit = 8) {
  const total = records.length

  return contarPor(records, campo)
    .slice(0, limit)
    .map((item) => ({
      ...item,
      percent: total === 0 ? 0 : Math.round((item.total / total) * 100),
    }))
}

export function buildAnalystSeries(records, limit = 8) {
  return contarPor(records, 'analyst').slice(0, limit)
}

export function buildMonthlySeries(records) {
  const porMes = new Map()

  for (const record of records) {
    const parts = dateParts(record.createdOn)
    if (parts === null) continue

    const key = `${parts.ano}-${parts.mes}`
    const atual = porMes.get(key) ?? { key, label: '', total: 0, concluidos: 0 }
    atual.total += 1
    if (isConcluded(record)) atual.concluidos += 1
    atual.label = `${MESES_PT[Number(parts.mes) - 1]}/${parts.ano.slice(2)}`
    porMes.set(key, atual)
  }

  return [...porMes.values()].sort((a, b) => a.key.localeCompare(b.key))
}
