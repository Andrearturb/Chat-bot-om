import { useEffect, useRef, useState } from 'react'
import './App.css'
import ChatArea from './components/ChatArea'
import ChatComposer from './components/ChatComposer'
import ConversationHistory from './components/ConversationHistory'
import HeroAssistant from './components/HeroAssistant'
import Sidebar from './components/Sidebar'
import SuggestionChips from './components/SuggestionChips'
import IndicatorsPage from './features/indicators/IndicatorsPage'

const WEBHOOK_URL = import.meta.env.VITE_N8N_WEBHOOK_URL?.trim()
const BACKEND_URL = import.meta.env.VITE_BACKEND_URL?.trim()?.replace(/\/$/, '')
const HEALTH_URL = BACKEND_URL ? `${BACKEND_URL}/health` : null
const CONVERSATIONS_KEY = 'gentil-obras-conversations-v2'
const CURRENT_CONVERSATION_KEY = 'gentil-obras-current-conversation-v1'
const LEGACY_SESSION_KEY = 'gentil-obras-session-id'
const GENTILEZA_GREETING = 'Olá! Eu me chamo Gentileza 👋 Como posso te ajudar com Obras & Manutenções hoje?'

function newSessionId() {
  return crypto.randomUUID()
}

function createDraftConversation({ withGreeting = false } = {}) {
  return {
    id: crypto.randomUUID(),
    sessionId: newSessionId(),
    messages: withGreeting
      ? [{ id: crypto.randomUUID(), role: 'assistant', content: GENTILEZA_GREETING, isGreeting: true }]
      : [],
  }
}

function isValidMessage(message) {
  return (
    message &&
    typeof message === 'object' &&
    typeof message.id === 'string' &&
    (message.role === 'user' || message.role === 'assistant') &&
    typeof message.content === 'string'
  )
}

function isValidConversation(conversation) {
  return (
    conversation &&
    typeof conversation === 'object' &&
    typeof conversation.id === 'string' &&
    conversation.id.trim() !== '' &&
    typeof conversation.sessionId === 'string' &&
    conversation.sessionId.trim() !== '' &&
    typeof conversation.title === 'string' &&
    typeof conversation.createdAt === 'string' &&
    typeof conversation.updatedAt === 'string' &&
    Array.isArray(conversation.messages) &&
    conversation.messages.every(isValidMessage)
  )
}

function createTitleFromMessage(content) {
  const normalized = content.replace(/\s+/g, ' ').trim()
  if (!normalized) return 'Nova conversa'
  if (normalized.length <= 48) return normalized
  return `${normalized.slice(0, 45)}...`
}

function validStore(parsed) {
  return (
    parsed &&
    parsed.version === 2 &&
    (parsed.activeConversationId === null || typeof parsed.activeConversationId === 'string') &&
    Array.isArray(parsed.conversations) &&
    parsed.conversations.every(isValidConversation) &&
    parsed.activeConversationId === null || parsed.conversations.some((conversation) => conversation.id === parsed.activeConversationId)
  )
}

function loadConversationStore() {
  try {
    const storedV2 = localStorage.getItem(CONVERSATIONS_KEY)
    if (storedV2) {
      const parsed = JSON.parse(storedV2)
      if (validStore(parsed)) {
        const conversations = parsed.conversations.filter((conversation) => conversation.messages.length > 0)
        const mostRecentConversation = [...conversations].sort((a, b) => new Date(b.updatedAt) - new Date(a.updatedAt))[0]
        let activeConversationId
        if (parsed.activeConversationId === null) {
          activeConversationId = null
        } else if (conversations.some((conversation) => conversation.id === parsed.activeConversationId)) {
          activeConversationId = parsed.activeConversationId
        } else {
          activeConversationId = mostRecentConversation?.id || null
        }
        return { version: 2, activeConversationId, conversations }
      }
    }

    const storedV1 = localStorage.getItem(CURRENT_CONVERSATION_KEY)
    if (storedV1) {
      const parsed = JSON.parse(storedV1)
      const validV1 = (
        parsed &&
        parsed.version === 1 &&
        typeof parsed.sessionId === 'string' &&
        parsed.sessionId.trim() !== '' &&
        Array.isArray(parsed.messages) &&
        parsed.messages.every(isValidMessage)
      )

      if (validV1) {
        const now = new Date().toISOString()
        const migrated = {
          id: crypto.randomUUID(),
          sessionId: parsed.sessionId,
          title: parsed.messages.find((message) => message.role === 'user')?.content
            ? createTitleFromMessage(parsed.messages.find((message) => message.role === 'user').content)
            : 'Nova conversa',
          createdAt: now,
          updatedAt: now,
          messages: parsed.messages,
        }
        if (migrated.messages.length > 0) {
          return { version: 2, activeConversationId: migrated.id, conversations: [migrated] }
        }
      }
    }
  } catch (error) {
    console.warn('Não foi possível restaurar o histórico de conversas:', error)
  }

  return { version: 2, activeConversationId: null, conversations: [] }
}

