/**
 * Gestão de Acessos — somente users.manage
 * Credenciais são gerenciadas pelo Keycloak, não aqui.
 */

import { useEffect, useState } from 'react'
import { api } from '../../lib/apiClient.js'
import './users.css'

export default function UsersModal({ onClose }) {
  const [users, setUsers] = useState([])
  const [profiles, setProfiles] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let cancelled = false
    Promise.all([api.get('/users'), api.get('/users/profiles')])
      .then(([us, ps]) => { if (!cancelled) { setUsers(us); setProfiles(ps); setLoading(false) } })
      .catch(e => { if (!cancelled) { setError(e.message); setLoading(false) } })
    return () => { cancelled = true }
  }, [])

  async function handleProfileChange(userId, profileName) {
    setSaving(true)
    try {
      await api.put(`/users/${userId}/profile`, { profile_name: profileName })
      setUsers(prev => prev.map(u => u.id === userId ? { ...u, profile: profileName } : u))
    } catch (e) { alert(`Erro: ${e.message}`) }
    finally { setSaving(false) }
  }

  async function handleStatusChange(userId, newStatus) {
    setSaving(true)
    try {
      await api.put(`/users/${userId}/status`, { status: newStatus })
      setUsers(prev => prev.map(u => u.id === userId ? { ...u, status: newStatus } : u))
    } catch (e) { alert(`Erro: ${e.message}`) }
    finally { setSaving(false) }
  }

  const statusLabel = { active: 'Ativo', disabled: 'Desativado', pending: 'Pendente' }

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true" aria-label="Gestão de acessos">
      <div className="modal-panel modal-panel--wide">
        <div className="modal-header">
          <h2 className="modal-title">Gestão de Acessos</h2>
          <button className="modal-close" type="button" onClick={onClose} aria-label="Fechar">✕</button>
        </div>
        <div className="modal-notice">
          Credenciais e autenticação são gerenciadas pelo provedor de identidade (Keycloak).
          Esta interface gerencia perfis, permissões e limites dentro da aplicação.
        </div>
        {loading && <div className="modal-loading">Carregando usuários…</div>}
        {error && <div className="modal-error">{error}</div>}
        {!loading && !error && (
          <div className="users-table-wrapper">
            <table className="users-table">
              <thead>
                <tr>
                  <th>Nome</th><th>Email</th><th>Perfil</th>
                  <th>Status</th><th>Último acesso</th><th>Limite IA/dia</th><th>Ações</th>
                </tr>
              </thead>
              <tbody>
                {users.map(u => (
                  <tr key={u.id}>
                    <td>{u.display_name}</td>
                    <td className="users-table__email">{u.email}</td>
                    <td>
                      <select className="users-table__select" value={u.profile || ''} disabled={saving}
                              onChange={e => handleProfileChange(u.id, e.target.value)}>
                        <option value="">Sem perfil</option>
                        {profiles.map(p => <option key={p.name} value={p.name}>{p.display_name}</option>)}
                      </select>
                    </td>
                    <td><span className={`status-badge status-badge--${u.status}`}>{statusLabel[u.status] || u.status}</span></td>
                    <td className="users-table__date">
                      {u.last_seen_at ? new Date(u.last_seen_at).toLocaleString('pt-BR') : '—'}
                    </td>
                    <td>{u.ai_daily_limit ?? '—'}</td>
                    <td className="users-table__actions">
                      {u.status === 'active'
                        ? <button className="action-btn action-btn--danger" disabled={saving}
                                  onClick={() => handleStatusChange(u.id, 'disabled')}>Desativar</button>
                        : <button className="action-btn action-btn--success" disabled={saving}
                                  onClick={() => handleStatusChange(u.id, 'active')}>Ativar</button>
                      }
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
