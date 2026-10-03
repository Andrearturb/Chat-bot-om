const TODOS = 'todos'

export const defaultCostFilters = {
  tipo: TODOS, fornecedor: TODOS, loja: TODOS, praca: TODOS, mes: TODOS, ano: TODOS,
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

export function postingParts(value) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value ?? '').slice(0, 10))
  if (!match || Number(match[2]) < 1 || Number(match[2]) > 12) return null
  return { ano: match[1], mes: match[2] }
}

export function filterCosts(rows, filters = defaultCostFilters) {
  return rows.filter((row) => {
    if (filters.tipo !== TODOS && row.contaRazao !== filters.tipo) return false
    if (filters.fornecedor !== TODOS && normalize(row.supplierName) !== normalize(filters.fornecedor)) return false
    if (filters.loja !== TODOS && normalize(row.storeName ?? 'Não atribuído') !== normalize(filters.loja)) return false
    if (filters.praca !== TODOS && normalize(row.praca) !== normalize(filters.praca)) return false
    if (filters.mes !== TODOS || filters.ano !== TODOS) {
      const parts = postingParts(row.postingDate)
      if (!parts) return false
      if (filters.mes !== TODOS && parts.mes !== filters.mes) return false
      if (filters.ano !== TODOS && parts.ano !== filters.ano) return false
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
