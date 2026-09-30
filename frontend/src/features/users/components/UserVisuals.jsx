import { initials, profileLabel } from '../userUtils.js'

const ICON_PATHS = {
  search: <><circle cx="11" cy="11" r="7" /><path d="m20 20-3.6-3.6" /></>,
  users: <><circle cx="9" cy="8" r="3.5" /><path d="M2.5 19.5c1-3.4 3.6-5.2 6.5-5.2s5.5 1.8 6.5 5.2" /><path d="M16 4.8a3.3 3.3 0 0 1 0 6.4M17.6 14.6c2 .7 3.3 2.3 3.9 4.9" /></>,
  shield: <><path d="M12 3 5 6v5.5c0 4.3 2.9 8 7 9.5 4.1-1.5 7-5.2 7-9.5V6l-7-3Z" /><path d="m9 12 2 2 4-4" /></>,
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

export function SessionBadge({ active }) {
  return (
    <span className={`users-status users-status--${active ? 'active' : 'idle'}`}>
      <i aria-hidden="true" />
      {active ? 'Sessão ativa' : 'Sem sessão'}
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
