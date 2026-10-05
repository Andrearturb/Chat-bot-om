import { useEffect, useMemo, useState } from 'react'
import { fetchPreventiveIndicatorsData } from '../api'
import CorrectiveFilters from '../corrective/components/CorrectiveFilters'
import CorrectiveKpis from '../corrective/components/CorrectiveKpis'
import CorrectiveCharts from '../corrective/components/CorrectiveCharts'
import CorrectiveRankTables from '../corrective/components/CorrectiveRankTables'
import CorrectiveDetailModal from '../corrective/components/CorrectiveDetailModal'
import {
  buildAnalystSeries, buildMonthlySeries, buildRank, buildSubcategoryRanks, filterByRank, migrateFilterValues,
} from '../corrective/correctiveData'
import {
  applyPreventiveFilters, buildPreventiveFilterOptions, buildPreventiveKpis,
  buildPreventiveStatusCounters, defaultPreventiveFilters, preventiveStatusPredicates,
} from './preventiveData'


const STATE_KEY = 'gentileza-indicators-preventive-v1'

function loadFilters() {
  try {
    const saved = sessionStorage.getItem(STATE_KEY)
    return saved ? migrateFilterValues(JSON.parse(saved), defaultPreventiveFilters) : defaultPreventiveFilters
  } catch {
    return defaultPreventiveFilters
  }
}

function saveFilters(filters) {
  try {
    sessionStorage.setItem(STATE_KEY, JSON.stringify(filters))
  } catch {
    // Os filtros continuam válidos nesta visita mesmo sem sessionStorage.
  }
}

export default function PreventivePanel() {
  const [records, setRecords] = useState([])
  const [uploadData, setUploadData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState(null)
  const [filters, setFilters] = useState(loadFilters)
  const [detail, setDetail] = useState(null)

  useEffect(() => {
    const controller = new AbortController()
    fetchPreventiveIndicatorsData({ signal: controller.signal })
      .then((data) => { setRecords(data.records); setUploadData(data.uploadData) })
      .catch((cause) => { if (cause?.name !== 'AbortError') setError(cause) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [])

  async function refresh() {
    setRefreshing(true)
    setError(null)
    try {
      const data = await fetchPreventiveIndicatorsData()
      setRecords(data.records)
      setUploadData(data.uploadData)
    } catch (cause) {
      setError(cause)
    } finally {
      setRefreshing(false)
    }
  }

  const options = useMemo(() => buildPreventiveFilterOptions(records), [records])
  const filtered = useMemo(() => applyPreventiveFilters(records, filters), [records, filters])
  const kpis = useMemo(() => buildPreventiveKpis(filtered), [filtered])
  const counters = useMemo(() => buildPreventiveStatusCounters(filtered), [filtered])
  const analystSeries = useMemo(() => buildAnalystSeries(filtered), [filtered])
  const monthlySeries = useMemo(() => buildMonthlySeries(filtered), [filtered])
  const lojaRank = useMemo(() => buildRank(filtered, 'location'), [filtered])
  const categoryRank = useMemo(() => buildRank(filtered, 'category'), [filtered])
  const subcategoriesByCategory = useMemo(() => buildSubcategoryRanks(filtered), [filtered])
  const periodicityRank = useMemo(() => buildRank(filtered, 'periodicity'), [filtered])

  function updateFilter(key, value) {
    const next = { ...filters, [key]: value }
    setFilters(next)
    saveFilters(next)
  }

  function clearFilters() {
    setFilters(defaultPreventiveFilters)
    saveFilters(defaultPreventiveFilters)
  }

  function openRank(field, label, title) {
    setDetail({ titulo: title, registros: filterByRank(filtered, field, label) })
  }

  function openSubcategory(category, subcategory) {
    const categoryRecords = filterByRank(filtered, 'category', category)
    setDetail({
      titulo: `Categoria: ${category} • ${subcategory}`,
      registros: filterByRank(categoryRecords, 'subcategory', subcategory),
    })
  }

  if (loading) return <section className="indicators-state">Carregando chamados preventivos...</section>
  if (error && records.length === 0) {
    return (
      <section className="indicators-state indicators-state--error" role="alert">
        <div><h2>Não foi possível carregar as preventivas</h2><p>{error.message}</p>
          <button type="button" onClick={refresh}>Tentar novamente</button></div>
      </section>
    )
  }
  if (records.length === 0) {
    return (
      <section className="indicators-state"><div><h2>Nenhum chamado preventivo disponível</h2>
        <p>Sincronize o app 57532 da Tape para preencher este painel.</p>
        <button type="button" onClick={refresh}>Atualizar dados</button></div></section>
    )
  }

  const updatedAt = uploadData ? new Date(uploadData).toLocaleString('pt-BR') : 'Não disponível'
  return (
    <div className="corrective-panel">
      <div className="preventive-toolbar">
        <span>Última atualização: {updatedAt}</span>
        <button type="button" onClick={refresh} disabled={refreshing}>
          {refreshing ? 'Atualizando...' : 'Atualizar dados'}
        </button>
      </div>
      {error && <div className="indicators-inline-warning" role="status">
        A última atualização falhou. Os dados carregados anteriormente continuam visíveis.
      </div>}
      <CorrectiveFilters filters={filters} options={options} onChange={updateFilter} onClear={clearFilters}
                         ariaLabel="Filtros dos chamados preventivos" />
      <CorrectiveKpis kpis={kpis} counters={counters} records={filtered} onOpenDetail={setDetail}
                      predicates={preventiveStatusPredicates}
                      panelLabel="Indicadores dos chamados preventivos"
                      slaPredicate={(record) => preventiveStatusPredicates.concluidos(record) && record.slaKnown}
                      labels={{ emAberto: 'Backlog', solicitacaoFinalizada: 'Serviço Finalizado' }} />
      <CorrectiveCharts analystSeries={analystSeries} monthlySeries={monthlySeries} />
      <CorrectiveRankTables
        lojaRank={lojaRank} categoryRank={categoryRank} subcategoriesByCategory={subcategoriesByCategory}
        onOpenStore={(loja) => openRank('location', loja, `Loja: ${loja}`)}
        onOpenSubcategory={openSubcategory}
        periodicityRank={periodicityRank}
        onOpenPeriodicity={(period) => openRank('periodicity', period, `Periodicidade: ${period}`)}
      />
      <CorrectiveDetailModal detail={detail} onClose={() => setDetail(null)} showPeriodicity />
    </div>
  )
}
