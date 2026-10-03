import { useEffect, useMemo, useState } from 'react'
import { fetchCostIndicatorsData } from '../api'
import {
  costFilterOptions, costKpis, costPredicates, costRank, defaultCostFilters,
  filterCosts, money, sortCostDetails,
} from './costsData'
import './costs.css'

const STATE_KEY = 'gentileza-indicators-costs-v1'
const MONTHS = { '01': 'Janeiro', '02': 'Fevereiro', '03': 'Março', '04': 'Abril', '05': 'Maio', '06': 'Junho', '07': 'Julho', '08': 'Agosto', '09': 'Setembro', '10': 'Outubro', '11': 'Novembro', '12': 'Dezembro' }

function initialFilters() {
  try { return { ...defaultCostFilters, ...JSON.parse(sessionStorage.getItem(STATE_KEY) || '{}') } }
  catch { return defaultCostFilters }
}

function dateBr(value) {
  return value ? value.slice(0, 10).split('-').reverse().join('/') : '—'
}

function DetailModal({ detail, onClose }) {
  useEffect(() => {
    if (!detail) return undefined
    const handleEscape = (event) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', handleEscape)
    return () => window.removeEventListener('keydown', handleEscape)
  }, [detail, onClose])
  if (!detail) return null
  return (
    <div className="costs-modal" role="dialog" aria-modal="true" aria-label={detail.title}>
      <button type="button" className="costs-modal__backdrop" onClick={onClose} aria-label="Fechar detalhes" />
      <div className="costs-modal__content">
        <header><div><h3>{detail.title}</h3><p>{detail.rows.length.toLocaleString('pt-BR')} lançamentos · {money(costKpis(detail.rows).total)}</p></div>
          <button type="button" onClick={onClose} aria-label="Fechar">×</button></header>
        <div className="costs-modal__scroll"><table>
          <thead><tr><th aria-sort="descending">Lançamento ↓</th><th>Documento</th><th>Loja</th><th>Centro de custo</th><th>Fornecedor</th><th>Descrição</th><th>Conta</th><th>Chave</th><th>Valor</th></tr></thead>
          <tbody>{sortCostDetails(detail.rows).map((row) => <tr key={row.id}>
            <td>{dateBr(row.postingDate)}</td><td>{row.documentNumber || '—'}<small>{dateBr(row.documentDate)}</small></td>
            <td>{row.storeName || 'Não atribuído'}</td><td>{row.costCenter}</td><td>{row.supplierName || '—'}</td>
            <td>{row.description || '—'}</td><td>{row.contaRazao}</td><td>{row.postingKey || '—'}</td><td>{money(row.amount)}</td>
          </tr>)}</tbody>
        </table></div>
      </div>
    </div>
  )
}

function FilterSelect({ label, value, options, onChange, labelFor }) {
  return <label className="costs-filter"><span>{label}</span><select value={value} onChange={(event) => onChange(event.target.value)}>
    <option value="todos">Todos</option>
    {options.map((option) => <option key={option} value={option}>{labelFor?.(option) || option}</option>)}
  </select></label>
}

function CostCard({ title, value, detail, onClick }) {
  return <button type="button" className="costs-kpi" onClick={onClick}>
    <span>{title}</span><strong>{money(value)}</strong><small>{detail} · Ver lançamentos →</small>
  </button>
}

function Ranking({ title, items, onOpen }) {
  const max = Math.max(...items.map((item) => Math.abs(item.amount)), 1)
  return <section className="costs-ranking"><h3>{title}</h3>{items.length === 0 ? <p>Sem lançamentos neste filtro.</p> :
    <div className="costs-ranking__list">{items.map((item, index) => <button type="button" key={item.label} onClick={() => onOpen(item.label)}>
      <span className="costs-ranking__number">{index + 1}.</span><span className="costs-ranking__name">{item.label}</span>
      <strong>{money(item.amount)}</strong><small>{item.count} lançamentos</small>
      <span className="costs-ranking__bar"><i style={{ width: `${Math.max(0, Math.abs(item.amount) / max * 100)}%` }} /></span>
    </button>)}</div>}
  </section>
}

