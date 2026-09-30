import { initials, profileLabel, statusLabel } from '../userUtils.js'

const ICON_PATHS = {
  search: <><circle cx="11" cy="11" r="7" /><path d="m20 20-3.6-3.6" /></>,
  plus: <path d="M12 5v14M5 12h14" />,
  edit: <><path d="M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16v4Z" /><path d="m13.5 6.5 4 4" /></>,
  power: <><path d="M12 3v8" /><path d="M6.4 6.6a8 8 0 1 0 11.2 0" /></>,
  check: <path d="m5 12.5 4.2 4.2L19 7" />,
  key: <><circle cx="8" cy="15" r="4" /><path d="m10.8 12.2 8.7-8.7M16 7l2.5 2.5M14 9l1.8 1.8" /></>,
  mail: <><rect x="3" y="5" width="18" height="14" rx="2.5" /><path d="m4 7 8 6 8-6" /></>,
  users: <><circle cx="9" cy="8" r="3.5" /><path d="M2.5 19.5c1-3.4 3.6-5.2 6.5-5.2s5.5 1.8 6.5 5.2" /><path d="M16 4.8a3.3 3.3 0 0 1 0 6.4M17.6 14.6c2 .7 3.3 2.3 3.9 4.9" /></>,
  shield: <><path d="M12 3 5 6v5.5c0 4.3 2.9 8 7 9.5 4.1-1.5 7-5.2 7-9.5V6l-7-3Z" /><path d="m9 12 2 2 4-4" /></>,
  clock: <><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3 1.8" /></>,
  lock: <><rect x="4.5" y="10.5" width="15" height="10" rx="2.5" /><path d="M8 10.5V7.5a4 4 0 0 1 8 0v3" /></>,
  eye: <><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12Z" /><circle cx="12" cy="12" r="3" /></>,
  eyeOff: <><path d="M3 3l18 18" /><path d="M10.6 5.1A10.9 10.9 0 0 1 12 5c6.4 0 10 7 10 7a17.6 17.6 0 0 1-3.2 4.2" /><path d="M6.6 6.6C3.9 8.4 2 12 2 12s3.6 7 10 7a9.8 9.8 0 0 0 5.4-1.6" /><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2" /></>,
  copy: <><rect x="8" y="8" width="12" height="12" rx="2.5" /><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" /></>,
  refresh: <><path d="M20 7v5h-5" /><path d="M18.2 12A7 7 0 1 1 16 6.6L20 10" /></>,
  link: <><path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1" /><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1" /></>,
  alert: <><circle cx="12" cy="12" r="9" /><path d="M12 7.5v5.5M12 16.5h.01" /></>,
  info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v5.5M12 7.5h.01" /></>,
}

export function UsersIcon({ name, size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {ICON_PATHS[name] || ICON_PATHS.info}
    </svg>
  )
}

export function ProfileBadge({ profile }) {
  const tone = profile ? profile.toLowerCase() : 'none'
  return <span className={`users-profile users-profile--${tone}`}>{profileLabel(profile)}</span>
}

export function StatusBadge({ status }) {
  return (
    <span className={`users-status users-status--${status || 'unknown'}`}>
      <i aria-hidden="true" />
      {statusLabel(status)}
    </span>
  )
}

export function UserAvatar({ name, profile, size = 'md' }) {
  const tone = profile ? profile.toLowerCase() : 'none'
  return (
    <span className={`users-avatar users-avatar--${size} users-avatar--${tone}`} aria-hidden="true">
      {initials(name)}
    </span>
  )
}

/* ── Toast e confirmação (mesmo padrão da Central de Ativos) ─────────── */
export function UsersToast({ toast }) {
  if (!toast) return null
  return (
    <div className={`users-toast users-toast--${toast.kind}`} role={toast.kind === 'error' ? 'alert' : 'status'}>
      <UsersIcon name={toast.kind === 'success' ? 'check' : toast.kind === 'error' ? 'alert' : 'info'} size={16} />
      <span>{toast.message}</span>
    </div>
  )
}

export function ConfirmDialog({ confirm, busy = false }) {
  if (!confirm) return null
  const tone = confirm.tone || 'danger'
  return (
    <div className="users-overlay users-overlay--center" role="presentation">
      <div className="users-confirmation" role="alertdialog" aria-modal="true"
           aria-labelledby="users-confirmation-title" aria-describedby="users-confirmation-message">
        <span className={`users-confirmation__icon users-confirmation__icon--${tone}`} aria-hidden="true">
          <UsersIcon name={confirm.icon || (tone === 'danger' ? 'power' : 'info')} size={20} />
        </span>
        <h2 id="users-confirmation-title">{confirm.title}</h2>
        <p id="users-confirmation-message">{confirm.message}</p>
        <div className="users-dialog-actions">
          <button className="users-button users-button--quiet" type="button" onClick={confirm.onCancel} disabled={busy} autoFocus>
            Cancelar
          </button>
          <button className={`users-button users-button--${tone === 'danger' ? 'danger' : 'primary'}`} type="button"
                  onClick={confirm.onConfirm} disabled={busy}>
            {busy ? 'Aguarde…' : confirm.confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
