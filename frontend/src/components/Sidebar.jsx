import { assistantImage } from '../assets/assistantImage'

const navigation = [
  ['⌂', 'Assistente'],
  ['◌', 'Conversas'],
  ['▥', 'Indicadores'],
  ['⚙', 'Configurações'],
]

export default function Sidebar({ onNewConversation, onOpenConversations, onCloseConversations, historyOpen }) {
  return (
    <aside className="sidebar">
      <div className="sidebar__avatar" aria-label="Assistente de Obras & Manutenções">
        <img src={assistantImage} alt="" />
      </div>
      <nav className="sidebar__nav" aria-label="Navegação principal">
        {navigation.map(([icon, label], index) => {
          const isActive = index === 0 ? !historyOpen : index === 1 ? historyOpen : false
          const onClick = index === 0 ? onCloseConversations : index === 1 ? onOpenConversations : undefined

          return (
          <button className={`nav-button ${isActive ? 'nav-button--active' : ''}`} key={label} type="button" title={label} aria-label={label} aria-current={isActive ? 'page' : undefined} onClick={onClick}>
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
