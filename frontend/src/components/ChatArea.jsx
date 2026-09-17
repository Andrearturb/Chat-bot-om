import { useEffect, useRef } from 'react'
import assistantImage from '../assets/assistente-obras.jpeg'

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
  const bottomRef = useRef(null)

  useEffect(() => {
    if (!active) return
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [active, messages])

  return (
    <section className={`chat-area ${active ? 'chat-area--active' : ''}`} aria-live="polite">
      <div className="chat-header">
        <img src={assistantImage} alt="" />
        <div><strong>Assistente de Obras &amp; Manutenções</strong><span><i /> Online</span></div>
      </div>
      <div className="messages">
        {messages.map((message) => <Message key={message.id} message={message} />)}
        <div ref={bottomRef} />
      </div>
    </section>
  )
}
