import { useEffect, useMemo, useRef, useState } from 'react'
import { fetchSystemStatus } from './api'
import './settings.css'

function Icon({ name }) {
  const common = {
    width: 22,
    height: 22,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: '1.8',
    strokeLinecap: 'round',
    strokeLinejoin: 'round',
    'aria-hidden': 'true',
  }

  if (name === 'status') {
    return (
      <svg {...common}>
        <path d="M4 12.5 8.4 17 20 5.5" />
      </svg>
    )
  }

  if (name === 'app') {
    return (
      <svg {...common}>
        <rect x="4" y="4" width="16" height="16" rx="4" />
        <path d="M8 12h2l1.2-3 2.2 6 1.3-3H17" />
      </svg>
    )
  }

  if (name === 'database') {
    return (
      <svg {...common}>
        <ellipse cx="12" cy="6" rx="6.5" ry="2.7" />
        <path d="M5.5 6v5c0 1.5 2.9 2.7 6.5 2.7s6.5-1.2 6.5-2.7V6" />
        <path d="M5.5 11v5c0 1.5 2.9 2.7 6.5 2.7s6.5-1.2 6.5-2.7v-5" />
      </svg>
    )
  }

  if (name === 'automation') {
    return (
      <svg {...common}>
        <path d="M7 7h10v10H7z" />
        <path d="M3 12h4M17 12h4M12 3v4M12 17v4" />
        <circle cx="12" cy="12" r="2.2" />
      </svg>
    )
  }

  if (name === 'sync') {
    return (
      <svg {...common}>
        <path d="M20 7v5h-5" />
        <path d="M4 17v-5h5" />
        <path d="M18.2 10A7 7 0 0 0 6.4 6.7L4 9" />
        <path d="M5.8 14A7 7 0 0 0 17.6 17.3L20 15" />
      </svg>
    )
  }

  if (name === 'clock') {
    return (
      <svg {...common}>
        <circle cx="12" cy="12" r="8.5" />
        <path d="M12 7.5V12l3 1.8" />
      </svg>
    )
  }

  if (name === 'users') {
    return (
      <svg {...common}>
        <circle cx="9" cy="8" r="3.5" />
        <path d="M2.5 19.5c1-3.4 3.6-5.2 6.5-5.2s5.5 1.8 6.5 5.2" />
        <path d="M16 4.8a3.3 3.3 0 0 1 0 6.4M17.6 14.6c2 .7 3.3 2.3 3.9 4.9" />
      </svg>
    )
  }

  if (name === 'records') {
    return (
      <svg {...common}>
        <path d="M7 4h10a2 2 0 0 1 2 2v12H5V6a2 2 0 0 1 2-2Z" />
        <path d="M8 9h8M8 13h8" />
      </svg>
    )
  }

  return (
    <svg {...common}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 10.5V16M12 8h.01" />
    </svg>
  )
}

