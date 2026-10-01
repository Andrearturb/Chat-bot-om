import { useEffect, useState } from 'react'
import { useAuth } from './authContext.js'
import { logoutAndRedirect } from './api.js'

export default function UserMenu({ onOpenAudit, onOpenSettings }) {
  const { user, profile, hasPermission } = useAuth()
  const [open, setOpen] = useState(false)
  const [leaving, setLeaving] = useState(false)

  useEffect(() => {
    if (!open) return undefined
    const onKeyDown = (event) => { if (event.key === 'Escape') setOpen(false) }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open])

  async function handleLogout() {
    setOpen(false)
    setLeaving(true)
    await logoutAndRedirect()
  }

  if (!user) return null
  const initials = (user.display_name || user.email || '?')
    .split(' ').slice(0, 2).map(n => n[0]?.toUpperCase() || '').join('')

  return (
    <div className="user-menu">
      <button className="user-menu__trigger" type="button" onClick={() => setOpen(v => !v)}
              aria-haspopup="menu" aria-expanded={open} disabled={leaving}
              title={`${user.display_name} — ${profile?.display_name || 'Sem perfil'}`}>
        <span className="user-menu__avatar" aria-hidden="true">{initials}</span>
        <span className="user-menu__name">{leaving ? 'Saindo…' : (user.display_name?.split(' ')[0] || user.email)}</span>
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
