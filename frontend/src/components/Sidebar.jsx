import { assistantImage } from '../assets/assistantImage'

// Inline SVG icon for the Assets section — represents equipment/inventory
function AssetsIcon() {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect x="2" y="7" width="20" height="14" rx="2" />
      <path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2" />
      <line x1="12" y1="12" x2="12" y2="16" />
      <line x1="10" y1="14" x2="14" y2="14" />
    </svg>
  )
}

const navigation = [
  { icon: '⌂',          label: 'Assistente',    section: 'assistant' },
  { icon: '◌',          label: 'Conversas',      section: 'conversations' },
  { icon: '▥',          label: 'Indicadores',    section: 'indicators' },
  { icon: <AssetsIcon />, label: 'Ativos',        section: 'assets' },
  { icon: '⚙',          label: 'Configurações',  section: 'settings' },
]

export default function Sidebar({
  activeSection,
  onNewConversation,
  onOpenConversations,
  onGoAssistant,
  onOpenIndicators,
  onOpenAssets,
  onOpenSettings,
  historyOpen,
  settingsOpen,
}) {
  return (
    <aside className="sidebar">
      <div className="sidebar__avatar" aria-label="Assistente de Obras & Manutenções">
        <img src={assistantImage} alt="" />
      </div>
      <nav className="sidebar__nav" aria-label="Navegação principal">
        {navigation.map(({ icon, label, section }) => {
          const isActive = section === 'settings'
            ? settingsOpen
            : settingsOpen
              ? false
              : section === 'conversations'
                ? historyOpen
                : !historyOpen && activeSection === section

          const onClick = section === 'assistant'
            ? onGoAssistant
            : section === 'conversations'
              ? onOpenConversations
              : section === 'indicators'
                ? onOpenIndicators
                : section === 'assets'
                  ? onOpenAssets
                  : section === 'settings'
                    ? onOpenSettings
                    : undefined

          return (
            <button
              className={`nav-button ${isActive ? 'nav-button--active' : ''}`}
              key={label}
              type="button"
              title={label}
              aria-label={label}
              aria-current={isActive ? 'page' : undefined}
              data-history-toggle={section === 'conversations' ? 'true' : undefined}
              onClick={onClick}
            >
              <span aria-hidden="true">{icon}</span>
              <small>{label}</small>
            </button>
          )
        })}
      </nav>
      <div className="sidebar__brand">
        <strong>Gentil</strong>
        <strong>Negócios</strong>
        <small><i /> Obras &amp; Manutenções</small>
      </div>
      <button
        className="nav-button nav-button--new"
        type="button"
        onClick={onNewConversation}
        title="Nova conversa"
        aria-label="Nova conversa"
      >
        <span aria-hidden="true">＋</span>
        <small>Nova</small>
      </button>
    </aside>
  )
}
