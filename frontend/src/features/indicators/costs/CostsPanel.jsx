import { useEffect, useMemo, useState } from 'react'
import {
  CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { MultiSelect } from '../../../components/MultiSelect'
import { fetchCostIndicatorsData } from '../api'
import IndicatorLoadingState from '../components/IndicatorLoadingState'
import { migrateFilterValues } from '../utils/filterState.js'
import {
  buildCostMonthlySeries, costFilterOptions, costKpis, costPredicates, costRank, costRankByType,
  defaultCostFilters, filterCosts, money, sortCostDetails,
} from './costsData'
import './costs.css'

// Mesma dupla de cores do gráfico Total/Concluídos da corretiva
// (CorrectiveCharts.jsx): corretiva e preventiva ficam com o mesmo
// significado visual em toda a Central de Indicadores.
const COR_CORRETIVA = '#2f6fb3'
const COR_PREVENTIVA = '#1f9d6b'

const STATE_KEY = 'gentileza-indicators-costs-v1'
const MONTHS = { '01': 'Janeiro', '02': 'Fevereiro', '03': 'Março', '04': 'Abril', '05': 'Maio', '06': 'Junho', '07': 'Julho', '08': 'Agosto', '09': 'Setembro', '10': 'Outubro', '11': 'Novembro', '12': 'Dezembro' }
const TIPO_LABEL = (value) => (value === '41140014' ? 'Corretiva' : value === '41140026' ? 'Preventiva' : value)

function initialFilters() {
  try {
    const saved = JSON.parse(sessionStorage.getItem(STATE_KEY) || '{}')
    // Quem tinha filtro salvo no formato antigo (um valor, não array) continua
    // funcionando: a migração converte na leitura, uma vez.
    return migrateFilterValues(saved, defaultCostFilters)
  } catch { return defaultCostFilters }
}

/** `options.campo` é lista plana de valores; o MultiSelect quer {value, label}. */
function toChoices(values, mapLabel) {
  return (values ?? []).map((value) => ({ value, label: mapLabel ? mapLabel(value) : value }))
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

/** Mesmo card de ranking, mas com o valor líquido separado por conta razão —
 * a barra vira duas cores, uma para corretiva e outra para preventiva. */
function RankingByType({ title, items, onOpen }) {
  const max = Math.max(...items.map((item) => Math.abs(item.total)), 1)
  return <section className="costs-ranking"><h3>{title}</h3>{items.length === 0 ? <p>Sem lançamentos neste filtro.</p> :
    <div className="costs-ranking__list">{items.map((item, index) => <button type="button" key={item.label} onClick={() => onOpen(item.label)}>
      <span className="costs-ranking__number">{index + 1}.</span><span className="costs-ranking__name">{item.label}</span>
      <strong>{money(item.total)}</strong>
      <small>{money(item.corretiva)} corretiva · {money(item.preventiva)} preventiva</small>
      <span className="costs-ranking__bar costs-ranking__bar--split">
        <i style={{ width: `${Math.max(0, Math.abs(item.corretiva) / max * 100)}%`, background: COR_CORRETIVA }} />
        <i style={{ width: `${Math.max(0, Math.abs(item.preventiva) / max * 100)}%`, background: COR_PREVENTIVA }} />
      </span>
    </button>)}</div>}
  </section>
}

function MonthlyProgressionChart({ series }) {
  return <article className="costs-chart">
    <h3>Progressão de custos por mês</h3>
    {series.length === 0 ? <p className="costs-empty">Sem dados para o filtro atual.</p> : (
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={series}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(5,56,98,0.12)" />
          <XAxis dataKey="label" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} tickFormatter={(value) => money(value)} width={90} />
          <Tooltip formatter={(value) => money(value)} />
          <Legend />
          <Line type="monotone" dataKey="corretiva" name="Corretiva" stroke={COR_CORRETIVA} strokeWidth={2} dot={false} />
          <Line type="monotone" dataKey="preventiva" name="Preventiva" stroke={COR_PREVENTIVA} strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    )}
  </article>
}

export default function CostsPanel({ onBack }) {
  const [rows, setRows] = useState([])
  const [uploadData, setUploadData] = useState(null)
  const [loading, setLoading] = useState(true)
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
    setLoading(true); setError(null)
    try { const data = await fetchCostIndicatorsData(); setRows(data.records); setUploadData(data.uploadData) }
    catch (cause) { setError(cause) }
    finally { setLoading(false) }
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
  const pracaRank = useMemo(() => costRankByType(filtered, 'praca'), [filtered])
  const monthlySeries = useMemo(() => buildCostMonthlySeries(filtered), [filtered])
  const showDetail = (title, selected) => setDetail({ title, rows: selected })

  if (loading) return <IndicatorLoadingState title="Carregando custos de manutenção" />
  if (error && rows.length === 0) return <section className="indicators-state indicators-state--error" role="alert"><div>
    <h2>Não foi possível carregar os custos</h2><p>{error.message}</p><button type="button" onClick={refresh}>Tentar novamente</button>
  </div></section>
  if (rows.length === 0) return <section className="indicators-state"><div><h2>Nenhum custo importado</h2>
    <p>Importe a extração FBL3N para preencher este painel.</p><button type="button" onClick={onBack}>Voltar à Central de Indicadores</button></div></section>

  return <div className="costs-panel">
    <div className="costs-toolbar"><span>Última atualização: {uploadData ? new Date(uploadData).toLocaleString('pt-BR') : 'Não disponível'}</span></div>
    {error && <div className="indicators-inline-warning" role="status">A atualização falhou. Os dados já carregados continuam visíveis.</div>}
    <section className="costs-filters" aria-label="Filtros de custos">
      <MultiSelect label="Tipo" options={toChoices(options.tipo, TIPO_LABEL)} selected={filters.tipo}
                   allLabel="Todos os tipos" unit={['tipo', 'tipos']}
                   onChange={(next) => updateFilter('tipo', next)} />
      <MultiSelect label="Fornecedor" options={toChoices(options.fornecedor)} selected={filters.fornecedor}
                   allLabel="Todos os fornecedores" unit={['fornecedor', 'fornecedores']}
                   onChange={(next) => updateFilter('fornecedor', next)} />
      <MultiSelect label="Loja" options={toChoices(options.loja)} selected={filters.loja}
                   allLabel="Todas as lojas" unit={['loja', 'lojas']}
                   onChange={(next) => updateFilter('loja', next)} />
      <MultiSelect label="Praça" options={toChoices(options.praca)} selected={filters.praca}
                   allLabel="Todas as praças" unit={['praça', 'praças']}
                   onChange={(next) => updateFilter('praca', next)} />
      <MultiSelect label="Mês" options={toChoices(options.mes, (v) => MONTHS[v] ?? v)} selected={filters.mes}
                   allLabel="Todos os meses" unit={['mês', 'meses']}
                   onChange={(next) => updateFilter('mes', next)} />
      <MultiSelect label="Ano" options={toChoices(options.ano)} selected={filters.ano}
                   allLabel="Todos os anos" unit={['ano', 'anos']}
                   onChange={(next) => updateFilter('ano', next)} />
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
    <MonthlyProgressionChart series={monthlySeries} />
    <RankingByType title="Custo por praça · corretiva x preventiva" items={pracaRank}
      onOpen={(label) => showDetail(`Praça: ${label}`, filtered.filter((row) => (row.praca || 'Não informado') === label))} />
    <div className="costs-rankings">
      <Ranking title="Fornecedores por valor · top 20" items={supplierRank} onOpen={(label) => showDetail(`Fornecedor: ${label}`, filtered.filter((row) => (row.supplierName || 'Não informado') === label))} />
      <Ranking title="Lojas por valor · top 20" items={storeRank} onOpen={(label) => showDetail(`Loja: ${label}`, filtered.filter((row) => (row.storeName || 'Não atribuído') === label))} />
    </div>
    <DetailModal detail={detail} onClose={() => setDetail(null)} />
  </div>
}
