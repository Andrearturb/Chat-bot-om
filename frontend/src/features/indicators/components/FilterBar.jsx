import { uniqueOptions } from '../utils/dashboardData';
const selectClass = 'filter-select';
export const FilterBar = ({ records, filters, onChange }) => {
    const regions = uniqueOptions(records, (record) => record.region);
    const statuses = uniqueOptions(records, (record) => record.status);
    const categories = uniqueOptions(records, (record) => record.category);
    const providers = uniqueOptions(records, (record) => record.provider);
    const analysts = uniqueOptions(records, (record) => record.analyst);
    return (<section className="filter-bar">
      <input className="filter-search" type="search" placeholder="Buscar ticket, fornecedor, categoria ou analista" value={filters.query} onChange={(event) => onChange({ ...filters, query: event.target.value })}/>

      <select className={selectClass} value={filters.region} onChange={(event) => onChange({ ...filters, region: event.target.value })}>
        <option value="all">Todas as praças</option>
        {regions.map((region) => (<option key={region} value={region}>
            {region}
          </option>))}
      </select>

      <select className={selectClass} value={filters.status} onChange={(event) => onChange({ ...filters, status: event.target.value })}>
        <option value="all">Todos os status</option>
        {statuses.map((status) => (<option key={status} value={status}>
            {status}
          </option>))}
      </select>

      <select className={selectClass} value={filters.category} onChange={(event) => onChange({ ...filters, category: event.target.value })}>
        <option value="all">Todas as categorias</option>
        {categories.map((category) => (<option key={category} value={category}>
            {category}
          </option>))}
      </select>

      <select className={selectClass} value={filters.provider} onChange={(event) => onChange({ ...filters, provider: event.target.value })}>
        <option value="all">Todos os fornecedores</option>
        {providers.map((provider) => (<option key={provider} value={provider}>
            {provider}
          </option>))}
      </select>

      <select className={selectClass} value={filters.analyst} onChange={(event) => onChange({ ...filters, analyst: event.target.value })}>
        <option value="all">Todos os analistas</option>
        {analysts.map((analyst) => (<option key={analyst} value={analyst}>
            {analyst}
          </option>))}
      </select>

      <input className={selectClass} type="date" value={filters.startDate} onChange={(event) => onChange({ ...filters, startDate: event.target.value })}/>
      <input className={selectClass} type="date" value={filters.endDate} onChange={(event) => onChange({ ...filters, endDate: event.target.value })}/>
    </section>);
};