function formatDateTime(value) {
  if (!value) return 'Ainda não disponível'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Ainda não disponível'

  return new Intl.DateTimeFormat('pt-BR', {
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(date)
}

function formatCount(value) {
  if (!Number.isFinite(Number(value))) return 'Não disponível'
  return Number(value).toLocaleString('pt-BR')
}

function mapComponentStatus(value, { sync = false } = {}) {
  if (value === 'ok') {
    return { label: sync ? 'Sincronizada' : 'Online', tone: 'ok' }
  }
  if (value === 'unknown') {
    return { label: 'Sem sincronização', tone: 'warning' }
  }
  if (value === 'error') {
    return { label: 'Indisponível', tone: 'error' }
  }
  return { label: 'Não verificado', tone: 'neutral' }
}

function StatusRow({ icon, label, description, status }) {
  return (
    <div className="settings-status-row">
      <span className="settings-status-row__icon"><Icon name={icon} /></span>
      <div className="settings-status-row__copy">
        <strong>{label}</strong>
        <small>{description}</small>
      </div>
      <span className={`settings-status-pill settings-status-pill--${status.tone}`}>
        <i aria-hidden="true" />
        {status.label}
      </span>
    </div>
  )
}

function SettingsMenu({ onOpenStatus, onOpenUsers }) {
  return (
    <>
      <div className="settings-modal__heading">
        <p>CONFIGURAÇÕES</p>
        <h2 id="settings-dialog-title">Configurações do Gentileza</h2>
        <span id="settings-dialog-description">Acesse informações e opções do aplicativo.</span>
      </div>

      <div className="settings-options">
        <button className="settings-option-card" type="button" onClick={onOpenStatus}>
          <span className="settings-option-card__icon"><Icon name="status" /></span>
          <span className="settings-option-card__copy">
            <strong>Status do sistema</strong>
            <small>Consulte se o Gentileza e seus serviços estão funcionando normalmente.</small>
          </span>
          <span className="settings-option-card__arrow" aria-hidden="true">›</span>
        </button>
        {onOpenUsers && (
          <button className="settings-option-card" type="button" onClick={onOpenUsers}>
            <span className="settings-option-card__icon settings-option-card__icon--users"><Icon name="users" /></span>
            <span className="settings-option-card__copy">
              <strong>Gestão de Usuários</strong>
              <small>Consulte quem acessa o Chat-bot O&amp;M e abra o console do Keycloak para liberar ou bloquear contas.</small>
            </span>
            <span className="settings-option-card__arrow" aria-hidden="true">›</span>
          </button>
        )}
      </div>

      <div className="settings-modal__future-note">
        <span aria-hidden="true">＋</span>
        <p>Este espaço está preparado para receber novas opções de configuração quando necessário.</p>
      </div>
    </>
  )
}

function SystemStatus({ data, loading, error, checkedAt, onBack, onRefresh }) {
  const components = data?.components ?? {}
  const operational = data?.operations ?? {}

  const rows = [
    {
      icon: 'app',
      label: 'Gentileza',
      description: 'Funcionamento geral do aplicativo',
      status: mapComponentStatus(components.api?.status),
    },
    {
      icon: 'database',
      label: 'Base de dados',
      description: 'Acesso às informações da operação',
      status: mapComponentStatus(components.database?.status),
    },
    {
      icon: 'automation',
      label: 'Automação de consultas',
      description: 'Processamento das perguntas do assistente',
      status: mapComponentStatus(components.n8n?.status),
    },
    {
      icon: 'sync',
      label: 'Sincronização com Tape',
      description: 'Atualização da base operacional',
      status: mapComponentStatus(components.tape_sync?.status, { sync: true }),
    },
  ]

  const hasError = Boolean(error)
  const hasAttention = rows.some((row) => row.status.tone === 'error' || row.status.tone === 'warning')
  const overallTone = hasError ? 'error' : loading ? 'checking' : hasAttention ? 'warning' : 'ok'
  const overallText = hasError
    ? 'Não foi possível verificar o sistema'
    : loading
      ? 'Verificando o sistema...'
      : hasAttention
        ? 'Alguns serviços precisam de atenção'
        : 'Tudo funcionando normalmente'

  return (
    <>
      <div className="settings-status-header">
        <button className="settings-back-button" type="button" onClick={onBack} aria-label="Voltar para configurações">←</button>
        <div>
          <p>CONFIGURAÇÕES</p>
          <h2 id="settings-dialog-title">Status do sistema</h2>
          <span id="settings-dialog-description">Acompanhe o funcionamento dos serviços do Gentileza.</span>
        </div>
      </div>

      <div className={`settings-overall settings-overall--${overallTone}`} role="status" aria-live="polite">
        <span className="settings-overall__icon" aria-hidden="true">{overallTone === 'ok' ? '✓' : overallTone === 'checking' ? '…' : '!'}</span>
        <div>
          <strong>{overallText}</strong>
          <small>{error?.message || (checkedAt ? `Última verificação: ${checkedAt}` : 'Consultando os serviços do aplicativo.')}</small>
        </div>
      </div>

      <div className="settings-status-list" aria-busy={loading}>
        {rows.map((row) => <StatusRow key={row.label} {...row} />)}
      </div>

      <div className="settings-system-metrics">
        <div className="settings-metric-card">
          <span className="settings-metric-card__icon"><Icon name="clock" /></span>
          <small>Última sincronização</small>
          <strong>{formatDateTime(operational.last_sync)}</strong>
        </div>
        <div className="settings-metric-card">
          <span className="settings-metric-card__icon"><Icon name="records" /></span>
          <small>Base operacional</small>
          <strong>{operational.service_count == null ? 'Não disponível' : `${formatCount(operational.service_count)} chamados`}</strong>
        </div>
        <div className="settings-metric-card">
          <span className="settings-metric-card__icon"><Icon name="info" /></span>
          <small>Versão do Gentileza</small>
          <strong>{data?.version || 'Não disponível'}</strong>
        </div>
      </div>

      <div className="settings-status-actions">
        <span>{checkedAt ? `Verificado ${checkedAt}` : 'Aguardando verificação'}</span>
        <button type="button" onClick={onRefresh} disabled={loading}>
          <span className={loading ? 'settings-refresh-icon settings-refresh-icon--loading' : 'settings-refresh-icon'} aria-hidden="true">↻</span>
          {loading ? 'Verificando...' : 'Verificar agora'}
        </button>
      </div>
    </>
  )
}

export default function SettingsModal({ open, onClose, onOpenUsers }) {
  if (!open) return null
  // O estado (tela atual, status carregado) mora em SettingsDialog: fechar a janela o descarta.
  return <SettingsDialog onClose={onClose} onOpenUsers={onOpenUsers} />
}

function SettingsDialog({ onClose, onOpenUsers }) {
  const [view, setView] = useState('menu')
  const [statusData, setStatusData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [checkedAt, setCheckedAt] = useState('')
  const closeButtonRef = useRef(null)
  const requestRef = useRef(null)

  const dialogLabel = useMemo(() => view === 'menu' ? 'Configurações do Gentileza' : 'Status do sistema', [view])

  useEffect(() => {
    closeButtonRef.current?.focus()
    const onKeyDown = (event) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  // Ao fechar a janela, cancela a consulta de status que ainda esteja em andamento.
  useEffect(() => () => {
    requestRef.current?.abort()
    requestRef.current = null
  }, [])

  async function loadStatus() {
    requestRef.current?.abort()
    const controller = new AbortController()
    requestRef.current = controller
    setLoading(true)
    setError(null)

    try {
      const payload = await fetchSystemStatus({ signal: controller.signal })
      if (requestRef.current !== controller) return
      setStatusData(payload)
      setCheckedAt(new Intl.DateTimeFormat('pt-BR', { hour: '2-digit', minute: '2-digit' }).format(new Date()))
    } catch (loadError) {
      if (loadError?.name === 'AbortError' || requestRef.current !== controller) return
      setError(loadError)
      setCheckedAt(new Intl.DateTimeFormat('pt-BR', { hour: '2-digit', minute: '2-digit' }).format(new Date()))
    } finally {
      if (requestRef.current === controller) {
        requestRef.current = null
        setLoading(false)
      }
    }
  }

  function openStatus() {
    setView('status')
    loadStatus()
  }

  return (
    <div
      className="settings-overlay"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <section
        className="settings-modal"
        role="dialog"
        aria-modal="true"
        aria-label={dialogLabel}
        aria-labelledby="settings-dialog-title"
        aria-describedby="settings-dialog-description"
      >
        <button ref={closeButtonRef} className="settings-close" type="button" onClick={onClose} aria-label="Fechar configurações">×</button>

        {view === 'menu' ? (
          <SettingsMenu onOpenStatus={openStatus} onOpenUsers={onOpenUsers} />
        ) : (
          <SystemStatus
            data={statusData}
            loading={loading}
            error={error}
            checkedAt={checkedAt}
            onBack={() => setView('menu')}
            onRefresh={loadStatus}
          />
        )}
      </section>
    </div>
  )
}
