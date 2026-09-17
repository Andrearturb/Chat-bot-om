import { useEffect, useRef } from 'react'
import { assistantImage } from '../assets/assistantImage'

function formatMarkdown(content) {
  const escaped = content
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')

  return escaped
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`(.+?)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br />')
}

function Message({ message }) {
  return (
    <article className={`message message--${message.role}`}>
      {message.role === 'assistant' && <img className="message__avatar" src={assistantImage} alt="" />}
      <div className="message__content" dangerouslySetInnerHTML={{ __html: formatMarkdown(message.content) }} />
    </article>
  )
}

export default function ChatArea({ messages, active }) {
  const messagesRef = useRef(null)

  useEffect(() => {
    if (!active || !messagesRef.current) return

    const container = messagesRef.current
    container.scrollTo({
      top: container.scrollHeight,
      behavior: 'smooth',
    })
  }, [active, messages])

  return (
    <section className={`chat-area ${active ? 'chat-area--active' : ''}`} aria-live="polite">
      <div className="chat-header">
        <img src={assistantImage} alt="" />
        <div><strong>Assistente de Obras &amp; Manutenções</strong><span><i /> Online</span></div>
      </div>
      <div className="messages" ref={messagesRef}>
        {messages.map((message) => <Message key={message.id} message={message} />)}
      </div>
    </section>
  )
}
