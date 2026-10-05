/**
 * Migra filtros salvos no formato antigo (um valor, sentinela "todos") para o
 * formato atual (array; vazio = sem restrição). Idempotente: filtro já em
 * array passa direto. Campo ausente no que foi salvo cai no default — é o
 * caso de um filtro novo que não existia quando a sessão anterior gravou o
 * sessionStorage.
 *
 * Compartilhado por todos os painéis de indicadores com filtro em
 * sessionStorage (corretiva, preventiva, custos): a forma do problema — valor
 * único gravado antes de os filtros virarem múltipla seleção — é a mesma nos
 * três, embora cada um normalize seus próprios campos de um jeito diferente.
 */
export function migrateFilterValues(saved, defaults) {
  const migrated = { ...defaults }
  for (const key of Object.keys(defaults)) {
    const value = saved?.[key]
    if (value === undefined) continue
    if (Array.isArray(value)) { migrated[key] = value; continue }
    migrated[key] = (value === 'todos' || value === '' || value === null) ? [] : [value]
  }
  return migrated
}
