/**
 * Gestão de Usuários — consulta somente leitura (permissão users.view).
 *
 * Cadastro, liberação, bloqueio e senhas ficam no console do Keycloak, com os
 * gestores de acesso. Aqui a lista mostra quem já entrou no Chat-bot O&M, o
 * perfil do último acesso e se há sessão ativa. Quem garante o acesso é o backend.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import mascot from '../../assets/gentileza-indicadores.png'
import { fetchUsers } from './api.js'
import { ProfileBadge, SessionBadge, UserAvatar, UsersIcon } from './components/UserVisuals.jsx'
import {
  filterUsers,
  formatLastAccess,
  NO_PROFILE,
  PROFILE_OPTIONS,
  sortUsers,
  summarizeUsers,
} from './userUtils.js'
import './users.css'

function friendlyError(error) {
  if (error?.kind === 'network') return 'Não foi possível conectar ao servidor. Verifique sua conexão e tente novamente.'
  if (error?.status === 403) return 'Você não tem permissão para consultar os usuários.'
  return 'Não foi possível carregar os usuários. Tente novamente.'
}

function StatCard({ label, value, tone, active = false, onClick }) {
  const content = (
    <>
      <span className="users-stat__label">{label}</span>
      <strong className="users-stat__value">{value ?? <span className="users-stat__loading" aria-label="Carregando" />}</strong>
    </>
  )
  if (!onClick) return <div className={`users-stat users-stat--${tone}`}>{content}</div>
  return (
    <button type="button" className={`users-stat users-stat--${tone}${active ? ' is-active' : ''}`}
            onClick={onClick} aria-pressed={active}>
      {content}
    </button>
  )
}

export default function UsersPage({ currentUserId, consoleUrl }) {
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [query, setQuery] = useState('')
  const [profileFilter, setProfileFilter] = useState('')
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
      setUsers(sortUsers((await fetchUsers(ctrl.signal)) || []))
    } catch (error) {
      if (error?.name === 'AbortError') return
      setLoadError(friendlyError(error))
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

  const summary = useMemo(() => summarizeUsers(users), [users])
  const visibleUsers = useMemo(
    () => filterUsers(users, { query, profile: profileFilter }),
    [users, query, profileFilter],
  )
  const hasFilters = Boolean(query.trim() || profileFilter)
  const initialLoading = loading && users.length === 0

  function clearFilters() {
    setQuery('')
    setProfileFilter('')
  }

  return (
    <section className="users-page" aria-labelledby="users-title">
      <header className="users-hero">
        <div className="users-hero__mascot" aria-hidden="true">
          <span className="users-hero__ring users-hero__ring--one" />
          <span className="users-hero__ring users-hero__ring--two" />
          <img src={mascot} alt="" />
        </div>
        <div className="users-hero__copy">
          <p className="users-hero__eyebrow">Configurações <span aria-hidden="true" /> Acessos</p>
          <h1 id="users-title">Gestão de Usuários</h1>
          <p>Veja quem acessa o Chat-bot O&amp;M. Cadastro, liberação e bloqueio são feitos no Keycloak.</p>
          {consoleUrl && (
            <a className="users-hero__cta" href={consoleUrl} target="_blank" rel="noopener noreferrer">
              <UsersIcon name="shield" size={17} /> Gerenciar no Keycloak
            </a>
          )}
        </div>
        <div className="users-hero__stats" role="group" aria-label="Resumo dos acessos">
          <StatCard label="Usuários" tone="total" value={initialLoading ? null : summary.total}
                    active={!profileFilter} onClick={() => setProfileFilter('')} />
          <StatCard label="Com sessão ativa" tone="active" value={initialLoading ? null : summary.activeSessions} />
          <StatCard label="Sem perfil" tone="pending" value={initialLoading ? null : summary.withoutProfile}
                    active={profileFilter === NO_PROFILE}
                    onClick={() => setProfileFilter(profileFilter === NO_PROFILE ? '' : NO_PROFILE)} />
        </div>
      </header>

      <section className="users-panel" aria-labelledby="users-list-title">
        <div className="users-panel__heading">
          <div>
            <span className="users-eyebrow">Acessos ao Chat-bot O&amp;M</span>
            <h2 id="users-list-title">Quem já entrou</h2>
            <p>O perfil mostrado é o do último acesso de cada pessoa.</p>
          </div>
        </div>

        <div className="users-inline-alert users-inline-alert--info" role="note">
          <UsersIcon name="info" size={17} />
          <span>
            Para liberar uma conta nova, um gestor de acesso inclui a pessoa no grupo do perfil no Keycloak.
            A troca de perfil vale em até 5 minutos; o bloqueio com encerramento das sessões vale na hora.
          </span>
        </div>

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
            <option value={NO_PROFILE}>Sem perfil</option>
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
            <span>{hasFilters ? 'Ajuste a busca ou limpe os filtros para ver outros usuários.' : 'Ninguém entrou no Chat-bot O&M ainda.'}</span>
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
                  <th scope="col">Sessão</th>
                  <th scope="col">Último acesso</th>
                </tr>
              </thead>
              <tbody>
                {visibleUsers.map((user) => (
                  <tr key={user.id}>
                    <td data-label="Nome">
                      <div className="users-person">
                        <UserAvatar name={user.display_name} profile={user.profile} />
                        <span className="users-person__copy">
                          <strong>{user.display_name}{user.id === currentUserId && <em className="users-self-tag">Você</em>}</strong>
                          <small>{user.email}</small>
                          {user.username && <small className="users-person__username">@{user.username}</small>}
                        </span>
                      </div>
                    </td>
                    <td data-label="E-mail" className="users-table__email">{user.email}</td>
                    <td data-label="Usuário" className="users-table__username">{user.username ? `@${user.username}` : '—'}</td>
                    <td data-label="Perfil"><ProfileBadge profile={user.profile} /></td>
                    <td data-label="Sessão"><SessionBadge active={user.active_session} /></td>
                    <td data-label="Último acesso" className="users-table__date">{formatLastAccess(user.last_seen_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </section>
  )
}
