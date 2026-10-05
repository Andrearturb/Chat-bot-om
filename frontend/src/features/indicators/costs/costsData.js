export const defaultCostFilters = {
  tipo: [], fornecedor: [], loja: [], praca: [], mes: [], ano: [],
}

export const costPredicates = {
  corretiva: (row) => row.contaRazao === '41140014',
  preventiva: (row) => row.contaRazao === '41140026',
  naoAtribuido: (row) => row.tapeCenterRecordId == null,
}

export const money = (value) => new Intl.NumberFormat('pt-BR', {
  style: 'currency', currency: 'BRL',
}).format(value)

const normalize = (value) => String(value ?? '').trim().toLocaleLowerCase('pt-BR')

/** Array vazio não restringe; senão o valor da linha precisa estar entre os
 * selecionados. Mesma semântica de múltipla seleção da corretiva/preventiva. */
function matchesAny(fieldValue, selected) {
  if (!selected || selected.length === 0) return true
  const needle = normalize(fieldValue)
  return selected.some((option) => normalize(option) === needle)
}

export function postingParts(value) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value ?? '').slice(0, 10))
  if (!match || Number(match[2]) < 1 || Number(match[2]) > 12) return null
  return { ano: match[1], mes: match[2] }
}

export function filterCosts(rows, filters = defaultCostFilters) {
  return rows.filter((row) => {
    if (!matchesAny(row.contaRazao, filters.tipo)) return false
    if (!matchesAny(row.supplierName, filters.fornecedor)) return false
    if (!matchesAny(row.storeName ?? 'Não atribuído', filters.loja)) return false
    if (!matchesAny(row.praca, filters.praca)) return false

    const temFiltroDeData = (filters.mes?.length ?? 0) > 0 || (filters.ano?.length ?? 0) > 0
    if (temFiltroDeData) {
      const parts = postingParts(row.postingDate)
      if (!parts) return false
      if (filters.mes?.length && !filters.mes.includes(parts.mes)) return false
      if (filters.ano?.length && !filters.ano.includes(parts.ano)) return false
    }
    return true
  })
}

export function costFilterOptions(rows) {
  const options = { tipo: new Set(), fornecedor: new Set(), loja: new Set(), praca: new Set(), mes: new Set(), ano: new Set() }
  for (const row of rows) {
    if (row.contaRazao) options.tipo.add(row.contaRazao)
    if (row.supplierName) options.fornecedor.add(row.supplierName)
    options.loja.add(row.storeName || 'Não atribuído')
    if (row.praca) options.praca.add(row.praca)
    const parts = postingParts(row.postingDate)
    if (parts) { options.mes.add(parts.mes); options.ano.add(parts.ano) }
  }
  return Object.fromEntries(Object.entries(options).map(([key, values]) => [
    key, [...values].sort((a, b) => a.localeCompare(b, 'pt-BR')),
  ]))
}

const cents = (amount) => Math.round(Number(amount || 0) * 100)

export const sumCosts = (rows) => rows.reduce((total, row) => total + cents(row.amount), 0) / 100

export function costKpis(rows) {
  const corretiva = rows.filter(costPredicates.corretiva)
  const preventiva = rows.filter(costPredicates.preventiva)
  const naoAtribuido = rows.filter(costPredicates.naoAtribuido)
  return {
    corretiva: sumCosts(corretiva), preventiva: sumCosts(preventiva),
    total: sumCosts(rows), naoAtribuido: sumCosts(naoAtribuido),
    naoAtribuidoCount: naoAtribuido.length,
  }
}

// Mesma convenção de abreviação de mês usada em corrective/correctiveData.js,
// para o rótulo do eixo do gráfico de progressão mensal.
const MESES_PT = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez']

/** Progressão mensal do custo líquido, separada por conta razão. Mesmos
 * predicados do KPI, então o card de tendência nunca pode discordar dos
 * cards de corretiva/preventiva para o mesmo recorte de linhas. */
export function buildCostMonthlySeries(rows) {
  const byMonth = new Map()
  for (const row of rows) {
    const parts = postingParts(row.postingDate)
    if (!parts) continue
    const key = `${parts.ano}-${parts.mes}`
    const current = byMonth.get(key) ?? { key, label: '', corretiva: 0, preventiva: 0, total: 0 }
    const valueCents = cents(row.amount)
    if (costPredicates.corretiva(row)) current.corretiva += valueCents
    else if (costPredicates.preventiva(row)) current.preventiva += valueCents
    current.total += valueCents
    current.label = `${MESES_PT[Number(parts.mes) - 1]}/${parts.ano.slice(2)}`
    byMonth.set(key, current)
  }
  return [...byMonth.values()]
    .sort((a, b) => a.key.localeCompare(b.key))
    .map((item) => ({
      ...item, corretiva: item.corretiva / 100, preventiva: item.preventiva / 100, total: item.total / 100,
    }))
}

/** Como costRank, mas com o valor líquido separado por conta razão — o rank
 * por praça pedido para distinguir corretiva de preventiva em cada linha. */
export function costRankByType(rows, field, limit = 20) {
  const groups = new Map()
  for (const row of rows) {
    const label = field === 'storeName' ? row.storeName || 'Não atribuído' : row[field] || 'Não informado'
    const group = groups.get(label) ?? { label, corretiva: 0, preventiva: 0, total: 0, count: 0 }
    const valueCents = cents(row.amount)
    if (costPredicates.corretiva(row)) group.corretiva += valueCents
    else if (costPredicates.preventiva(row)) group.preventiva += valueCents
    group.total += valueCents
    group.count += 1
    groups.set(label, group)
  }
  return [...groups.values()].sort((a, b) => b.total - a.total || a.label.localeCompare(b.label, 'pt-BR'))
    .slice(0, limit)
    .map((group) => ({
      ...group, corretiva: group.corretiva / 100, preventiva: group.preventiva / 100, total: group.total / 100,
    }))
}

export function costRank(rows, field, limit = 20) {
  const groups = new Map()
  for (const row of rows) {
    const label = field === 'storeName' ? row.storeName || 'Não atribuído' : row[field] || 'Não informado'
    const group = groups.get(label) ?? { label, amount: 0, count: 0 }
    group.amount += cents(row.amount)
    group.count += 1
    groups.set(label, group)
  }
  return [...groups.values()].sort((a, b) => b.amount - a.amount || a.label.localeCompare(b.label, 'pt-BR'))
    .slice(0, limit).map((group) => ({ ...group, amount: group.amount / 100 }))
}

export function sortCostDetails(rows) {
  return [...rows].sort((a, b) => b.postingDate.localeCompare(a.postingDate) || b.id - a.id)
}
