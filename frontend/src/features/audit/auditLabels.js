/** Rótulos e datas da Auditoria: funções puras, sem React (testáveis com `node --test`). */

export const ACTION_LABELS = {
  LOGIN_SUCCESS: 'Entrou no sistema',
  LOGOUT: 'Saiu do sistema',
  ASSET_CREATE: 'Cadastrou equipamento',
  ASSET_UPDATE: 'Editou equipamento',
  ASSET_DELETE: 'Excluiu equipamento',
  DOCUMENT_UPLOAD: 'Enviou documento',
  DOCUMENT_REPLACE: 'Substituiu documento',
  DOCUMENT_DELETE: 'Excluiu documento',
  DOCUMENT_VIEW: 'Visualizou documento',
  DOCUMENT_DOWNLOAD: 'Baixou documento',
  SYNC_TAPE: 'Sincronizou a Tape',
  ASSET_EXPORT: 'Exportou ativos',
}

export const ENTITY_LABELS = {
  app_user: 'Usuário',
  climate_asset: 'Climatização',
  fire_asset: 'Incêndio',
  water_asset: 'Água',
  store_document: 'Documento',
  upload: 'Importação',
  asset_export: 'Ativos',
}

/** Texto de uma ação: o rótulo conhecido ou, para códigos novos, o código escrito por extenso. */
export function actionLabel(code) {
  if (!code) return '—'
  if (ACTION_LABELS[code]) return ACTION_LABELS[code]
  const text = String(code).toLowerCase().replace(/_/g, ' ')
  return text.charAt(0).toUpperCase() + text.slice(1)
}

export function entityLabel(type) {
  if (!type) return '—'
  return ENTITY_LABELS[type] || String(type).replace(/_/g, ' ')
}

/** Detalhe curto do registro: loja, código do equipamento ou nome do arquivo. */
export function describeLog(log) {
  const values = { ...(log.old_values || {}), ...(log.new_values || {}) }
  const parts = [log.store_name, values.asset_code, values.filename].filter(Boolean)
  if (values.stores != null) {
    parts.push(`${values.stores} ${values.stores === 1 ? 'loja' : 'lojas'}`)
    if (values.assets != null) parts.push(`${values.assets} ${values.assets === 1 ? 'equipamento' : 'equipamentos'}`)
  }
  return parts.length ? parts.join(' · ') : '—'
}

/** Opções do filtro de ação: [{ value, label }] em ordem alfabética do rótulo. */
export function actionOptions(codes) {
  return [...new Set(codes || [])]
    .map(code => ({ value: code, label: actionLabel(code) }))
    .sort((a, b) => a.label.localeCompare(b.label, 'pt-BR'))
}

/**
 * Início e fim do dia local ("2026-10-01") em UTC, que é o que a API compara com o banco.
 * Campo vazio devolve '' (sem filtro).
 */
export function dayStartUtc(day) {
  if (!day) return ''
  const [year, month, date] = day.split('-').map(Number)
  return new Date(year, month - 1, date, 0, 0, 0, 0).toISOString()
}

export function dayEndUtc(day) {
  if (!day) return ''
  const [year, month, date] = day.split('-').map(Number)
  return new Date(year, month - 1, date, 23, 59, 59, 999).toISOString()
}

export function formatDateTime(isoValue) {
  const date = new Date(isoValue)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'medium' })
}