export default function CostsPanel() {
  const [rows, setRows] = useState([])
  const [uploadData, setUploadData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState(null)
  const [filters, setFilters] = useState(initialFilters)
  const [detail, setDetail] = useState(null)

  useEffect(() => {
    const controller = new AbortController()
    fetchCostIndicatorsData({ signal: controller.signal })
      .then((data) => { setRows(data.records); setUploadData(data.uploadData) })
      .catch((cause) => { if (cause?.name !== 'AbortError') setError(cause) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [])

  async function refresh() {
    setRefreshing(true); setError(null)
    try { const data = await fetchCostIndicatorsData(); setRows(data.records); setUploadData(data.uploadData) }
    catch (cause) { setError(cause) }
    finally { setRefreshing(false) }
  }

  function updateFilter(key, value) {
    const next = { ...filters, [key]: value }
    setFilters(next)
    try { sessionStorage.setItem(STATE_KEY, JSON.stringify(next)) } catch { /* filtros válidos nesta visita */ }
  }
  function clearFilters() {
    setFilters(defaultCostFilters)
    try { sessionStorage.setItem(STATE_KEY, JSON.stringify(defaultCostFilters)) } catch { /* idem */ }
  }

  const options = useMemo(() => costFilterOptions(rows), [rows])
  const filtered = useMemo(() => filterCosts(rows, filters), [rows, filters])
  const kpis = useMemo(() => costKpis(filtered), [filtered])
  const supplierRank = useMemo(() => costRank(filtered, 'supplierName'), [filtered])
  const storeRank = useMemo(() => costRank(filtered, 'storeName'), [filtered])
  const showDetail = (title, selected) => setDetail({ title, rows: selected })

  if (loading) return <section className="indicators-state">Carregando custos de manutenção...</section>
  if (error && rows.length === 0) return <section className="indicators-state indicators-state--error" role="alert"><div>
    <h2>Não foi possível carregar os custos</h2><p>{error.message}</p><button type="button" onClick={refresh}>Tentar novamente</button>
  </div></section>
  if (rows.length === 0) return <section className="indicators-state"><div><h2>Nenhum custo importado</h2>
    <p>Importe a extração FBL3N para preencher este painel.</p><button type="button" onClick={refresh}>Atualizar dados</button></div></section>

  return <div className="costs-panel">
    <div className="costs-toolbar"><span>Última atualização: {uploadData ? new Date(uploadData).toLocaleString('pt-BR') : 'Não disponível'}</span>
      <button type="button" onClick={refresh} disabled={refreshing}>{refreshing ? 'Atualizando...' : 'Atualizar dados'}</button></div>
    {error && <div className="indicators-inline-warning" role="status">A atualização falhou. Os dados já carregados continuam visíveis.</div>}
    <section className="costs-filters" aria-label="Filtros de custos">
      <FilterSelect label="Tipo" value={filters.tipo} options={options.tipo} onChange={(v) => updateFilter('tipo', v)}
        labelFor={(v) => v === '41140014' ? 'Corretiva' : v === '41140026' ? 'Preventiva' : v} />
      <FilterSelect label="Fornecedor" value={filters.fornecedor} options={options.fornecedor} onChange={(v) => updateFilter('fornecedor', v)} />
      <FilterSelect label="Loja" value={filters.loja} options={options.loja} onChange={(v) => updateFilter('loja', v)} />
      <FilterSelect label="Praça" value={filters.praca} options={options.praca} onChange={(v) => updateFilter('praca', v)} />
      <FilterSelect label="Mês" value={filters.mes} options={options.mes} onChange={(v) => updateFilter('mes', v)} labelFor={(v) => MONTHS[v]} />
      <FilterSelect label="Ano" value={filters.ano} options={options.ano} onChange={(v) => updateFilter('ano', v)} />
      <button type="button" onClick={clearFilters}>Limpar filtros</button>
    </section>
    <section className="costs-kpis" aria-label="Indicadores de custos">
      <CostCard title="Manutenção corretiva" value={kpis.corretiva} detail="Conta 41140014"
        onClick={() => showDetail('Manutenção corretiva', filtered.filter(costPredicates.corretiva))} />
      <CostCard title="Manutenção preventiva" value={kpis.preventiva} detail="Conta 41140026"
        onClick={() => showDetail('Manutenção preventiva', filtered.filter(costPredicates.preventiva))} />
      <CostCard title="Custo das manutenções" value={kpis.total} detail={`${filtered.length.toLocaleString('pt-BR')} lançamentos`}
        onClick={() => showDetail('Todos os lançamentos', filtered)} />
      {kpis.naoAtribuidoCount > 0 && <CostCard title="Não atribuído" value={kpis.naoAtribuido}
        detail={`${kpis.naoAtribuidoCount} lançamentos`} onClick={() => showDetail('Lançamentos não atribuídos', filtered.filter(costPredicates.naoAtribuido))} />}
    </section>
    <div className="costs-rankings">
      <Ranking title="Fornecedores por valor · top 20" items={supplierRank} onOpen={(label) => showDetail(`Fornecedor: ${label}`, filtered.filter((row) => (row.supplierName || 'Não informado') === label))} />
      <Ranking title="Lojas por valor · top 20" items={storeRank} onOpen={(label) => showDetail(`Loja: ${label}`, filtered.filter((row) => (row.storeName || 'Não atribuído') === label))} />
    </div>
    <DetailModal detail={detail} onClose={() => setDetail(null)} />
  </div>
}
