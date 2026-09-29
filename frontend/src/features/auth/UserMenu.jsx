import { useRef, useState } from 'react'
import { useAuth } from './AuthProvider.jsx'
import { logout } from './api.js'

export default function UserMenu({ onOpenUsers, onOpenAudit, onOpenSettings }) {
  const { user, profile, hasPermission } = useAuth()
  const [open, setOpen] = useState(false)

  async function handleLogout() {
    setOpen(false)
    try {
      const result = await logout()
      window.location.href = result?.logout_url || window.location.origin
    } catch {
      window.location.reload()
    }
  }

  if (!user) return null
  const initials = (user.display_name || user.email || '?')
    .split(' ').slice(0, 2).map(n => n[0]?.toUpperCase() || '').join('')

  return (
    <div className="user-menu">
      <button className="user-menu__trigger" type="button" onClick={() => setOpen(v => !v)}
              aria-haspopup="menu" aria-expanded={open}
              title={`${user.display_name} — ${profile?.display_name || 'Sem perfil'}`}>
        <span className="user-menu__avatar" aria-hidden="true">{initials}</span>
        <span className="user-menu__name">{user.display_name?.split(' ')[0] || user.email}</span>
        <span className="user-menu__caret" aria-hidden="true">▾</span>
      </button>

      {open && (
        <>
          <div className="user-menu__overlay" onClick={() => setOpen(false)} aria-hidden="true" />
          <div className="user-menu__dropdown" role="menu" aria-label="Menu do usuário">
            <div className="user-menu__header">
              <strong>{user.display_name}</strong>
              <span>{profile?.display_name || 'Sem perfil'}</span>
              <small>{user.email}</small>
            </div>
            <div className="user-menu__items">
              {hasPermission('users.manage') && (
                <button className="user-menu__item" role="menuitem" type="button"
                        onClick={() => { setOpen(false); onOpenUsers?.() }}>
                  Gestão de acessos
                </button>
              )}
              {hasPermission('audit.view') && (
                <button className="user-menu__item" role="menuitem" type="button"
                        onClick={() => { setOpen(false); onOpenAudit?.() }}>
                  Auditoria
                </button>
              )}
              {hasPermission('settings.view') && (
                <button className="user-menu__item" role="menuitem" type="button"
                        onClick={() => { setOpen(false); onOpenSettings?.() }}>
                  Configurações
                </button>
              )}
              <hr className="user-menu__divider" />
              <button className="user-menu__item user-menu__item--danger" role="menuitem"
                      type="button" onClick={handleLogout}>
                Sair
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
