import { uniqueOptions } from '../utils/dashboardData'

export const FilterBar = ({ records, filters, onChange }) => {
  const fields = [
    { key: 'region', label: 'Praça', allLabel: 'Todas as praças', options: uniqueOptions(records, (record) => record.region) },
    { key: 'status', label: 'Status', allLabel: 'Todos os status', options: uniqueOptions(records, (record) => record.status) },
    { key: 'category', label: 'Categoria', allLabel: 'Todas as categorias', options: uniqueOptions(records, (record) => record.category) },
    { key: 'provider', label: 'Fornecedor', allLabel: 'Todos os fornecedores', options: uniqueOptions(records, (record) => record.provider) },
    { key: 'analyst', label: 'Analista', allLabel: 'Todos os analistas', options: uniqueOptions(records, (record) => record.analyst) },
  ]
  const updateField = (key, value) => onChange({ ...filters, [key]: value })

  return (
    <section className="filter-bar" aria-label="Filtros de desempenho">
      <label className="performance-filter-field performance-filter-field--search">
        <span>Buscar chamados</span>
        <input className="filter-search" type="search" placeholder="Ticket, fornecedor, categoria ou analista"
          value={filters.query} onChange={(event) => updateField('query', event.target.value)} />
      </label>
      {fields.map(({ key, label, allLabel, options }) => (
        <label className="performance-filter-field" key={key}>
          <span>{label}</span>
          <select className="filter-select" value={filters[key]} onChange={(event) => updateField(key, event.target.value)}>
            <option value="all">{allLabel}</option>
            {options.map((option) => <option key={option} value={option}>{option}</option>)}
          </select>
        </label>
      ))}
      <label className="performance-filter-field">
        <span>Data inicial</span>
        <input className="filter-select" type="date" value={filters.startDate}
          onChange={(event) => updateField('startDate', event.target.value)} />
      </label>
      <label className="performance-filter-field">
        <span>Data final</span>
        <input className="filter-select" type="date" value={filters.endDate}
          onChange={(event) => updateField('endDate', event.target.value)} />
      </label>
    </section>
  )
}