function extractResponse(data) {
  if (typeof data === 'string') return data
  if (Array.isArray(data)) return extractResponse(data[0])
  return data?.output || data?.text || data?.response || data?.message || JSON.stringify(data)
}

function App() {
  const [conversationStore, setConversationStore] = useState(() => loadConversationStore())
  const [draftConversation, setDraftConversation] = useState(() => createDraftConversation())
  const [prompt, setPrompt] = useState('')
  const [loading, setLoading] = useState(false)
  const [thinkingStartedAt, setThinkingStartedAt] = useState(null)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [serviceStatus, setServiceStatus] = useState('checking')
  const [activeSection, setActiveSection] = useState('assistant')
  const requestControllerRef = useRef(null)

  const { conversations, activeConversationId } = conversationStore
  const activeConversation = conversations.find((conversation) => conversation.id === activeConversationId) || draftConversation
  const messages = activeConversation?.messages ?? []
  const active = messages.length > 0

  useEffect(() => {
    document.querySelector('.app-shell')?.scrollTo(0, 0)
  }, [])

  useEffect(() => {
    let cancelled = false

    async function checkSystemHealth({ initial = false } = {}) {
      if (!HEALTH_URL) {
        if (!cancelled) setServiceStatus('error')
        console.error('VITE_BACKEND_URL não configurada')
        return
      }

      if (initial && !cancelled) setServiceStatus('checking')

      try {
        const response = await fetch(HEALTH_URL, {
          method: 'GET',
          headers: { Accept: 'application/json' },
          cache: 'no-store',
        })

        if (cancelled) return
        setServiceStatus(response.ok ? 'online' : 'error')
      } catch (error) {
        if (cancelled) return
        setServiceStatus('offline')
        console.warn('Não foi possível verificar a saúde do Gentileza:', error)
      }
    }

    checkSystemHealth({ initial: true })
    const interval = window.setInterval(() => checkSystemHealth(), 30000)

    return () => {
      cancelled = true
      window.clearInterval(interval)
    }
  }, [])

  useEffect(() => {
    try {
      localStorage.setItem(CONVERSATIONS_KEY, JSON.stringify(conversationStore))
      localStorage.removeItem(CURRENT_CONVERSATION_KEY)
      localStorage.removeItem(LEGACY_SESSION_KEY)
    } catch (error) {
      console.warn('Não foi possível salvar o histórico de conversas:', error)
    }
  }, [conversationStore])

  function updateConversation(conversationId, updater) {
    setConversationStore((current) => ({
      ...current,
      conversations: current.conversations.map((conversation) => (
        conversation.id === conversationId ? updater(conversation) : conversation
      )),
    }))
  }

  function abortCurrentRequest() {
    requestControllerRef.current?.controller?.abort()
    requestControllerRef.current = null
    setLoading(false)
    setThinkingStartedAt(null)
  }

  function createNewConversation() {
    abortCurrentRequest()
    setDraftConversation(createDraftConversation({ withGreeting: true }))
    setConversationStore((current) => ({
      ...current,
      activeConversationId: null,
    }))
    setPrompt('')
    setHistoryOpen(false)
    setActiveSection('assistant')
  }

  function goToAssistant() {
    setHistoryOpen(false)
    setActiveSection('assistant')
  }

  function openIndicators() {
    setHistoryOpen(false)
    setActiveSection('indicators')
  }

  function selectConversation(conversationId) {
    abortCurrentRequest()
    setPrompt('')
    setDraftConversation(createDraftConversation())
    setConversationStore((current) => ({ ...current, activeConversationId: conversationId }))
    setHistoryOpen(false)
    setActiveSection('assistant')
  }

  function deleteConversation(conversationId) {
    const isDeletingActive = conversationId === activeConversationId
    if (isDeletingActive) abortCurrentRequest()

    setConversationStore((current) => {
      const remaining = current.conversations.filter((conversation) => conversation.id !== conversationId)
      if (remaining.length > 0) {
        const mostRecentConversation = [...remaining].sort((a, b) => new Date(b.updatedAt) - new Date(a.updatedAt))[0]
        return {
          ...current,
          activeConversationId: isDeletingActive ? mostRecentConversation.id : current.activeConversationId,
          conversations: remaining,
        }
      }

      return { ...current, activeConversationId: null, conversations: [] }
    })
    setPrompt('')
    setLoading(false)
  }

  async function sendMessage(event, selectedPrompt = prompt) {
    event?.preventDefault()
    const content = selectedPrompt.trim()
    if (!content || loading || !activeConversation) return

    const conversationIdAtSend = activeConversation.id
    const sessionIdAtSend = activeConversation.sessionId
    const now = new Date().toISOString()
    const userMessage = { id: `${Date.now()}-user`, role: 'user', content }

    if (activeConversationId === null) {
      const conversation = {
        id: draftConversation.id,
        sessionId: draftConversation.sessionId,
        title: createTitleFromMessage(content),
        createdAt: now,
        updatedAt: now,
        messages: [...draftConversation.messages, userMessage],
      }
      setConversationStore((current) => ({
        ...current,
        activeConversationId: conversation.id,
        conversations: [conversation, ...current.conversations],
      }))
    } else {
      updateConversation(conversationIdAtSend, (conversation) => ({
        ...conversation,
        updatedAt: now,
        messages: [...conversation.messages, userMessage],
      }))
    }
    setPrompt('')
    setLoading(true)
    const startedAt = performance.now()
    setThinkingStartedAt(startedAt)

    const controller = new AbortController()
    requestControllerRef.current = { controller, conversationId: conversationIdAtSend }

    try {
      if (!WEBHOOK_URL) {
        const configurationError = new Error('VITE_N8N_WEBHOOK_URL não configurada')
        configurationError.kind = 'service'
        throw configurationError
      }

      const response = await fetch(WEBHOOK_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
        body: JSON.stringify({ action: 'sendMessage', sessionId: sessionIdAtSend, chatInput: content }),
      })

      if (!response.ok) {
        setServiceStatus('error')
        const serviceError = new Error(`HTTP ${response.status}`)
        serviceError.kind = 'service'
        throw serviceError
      }

      setServiceStatus('online')

      const data = await response.json()
      if (requestControllerRef.current?.controller !== controller) return

      updateConversation(conversationIdAtSend, (conversation) => ({
        ...conversation,
        updatedAt: new Date().toISOString(),
        messages: [...conversation.messages, {
          id: `${Date.now()}-assistant`,
          role: 'assistant',
          content: extractResponse(data),
          responseTime: Math.max(0, (performance.now() - startedAt) / 1000),
        }],
      }))
    } catch (error) {
      if (error.name === 'AbortError' || requestControllerRef.current?.controller !== controller) return

      const isServiceError = error.kind === 'service'
      setServiceStatus(isServiceError ? 'error' : 'offline')

      const errorMessage = isServiceError
        ? 'O Gentileza está acessível, mas ocorreu um erro ao processar esta solicitação. Tente novamente em instantes.'
        : 'Não consegui alcançar o serviço do Gentileza agora. Verifique a conexão ou a disponibilidade do n8n e tente novamente.'

      updateConversation(conversationIdAtSend, (conversation) => ({
        ...conversation,
        updatedAt: new Date().toISOString(),
        messages: [...conversation.messages, {
          id: `${Date.now()}-error`,
          role: 'assistant',
          content: errorMessage,
          responseTime: Math.max(0, (performance.now() - startedAt) / 1000),
          isError: true,
        }],
      }))
      console.error('Falha ao enviar mensagem para o n8n:', error)
    } finally {
      if (requestControllerRef.current?.controller === controller) {
        requestControllerRef.current = null
        setLoading(false)
        setThinkingStartedAt(null)
      }
    }
  }

  return (
    <main className="app-shell">
      <div className="ambient-glow ambient-glow--blue" />
      <div className="ambient-glow ambient-glow--yellow" />
      <div className="app-panel">
        <Sidebar
          activeSection={activeSection}
          onNewConversation={createNewConversation}
          onOpenConversations={() => setHistoryOpen((current) => !current)}
          onGoAssistant={goToAssistant}
          onOpenIndicators={openIndicators}
          historyOpen={historyOpen}
        />
        {historyOpen && (
          <ConversationHistory
            conversations={conversations}
            activeConversationId={activeConversationId}
            onSelect={selectConversation}
            onNewConversation={createNewConversation}
            onDelete={deleteConversation}
            onClose={() => setHistoryOpen(false)}
          />
        )}
        <div className={`workspace ${activeSection === 'assistant' && active ? 'workspace--active' : ''} ${activeSection === 'indicators' ? 'workspace--indicators' : ''}`}>
          <header className="workspace-header">
            <div className="workspace-title"><span className="header-accent" /> Gentil Negócios <span>· Obras &amp; Manutenções</span></div>
            <div className="header-greeting"><span className="header-greeting__icon">♧</span><span><strong>Bom dia!</strong><small>Vamos construir resultados.</small></span></div>
            {(active || activeSection === 'indicators') && <button className="new-conversation" type="button" onClick={createNewConversation}>+ Nova conversa</button>}
          </header>

          {activeSection === 'assistant' ? (
            <>
              <HeroAssistant active={active} />
              <ChatArea
                messages={messages}
                active={active}
                loading={loading}
                thinkingStartedAt={thinkingStartedAt}
                serviceStatus={serviceStatus}
              />
              <div className="interaction-zone">
                {!active && <SuggestionChips onSelect={(selectedPrompt) => sendMessage(null, selectedPrompt)} active={active} />}
                <ChatComposer value={prompt} onChange={setPrompt} onSubmit={sendMessage} loading={loading} />
              </div>
            </>
          ) : (
            <IndicatorsPage />
          )}
        </div>
      </div>
    </main>
  )
}

export default App
