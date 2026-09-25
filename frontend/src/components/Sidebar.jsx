import { assistantImage } from '../assets/assistantImage'

const navigation = [
  ['⌂', 'Assistente', 'assistant'],
  ['◌', 'Conversas', 'conversations'],
  ['▥', 'Indicadores', 'indicators'],
  ['⚙', 'Configurações', 'settings'],
]

export default function Sidebar({
  activeSection,
  onNewConversation,
  onOpenConversations,
  onGoAssistant,
  onOpenIndicators,
  historyOpen,
}) {
  return (
    <aside className="sidebar">
      <div className="sidebar__avatar" aria-label="Assistente de Obras & Manutenções">
        <img src={assistantImage} alt="" />
      </div>
      <nav className="sidebar__nav" aria-label="Navegação principal">
        {navigation.map(([icon, label, section]) => {
          const isActive = section === 'conversations'
            ? historyOpen
            : !historyOpen && activeSection === section

          const onClick = section === 'assistant'
            ? onGoAssistant
            : section === 'conversations'
              ? onOpenConversations
              : section === 'indicators'
                ? onOpenIndicators
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
      <div className="sidebar__brand"><strong>Gentil</strong><strong>Negócios</strong><small><i /> Obras &amp; Manutenções</small></div>
      <button className="nav-button nav-button--new" type="button" onClick={onNewConversation} title="Nova conversa" aria-label="Nova conversa"><span aria-hidden="true">＋</span><small>Nova</small></button>
    </aside>
  )
}
