import { useCallback, useEffect, useRef, useState } from "react";
import {
  createAsset,
  createDocument,
  fetchAssetStore,
  fetchAssetStoreFilters,
  fetchAssetStores,
  fetchAssetSummary,
  removeAsset,
  removeDocument,
  updateAsset,
  updateDocument,
} from "./api";
import "./assets.css";
import { AssetForm, DocumentForm } from "./components/AssetForms";
import { AssetsHero } from "./components/AssetsHero";
import { AssetGlyph, CategoryPanel, DocumentsPanel, Toast } from "./components/AssetPanels";

const TABS = [
  ["overview", "Visão geral"],
  ["climatization", "Climatização"],
  ["fire", "Combate a incêndio"],
  ["water", "Purificador / Gelágua"],
  ["documents", "Documentos"],
];

function formatDate(value) {
  if (!value) return "Não informado";
  const date = new Date(`${value}${String(value).length === 10 ? "T00:00:00" : ""}`);
  return Number.isNaN(date.getTime())
    ? "Não informado"
    : new Intl.DateTimeFormat("pt-BR").format(date);
}

function daysUntil(value) {
  if (!value) return null;
  const date = new Date(`${value}${String(value).length === 10 ? "T00:00:00" : ""}`);
  if (Number.isNaN(date.getTime())) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.ceil((date.getTime() - today.getTime()) / 86400000);
}

function statusInsight(items = []) {
  const attention = items.filter((item) => item.status === "Atenção").length;
  const inactive = items.filter((item) => item.status === "Inativo").length;
  const operational = items.filter((item) => item.status === "Operacional").length;
  if (attention > 0) return { text: `${attention} em atenção${operational ? ` · ${operational} operacional(is)` : ""}`, tone: "warning" };
  if (inactive > 0) return { text: `${inactive} inativo(s)${operational ? ` · ${operational} operacional(is)` : ""}`, tone: "muted" };
  if (operational > 0) return { text: `${operational} operacional(is)`, tone: "ok" };
  return { text: "Nenhum status registrado.", tone: "muted" };
}

function overviewInsight(store, category, items = []) {
  if (category === "documents") {
    const expired = store.documents_expired_count || 0;
    const expiring = store.documents_expiring_count || 0;
    if (expired > 0) {
      return {
        text: `${expired} vencido(s)${expiring ? ` · ${expiring} vence(m) em até 60 dias` : ""}`,
        tone: "danger",
      };
    }
    if (expiring > 0) return { text: `${expiring} vence(m) em até 60 dias`, tone: "warning" };
    return { text: items.length ? "Documentação sem pendências de validade." : "Nenhum documento cadastrado.", tone: items.length ? "ok" : "muted" };
  }

  if (category === "fire") {
    const dated = items
      .map((item) => ({ item, days: daysUntil(item.expiration_date) }))
      .filter(({ days }) => days !== null)
      .sort((a, b) => a.days - b.days);
    const expired = dated.filter(({ days }) => days < 0).length;
    const expiring = dated.filter(({ days }) => days >= 0 && days <= 60).length;
    if (expired > 0) return { text: `${expired} com validade vencida`, tone: "danger" };
    if (expiring > 0) return { text: `${expiring} vence(m) em até 60 dias`, tone: "warning" };
    if (dated[0]) return { text: `Próxima validade: ${formatDate(dated[0].item.expiration_date)}`, tone: "ok" };
    return statusInsight(items);
  }

  if (category === "water") {
    const filterDates = items
      .filter((item) => item.next_filter_change)
      .map((item) => ({ item, days: daysUntil(item.next_filter_change) }))
      .filter(({ days }) => days !== null)
      .sort((a, b) => a.days - b.days);
    if (filterDates[0]) {
      const { item, days } = filterDates[0];
      if (days < 0) return { text: `Troca de filtro vencida em ${formatDate(item.next_filter_change)}`, tone: "danger" };
      if (days <= 30) return { text: `Próxima troca: ${formatDate(item.next_filter_change)}`, tone: "warning" };
      return { text: `Próxima troca: ${formatDate(item.next_filter_change)}`, tone: "ok" };
    }
    return statusInsight(items);
  }

  return statusInsight(items);
}

function SearchIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.6-3.6" />
    </svg>
  );
}

