import { useEffect, useRef, useState } from 'react'
import './App.css'
import ChatArea from './components/ChatArea'
import ChatComposer from './components/ChatComposer'
import HeroAssistant from './components/HeroAssistant'
import Sidebar from './components/Sidebar'
import SuggestionChips from './components/SuggestionChips'

const WEBHOOK_URL = 'http://localhost:5678/webhook/9db5ead4-d4ca-4f5c-a1b4-3969e60cb8df/chat'
const CONVERSATION_KEY = 'gentil-obras-current-conversation-v1'
const LEGACY_SESSION_KEY = 'gentil-obras-session-id'

function newSessionId() {
  return crypto.randomUUID()
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

function loadConversation() {
  try {
    const raw = localStorage.getItem(CONVERSATION_KEY)

    if (raw) {
      const parsed = JSON.parse(raw)
      const valid = (
        parsed &&
        parsed.version === 1 &&
        typeof parsed.sessionId === 'string' &&
        parsed.sessionId.trim() !== '' &&
        Array.isArray(parsed.messages) &&
        parsed.messages.every(isValidMessage)
      )

      if (valid) {
        return {
          sessionId: parsed.sessionId,
          messages: parsed.messages,
        }
      }
    }
  } catch (error) {
    console.warn('Não foi possível restaurar a conversa:', error)
  }

  return {
    sessionId: newSessionId(),
    messages: [],
  }
}

function extractResponse(data) {
  if (typeof data === 'string') return data
  if (Array.isArray(data)) return extractResponse(data[0])
  return data?.output || data?.text || data?.response || data?.message || JSON.stringify(data)
}

function App() {
  const [initialConversation] = useState(() => loadConversation())
  const [sessionId, setSessionId] = useState(initialConversation.sessionId)
  const [messages, setMessages] = useState(initialConversation.messages)
  const [prompt, setPrompt] = useState('')
  const [loading, setLoading] = useState(false)
  const requestControllerRef = useRef(null)
  const active = messages.length > 0

  useEffect(() => {
    document.querySelector('.app-shell')?.scrollTo(0, 0)
  }, [])

  useEffect(() => {
    try {
      localStorage.setItem(
        CONVERSATION_KEY,
        JSON.stringify({
          version: 1,
          sessionId,
          messages,
        }),
      )
      localStorage.removeItem(LEGACY_SESSION_KEY)
    } catch (error) {
      console.warn('Não foi possível salvar a conversa:', error)
    }
  }, [sessionId, messages])

  function resetConversation() {
    requestControllerRef.current?.abort()
    requestControllerRef.current = null
    setLoading(false)

    const nextSessionId = newSessionId()
    setSessionId(nextSessionId)
    setMessages([])
    setPrompt('')
  }

  async function sendMessage(event, selectedPrompt = prompt) {
    event?.preventDefault()
    const content = selectedPrompt.trim()
    if (!content || loading) return

    setMessages((current) => [...current, { id: `${Date.now()}-user`, role: 'user', content }])
    setPrompt('')
    setLoading(true)

    const controller = new AbortController()
    requestControllerRef.current = controller

    try {
      const response = await fetch(WEBHOOK_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
        body: JSON.stringify({ action: 'sendMessage', sessionId, chatInput: content }),
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      if (requestControllerRef.current !== controller) return
      setMessages((current) => [...current, { id: `${Date.now()}-assistant`, role: 'assistant', content: extractResponse(data) }])
    } catch (error) {
      if (error.name === 'AbortError' || requestControllerRef.current !== controller) return
      setMessages((current) => [...current, { id: `${Date.now()}-error`, role: 'assistant', content: 'Não consegui conectar ao assistente agora. Verifique se o n8n está disponível e tente novamente.' }])
      console.error('Falha ao enviar mensagem para o n8n:', error)
    } finally {
      if (requestControllerRef.current === controller) {
        requestControllerRef.current = null
        setLoading(false)
      }
    }
  }

  return (
    <main className="app-shell">
      <div className="ambient-glow ambient-glow--blue" />
      <div className="ambient-glow ambient-glow--yellow" />
      <div className="app-panel">
        <Sidebar onNewConversation={resetConversation} />
        <div className={`workspace ${active ? 'workspace--active' : ''}`}>
          <header className="workspace-header">
            <div className="workspace-title"><span className="header-accent" /> Gentil Negócios <span>· Obras &amp; Manutenções</span></div>
            <div className="header-greeting"><span className="header-greeting__icon">♧</span><span><strong>Bom dia!</strong><small>Vamos construir resultados.</small></span></div>
            {active && <button className="new-conversation" type="button" onClick={resetConversation}>+ Nova conversa</button>}
          </header>
          <HeroAssistant active={active} />
          <ChatArea messages={messages} active={active} />
          <div className="interaction-zone">
            {!active && <SuggestionChips onSelect={(selectedPrompt) => sendMessage(null, selectedPrompt)} active={active} />}
            <ChatComposer value={prompt} onChange={setPrompt} onSubmit={sendMessage} loading={loading} />
          </div>
        </div>
      </div>
    </main>
  )
}

export default App
