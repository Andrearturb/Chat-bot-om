function formatConversationDate(value) {
  const date = new Date(value)
  const today = new Date()
  const isToday = date.toDateString() === today.toDateString()

  if (isToday) {
    return `Hoje · ${date.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}`
  }

  return date.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })
    + ` · ${date.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}`
}

function ConversationItem({ conversation, active, onSelect, onDelete }) {
  function handleDelete(event) {
    event.stopPropagation()
    if (window.confirm('Excluir esta conversa?')) onDelete(conversation.id)
  }

  return (
    <div className={`conversation-item ${active ? 'conversation-item--active' : ''}`}>
      <button
        className="conversation-item__select"
        type="button"
        onClick={() => onSelect(conversation.id)}
        aria-current={active ? 'page' : undefined}
        title={conversation.title}
      >
        <strong>{conversation.title}</strong>
        <small>{formatConversationDate(conversation.updatedAt)} · {conversation.messages.length} mensagens</small>
      </button>
      <button className="conversation-item__delete" type="button" onClick={handleDelete} aria-label="Excluir conversa" title="Excluir conversa">×</button>
    </div>
  )
}

export default function ConversationHistory({ conversations, activeConversationId, onSelect, onNewConversation, onDelete, onClose }) {
  const ordered = [...conversations].sort((a, b) => new Date(b.updatedAt) - new Date(a.updatedAt))
  const today = new Date().toDateString()
  const todayConversations = ordered.filter((conversation) => new Date(conversation.updatedAt).toDateString() === today)
  const previousConversations = ordered.filter((conversation) => new Date(conversation.updatedAt).toDateString() !== today)

  function renderGroup(label, items) {
    if (items.length === 0) return null
    return (
      <section className="conversation-history__group">
        <h3>{label}</h3>
        {items.map((conversation) => (
          <ConversationItem
            key={conversation.id}
            conversation={conversation}
            active={conversation.id === activeConversationId}
            onSelect={onSelect}
            onDelete={onDelete}
          />
        ))}
      </section>
    )
  }

  return (
    <aside className="conversation-history" aria-label="Histórico de conversas">
      <div className="conversation-history__header">
        <div><span className="history-kicker">HISTÓRICO</span><h2>Conversas</h2></div>
        <button className="history-close" type="button" onClick={onClose} aria-label="Fechar histórico" title="Fechar histórico">×</button>
      </div>
      <button className="history-new" type="button" onClick={onNewConversation}><span>＋</span> Nova conversa</button>
      <div className="conversation-history__list">
        {renderGroup('Hoje', todayConversations)}
        {renderGroup('Anteriores', previousConversations)}
      </div>
    </aside>
  )
}
