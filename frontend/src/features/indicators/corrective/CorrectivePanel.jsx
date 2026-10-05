import { useMemo, useState } from 'react'
import CorrectiveFilters from './components/CorrectiveFilters'
import CorrectiveKpis from './components/CorrectiveKpis'
import CorrectiveCharts from './components/CorrectiveCharts'
import CorrectiveRankTables from './components/CorrectiveRankTables'
import CorrectiveDetailModal from './components/CorrectiveDetailModal'
import {
  applyCorrectiveFilters,
  buildAnalystSeries,
  buildCorrectiveKpis,
  buildFilterOptions,
  buildMonthlySeries,
  buildRank,
  buildSubcategoryRanks,
  buildStatusCounters,
  defaultCorrectiveFilters,
  filterByRank,
  migrateFilterValues,
} from './correctiveData'

export const CORRECTIVE_STATE_KEY = 'gentileza-indicators-corrective-v1'

function loadFilters() {
  try {
    const saved = sessionStorage.getItem(CORRECTIVE_STATE_KEY)
    if (!saved) return defaultCorrectiveFilters
    // Quem tinha filtro salvo no formato antigo (um valor, não array) continua
    // funcionando: a migração converte na leitura, uma vez.
    return migrateFilterValues(JSON.parse(saved), defaultCorrectiveFilters)
  } catch {
    return defaultCorrectiveFilters
  }
}

function saveFilters(filters) {
  try {
    sessionStorage.setItem(CORRECTIVE_STATE_KEY, JSON.stringify(filters))
  } catch {
    // Sessão sem armazenamento disponível: os filtros valem só para esta visita.
  }
}

export default function CorrectivePanel({ records }) {
  const [filters, setFilters] = useState(loadFilters)
  const [detail, setDetail] = useState(null)

  const options = useMemo(() => buildFilterOptions(records), [records])
  const filtered = useMemo(() => applyCorrectiveFilters(records, filters), [records, filters])

  const kpis = useMemo(() => buildCorrectiveKpis(filtered), [filtered])
  const counters = useMemo(() => buildStatusCounters(filtered), [filtered])
  const analystSeries = useMemo(() => buildAnalystSeries(filtered), [filtered])
  const monthlySeries = useMemo(() => buildMonthlySeries(filtered), [filtered])
  const lojaRank = useMemo(() => buildRank(filtered, 'location'), [filtered])
  const categoryRank = useMemo(() => buildRank(filtered, 'category'), [filtered])
  const subcategoriesByCategory = useMemo(() => buildSubcategoryRanks(filtered), [filtered])

  function openStore(loja) {
    setDetail({ titulo: `Loja: ${loja}`, registros: filterByRank(filtered, 'location', loja) })
  }

  function openSubcategory(category, subcategory) {
    const categoryRecords = filterByRank(filtered, 'category', category)
    setDetail({
      titulo: `Categoria: ${category} • ${subcategory}`,
      registros: filterByRank(categoryRecords, 'subcategory', subcategory),
    })
  }

  function updateFilter(key, value) {
    const proximos = { ...filters, [key]: value }
    setFilters(proximos)
    saveFilters(proximos)
  }

  function clearFilters() {
    setFilters(defaultCorrectiveFilters)
    saveFilters(defaultCorrectiveFilters)
  }

  return (
    <div className="corrective-panel">
      <CorrectiveFilters filters={filters} options={options} onChange={updateFilter} onClear={clearFilters} />
      <CorrectiveKpis kpis={kpis} counters={counters} records={filtered} onOpenDetail={setDetail} />
      <CorrectiveCharts analystSeries={analystSeries} monthlySeries={monthlySeries} />
      <CorrectiveRankTables
        lojaRank={lojaRank}
        categoryRank={categoryRank}
        subcategoriesByCategory={subcategoriesByCategory}
        onOpenStore={openStore}
        onOpenSubcategory={openSubcategory}
      />
      <CorrectiveDetailModal detail={detail} onClose={() => setDetail(null)} />
    </div>
  )
}
