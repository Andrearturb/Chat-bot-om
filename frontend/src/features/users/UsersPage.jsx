/**
 * Gestão de Usuários — exclusivo para ADMINISTRADOR.
 *
 * A interface só aparece para administradores, mas quem garante o acesso é o
 * backend (perfil validado na sessão server-side). Contas e senhas ficam no
 * Keycloak; perfil e status ficam no Chat-bot O&M.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import mascot from '../../assets/gentileza-indicadores.png'
import {
  activateUser,
  createUser,
  deactivateUser,
  fetchCapabilities,
  fetchUsers,
  resetUserPassword,
  sendPasswordEmail,
  updateUser,
} from './api.js'
import UserFormDrawer from './components/UserFormDrawer.jsx'
import {
  ConfirmDialog,
  ProfileBadge,
  StatusBadge,
  UserAvatar,
  UsersIcon,
  UsersToast,
} from './components/UserVisuals.jsx'
import {
  filterUsers,
  formatLastAccess,
  PROFILE_OPTIONS,
  STATUS_OPTIONS,
  summarizeUsers,
} from './userUtils.js'
import './users.css'

const STATUS_ORDER = { pending: 0, active: 1, disabled: 2 }

function sortUsers(list) {
  return [...list].sort((a, b) =>
    (STATUS_ORDER[a.status] ?? 3) - (STATUS_ORDER[b.status] ?? 3)
    || a.display_name.localeCompare(b.display_name, 'pt-BR', { sensitivity: 'base' }))
}

function friendlyError(error, fallback) {
  if (error?.kind === 'network') return 'Não foi possível conectar ao servidor. Verifique sua conexão e tente novamente.'
  if (error?.status === 403) return 'Você não tem permissão para esta ação.'
  // Mensagens do BFF já são escritas para o administrador (sem detalhes técnicos).
  const detail = typeof error?.detail === 'string' ? error.detail.trim() : ''
  return detail || fallback
}

function StatCard({ label, value, tone, active, onClick }) {
  return (
    <button type="button" className={`users-stat users-stat--${tone}${active ? ' is-active' : ''}`}
            onClick={onClick} aria-pressed={active}>
      <span className="users-stat__label">{label}</span>
      <strong className="users-stat__value">{value ?? <span className="users-stat__loading" aria-label="Carregando" />}</strong>
    </button>
  )
}

export default function UsersPage({ currentUserId, onSelfChanged }) {
  const [users, setUsers] = useState([])
  const [capabilities, setCapabilities] = useState({ identity_admin: false, email_actions: false })
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [query, setQuery] = useState('')
  const [profileFilter, setProfileFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [drawer, setDrawer] = useState(null)
  const [drawerError, setDrawerError] = useState('')
  const [saving, setSaving] = useState(false)
  const [confirm, setConfirm] = useState(null)
  const [confirmBusy, setConfirmBusy] = useState(false)
  const [toast, setToast] = useState(null)
  const [busyId, setBusyId] = useState(null)
  const loadRef = useRef(null)

  // initial: o primeiro carregamento já nasce com loading=true (sem setState síncrono no efeito).
  const load = useCallback(async ({ initial = false } = {}) => {
    loadRef.current?.abort()
    const ctrl = new AbortController()
    loadRef.current = ctrl
    if (!initial) {
      setLoading(true)
      setLoadError('')
    }
    try {
      const [list, caps] = await Promise.all([
        fetchUsers(ctrl.signal),
        fetchCapabilities(ctrl.signal).catch(() => ({ identity_admin: false, email_actions: false })),
      ])
      setUsers(sortUsers(list || []))
      setCapabilities(caps)
    } catch (error) {
      if (error?.name === 'AbortError') return
      setLoadError(friendlyError(error, 'Não foi possível carregar os usuários. Tente novamente.'))
    } finally {
      if (loadRef.current === ctrl) {
        loadRef.current = null
        setLoading(false)
      }
    }
  }, [])

  useEffect(() => {
    load({ initial: true })
    return () => loadRef.current?.abort()
  }, [load])

  useEffect(() => {
    if (!toast) return undefined
    const timer = window.setTimeout(() => setToast(null), toast.kind === 'warning' ? 6500 : 4000)
    return () => window.clearTimeout(timer)
  }, [toast])

  const summary = useMemo(() => summarizeUsers(users), [users])
  const visibleUsers = useMemo(
    () => filterUsers(users, { query, profile: profileFilter, status: statusFilter }),
    [users, query, profileFilter, statusFilter],
  )
  const hasFilters = Boolean(query.trim() || profileFilter || statusFilter)

  function clearFilters() {
    setQuery('')
    setProfileFilter('')
    setStatusFilter('')
  }

  function upsertUser(updated) {
    setUsers((current) => {
      const exists = current.some((item) => item.id === updated.id)
      return sortUsers(exists ? current.map((item) => (item.id === updated.id ? updated : item)) : [...current, updated])
    })
  }

  function notifyResult(result, successMessage) {
    if (result?.user) upsertUser(result.user)
    const warnings = result?.warnings || []
    setToast(warnings.length ? { kind: 'warning', message: warnings.join(' ') } : { kind: 'success', message: successMessage })
    if (result?.user?.is_self) onSelfChanged?.()
  }

  function openCreate() {
    setDrawerError('')
    setDrawer({ mode: 'create' })
  }

  function openEdit(user, presetStatus = null) {
    setDrawerError('')
    setDrawer({ mode: 'edit', user, presetStatus })
  }

  function closeDrawer() {
    if (saving) return
    setDrawer(null)
    setDrawerError('')
  }

  async function handleCreate(payload) {
    setSaving(true)
    setDrawerError('')
    try {
      const result = await createUser(payload)
      setDrawer(null)
      notifyResult(result, 'Usuário criado com sucesso.')
    } catch (error) {
      setDrawerError(friendlyError(error, 'Não foi possível criar o usuário. Tente novamente.'))
    } finally {
      setSaving(false)
    }
  }

  async function persistUpdate(user, payload) {
    setSaving(true)
    setDrawerError('')
    try {
      const result = await updateUser(user.id, payload)
      setDrawer(null)
      const approved = user.status === 'pending' && payload.status === 'active'
      notifyResult(result, approved ? 'Acesso liberado.' : 'Alterações salvas.')
    } catch (error) {
      setDrawerError(friendlyError(error, 'Não foi possível salvar as alterações. Tente novamente.'))
    } finally {
      setSaving(false)
    }
  }

  function handleUpdate(payload) {
    const user = drawer?.user
    if (!user) return
    if (!Object.keys(payload).length) {
      setDrawer(null)
      return
    }
    if (payload.status === 'disabled') {
      setConfirm({
        title: 'Desativar usuário?',
        message: `${user.display_name} não poderá acessar o Chat-bot O&M até ser reativado.`,
        confirmLabel: 'Desativar',
        tone: 'danger',
        onCancel: () => setConfirm(null),
        onConfirm: () => { setConfirm(null); persistUpdate(user, payload) },
      })
      return
    }
    if (payload.profile && user.profile === 'ADMINISTRADOR' && payload.profile !== 'ADMINISTRADOR') {
      setConfirm({
        title: 'Remover perfil de Administrador?',
        message: user.id === currentUserId
          ? 'Você perderá o acesso à Gestão de Usuários assim que salvar.'
          : `${user.display_name} deixará de gerenciar usuários e configurações.`,
        confirmLabel: 'Remover perfil',
        tone: 'danger',
        icon: 'shield',
        onCancel: () => setConfirm(null),
        onConfirm: () => { setConfirm(null); persistUpdate(user, payload) },
      })
      return
    }
    persistUpdate(user, payload)
  }

  function requestDeactivate(user) {
    setConfirm({
      title: 'Desativar usuário?',
      message: `${user.display_name} não poderá acessar o Chat-bot O&M até ser reativado.`,
      confirmLabel: 'Desativar',
      tone: 'danger',
      onCancel: () => setConfirm(null),
      onConfirm: async () => {
        setConfirmBusy(true)
        setBusyId(user.id)
        try {
          notifyResult(await deactivateUser(user.id), 'Usuário desativado.')
        } catch (error) {
          setToast({ kind: 'error', message: friendlyError(error, 'Não foi possível desativar o usuário.') })
        } finally {
          setConfirmBusy(false)
          setBusyId(null)
          setConfirm(null)
        }
      },
    })
  }

  async function handleActivate(user) {
    if (!user.profile) {
      // Aprovação exige perfil: abre a edição já com o status "Ativo".
      openEdit(user, 'active')
      return
    }
    setBusyId(user.id)
    try {
      notifyResult(await activateUser(user.id), user.status === 'pending' ? 'Acesso liberado.' : 'Usuário reativado.')
    } catch (error) {
      setToast({ kind: 'error', message: friendlyError(error, 'Não foi possível ativar o usuário.') })
    } finally {
      setBusyId(null)
    }
  }

  function handleResetPassword(password) {
    const user = drawer?.user
    if (!user) return
    setConfirm({
      title: 'Redefinir senha?',
      message: `${user.display_name} precisará usar a nova senha temporária no próximo acesso. As sessões abertas serão encerradas.`,
      confirmLabel: 'Redefinir senha',
      tone: 'primary',
      icon: 'key',
      onCancel: () => setConfirm(null),
      onConfirm: async () => {
        setConfirmBusy(true)
        try {
          notifyResult(await resetUserPassword(user.id, password), 'Senha temporária definida. Informe-a ao usuário.')
          setDrawer(null)
        } catch (error) {
          setDrawerError(friendlyError(error, 'Não foi possível redefinir a senha.'))
        } finally {
          setConfirmBusy(false)
          setConfirm(null)
        }
      },
    })
  }

  async function handleSendPasswordEmail() {
    const user = drawer?.user
    if (!user) return
    setSaving(true)
    try {
      notifyResult(await sendPasswordEmail(user.id), `E-mail de redefinição enviado para ${user.email}.`)
      setDrawer(null)
    } catch (error) {
      setDrawerError(friendlyError(error, 'Não foi possível enviar o e-mail.'))
    } finally {
      setSaving(false)
    }
  }

  const canCreate = capabilities.identity_admin
  const initialLoading = loading && users.length === 0

  return (
    <section className="users-page" aria-labelledby="users-title">
      <UsersToast toast={toast} />

      <header className="users-hero">
        <div className="users-hero__mascot" aria-hidden="true">
          <span className="users-hero__ring users-hero__ring--one" />
          <span className="users-hero__ring users-hero__ring--two" />
          <img src={mascot} alt="" />
        </div>
        <div className="users-hero__copy">
          <p className="users-hero__eyebrow">Configurações <span aria-hidden="true" /> Acessos</p>
          <h1 id="users-title">Gestão de Usuários</h1>
          <p>Gerencie os usuários e os níveis de acesso ao Chat-bot O&amp;M.</p>
          <button className="users-hero__cta" type="button" onClick={openCreate} disabled={!canCreate || initialLoading}
                  title={canCreate ? undefined : 'Integração com o Keycloak indisponível'}>
            <UsersIcon name="plus" size={17} /> Novo usuário
          </button>
        </div>
        <div className="users-hero__stats" role="group" aria-label="Resumo e filtro por status">
          <StatCard label="Usuários" tone="total" value={initialLoading ? null : summary.total}
                    active={!statusFilter} onClick={() => setStatusFilter('')} />
          <StatCard label="Ativos" tone="active" value={initialLoading ? null : summary.active}
                    active={statusFilter === 'active'} onClick={() => setStatusFilter(statusFilter === 'active' ? '' : 'active')} />
          <StatCard label="Pendentes" tone="pending" value={initialLoading ? null : summary.pending}
                    active={statusFilter === 'pending'} onClick={() => setStatusFilter(statusFilter === 'pending' ? '' : 'pending')} />
          <StatCard label="Bloqueados" tone="disabled" value={initialLoading ? null : summary.disabled}
                    active={statusFilter === 'disabled'} onClick={() => setStatusFilter(statusFilter === 'disabled' ? '' : 'disabled')} />
        </div>
      </header>

      <section className="users-panel" aria-labelledby="users-list-title">
        <div className="users-panel__heading">
          <div>
            <span className="users-eyebrow">Acessos ao Chat-bot O&amp;M</span>
            <h2 id="users-list-title">Usuários cadastrados</h2>
            <p>Senhas e login ficam no Keycloak. Aqui você define quem acessa e com qual perfil.</p>
          </div>
        </div>

        {!loading && !loadError && !capabilities.identity_admin && (
          <div className="users-inline-alert users-inline-alert--warning" role="status">
            <UsersIcon name="info" size={17} />
            <span>
              A integração com o Keycloak está indisponível. Você ainda pode ajustar perfis e status,
              mas o cadastro de novos usuários e a redefinição de senha ficam temporariamente bloqueados.
            </span>
          </div>
        )}

        <div className="users-toolbar">
          <label className="users-search">
            <span className="users-search__icon"><UsersIcon name="search" size={18} /></span>
            <input value={query} onChange={(event) => setQuery(event.target.value)}
                   placeholder="Buscar usuário" aria-label="Buscar usuário por nome, e-mail ou usuário" autoComplete="off" />
            {query && (
              <button type="button" className="users-search__clear" onClick={() => setQuery('')} aria-label="Limpar busca">×</button>
            )}
          </label>
          <select value={profileFilter} onChange={(event) => setProfileFilter(event.target.value)} aria-label="Filtrar por perfil">
            <option value="">Todos os perfis</option>
            {PROFILE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
          <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)} aria-label="Filtrar por status">
            <option value="">Todos os status</option>
            {STATUS_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        </div>

        <div className="users-meta" aria-live="polite">
          <span>
            <strong>{visibleUsers.length}</strong> {visibleUsers.length === 1 ? 'usuário' : 'usuários'}
            {hasFilters ? ` de ${users.length}` : ''}
          </span>
          {hasFilters && <button type="button" className="users-link-button" onClick={clearFilters}>Limpar filtros</button>}
        </div>

        {initialLoading ? (
          <div className="users-state" role="status">
            <span className="users-loader" aria-hidden="true" />
            <strong>Carregando usuários...</strong>
          </div>
        ) : loadError ? (
          <div className="users-state users-state--error" role="alert">
            <span className="users-state__icon users-state__icon--error"><UsersIcon name="alert" size={22} /></span>
            <strong>{loadError}</strong>
            <button className="users-button users-button--primary" type="button" onClick={() => load()}>Tentar novamente</button>
          </div>
        ) : visibleUsers.length === 0 ? (
          <div className="users-state">
            <span className="users-state__icon"><UsersIcon name="users" size={22} /></span>
            <strong>Nenhum usuário encontrado.</strong>
            <span>{hasFilters ? 'Ajuste a busca ou limpe os filtros para ver outros usuários.' : 'Cadastre o primeiro usuário para liberar o acesso.'}</span>
            {hasFilters && <button className="users-button users-button--quiet" type="button" onClick={clearFilters}>Limpar filtros</button>}
          </div>
        ) : (
          <div className={`users-table-wrap${loading ? ' is-refreshing' : ''}`}>
            <table className="users-table">
              <thead>
                <tr>
                  <th scope="col">Nome</th>
                  <th scope="col">E-mail</th>
                  <th scope="col">Usuário</th>
                  <th scope="col">Perfil</th>
                  <th scope="col">Status</th>
                  <th scope="col">Último acesso</th>
                  <th scope="col"><span className="users-sr-only">Ações</span></th>
                </tr>
              </thead>
              <tbody>
                {visibleUsers.map((user) => {
                  const isSelf = user.id === currentUserId
                  const busy = busyId === user.id
                  return (
                    <tr key={user.id} className={user.status === 'disabled' ? 'is-disabled' : undefined}>
                      <td data-label="Nome">
                        <button type="button" className="users-person" onClick={() => openEdit(user)}
                                aria-label={`Editar ${user.display_name}`}>
                          <UserAvatar name={user.display_name} profile={user.profile} />
                          <span className="users-person__copy">
                            <strong>{user.display_name}{isSelf && <em className="users-self-tag">Você</em>}</strong>
                            <small>{user.email}</small>
                            {user.username && <small className="users-person__username">@{user.username}</small>}
                          </span>
                        </button>
                      </td>
                      <td data-label="E-mail" className="users-table__email">{user.email}</td>
                      <td data-label="Usuário" className="users-table__username">{user.username ? `@${user.username}` : '—'}</td>
                      <td data-label="Perfil"><ProfileBadge profile={user.profile} /></td>
                      <td data-label="Status"><StatusBadge status={user.status} /></td>
                      <td data-label="Último acesso" className="users-table__date">{formatLastAccess(user.last_seen_at)}</td>
                      <td className="users-table__actions">
                        <button type="button" className="users-action" onClick={() => openEdit(user)}
                                aria-label={`Editar ${user.display_name}`} title="Editar">
                          <UsersIcon name="edit" size={15} /><span className="users-action__label">Editar</span>
                        </button>
                        {user.status === 'active' ? (
                          <button type="button" className="users-action users-action--danger" onClick={() => requestDeactivate(user)}
                                  disabled={isSelf || busy} aria-label={`Desativar ${user.display_name}`}
                                  title={isSelf ? 'Você não pode desativar a sua própria conta.' : 'Desativar'}>
                            <UsersIcon name="power" size={15} /><span className="users-action__label">Desativar</span>
                          </button>
                        ) : (
                          <button type="button" className="users-action users-action--success" onClick={() => handleActivate(user)} disabled={busy}
                                  aria-label={`${user.status === 'pending' ? 'Aprovar' : 'Ativar'} ${user.display_name}`}
                                  title={user.status === 'pending' ? 'Aprovar' : 'Ativar'}>
                            <UsersIcon name="check" size={15} /><span className="users-action__label">{user.status === 'pending' ? 'Aprovar' : 'Ativar'}</span>
                          </button>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {drawer && (
        <UserFormDrawer
          key={drawer.mode === 'edit' ? `edit-${drawer.user.id}` : 'create'}
          mode={drawer.mode}
          user={drawer.user}
          presetStatus={drawer.presetStatus}
          capabilities={capabilities}
          currentUserId={currentUserId}
          activeAdminCount={summary.activeAdmins}
          saving={saving}
          error={drawerError}
          onCancel={closeDrawer}
          onSubmit={drawer.mode === 'create' ? handleCreate : handleUpdate}
          onResetPassword={handleResetPassword}
          onSendPasswordEmail={handleSendPasswordEmail}
        />
      )}

      <ConfirmDialog confirm={confirm} busy={confirmBusy} />
    </section>
  )
}
