import { EMPTY_FILTERS, isFiltered, matchesStore, storesCountLabel, storesForPracas, withPracas } from "../filters";
import { MultiSelect } from "../../../components/MultiSelect";

export function AssetFilters({ pracas, storeOptions, filters, onChange, shownCount, searching }) {
  const pracaChoices = pracas.map((praca) => ({ value: praca, label: praca }));
  const storeChoices = storesForPracas(storeOptions, filters.pracas).map((option) => ({
    value: option.id,
    label: option.name,
    hint: [option.praca, option.bpcs && `BPCS ${option.bpcs}`, option.sap && `SAP ${option.sap}`].filter(Boolean).join(" · "),
    option,
  }));
  const storeNames = new Map(storeOptions.map((option) => [option.id, option.name]));

  return (
    <>
      <div className="assets-filter-row">
        <MultiSelect
          label="Praças" options={pracaChoices} selected={filters.pracas} allLabel="Todas as praças"
          unit={["praça", "praças"]}
          onChange={(next) => onChange(withPracas(filters, storeOptions, next))}
        />
        <MultiSelect
          label="Lojas" options={storeChoices} selected={filters.storeIds} allLabel="Todas as lojas"
          unit={["loja", "lojas"]} emptyText="Nenhuma loja nessas praças."
          filterOption={(choice, text) => matchesStore(choice.option, text)}
          onChange={(next) => onChange({ ...filters, storeIds: next })}
        />
      </div>

      <div className="assets-search-meta" aria-live="polite">
        <span>
          <strong>{storesCountLabel(shownCount, Math.max(storeOptions.length, shownCount))}</strong>
          {searching ? " · atualizando resultados..." : ""}
        </span>
        {isFiltered(filters) ? (
          <div className="assets-active-filters">
            {filters.pracas.map((praca) => (
              <button key={`p-${praca}`} type="button" title="Remover praça"
                      onClick={() => onChange(withPracas(filters, storeOptions, filters.pracas.filter((item) => item !== praca)))}>
                Praça: {praca} <b aria-hidden="true">×</b>
              </button>
            ))}
            {filters.storeIds.map((id) => (
              <button key={`l-${id}`} type="button" title="Remover loja"
                      onClick={() => onChange({ ...filters, storeIds: filters.storeIds.filter((item) => item !== id) })}>
                Loja: {storeNames.get(id) ?? id} <b aria-hidden="true">×</b>
              </button>
            ))}
            <button className="assets-clear-filters" type="button" onClick={() => onChange(EMPTY_FILTERS)}>
              Limpar filtros
            </button>
          </div>
        ) : null}
      </div>
    </>
  );
}
