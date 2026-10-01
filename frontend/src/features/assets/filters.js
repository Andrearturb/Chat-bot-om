/** Filtros da Central de Ativos (Praças e Lojas) e parâmetros da exportação: regras puras, sem React. */

export const EMPTY_FILTERS = { pracas: [], storeIds: [] }

export const ASSET_TYPE_OPTIONS = [
  { value: 'climatization', label: 'Climatização' },
  { value: 'fire_safety', label: 'Incêndio' },
  { value: 'water', label: 'Água' },
]

export function normalize(text) {
  return String(text ?? '').normalize('NFD').replace(/\p{M}/gu, '').toLowerCase().trim()
}

/** Mesma regra do servidor (normalize_key): sem acento, caixa, espaços ou pontuação. */
function pracaKey(text) {
  return normalize(text).replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
}

export function samePraca(a, b) {
  return pracaKey(a) === pracaKey(b)
}

export function isFiltered(filters) {
  return filters.pracas.length > 0 || filters.storeIds.length > 0
}

/** Lojas que o seletor oferece: só as das praças marcadas (todas, se nenhuma estiver marcada). */
export function storesForPracas(options, pracas) {
  if (pracas.length === 0) return options
  return options.filter(option => pracas.some(praca => samePraca(praca, option.praca)))
}

/** Tira das lojas marcadas as que ficaram fora das praças marcadas. */
export function pruneStoreIds(options, pracas, storeIds) {
  const allowed = new Set(storesForPracas(options, pracas).map(option => option.id))
  return storeIds.filter(id => allowed.has(id))
}

/** Troca as praças marcadas e mantém o filtro de lojas coerente. */
export function withPracas(filters, options, pracas) {
  return { pracas, storeIds: pruneStoreIds(options, pracas, filters.storeIds) }
}

export function matchesStore(option, text) {
  const needle = normalize(text)
  if (!needle) return true
  return [option.name, option.bpcs, option.sap, option.praca].some(value => normalize(value).includes(needle))
}

export function filtersParams(filters, params = new URLSearchParams()) {
  filters.pracas.forEach(praca => params.append('praca', praca))
  filters.storeIds.forEach(id => params.append('store_id', String(id)))
  return params
}

/** Parâmetros da exportação. Escopo "all" ignora os filtros da tela; "filtered" os envia. */
export function exportParams(filters, types, scope) {
  const params = new URLSearchParams()
  if (scope === 'filtered') filtersParams(filters, params)
  types.forEach(type => params.append('asset_type', type))
  return params
}

export function storesCountLabel(shown, total) {
  if (shown === total) return `${total} ${total === 1 ? 'loja' : 'lojas'}`
  return `${shown} de ${total} lojas`
}

export function exportSummary(preview, types) {
  const stores = `${preview.stores} ${preview.stores === 1 ? 'loja' : 'lojas'}`
  const parts = ASSET_TYPE_OPTIONS
    .filter(option => types.includes(option.value))
    .map(option => `${preview[option.value]} ${option.label.toLowerCase()}`)
  return [stores, ...parts].join(' · ')
}
