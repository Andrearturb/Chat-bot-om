import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import './App.css'
import ChatArea from './components/ChatArea'
import ChatComposer from './components/ChatComposer'
import ConversationHistory from './components/ConversationHistory'
import HeroAssistant from './components/HeroAssistant'
import Sidebar from './components/Sidebar'
import SuggestionChips from './components/SuggestionChips'
import IndicatorsPage from './features/indicators/IndicatorsPage'
import AssetsPage from './features/assets/AssetsPage'
import SettingsModal from './features/settings/SettingsModal'

import { AuthProvider, useAuth } from './features/auth/AuthProvider.jsx'
import LoginScreen from './features/auth/LoginScreen.jsx'
import AccessPending from './features/auth/AccessPending.jsx'
import AccessDenied from './features/auth/AccessDenied.jsx'
import UserMenu from './features/auth/UserMenu.jsx'
import { api } from './lib/apiClient.js'

const UsersModal = lazy(() => import('./features/users/UsersModal.jsx'))
const AuditModal = lazy(() => import('./features/audit/AuditModal.jsx'))

// ── Preferências de navegação (sessionStorage — não sensível) ──────────────────
const NAV_KEY = 'gentileza-navigation-v1'
const VALID_SECTIONS = new Set(['assistant', 'indicators', 'assets'])
const VALID_INDICATORS = new Set(['home', 'performance', 'corrective', 'preventive', 'financial'])
const GREETING_CONTENT = 'Olá! Eu me chamo Gentileza 👋 Como posso te ajudar com Obras & Manutenções hoje?'

function loadNav() {
  const fallback = { activeSection: 'assistant', activeIndicator: 'home', historyOpen: false }
  try {
    const s = sessionStorage.getItem(NAV_KEY)
    if (!s) return fallback
    const p = JSON.parse(s)
    return {
      activeSection: VALID_SECTIONS.has(p.activeSection) ? p.activeSection : fallback.activeSection,
      activeIndicator: VALID_INDICATORS.has(p.activeIndicator) ? p.activeIndicator : fallback.activeIndicator,
      historyOpen: typeof p.historyOpen === 'boolean' ? p.historyOpen : fallback.historyOpen,
    }
  } catch { return fallback }
}

function greetingMsg() {
  return { id: `${Date.now()}-greeting`, role: 'assistant', content: GREETING_CONTENT, isGreeting: true }
}