/* ── Main page component ────────────────────────────────────────────── */
export default function AssetsPage() {
  const [summary, setSummary] = useState(null);
  const [stores, setStores] = useState([]);
  const [pracas, setPracas] = useState([]);
  const [selectedStore, setSelectedStore] = useState(null);
  const [tab, setTab] = useState("overview");
  const [query, setQuery] = useState("");
  const [praca, setPraca] = useState("");
  const [initialLoading, setInitialLoading] = useState(true);
  const [searching, setSearching] = useState(false);
  const [summaryLoading, setSummaryLoading] = useState(true);
  const [openingStoreId, setOpeningStoreId] = useState(null);
  const [error, setError] = useState("");
  const [toast, setToast] = useState(null);
  const [drawer, setDrawer] = useState(null);
  const [saving, setSaving] = useState(false);

  const initializedRef = useRef(false);
  const searchControllerRef = useRef(null);
  const loadStores = useCallback(async (search, region) => {
    const q = search !== undefined ? search : query;
    const p = region !== undefined ? region : praca;
    searchControllerRef.current?.abort();
    const controller = new AbortController();
    searchControllerRef.current = controller;
    try {
      setSearching(true);
      setError("");
      const storeData = await fetchAssetStores({ q, praca: p, signal: controller.signal });
      setStores(storeData);
    } catch (err) {
      if (err?.name !== "AbortError") setError(err.message);
    } finally {
      if (searchControllerRef.current === controller) {
        searchControllerRef.current = null;
        setSearching(false);
      }
    }
  }, [query, praca]);

  useEffect(() => {
    const controller = new AbortController();
    async function initializeAssets() {
      try {
        setInitialLoading(true);
        setSummaryLoading(true);
        setError("");
        const summaryData = await fetchAssetSummary({ signal: controller.signal });
        setSummary(summaryData);
        const [filtersData, storeData] = await Promise.all([
          fetchAssetStoreFilters({ signal: controller.signal }),
          fetchAssetStores({ signal: controller.signal }),
        ]);
        setPracas(filtersData?.pracas || []);
        setStores(storeData);
        initializedRef.current = true;
      } catch (err) {
        if (err?.name !== "AbortError") setError(err.message);
      } finally {
        setInitialLoading(false);
        setSummaryLoading(false);
      }
    }
    initializeAssets();
    return () => {
      controller.abort();
      searchControllerRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (!initializedRef.current) return undefined;
    const timer = window.setTimeout(() => loadStores(query, praca), 300);
    return () => window.clearTimeout(timer);
  }, [query, praca, loadStores]);

  useEffect(() => {
    if (!toast || toast.kind === "confirm") return undefined;
    const timer = window.setTimeout(() => setToast(null), 3600);
    return () => window.clearTimeout(timer);
  }, [toast]);

  async function openStore(store) {
    if (openingStoreId !== null) return;
    try {
      setOpeningStoreId(store.id);
      const detail = await fetchAssetStore(store.id);
      setSelectedStore(detail);
      setTab("overview");
    } catch (err) {
      setToast({ kind: "error", message: err.message });
    } finally {
      setOpeningStoreId(null);
    }
  }

  function closeStore() {
    setSelectedStore(null);
    setDrawer(null);
  }

  async function refreshStore() {
    const summaryData = await fetchAssetSummary();
    setSummary(summaryData);
    const requests = [
      fetchAssetStores({ q: query, praca }),
      fetchAssetStoreFilters(),
    ];
    if (selectedStore) requests.push(fetchAssetStore(selectedStore.id));
    const [storeData, filtersData, detail] = await Promise.all(requests);
    setStores(storeData);
    setPracas(filtersData?.pracas || []);
    if (detail) setSelectedStore(detail);
  }

  async function saveAsset(category, payload) {
    try {
      setSaving(true);
      if (drawer.item) await updateAsset(category, drawer.item.id, payload);
      else await createAsset(selectedStore.id, category, payload);
      setDrawer(null);
      setToast({ kind: "success", message: "Equipamento salvo com sucesso." });
      await refreshStore();
    } catch (err) {
      setToast({ kind: "error", message: err.message });
    } finally {
      setSaving(false);
    }
  }

  function confirmDeleteItem(category, item) {
    setToast({
      kind: "confirm",
      message: `Excluir ${item.asset_code}? Esta ação não pode ser desfeita.`,
      onCancel: () => setToast(null),
      onConfirm: async () => {
        setToast(null);
        try {
          await removeAsset(category, item.id);
          setToast({ kind: "success", message: "Equipamento excluído." });
          await refreshStore();
        } catch (err) {
          setToast({ kind: "error", message: err.message });
        }
      },
    });
  }

  async function saveDocument(formData) {
    try {
      setSaving(true);
      if (drawer.item) await updateDocument(drawer.item.id, formData);
      else await createDocument(selectedStore.id, formData);
      setDrawer(null);
      setToast({ kind: "success", message: "Documento salvo com sucesso." });
      await refreshStore();
    } catch (err) {
      setToast({ kind: "error", message: err.message });
    } finally {
      setSaving(false);
    }
  }

  function confirmDeleteDocument(doc) {
    setToast({
      kind: "confirm",
      message: `Excluir ${doc.original_filename}? O arquivo também será removido.`,
      onCancel: () => setToast(null),
      onConfirm: async () => {
        setToast(null);
        try {
          await removeDocument(doc.id);
          setToast({ kind: "success", message: "Documento excluído." });
          await refreshStore();
        } catch (err) {
          setToast({ kind: "error", message: err.message });
        }
      },
    });
  }

  const detailCount = selectedStore
    ? selectedStore.climatization_count + selectedStore.fire_safety_count + selectedStore.water_count
    : 0;
  const hasFilters = Boolean(query.trim() || praca);

  return (
    <section className="assets-page" aria-label="Central de Ativos">
      <Toast toast={toast} />

      {!selectedStore ? (
        <>
          <AssetsHero summary={summary} loading={summaryLoading} />

          <section className="assets-store-section" aria-labelledby="stores-heading">
            <div className="assets-section-heading">
              <div>
                <span className="assets-eyebrow">Base operacional</span>
                <h2 id="stores-heading">Lojas</h2>
                <p>Encontre a loja e acesse rapidamente seus equipamentos e documentos.</p>
              </div>
              <span className="assets-section-mark" aria-hidden="true">● Base centralizada</span>
            </div>

            <div className="assets-search-row">
              <label className="assets-search">
                <span className="assets-search__icon" aria-hidden="true"><SearchIcon /></span>
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Pesquisar por loja, BPCS, SAP ou praça..."
                  aria-label="Pesquisar lojas"
                  autoComplete="off"
                />
                {searching ? <span className="assets-search__spinner" aria-label="Pesquisando" /> : null}
              </label>
              <select value={praca} onChange={(event) => setPraca(event.target.value)} aria-label="Filtrar por praça">
                <option value="">Todas as praças</option>
                {pracas.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>

            <div className="assets-search-meta" aria-live="polite">
              <span>
                <strong>{stores.length}</strong> {stores.length === 1 ? "loja encontrada" : "lojas encontradas"}
                {searching ? " · atualizando resultados..." : ""}
              </span>
              {hasFilters ? (
                <div className="assets-active-filters">
                  {query.trim() ? (
                    <button type="button" onClick={() => setQuery("")} title="Remover pesquisa">
                      Pesquisa: {query.trim()} <b aria-hidden="true">×</b>
                    </button>
                  ) : null}
                  {praca ? (
                    <button type="button" onClick={() => setPraca("")} title="Remover filtro de praça">
                      Praça: {praca} <b aria-hidden="true">×</b>
                    </button>
                  ) : null}
                  <button className="assets-clear-filters" type="button" onClick={() => { setQuery(""); setPraca(""); }}>
                    Limpar filtros
                  </button>
                </div>
              ) : null}
            </div>

            {error && stores.length > 0 ? <p className="assets-inline-error" role="alert">{error}</p> : null}

            {initialLoading && stores.length === 0 ? (
              <div className="assets-state" role="status" aria-live="polite">
                <span className="assets-loader" aria-hidden="true" />
                <strong>Carregando lojas...</strong>
              </div>
            ) : error && stores.length === 0 ? (
              <div className="assets-state assets-state--error" role="alert">
                <strong>Não foi possível carregar a Central de Ativos.</strong>
                <p>{error}</p>
                <button className="assets-button assets-button--primary" type="button" onClick={() => loadStores()}>
                  Tentar novamente
                </button>
              </div>
            ) : stores.length === 0 ? (
              <div className="assets-state assets-state--compact">
                <span className="assets-empty-search" aria-hidden="true"><SearchIcon /></span>
                <strong>Nenhuma loja encontrada para esta pesquisa.</strong>
                <span>Ajuste os termos ou limpe os filtros para visualizar outras lojas.</span>
                {hasFilters ? (
                  <button className="assets-button assets-button--quiet" type="button" onClick={() => { setQuery(""); setPraca(""); }}>
                    Limpar filtros
                  </button>
                ) : null}
              </div>
            ) : (
              <div className={`assets-store-grid${searching ? " is-searching" : ""}`}>
                {stores.map((store) => {
                  const isOpening = openingStoreId === store.id;
                  return (
                    <button
                      className={`assets-store-card${isOpening ? " is-opening" : ""}`}
                      type="button"
                      key={store.id}
                      onClick={() => openStore(store)}
                      disabled={openingStoreId !== null}
                      aria-label={`Abrir loja ${store.store_name}`}
                    >
                      <span className="assets-store-card__accent" aria-hidden="true" />
                      <div className="assets-store-card__heading">
                        <div>
                          <span className="assets-eyebrow">Loja</span>
                          <h3>{store.store_name}</h3>
                        </div>
                      </div>
                      <p className="assets-store-card__codes">
                        BPCS {store.bpcs_number || "—"} · SAP {store.sap_number || "—"} · {store.praca || "Praça não informada"}
                      </p>
                      <div className="assets-store-card__counts" aria-label="Resumo do inventário">
                        <span><AssetGlyph type="climatization" compact /><b>{store.climatization_count}</b> Climatização</span>
                        <span><AssetGlyph type="fire" compact /><b>{store.fire_safety_count}</b> Incêndio</span>
                        <span><AssetGlyph type="water" compact /><b>{store.water_count}</b> Água</span>
                        <span><AssetGlyph type="documents" compact /><b>{store.documents_count}</b> Documentos</span>
                      </div>
                      <span className="assets-store-card__open" aria-hidden="true">
                        {isOpening ? <><span className="assets-mini-loader" /> Abrindo loja...</> : <>Abrir loja <b>→</b></>}
                      </span>
                    </button>
                  );
                })}
              </div>
            )}
          </section>
        </>
      ) : (
        <>
          <header className="assets-detail-header">
            <button className="assets-back" type="button" onClick={closeStore} aria-label="Voltar para Central de Ativos">
              ← Central de Ativos
            </button>
            <div>
              <span className="assets-eyebrow">Ficha técnica da loja</span>
              <h1>{selectedStore.store_name}</h1>
              <p>
                BPCS {selectedStore.bpcs_number || "—"} <i aria-hidden="true" /> SAP {selectedStore.sap_number || "—"} <i aria-hidden="true" /> {selectedStore.praca || "Praça não informada"}
              </p>
            </div>
            <span className="assets-detail-total" aria-live="polite">
              {detailCount} {detailCount === 1 ? "equipamento" : "equipamentos"} · {selectedStore.documents_count} {selectedStore.documents_count === 1 ? "documento" : "documentos"}
            </span>
          </header>

          <nav className="assets-tabs" aria-label="Seções da loja">
            {TABS.map(([id, label]) => (
              <button
                type="button"
                className={tab === id ? "is-active" : ""}
                key={id}
                aria-current={tab === id ? "page" : undefined}
                onClick={() => setTab(id)}
              >
                {label}
              </button>
            ))}
          </nav>

          <div className="assets-detail-content">
            {tab === "overview" && (
              <div className="assets-overview-grid">
                {[
                  ["climatization", "Climatização", selectedStore.climatization],
                  ["fire", "Combate a incêndio", selectedStore.fire_safety],
                  ["water", "Purificadores / Gelágua", selectedStore.water],
                  ["documents", "Documentos", selectedStore.documents],
                ].map(([category, label, items]) => {
                  const insight = overviewInsight(selectedStore, category, items || []);
                  return (
                    <article className="assets-overview-card" key={category}>
                      <AssetGlyph type={category} />
                      <div className="assets-overview-card__body">
                        <span className="assets-eyebrow">{label}</span>
                        <h2>{items?.length ?? 0} {category === "documents" ? "documentos" : "equipamentos"}</h2>
                        <p className={`assets-overview-insight assets-overview-insight--${insight.tone}`}>{insight.text}</p>
                      </div>
                      <button type="button" className="assets-overview-card__action" onClick={() => setTab(category)} aria-label={`Ver ${label}`}>
                        Ver {category === "documents" ? "documentos" : "equipamentos"} →
                      </button>
                    </article>
                  );
                })}
              </div>
            )}

            {tab !== "overview" && tab !== "documents" && (
              <CategoryPanel
                category={tab}
                items={
                  tab === "climatization"
                    ? selectedStore.climatization
                    : tab === "fire"
                      ? selectedStore.fire_safety
                      : selectedStore.water
                }
                onAdd={() => setDrawer({ type: "asset", category: tab })}
                onEdit={(item) => setDrawer({ type: "asset", category: tab, item })}
                onDelete={(item) => confirmDeleteItem(tab, item)}
              />
            )}

            {tab === "documents" && (
              <DocumentsPanel
                documents={selectedStore.documents}
                onAdd={() => setDrawer({ type: "document" })}
                onEdit={(item) => setDrawer({ type: "document", item })}
                onDelete={confirmDeleteDocument}
              />
            )}
          </div>
        </>
      )}

      {drawer?.type === "asset" && (
        <AssetForm
          category={drawer.category}
          initial={drawer.item}
          onCancel={() => setDrawer(null)}
          onSave={(payload) => saveAsset(drawer.category, payload)}
          saving={saving}
        />
      )}
      {drawer?.type === "document" && (
        <DocumentForm
          initial={drawer.item}
          onCancel={() => setDrawer(null)}
          onSave={saveDocument}
          saving={saving}
        />
      )}
    </section>
  );
}
