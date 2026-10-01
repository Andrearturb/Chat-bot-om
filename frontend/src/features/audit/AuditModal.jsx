import { useEffect, useRef, useState } from 'react'
import { api } from '../../lib/apiClient.js'
import {
  actionLabel, actionOptions, dayEndUtc, dayStartUtc, describeLog, entityLabel, formatDateTime,
} from './auditLabels.js'
import './audit.css'

const PAGE_SIZE = 50
const NO_FILTERS = { action: '', dateFrom: '', dateTo: '' }

export default function AuditModal({ onClose }) {
  const [result, setResult] = useState({ key: null, logs: [], error: '' })
  const [filters, setFilters] = useState(NO_FILTERS)
  const [actions, setActions] = useState([])
  const [page, setPage] = useState(1)
  const closeRef = useRef(null)

  // Esc fecha; o foco começa no botão de fechar (como nas Configurações).
  useEffect(() => {
    closeRef.current?.focus()
    const onKeyDown = event => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  useEffect(() => {
    api.get('/audit/actions').then(codes => setActions(actionOptions(codes))).catch(() => setActions([]))
  }, [])

  const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) })
  if (filters.action) params.set('action', filters.action)
  if (filters.dateFrom) params.set('date_from', dayStartUtc(filters.dateFrom))
  if (filters.dateTo) params.set('date_to', dayEndUtc(filters.dateTo))
  const requestKey = params.toString()

  useEffect(() => {
    let cancelled = false
    api.get(`/audit/logs?${requestKey}`)
      .then(data => { if (!cancelled) setResult({ key: requestKey, logs: data?.logs || [], error: '' }) })
      .catch(failure => {
        if (!cancelled) setResult({ key: requestKey, logs: [], error: failure.message || 'Não foi possível carregar a auditoria.' })
      })
    return () => { cancelled = true }
  }, [requestKey])

  // Carregando = a última resposta recebida não é a do filtro/página atuais.
  const loading = result.key !== requestKey
  const { logs, error } = result

  function changeFilter(name, value) {
    setFilters(previous => ({ ...previous, [name]: value }))
    setPage(1)
  }

  const hasFilters = Boolean(filters.action || filters.dateFrom || filters.dateTo)

  return (
    <div
      className="audit-overlay"
      role="presentation"
      onMouseDown={event => { if (event.target === event.currentTarget) onClose() }}
    >
      <section className="audit-modal" role="dialog" aria-modal="true" aria-labelledby="audit-title">
        <header className="audit-header">
          <div>
            <p className="audit-kicker">Segurança</p>
            <h2 id="audit-title">Auditoria</h2>
            <p className="audit-subtitle">Quem fez o quê no sistema, do mais recente para o mais antigo.</p>
          </div>
          <button ref={closeRef} className="audit-close" type="button" onClick={onClose} aria-label="Fechar auditoria">×</button>
        </header>

        <div className="audit-filters">
          <label className="audit-field">
            <span>Ação</span>
            <select value={filters.action} onChange={event => changeFilter('action', event.target.value)}>
              <option value="">Todas as ações</option>
              {actions.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </label>
          <label className="audit-field">
            <span>De</span>
            <input type="date" value={filters.dateFrom} max={filters.dateTo || undefined}
                   onChange={event => changeFilter('dateFrom', event.target.value)} />
          </label>
          <label className="audit-field">
            <span>Até</span>
            <input type="date" value={filters.dateTo} min={filters.dateFrom || undefined}
                   onChange={event => changeFilter('dateTo', event.target.value)} />
          </label>
          {hasFilters && (
            <button className="audit-clear" type="button" onClick={() => { setFilters(NO_FILTERS); setPage(1) }}>
              Limpar filtros
            </button>
          )}
        </div>

        {loading && <p className="audit-state" role="status">Carregando registros…</p>}
        {error && <p className="audit-state audit-state--error" role="alert">{error}</p>}

        {!loading && !error && (
          <>
            {logs.length === 0 ? (
              <p className="audit-state">Nenhum registro encontrado{hasFilters ? ' para esses filtros' : ''}.</p>
            ) : (
              <div className="audit-table-wrapper">
                <table className="audit-table">
                  <thead>
                    <tr><th>Quando</th><th>Quem</th><th>Ação</th><th>Onde</th><th>Detalhe</th></tr>
                  </thead>
                  <tbody>
                    {logs.map(log => (
                      <tr key={log.id}>
                        <td data-label="Quando" className="audit-table__date">{formatDateTime(log.created_at)}</td>
                        <td data-label="Quem">{log.user_display || (log.user_id ? `Usuário ${log.user_id}` : 'Sistema')}</td>
                        <td data-label="Ação"><span className="audit-action">{actionLabel(log.action)}</span></td>
                        <td data-label="Onde">{entityLabel(log.entity_type)}</td>
                        <td data-label="Detalhe" className="audit-table__detail">{describeLog(log)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <footer className="audit-pagination">
              <button type="button" disabled={page === 1} onClick={() => setPage(value => value - 1)}>← Anterior</button>
              <span>Página {page}</span>
              <button type="button" disabled={logs.length < PAGE_SIZE} onClick={() => setPage(value => value + 1)}>Próxima →</button>
            </footer>
          </>
        )}
      </section>
    </div>
  )
}
