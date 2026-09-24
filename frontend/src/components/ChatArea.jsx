import { useEffect, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { assistantImage } from '../assets/assistantImage'

function Message({ message, suggestions = [] }) {
  const isAssistant = message.role === 'assistant'

  return (
    <article className={`message message--${message.role}`}>
      {isAssistant && <img className="message__avatar" src={assistantImage} alt="" />}
      <div className="message__content">
        {isAssistant ? (
          <div className="message__markdown">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content || ''}</ReactMarkdown>
          </div>
        ) : message.content}
        {isAssistant && suggestions.length > 0 && (
          <div className="message__suggestions" aria-label="Sugestões relacionadas">
            {suggestions.map((suggestion) => (
              <button key={suggestion} type="button">{suggestion}</button>
            ))}
          </div>
        )}
      </div>
    </article>
  )
}

export default function ChatArea({ messages, active, suggestions = [] }) {
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
        <div><strong>Gentileza</strong><span><i /> Assistente de Obras &amp; Manutenções · Online</span></div>
      </div>
      <div className="messages" ref={messagesRef}>
        {messages.map((message) => (
          <Message key={message.id} message={message} suggestions={message.role === 'assistant' ? suggestions : []} />
        ))}
      </div>
    </section>
  )
}
