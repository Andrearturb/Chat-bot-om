import { useEffect, useState } from 'react'
import { api } from '../../lib/apiClient.js'
import './audit.css'

const actionLabel = {
  ASSET_CREATE: 'Criou ativo', ASSET_UPDATE: 'Editou ativo', ASSET_DELETE: 'Excluiu ativo',
  DOCUMENT_UPLOAD: 'Upload doc.', DOCUMENT_REPLACE: 'Substituiu doc.', DOCUMENT_DELETE: 'Excluiu doc.',
  DOCUMENT_VIEW: 'Visualizou doc.', DOCUMENT_DOWNLOAD: 'Download doc.',
  USER_ACTIVATE: 'Ativou usuário', USER_DISABLE: 'Desativou usuário',
  USER_ROLE_CHANGE: 'Alterou perfil', USER_PERMISSION_OVERRIDE: 'Override permissão',
  USER_AI_LIMIT_CHANGE: 'Alterou limite IA', LOGIN_SUCCESS: 'Login', LOGOUT: 'Logout',
  SYNC_TAPE: 'Sincronizou Tape',
}

export default function AuditModal({ onClose }) {
  const [logs, setLogs] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [filters, setFilters] = useState({ action: '', date_from: '', date_to: '' })
  const [page, setPage] = useState(1)

  useEffect(() => {
    let cancelled = false
    setLoading(true); setError(null)
    const p = new URLSearchParams({ page: String(page), page_size: '50' })
    if (filters.action) p.set('action', filters.action)
    if (filters.date_from) p.set('date_from', filters.date_from)
    if (filters.date_to) p.set('date_to', filters.date_to)
    api.get(`/audit/logs?${p}`)
      .then(d => { if (!cancelled) { setLogs(d?.logs || []); setLoading(false) } })
      .catch(e => { if (!cancelled) { setError(e.message); setLoading(false) } })
    return () => { cancelled = true }
  }, [page, filters])

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true" aria-label="Auditoria">
      <div className="modal-panel modal-panel--wide">
        <div className="modal-header">
          <h2 className="modal-title">Auditoria</h2>
          <button className="modal-close" type="button" onClick={onClose} aria-label="Fechar">✕</button>
        </div>
        <div className="audit-filters">
          <input className="audit-input" type="text" placeholder="Ação (ex: ASSET_CREATE)"
                 value={filters.action} onChange={e => { setFilters(f => ({ ...f, action: e.target.value })); setPage(1) }} />
          <input className="audit-input" type="datetime-local" title="De"
                 value={filters.date_from} onChange={e => { setFilters(f => ({ ...f, date_from: e.target.value })); setPage(1) }} />
          <input className="audit-input" type="datetime-local" title="Até"
                 value={filters.date_to} onChange={e => { setFilters(f => ({ ...f, date_to: e.target.value })); setPage(1) }} />
        </div>
        {loading && <div className="modal-loading">Carregando logs…</div>}
        {error && <div className="modal-error">{error}</div>}
        {!loading && !error && (
          <>
            <div className="audit-table-wrapper">
              <table className="audit-table">
                <thead>
                  <tr><th>Data/Hora</th><th>Usuário</th><th>Ação</th><th>Entidade</th><th>ID</th></tr>
                </thead>
                <tbody>
                  {logs.length === 0
                    ? <tr><td colSpan={5} style={{ textAlign: 'center', opacity: .5 }}>Nenhum registro encontrado.</td></tr>
                    : logs.map(log => (
                      <tr key={log.id}>
                        <td className="audit-table__date">{new Date(log.created_at).toLocaleString('pt-BR')}</td>
                        <td>{log.user_display || (log.user_id ? `#${log.user_id}` : '—')}</td>
                        <td><span className="audit-action">{actionLabel[log.action] || log.action}</span></td>
                        <td>{log.entity_type || '—'}</td>
                        <td className="audit-table__date">{log.entity_id || '—'}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
            <div className="audit-pagination">
              <button className="action-btn" disabled={page === 1} onClick={() => setPage(p => p - 1)}>← Anterior</button>
              <span>Página {page}</span>
              <button className="action-btn" disabled={logs.length < 50} onClick={() => setPage(p => p + 1)}>Próxima →</button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
