import { useEffect, useState } from 'react'
import './App.css'
import ChatArea from './components/ChatArea'
import ChatComposer from './components/ChatComposer'
import HeroAssistant from './components/HeroAssistant'
import Sidebar from './components/Sidebar'
import SuggestionChips from './components/SuggestionChips'

const WEBHOOK_URL = 'http://localhost:5678/webhook/9db5ead4-d4ca-4f5c-a1b4-3969e60cb8df/chat'
const SESSION_KEY = 'gentil-obras-session-id'

function newSessionId() {
  return crypto.randomUUID()
}

function getSessionId() {
  const stored = localStorage.getItem(SESSION_KEY)
  if (stored) return stored
  const sessionId = newSessionId()
  localStorage.setItem(SESSION_KEY, sessionId)
  return sessionId
}

function extractResponse(data) {
  if (typeof data === 'string') return data
  if (Array.isArray(data)) return extractResponse(data[0])
  return data?.output || data?.text || data?.response || data?.message || JSON.stringify(data)
}

function App() {
  const [sessionId, setSessionId] = useState(getSessionId)
  const [messages, setMessages] = useState([])
  const [prompt, setPrompt] = useState('')
  const [loading, setLoading] = useState(false)
  const active = messages.length > 0

  useEffect(() => {
    document.querySelector('.app-shell')?.scrollTo(0, 0)
  }, [])

  function resetConversation() {
    const nextSessionId = newSessionId()
    localStorage.setItem(SESSION_KEY, nextSessionId)
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

    try {
      const response = await fetch(WEBHOOK_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'sendMessage', sessionId, chatInput: content }),
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      setMessages((current) => [...current, { id: `${Date.now()}-assistant`, role: 'assistant', content: extractResponse(data) }])
    } catch (error) {
      setMessages((current) => [...current, { id: `${Date.now()}-error`, role: 'assistant', content: 'Não consegui conectar ao assistente agora. Verifique se o n8n está disponível e tente novamente.' }])
      console.error('Falha ao enviar mensagem para o n8n:', error)
    } finally {
      setLoading(false)
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
            <SuggestionChips onSelect={(selectedPrompt) => sendMessage(null, selectedPrompt)} active={active} />
            <ChatComposer value={prompt} onChange={setPrompt} onSubmit={sendMessage} loading={loading} />
          </div>
        </div>
      </div>
    </main>
  )
}

export default App
