import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { assistantImage } from '../assets/assistantImage'

function formatSeconds(value) {
  if (!Number.isFinite(value)) return null
  return new Intl.NumberFormat('pt-BR', {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format(Math.max(0, value))
}

function CopyIcon({ copied = false }) {
  if (copied) {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="m5 12 4 4L19 6" />
      </svg>
    )
  }

  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <rect x="9" y="9" width="10" height="10" rx="2" />
      <path d="M15 9V7a2 2 0 0 0-2-2H7a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2" />
    </svg>
  )
}

async function copyText(text) {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text)
      return
    } catch {
      // Usa o fallback abaixo quando a API moderna não estiver disponível no contexto atual.
    }
  }

  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.setAttribute('readonly', '')
  textarea.style.position = 'fixed'
  textarea.style.opacity = '0'
  document.body.appendChild(textarea)
  textarea.select()
  document.execCommand('copy')
  textarea.remove()
}

function Message({ message, suggestions = [] }) {
  const isAssistant = message.role === 'assistant'
  const showActions = isAssistant && !message.isGreeting
  const [copied, setCopied] = useState(false)
  const contentRef = useRef(null)
  const copyResetRef = useRef(null)
  const responseTime = formatSeconds(message.responseTime)

  useEffect(() => () => clearTimeout(copyResetRef.current), [])

  async function handleCopy() {
    const visibleText = contentRef.current?.innerText?.trim()
    const textToCopy = visibleText || message.content || ''

    try {
      await copyText(textToCopy)
      setCopied(true)
      clearTimeout(copyResetRef.current)
      copyResetRef.current = setTimeout(() => setCopied(false), 1600)
    } catch (error) {
      console.error('Não foi possível copiar a resposta:', error)
    }
  }

  return (
    <article className={`message message--${message.role}`}>
      {isAssistant && <img className="message__avatar" src={assistantImage} alt="" />}
      <div className="message__body">
        <div className="message__content">
          {isAssistant ? (
            <div className="message__markdown" ref={contentRef}>
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

        {showActions && (
          <div className="message__actions">
            {responseTime && (
              <span className={`message__response-time ${message.isError ? 'message__response-time--error' : ''}`}>
                {message.isError ? `Falhou em ${responseTime}s` : `Respondido em ${responseTime}s`}
              </span>
            )}
            <button
              className={`message__copy ${copied ? 'message__copy--copied' : ''}`}
              type="button"
              onClick={handleCopy}
              aria-label={copied ? 'Resposta copiada' : 'Copiar resposta'}
              title={copied ? 'Copiado' : 'Copiar'}
            >
              <CopyIcon copied={copied} />
              <span>{copied ? 'Copiado' : 'Copiar'}</span>
            </button>
          </div>
        )}
      </div>
    </article>
  )
}

function ThinkingMessage({ startedAt }) {
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    if (!Number.isFinite(startedAt)) {
      setElapsed(0)
      return undefined
    }

    const updateElapsed = () => {
      setElapsed(Math.max(0, (performance.now() - startedAt) / 1000))
    }

    updateElapsed()
    const interval = setInterval(updateElapsed, 100)
    return () => clearInterval(interval)
  }, [startedAt])

  return (
    <article className="message message--assistant message--thinking" aria-label="Gentileza está processando a resposta">
      <img className="message__avatar" src={assistantImage} alt="" />
      <div className="message__body">
        <div className="message__content message__thinking">
          <span className="thinking-dots" aria-hidden="true"><i /><i /><i /></span>
          <span>Pensando... {formatSeconds(elapsed)}s</span>
        </div>
      </div>
    </article>
  )
}

export default function ChatArea({ messages, active, suggestions = [], loading = false, thinkingStartedAt = null }) {
  const messagesRef = useRef(null)

  useEffect(() => {
    if (!active || !messagesRef.current) return

    const container = messagesRef.current
    container.scrollTo({
      top: container.scrollHeight,
      behavior: 'smooth',
    })
  }, [active, messages, loading])

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
        {loading && <ThinkingMessage startedAt={thinkingStartedAt} />}
      </div>
    </section>
  )
}
