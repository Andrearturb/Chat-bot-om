import { useEffect, useMemo, useRef, useState } from 'react'
import { fetchIndicatorsData } from './api'
import { FilterBar } from './components/FilterBar'
import { KpiCard } from './components/KpiCard'
import { ChartsGrid } from './components/ChartsGrid'
import { SupplierProductivityBlock } from './components/SupplierProductivityBlock'
import { AnalystProductivityBlock } from './components/AnalystProductivityBlock'
import IndicatorDashboardHeader from './components/IndicatorDashboardHeader'
import IndicatorPlaceholder from './components/IndicatorPlaceholder'
import IndicatorsHome from './home/IndicatorsHome'
import CorrectivePanel from './corrective/CorrectivePanel'
import PreventivePanel from './preventive/PreventivePanel'
import CostsPanel from './costs/CostsPanel'
import {
  applyFilters,
  buildAnalystProductivity,
  buildCategoryTreemap,
  buildExecutiveSummary,
  buildMetrics,
  buildRegionSeries,
  buildSupplierProductivity,
  defaultFilters,
} from './utils/dashboardData'
import indicatorsMascot from '../../assets/gentileza-indicadores.webp'
import './indicators.css'

const PERFORMANCE_STATE_KEY = 'gentileza-indicators-performance-v1'
const INDICATORS_SCROLL_KEY = 'gentileza-indicators-scroll-v1'

function loadPerformanceState() {
  try {
    const saved = sessionStorage.getItem(PERFORMANCE_STATE_KEY)
    if (!saved) return null
    const parsed = JSON.parse(saved)
    if (!parsed || typeof parsed !== 'object') return null
    return parsed
  } catch (error) {
    console.warn('Não foi possível restaurar os filtros dos indicadores:', error)
    return null
  }
}

