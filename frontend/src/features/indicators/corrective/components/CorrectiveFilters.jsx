const MES_LABEL = {
  '01': 'Janeiro', '02': 'Fevereiro', '03': 'Março', '04': 'Abril',
  '05': 'Maio', '06': 'Junho', '07': 'Julho', '08': 'Agosto',
  '09': 'Setembro', '10': 'Outubro', '11': 'Novembro', '12': 'Dezembro',
}

function Select({ label, value, options, onChange, mapLabel }) {
  return (
    <label className="corrective-select">
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="todos">Todos</option>
        {options.map((option) => (
          <option key={option} value={option}>
            {mapLabel ? mapLabel(option) : option}
          </option>
        ))}
      </select>
    </label>
  )
}

export default function CorrectiveFilters({ filters, options, onChange, onClear, ariaLabel = 'Filtros dos chamados corretivos' }) {
  return (
    <section className="corrective-filters" aria-label={ariaLabel}>
      <Select label="Status do Chamado" value={filters.status} options={options.status}
              onChange={(value) => onChange('status', value)} />
      <Select label="Loja" value={filters.loja} options={options.loja}
              onChange={(value) => onChange('loja', value)} />
      <Select label="Praça" value={filters.praca} options={options.praca}
              onChange={(value) => onChange('praca', value)} />
      <Select label="Categoria" value={filters.categoria} options={options.categoria}
              onChange={(value) => onChange('categoria', value)} />
      <Select label="Mês" value={filters.mes} options={options.mes}
              onChange={(value) => onChange('mes', value)}
              mapLabel={(value) => MES_LABEL[value] ?? value} />
      <Select label="Ano" value={filters.ano} options={options.ano}
              onChange={(value) => onChange('ano', value)} />
      {options.periodicidade && (
        <Select label="Periodicidade" value={filters.periodicidade} options={options.periodicidade}
                onChange={(value) => onChange('periodicidade', value)} />
      )}
      <button type="button" className="corrective-filters__clear" onClick={onClear}>
        Limpar filtros
      </button>
    </section>
  )
}
