import { MultiSelect } from '../../../../components/MultiSelect'

const MES_LABEL = {
  '01': 'Janeiro', '02': 'Fevereiro', '03': 'Março', '04': 'Abril',
  '05': 'Maio', '06': 'Junho', '07': 'Julho', '08': 'Agosto',
  '09': 'Setembro', '10': 'Outubro', '11': 'Novembro', '12': 'Dezembro',
}

/** `options.campo` é lista plana de valores; o MultiSelect quer {value, label}. */
function toChoices(values, mapLabel) {
  return (values ?? []).map((value) => ({ value, label: mapLabel ? mapLabel(value) : value }))
}

export default function CorrectiveFilters({ filters, options, onChange, onClear, ariaLabel = 'Filtros dos chamados corretivos' }) {
  return (
    <section className="corrective-filters" aria-label={ariaLabel}>
      <MultiSelect label="Status do Chamado" options={toChoices(options.status)} selected={filters.status}
                   allLabel="Todos os status" unit={['status', 'status']}
                   onChange={(next) => onChange('status', next)} />
      <MultiSelect label="Loja" options={toChoices(options.loja)} selected={filters.loja}
                   allLabel="Todas as lojas" unit={['loja', 'lojas']}
                   onChange={(next) => onChange('loja', next)} />
      <MultiSelect label="Praça" options={toChoices(options.praca)} selected={filters.praca}
                   allLabel="Todas as praças" unit={['praça', 'praças']}
                   onChange={(next) => onChange('praca', next)} />
      <MultiSelect label="Categoria" options={toChoices(options.categoria)} selected={filters.categoria}
                   allLabel="Todas as categorias" unit={['categoria', 'categorias']}
                   onChange={(next) => onChange('categoria', next)} />
      <MultiSelect label="Analista" options={toChoices(options.analista)} selected={filters.analista}
                   allLabel="Todos os analistas" unit={['analista', 'analistas']}
                   onChange={(next) => onChange('analista', next)} />
      <MultiSelect label="Mês" options={toChoices(options.mes, (value) => MES_LABEL[value] ?? value)} selected={filters.mes}
                   allLabel="Todos os meses" unit={['mês', 'meses']}
                   onChange={(next) => onChange('mes', next)} />
      <MultiSelect label="Ano" options={toChoices(options.ano)} selected={filters.ano}
                   allLabel="Todos os anos" unit={['ano', 'anos']}
                   onChange={(next) => onChange('ano', next)} />
      {options.periodicidade && (
        <MultiSelect label="Periodicidade" options={toChoices(options.periodicidade)} selected={filters.periodicidade}
                     allLabel="Todas as periodicidades" unit={['periodicidade', 'periodicidades']}
                     onChange={(next) => onChange('periodicidade', next)} />
      )}
      <button type="button" className="corrective-filters__clear" onClick={onClear}>
        Limpar filtros
      </button>
    </section>
  )
}
