import { useEffect, useMemo, useState } from 'react'
import { fetchIndicatorsData } from './api'
import { FilterBar } from './components/FilterBar'
import { KpiCard } from './components/KpiCard'
import { ChartsGrid } from './components/ChartsGrid'
import { SupplierProductivityBlock } from './components/SupplierProductivityBlock'
import { AnalystProductivityBlock } from './components/AnalystProductivityBlock'
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
import './indicators.css'

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

export default function IndicatorsPage() {
  const [records, setRecords] = useState([])
  const [filters, setFilters] = useState(defaultFilters)
  const [globalStartDate, setGlobalStartDate] = useState('2026-01-01')
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

  if (loading) {
    return (
      <div className="indicators-page">
        <section className="indicators-state" aria-live="polite">
          <span className="indicators-loader" aria-hidden="true" />
          <div><h2>Carregando indicadores</h2><p>Consultando os dados do Gentileza...</p></div>
        </section>
      </div>
    )
  }

  if (error && records.length === 0) {
    return <div className="indicators-page"><ErrorState error={error} onRetry={refresh} /></div>
  }

  if (records.length === 0) {
    return (
      <div className="indicators-page">
        <section className="indicators-state">
          <span className="indicators-state__icon" aria-hidden="true">0</span>
          <div>
            <h2>Nenhum chamado disponível</h2>
            <p>O backend está acessível, mas a base ainda não possui registros para exibir.</p>
            <button type="button" onClick={refresh}>Atualizar dados</button>
          </div>
        </section>
      </div>
    )
  }

  return (
    <div className="indicators-page">
      <header className="indicators-hero">
        <div className="indicators-hero-copy">
          <p className="indicators-eyebrow">Indicadores operacionais</p>
          <h1>Desempenho de Obras &amp; Manutenções em uma única visão</h1>
          <p>
            O painel usa diretamente a base do Gentileza para analisar chamados, praças,
            categorias, fornecedores e produtividade, sem upload manual de planilha.
          </p>
        </div>

        <div className="indicators-hero-meta">
          <div>
            <span className="meta-label">Período disponível</span>
            <strong>{findDateRange(records)}</strong>
          </div>
          <div>
            <span className="meta-label">Última atualização</span>
            <strong>{formatDateTime(uploadData)}</strong>
          </div>
          <div className="indicators-refresh-card">
            <span className="meta-label">Base atual</span>
            <strong>{records.length.toLocaleString('pt-BR')} chamados</strong>
            <button type="button" onClick={refresh} disabled={refreshing}>
              {refreshing ? 'Atualizando...' : 'Atualizar dados'}
            </button>
          </div>
        </div>
      </header>

      <main className="indicators-content">
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
      </main>
    </div>
  )
}