// ── Componente principal (dentro do AuthProvider) ─────────────────────────────
function AppShell() {
  const { auth_status, user, hasPermission, auth_error } = useAuth()

  const [nav] = useState(() => loadNav())
  const [activeSection, setActiveSection] = useState(nav.activeSection)
  const [activeIndicator, setActiveIndicator] = useState(nav.activeIndicator)
  const [historyOpen, setHistoryOpen] = useState(nav.historyOpen)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [usersOpen, setUsersOpen] = useState(false)
  const [auditOpen, setAuditOpen] = useState(false)
  const [prompt, setPrompt] = useState('')
  const [loading, setLoading] = useState(false)
  const [thinkingStartedAt, setThinkingStartedAt] = useState(null)
  const [serviceStatus, setServiceStatus] = useState('checking')

  // Conversas no PostgreSQL (não localStorage)
  const [conversations, setConversations] = useState([])
  const [activeConversationId, setActiveConversationId] = useState(null)
  const [messages, setMessages] = useState([greetingMsg()])
  const abortRef = useRef(null)

  const active = messages.some(m => !m.isGreeting)

  // ── Health check ──────────────────────────────────────────────────────────────
  useEffect(() => {
    if (auth_status !== 'authenticated') return
    let cancelled = false

    async function check(initial = false) {
      if (initial && !cancelled) setServiceStatus('checking')
      try {
        await api.get('/health/live', { cache: 'no-store' })
        if (!cancelled) setServiceStatus('online')
      } catch {
        if (!cancelled) setServiceStatus('offline')
      }
    }

    check(true)
    const id = setInterval(check, 30_000)
    return () => { cancelled = true; clearInterval(id) }
  }, [auth_status])

  // ── Carrega lista de conversas ────────────────────────────────────────────────
  const loadConversations = useCallback(async () => {
    if (!hasPermission('assistant.history')) return
    try {
      const list = await api.get('/assistant/conversations')
      setConversations(list || [])
    } catch { /* silencia */ }
  }, [hasPermission])

  useEffect(() => {
    if (auth_status === 'authenticated') loadConversations()
  }, [auth_status, loadConversations])

  // ── Persiste preferências de navegação ────────────────────────────────────────
  useEffect(() => {
    try { sessionStorage.setItem(NAV_KEY, JSON.stringify({ activeSection, activeIndicator, historyOpen })) }
    catch { /* ignora */ }
  }, [activeSection, activeIndicator, historyOpen])

  // ── Navegação ─────────────────────────────────────────────────────────────────
  function abortRequest() {
    abortRef.current?.abort(); abortRef.current = null
    setLoading(false); setThinkingStartedAt(null)
  }

  function createNewConversation() {
    abortRequest()
    setActiveConversationId(null); setMessages([greetingMsg()])
    setPrompt(''); setHistoryOpen(false); setActiveSection('assistant')
  }

  async function selectConversation(id) {
    abortRequest(); setPrompt(''); setHistoryOpen(false); setActiveSection('assistant')
    setActiveConversationId(id)
    try {
      const conv = await api.get(`/assistant/conversations/${id}`)
      setMessages(conv.messages.map(m => ({ id: m.id, role: m.role, content: m.content, responseTime: m.response_time })))
    } catch {
      setMessages([{ id: 'err', role: 'assistant', content: 'Não foi possível carregar esta conversa.', isError: true }])
    }
  }

  async function deleteConversation(id) {
    try {
      await api.delete(`/assistant/conversations/${id}`)
      setConversations(prev => prev.filter(c => c.id !== id))
      if (activeConversationId === id) createNewConversation()
    } catch { /* silencia */ }
  }

  // ── Envio de mensagem ─────────────────────────────────────────────────────────
  async function sendMessage(event, selectedPrompt = prompt) {
    event?.preventDefault()
    const content = selectedPrompt.trim()
    if (!content || loading) return

    const userMsg = { id: `${Date.now()}-user`, role: 'user', content }
    setMessages(prev => [...prev.filter(m => !m.isGreeting), userMsg])
    setPrompt(''); setLoading(true)
    const startedAt = performance.now()
    setThinkingStartedAt(startedAt)

    const ctrl = new AbortController()
    abortRef.current = ctrl

    try {
      const result = await api.post('/assistant/chat',
        { message: content, conversation_id: activeConversationId || null },
        { signal: ctrl.signal })

      if (ctrl.signal.aborted) return
      setServiceStatus('online')
      setActiveConversationId(result.conversation_id)
      setMessages(prev => [...prev, {
        id: result.message.id, role: 'assistant', content: result.message.content,
        responseTime: result.message.response_time,
      }])
      loadConversations()
    } catch (error) {
      if (error?.name === 'AbortError' || ctrl.signal.aborted) return
      const is429 = error?.status === 429
      setServiceStatus(is429 ? 'online' : 'error')
      const msg = is429
        ? (error?.detail?.message || 'Limite do assistente atingido. Aguarde um momento.')
        : error?.status === 403 ? 'Sem permissão para usar o assistente.'
        : 'Não consegui alcançar o Gentileza agora. Verifique a conexão e tente novamente.'
      setMessages(prev => [...prev, {
        id: `${Date.now()}-err`, role: 'assistant', content: msg,
        responseTime: Math.max(0, (performance.now() - startedAt) / 1000), isError: true,
      }])
    } finally {
      if (!ctrl.signal.aborted) {
        abortRef.current = null; setLoading(false); setThinkingStartedAt(null)
      }
    }
  }

  // ── Estados de autenticação ───────────────────────────────────────────────────
  if (auth_status === 'loading')         return <div className="auth-loading" role="status"><span>Verificando acesso…</span></div>
  if (auth_status === 'unauthenticated') return <LoginScreen authError={auth_error} />
  if (auth_status === 'pending')         return <AccessPending />
  if (auth_status === 'disabled')        return <AccessDenied />

  const canUseAssistant  = hasPermission('assistant.use')
  const canSeeHistory    = hasPermission('assistant.history')
  const canSeeIndicators = hasPermission('indicators.view')
  const canSeeAssets     = hasPermission('assets.view')
  const canSeeSettings   = hasPermission('settings.view')

  const hour = new Date().getHours()
  const greeting = hour < 12 ? 'Bom dia' : hour < 18 ? 'Boa tarde' : 'Boa noite'
  const firstName = user?.display_name?.split(' ')[0] || user?.email || ''

  return (
    <main className="app-shell">
      <div className="ambient-glow ambient-glow--blue" />
      <div className="ambient-glow ambient-glow--yellow" />
      <div className="app-panel">
        <Sidebar
          activeSection={activeSection}
          onNewConversation={createNewConversation}
          onOpenConversations={canSeeHistory ? () => setHistoryOpen(v => !v) : undefined}
          onGoAssistant={canUseAssistant ? () => { abortRequest(); setActiveConversationId(null); setMessages([greetingMsg()]); setPrompt(''); setHistoryOpen(false); setActiveSection('assistant') } : undefined}
          onOpenIndicators={canSeeIndicators ? () => { setHistoryOpen(false); setActiveSection('indicators') } : undefined}
          onOpenAssets={canSeeAssets ? () => { setHistoryOpen(false); setActiveSection('assets') } : undefined}
          onOpenSettings={canSeeSettings ? () => setSettingsOpen(true) : undefined}
          historyOpen={historyOpen} settingsOpen={settingsOpen}
          permissions={{ canUseAssistant, canSeeHistory, canSeeIndicators, canSeeAssets, canSeeSettings }}
        />

        {historyOpen && canSeeHistory && (
          <ConversationHistory
            conversations={conversations}
            activeConversationId={activeConversationId}
            onSelect={selectConversation}
            onNewConversation={createNewConversation}
            onDelete={deleteConversation}
            onClose={() => setHistoryOpen(false)}
          />
        )}

        <div className={`workspace ${activeSection === 'assistant' && active ? 'workspace--active' : ''} ${activeSection === 'indicators' ? 'workspace--indicators' : ''} ${activeSection === 'assets' ? 'workspace--assets' : ''}`}>
          <header className="workspace-header">
            <div className="workspace-title"><span className="header-accent" /> Gentil Negócios <span>· Obras &amp; Manutenções</span></div>
            <div className="header-greeting">
              <span className="header-greeting__icon">♧</span>
              <span><strong>{greeting}, {firstName}!</strong><small>Vamos construir resultados.</small></span>
            </div>
            <div className="header-actions">
              {(active || activeSection !== 'assistant') && (
                <button className="new-conversation" type="button" onClick={createNewConversation}>+ Nova conversa</button>
              )}
              <UserMenu
                onOpenUsers={() => setUsersOpen(true)}
                onOpenAudit={() => setAuditOpen(true)}
                onOpenSettings={() => setSettingsOpen(true)}
              />
            </div>
          </header>

          {activeSection === 'assistant' && canUseAssistant ? (
            <>
              <HeroAssistant active={active} />
              <ChatArea messages={messages} active={active} loading={loading}
                        thinkingStartedAt={thinkingStartedAt} serviceStatus={serviceStatus} />
              <div className="interaction-zone">
                {!active && <SuggestionChips onSelect={p => sendMessage(null, p)} active={active} />}
                <ChatComposer value={prompt} onChange={setPrompt} onSubmit={sendMessage} loading={loading} />
              </div>
            </>
          ) : activeSection === 'assistant' && !canUseAssistant ? (
            <div className="permission-denied"><p>Você não tem permissão para usar o assistente.</p></div>
          ) : activeSection === 'indicators' && canSeeIndicators ? (
            <IndicatorsPage activeIndicator={activeIndicator} onIndicatorChange={setActiveIndicator} />
          ) : activeSection === 'assets' && canSeeAssets ? (
            <AssetsPage />
          ) : null}
        </div>
      </div>

      <SettingsModal open={settingsOpen} onClose={() => setSettingsOpen(false)} />

      {usersOpen && hasPermission('users.manage') && (
        <Suspense fallback={null}>
          <UsersModal onClose={() => setUsersOpen(false)} />
        </Suspense>
      )}
      {auditOpen && hasPermission('audit.view') && (
        <Suspense fallback={null}>
          <AuditModal onClose={() => setAuditOpen(false)} />
        </Suspense>
      )}
    </main>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <AppShell />
    </AuthProvider>
  )
}