function loadIndicatorScrollPositions() {
  try {
    const saved = sessionStorage.getItem(INDICATORS_SCROLL_KEY)
    if (!saved) return {}
    const parsed = JSON.parse(saved)
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch (error) {
    console.warn('Não foi possível restaurar a posição dos indicadores:', error)
    return {}
  }
}

function saveIndicatorScrollPosition(indicator, scrollTop) {
  try {
    const positions = loadIndicatorScrollPositions()
    positions[indicator] = Math.max(0, Math.round(scrollTop || 0))
    sessionStorage.setItem(INDICATORS_SCROLL_KEY, JSON.stringify(positions))
  } catch (error) {
    console.warn('Não foi possível salvar a posição dos indicadores:', error)
  }
}

function formatDateTime(value) {
  if (!value) return 'Não disponível'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Não disponível'
  return new Intl.DateTimeFormat('pt-BR', {
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(date)
}

function formatDate(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat('pt-BR').format(date)
}

function findDateRange(records) {
  const dates = records
    .map((record) => record.createdOn ?? record.requestDate)
    .filter(Boolean)
    .map((value) => new Date(value))
    .filter((date) => !Number.isNaN(date.getTime()))

  if (!dates.length) return 'Sem período disponível'

  const timestamps = dates.map((date) => date.getTime())
  return `${formatDate(new Date(Math.min(...timestamps)).toISOString())} até ${formatDate(new Date(Math.max(...timestamps)).toISOString())}`
}

function HeroIcon({ type }) {
  const common = { width: 20, height: 20, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: '2', strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': 'true' }

  if (type === 'calendar') {
    return (
      <svg {...common}>
        <rect x="3" y="4" width="18" height="18" rx="3" />
        <line x1="16" y1="2" x2="16" y2="6" />
        <line x1="8" y1="2" x2="8" y2="6" />
        <line x1="3" y1="10" x2="21" y2="10" />
      </svg>
    )
  }

  if (type === 'clock') {
    return (
      <svg {...common}>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v5l3 2" />
      </svg>
    )
  }

  return (
    <svg {...common}>
      <ellipse cx="12" cy="6" rx="6" ry="2.5" />
      <path d="M6 6v5c0 1.4 2.7 2.5 6 2.5s6-1.1 6-2.5V6" />
      <path d="M6 11v5c0 1.4 2.7 2.5 6 2.5s6-1.1 6-2.5v-5" />
    </svg>
  )
}

function HeroMetaCard({ icon, label, value, children, action }) {
  return (
    <div className={`hero-meta-card${action ? ' hero-meta-card--action' : ''}`}>
      <span className="hero-meta-card__icon"><HeroIcon type={icon} /></span>
      <div className="hero-meta-card__body">
        <span className="meta-label">{label}</span>
        <strong>{value}</strong>
      </div>
      {children}
    </div>
  )
}

function CentralHero({ records, uploadData, loading, refreshing, onRefresh }) {
  const period = loading && records.length === 0 ? 'Carregando...' : findDateRange(records)
  const updatedAt = loading && !uploadData ? 'Carregando...' : formatDateTime(uploadData)
  const base = loading && records.length === 0 ? 'Carregando...' : `${records.length.toLocaleString('pt-BR')} chamados`

  return (
    <header className="indicators-hero">
      <div className="indicators-hero__left">
        <div className="indicators-hero__mascot-panel">
          <div className="indicators-hero__ring indicators-hero__ring--one" aria-hidden="true" />
          <div className="indicators-hero__ring indicators-hero__ring--two" aria-hidden="true" />
          <div className="indicators-hero__city" aria-hidden="true" />
          <img src={indicatorsMascot} alt="" className="indicators-hero__mascot" />
          <div className="indicators-hero__speech">
            Aqui, todos os indicadores em um só lugar para apoiar suas decisões. 💡
          </div>
        </div>

        <div className="indicators-hero-copy">
          <p className="indicators-eyebrow">Indicadores operacionais</p>
          <h1>
            <span>Central de</span>
            <span>Indicadores</span>
          </h1>
          <h2>Informação que impulsiona resultados.</h2>
          <p>
            Acesse as principais visões de Obras &amp; Manutenções em uma central única,
            organizada e preparada para receber novos indicadores.
          </p>
        </div>
      </div>

      <div className="indicators-hero__right">
        <div className="indicators-hero__bars" aria-hidden="true">
          <span />
          <span />
          <span />
        </div>

        <div className="indicators-hero-meta">
          <HeroMetaCard icon="calendar" label="Período disponível" value={period} />
          <HeroMetaCard icon="clock" label="Última atualização" value={updatedAt} />
          <HeroMetaCard icon="database" label="Base atual" value={base} action>
            <button type="button" onClick={onRefresh} disabled={refreshing || loading}>
              {refreshing ? 'Atualizando...' : 'Atualizar dados'}
            </button>
          </HeroMetaCard>
        </div>
      </div>
    </header>
  )
}

function ErrorState({ error, onRetry }) {
  const network = error?.kind === 'network'
  return (
    <section className="indicators-state indicators-state--error" role="alert">
      <span className="indicators-state__icon" aria-hidden="true">!</span>
      <div>
        <h2>{network ? 'Backend indisponível' : 'Não foi possível carregar os indicadores'}</h2>
        <p>{error?.message || 'Ocorreu um erro ao consultar os dados.'}</p>
        <button type="button" onClick={onRetry}>Tentar novamente</button>
      </div>
    </section>
  )
}

function EmptyState({ onRetry }) {
  return (
    <section className="indicators-state">
      <span className="indicators-state__icon" aria-hidden="true">0</span>
      <div>
        <h2>Nenhum chamado disponível</h2>
        <p>O backend está acessível, mas a base ainda não possui registros para exibir.</p>
        <button type="button" onClick={onRetry}>Atualizar dados</button>
      </div>
    </section>
  )
}

export default function IndicatorsPage({ activeIndicator = 'home', onIndicatorChange = () => {} }) {
  const pageRef = useRef(null)
  const restoredState = useMemo(() => loadPerformanceState(), [])
  const [records, setRecords] = useState([])
  const [filters, setFilters] = useState(() => ({ ...defaultFilters, ...(restoredState?.filters ?? {}) }))
  const [globalStartDate, setGlobalStartDate] = useState(restoredState?.globalStartDate ?? '2026-01-01')
  const [uploadData, setUploadData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    const controller = new AbortController()
    let mounted = true

    async function initialLoad() {
      setLoading(true)
      setError(null)
      try {
        const result = await fetchIndicatorsData({ signal: controller.signal })
        if (!mounted) return
        setRecords(result.records)
        setUploadData(result.uploadData)
      } catch (loadError) {
        if (mounted && loadError?.name !== 'AbortError') setError(loadError)
      } finally {
        if (mounted) setLoading(false)
      }
    }

    initialLoad()
    return () => {
      mounted = false
      controller.abort()
    }
  }, [])

  useEffect(() => {
    try {
      sessionStorage.setItem(PERFORMANCE_STATE_KEY, JSON.stringify({ filters, globalStartDate }))
    } catch (storageError) {
      console.warn('Não foi possível salvar os filtros dos indicadores:', storageError)
    }
  }, [filters, globalStartDate])

  useEffect(() => {
    const page = pageRef.current
    if (!page) return undefined

    let frame = null
    const persistScroll = () => {
      if (frame !== null) cancelAnimationFrame(frame)
      frame = requestAnimationFrame(() => {
        saveIndicatorScrollPosition(activeIndicator, page.scrollTop)
      })
    }

    page.addEventListener('scroll', persistScroll, { passive: true })

    return () => {
      if (frame !== null) cancelAnimationFrame(frame)
      saveIndicatorScrollPosition(activeIndicator, page.scrollTop)
      page.removeEventListener('scroll', persistScroll)
    }
  }, [activeIndicator])

  useEffect(() => {
    const page = pageRef.current
    if (!page) return undefined

    // No painel de desempenho, espera os dados terminarem de carregar para que
    // a altura real da página exista antes de restaurar a rolagem.
    if (activeIndicator === 'performance' && loading) return undefined

    const positions = loadIndicatorScrollPositions()
    const savedTop = Number(positions[activeIndicator])
    if (!Number.isFinite(savedTop) || savedTop <= 0) return undefined

    const frame = requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        page.scrollTo({ top: savedTop, left: 0, behavior: 'auto' })
      })
    })

    return () => cancelAnimationFrame(frame)
  }, [activeIndicator, loading, records.length])

  const refresh = async () => {
    setRefreshing(true)
    setError(null)
    try {
      const result = await fetchIndicatorsData()
      setRecords(result.records)
      setUploadData(result.uploadData)
    } catch (loadError) {
      setError(loadError)
    } finally {
      setRefreshing(false)
    }
  }

  const filteredRecords = useMemo(() => applyFilters(records, filters), [filters, records])
  const contextRecords = useMemo(
    () => applyFilters(records, { ...filters, startDate: '', endDate: '' }),
    [records, filters],
  )
  const globalRecords = useMemo(() => {
    if (!globalStartDate) return contextRecords
    const start = new Date(`${globalStartDate}T00:00:00`)
    return contextRecords.filter((record) => {
      const dateStr = record.createdOn ?? record.requestDate
      if (!dateStr) return true
      const date = new Date(dateStr)
      return !Number.isNaN(date.getTime()) && date >= start
    })
  }, [contextRecords, globalStartDate])

  const metrics = useMemo(() => buildMetrics(filteredRecords), [filteredRecords])
  const globalMetrics = useMemo(() => buildMetrics(globalRecords), [globalRecords])
  const regions = useMemo(
    () => buildRegionSeries(filteredRecords, records, filters),
    [filteredRecords, records, filters],
  )
  const categoryTree = useMemo(() => buildCategoryTreemap(filteredRecords), [filteredRecords])
  const supplierProductivity = useMemo(
    () => buildSupplierProductivity(contextRecords, filters),
    [contextRecords, filters],
  )
  const analystProductivity = useMemo(
    () => buildAnalystProductivity(contextRecords, filters),
    [contextRecords, filters],
  )
  const executiveSummary = useMemo(
    () => buildExecutiveSummary(records, filteredRecords, filters),
    [records, filteredRecords, filters],
  )

  const globalStartLabel = globalStartDate
    ? new Date(`${globalStartDate}T00:00:00`).toLocaleDateString('pt-BR')
    : 'início'

  if (activeIndicator === 'home') {
    return (
      <div className="indicators-page indicators-page--home" ref={pageRef}>
        <CentralHero
          records={records}
          uploadData={uploadData}
          loading={loading}
          refreshing={refreshing}
          onRefresh={refresh}
        />
        <main className="indicators-content indicators-content--home">
          <IndicatorsHome onOpenIndicator={onIndicatorChange} error={error} onRetry={refresh} />
        </main>
      </div>
    )
  }

  const dashboardBody = (() => {
    const panelIndicators = ['performance', 'corrective', 'preventive', 'financial']

    if (!panelIndicators.includes(activeIndicator)) {
      return <IndicatorPlaceholder type={activeIndicator} />
    }

    if (activeIndicator === 'preventive') return <PreventivePanel />
    if (activeIndicator === 'financial') return <CostsPanel />

    if (loading) {
      return (
        <section className="indicators-state" aria-live="polite">
          <span className="indicators-loader" aria-hidden="true" />
          <div><h2>Carregando indicador</h2><p>Consultando os dados do Gentileza...</p></div>
        </section>
      )
    }

    if (error && records.length === 0) return <ErrorState error={error} onRetry={refresh} />
    if (records.length === 0) return <EmptyState onRetry={refresh} />

    if (activeIndicator === 'corrective') {
      return (
        <>
          {error && (
            <div className="indicators-inline-warning" role="status">
              A última atualização falhou. Os dados carregados anteriormente continuam visíveis.
              <button type="button" onClick={refresh}>Tentar novamente</button>
            </div>
          )}
          <CorrectivePanel records={records} />
        </>
      )
    }

    return (
      <>
        {error && (
          <div className="indicators-inline-warning" role="status">
            A última atualização falhou. Os dados carregados anteriormente continuam visíveis.
            <button type="button" onClick={refresh}>Tentar novamente</button>
          </div>
        )}

        <FilterBar records={records} filters={filters} onChange={setFilters} />

        <section className="kpi-section">
          <div className="kpi-section__toolbar">
            <span className="kpi-section__legend">Filtrado / Global a partir de</span>
            <div className="global-date-filter">
              <label htmlFor="global-start-date" className="global-date-filter__label">A partir de</label>
              <input
                id="global-start-date"
                type="date"
                className="global-date-filter__input"
                value={globalStartDate}
                onChange={(event) => setGlobalStartDate(event.target.value)}
              />
            </div>
          </div>

          <div className="kpi-grid">
            <KpiCard label="Total de chamados" value={metrics.total.toString()} globalValue={globalMetrics.total.toString()} helper={`Filtrado / Global desde ${globalStartLabel}`} progress={100} tone="cyan" />
            <KpiCard label="Backlog" value={metrics.backlog.toString()} globalValue={globalMetrics.backlog.toString()} helper="Chamados em espera" progress={metrics.total ? (metrics.backlog / metrics.total) * 100 : 0} tone="amber" />
            <KpiCard label="Em andamento" value={metrics.inProgress.toString()} globalValue={globalMetrics.inProgress.toString()} helper="Itens ainda em atendimento" progress={metrics.total ? (metrics.inProgress / metrics.total) * 100 : 0} tone="amber" />
            <KpiCard label="Concluídos" value={metrics.concluded.toString()} globalValue={globalMetrics.concluded.toString()} helper="Chamados concluídos" progress={metrics.completionRate} tone="teal" />
            <KpiCard label="Rejeitados" value={metrics.rejected.toString()} globalValue={globalMetrics.rejected.toString()} helper="Chamados não aprovados" progress={metrics.total ? (metrics.rejected / metrics.total) * 100 : 0} tone="rose" />
            <KpiCard label="Tempo médio" value={`${metrics.avgSlaDays.toFixed(1)} / ${globalMetrics.avgSlaDays.toFixed(1)} dias`} helper="Entre abertura e conclusão" progress={Math.min(100, metrics.avgSlaDays * 10)} tone="cyan" />
          </div>
        </section>

        <ChartsGrid regions={regions} categoryTree={categoryTree} executiveSummary={executiveSummary} />
        <SupplierProductivityBlock suppliers={supplierProductivity} />
        <AnalystProductivityBlock analysts={analystProductivity} />
      </>
    )
  })()

  return (
    <div className="indicators-page indicators-page--dashboard" ref={pageRef}>
      <IndicatorDashboardHeader
        activeIndicator={activeIndicator}
        onChange={onIndicatorChange}
        onBack={() => onIndicatorChange('home')}
      />
      <main className="indicators-content indicators-content--dashboard">
        {dashboardBody}
      </main>
    </div>
  )
}
