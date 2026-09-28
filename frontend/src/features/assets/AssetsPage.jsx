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
  const date = new Date(
    `${value}${String(value).length === 10 ? "T00:00:00" : ""}`,
  );
  return Number.isNaN(date.getTime())
    ? "Não informado"
    : new Intl.DateTimeFormat("pt-BR").format(date);
}

function countFor(store, category) {
  return category === "climatization"
    ? store.climatization_count
    : category === "fire"
      ? store.fire_safety_count
      : category === "water"
        ? store.water_count
        : store.documents_count;
}

/* ── Main page component ────────────────────────────────────────────── */
export default function AssetsPage() {
  const [summary, setSummary]             = useState(null);
  const [stores, setStores]               = useState([]);
  const [pracas, setPracas]               = useState([]);
  const [selectedStore, setSelectedStore] = useState(null);
  const [tab, setTab]                     = useState("overview");
  const [query, setQuery]                 = useState("");
  const [praca, setPraca]                 = useState("");
  const [loading, setLoading]             = useState(true);
  const [summaryLoading, setSummaryLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError]                 = useState("");
  const [toast, setToast]                 = useState(null);
  const [drawer, setDrawer]               = useState(null);
  const [saving, setSaving]               = useState(false);

  const queryRef = useRef(query);
  const pracaRef = useRef(praca);
  const initializedRef = useRef(false);
  queryRef.current = query;
  pracaRef.current = praca;

  const loadStores = useCallback(async (search, region) => {
    const q = search !== undefined ? search : queryRef.current;
    const p = region !== undefined ? region : pracaRef.current;
    try {
      setLoading(true);
      setError("");
      const storeData = await fetchAssetStores({ q, praca: p });
      setStores(storeData);
    } catch (err) {
      if (err?.name !== "AbortError") setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  // Inicializa a Central uma única vez: a sincronização de lojas ocorre no
  // resumo e não é repetida a cada tecla digitada na pesquisa.
  useEffect(() => {
    const controller = new AbortController();
    async function initializeAssets() {
      try {
        setLoading(true);
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
        setLoading(false);
        setSummaryLoading(false);
      }
    }
    initializeAssets();
    return () => controller.abort();
  }, []);

  // Pesquisa/filtro com debounce; atualiza apenas a listagem de lojas.
  useEffect(() => {
    if (!initializedRef.current) return undefined;
    const timer = window.setTimeout(() => {
      loadStores(query, praca);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [query, praca, loadStores]);

  // Auto-dismiss non-confirm toasts
  useEffect(() => {
    if (!toast || toast.kind === "confirm") return undefined;
    const timer = window.setTimeout(() => setToast(null), 3600);
    return () => window.clearTimeout(timer);
  }, [toast]);

  async function openStore(store) {
    try {
      setDetailLoading(true);
      const detail = await fetchAssetStore(store.id);
      setSelectedStore(detail);
      setTab("overview");
    } catch (err) {
      setToast({ kind: "error", message: err.message });
    } finally {
      setDetailLoading(false);
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
      fetchAssetStores({ q: queryRef.current, praca: pracaRef.current }),
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
      if (drawer.item) {
        await updateDocument(drawer.item.id, formData);
      } else {
        await createDocument(selectedStore.id, formData);
      }
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
    ? selectedStore.climatization_count +
      selectedStore.fire_safety_count +
      selectedStore.water_count
    : 0;

  return (
    <section className="assets-page" aria-label="Central de Ativos">
      <Toast toast={toast} />

      {/* ── Home view ─────────────────────────────────────────────────── */}
      {!selectedStore ? (
        <>
          <AssetsHero summary={summary} loading={summaryLoading} />

          <section className="assets-store-section" aria-labelledby="stores-heading">
            <div className="assets-section-heading">
              <div>
                <span className="assets-eyebrow">Base operacional</span>
                <h2 id="stores-heading">Lojas</h2>
                <p>Selecione uma loja para consultar seus equipamentos e documentos.</p>
              </div>
              <span className="assets-section-mark" aria-hidden="true">● Base centralizada</span>
            </div>

            <div className="assets-search-row">
              <label className="assets-search">
                <span aria-hidden="true">⌕</span>
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Pesquisar por loja, BPCS, SAP ou praça..."
                  aria-label="Pesquisar lojas"
                  autoComplete="off"
                />
              </label>
              <select
                value={praca}
                onChange={(event) => setPraca(event.target.value)}
                aria-label="Filtrar por praça"
              >
                <option value="">Todas as praças</option>
                {pracas.map((p) => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
            </div>

            {loading ? (
              <div className="assets-state" role="status" aria-live="polite">
                <span className="assets-loader" aria-hidden="true" />
                <strong>Carregando lojas...</strong>
              </div>
            ) : error ? (
              <div className="assets-state assets-state--error" role="alert">
                <strong>Não foi possível carregar a Central de Ativos.</strong>
                <p>{error}</p>
                <button
                  className="assets-button assets-button--primary"
                  type="button"
                  onClick={() => loadStores()}
                >
                  Tentar novamente
                </button>
              </div>
            ) : stores.length === 0 ? (
              <div className="assets-state">
                <strong>Nenhuma loja encontrada para esta pesquisa.</strong>
                <span>Ajuste os termos e tente novamente.</span>
              </div>
            ) : (
              <div className="assets-store-grid">
                {stores.map((store) => (
                  <button
                    className="assets-store-card"
                    type="button"
                    key={store.id}
                    onClick={() => openStore(store)}
                    aria-label={`Abrir loja ${store.store_name}`}
                  >
                    <span className="assets-store-card__accent" aria-hidden="true" />
                    <div className="assets-store-card__heading">
                      <div>
                        <span className="assets-eyebrow">Loja</span>
                        <h3>{store.store_name}</h3>
                      </div>
                      <span className="assets-arrow" aria-hidden="true">↗</span>
                    </div>
                    <p className="assets-store-card__codes">
                      BPCS {store.bpcs_number || "—"} · SAP{" "}
                      {store.sap_number || "—"} ·{" "}
                      {store.praca || "Praça não informada"}
                    </p>
                    <div className="assets-store-card__counts">
                      <span>❄ {store.climatization_count}</span>
                      <span>🧯 {store.fire_safety_count}</span>
                      <span>💧 {store.water_count}</span>
                      <span>📄 {store.documents_count}</span>
                    </div>
                    <small>Atualizado em {formatDate(store.updated_at)}</small>
                    <span className="assets-store-card__open" aria-hidden="true">
                      Abrir loja <b>→</b>
                    </span>
                  </button>
                ))}
              </div>
            )}
          </section>
        </>
      ) : (
        /* ── Store detail view ────────────────────────────────────────── */
        <>
          <header className="assets-detail-header">
            <button
              className="assets-back"
              type="button"
              onClick={closeStore}
              aria-label="Voltar para Central de Ativos"
            >
              ← Central de Ativos
            </button>
            <div>
              <span className="assets-eyebrow">Ficha técnica da loja</span>
              <h1>{selectedStore.store_name}</h1>
              <p>
                BPCS {selectedStore.bpcs_number || "—"}{" "}
                <i aria-hidden="true" />{" "}
                SAP {selectedStore.sap_number || "—"}{" "}
                <i aria-hidden="true" />{" "}
                {selectedStore.praca || "Praça não informada"}
              </p>
            </div>
            <span className="assets-detail-total" aria-live="polite">
              {detailLoading ? "..." : `${detailCount} equipamentos`}
            </span>
          </header>

          {/* Summary cards */}
          <div className="assets-summary-grid" role="list">
            {[
              ["climatization", "Climatização"],
              ["fire", "Combate a incêndio"],
              ["water", "Purificador / Gelágua"],
              ["documents", "Documentos"],
            ].map(([category, label]) => (
              <button
                type="button"
                key={category}
                className="assets-summary-card"
                role="listitem"
                onClick={() => setTab(category)}
                aria-label={`Ver ${label}: ${countFor(selectedStore, category)} ${category === "documents" ? "documentos" : "equipamentos"}`}
              >
                <AssetGlyph type={category} />
                <span>{label}</span>
                <strong>{countFor(selectedStore, category)}</strong>
                <small>
                  {category === "documents" ? "documentos" : "equipamentos"}
                </small>
              </button>
            ))}
          </div>

          {/* Tabs */}
          <nav className="assets-tabs" aria-label="Seções da loja">
            {TABS.map(([id, label]) => (
              <button
                type="button"
                className={tab === id ? "is-active" : ""}
                key={id}
                aria-current={tab === id ? "true" : undefined}
                onClick={() => setTab(id)}
              >
                {label}
              </button>
            ))}
          </nav>

          {detailLoading ? (
            <div className="assets-state" role="status" aria-live="polite">
              <span className="assets-loader" aria-hidden="true" />
              <strong>Carregando dados da loja...</strong>
            </div>
          ) : (
            <div className="assets-detail-content">
              {/* Overview tab */}
              {tab === "overview" && (
                <div className="assets-overview-grid">
                  {[
                    ["climatization", "Climatização",          selectedStore.climatization],
                    ["fire",          "Combate a incêndio",    selectedStore.fire_safety],
                    ["water",         "Purificadores / Gelágua", selectedStore.water],
                    ["documents",     "Documentos",            selectedStore.documents],
                  ].map(([category, label, items]) => (
                    <article className="assets-overview-card" key={category}>
                      <AssetGlyph type={category} />
                      <div>
                        <span className="assets-eyebrow">{label}</span>
                        <h2>
                          {items?.length ?? 0}{" "}
                          {category === "documents" ? "documentos" : "equipamentos"}
                        </h2>
                        <p>
                          {category === "documents" &&
                          selectedStore.documents_expiring_count > 0
                            ? `${selectedStore.documents_expiring_count} próximo(s) do vencimento`
                            : category === "documents" &&
                              selectedStore.documents_expired_count > 0
                              ? `${selectedStore.documents_expired_count} vencido(s)`
                              : "Cadastro organizado por loja."}
                        </p>
                      </div>
                      <button
                        type="button"
                        className="assets-overview-card__action"
                        onClick={() => setTab(category)}
                        aria-label={`Ver ${label}`}
                      >
                        Ver detalhes →
                      </button>
                    </article>
                  ))}
                </div>
              )}

              {/* Equipment tabs */}
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

              {/* Documents tab */}
              {tab === "documents" && (
                <DocumentsPanel
                  documents={selectedStore.documents}
                  onAdd={() => setDrawer({ type: "document" })}
                  onEdit={(item) => setDrawer({ type: "document", item })}
                  onDelete={confirmDeleteDocument}
                />
              )}
            </div>
          )}
        </>
      )}

      {/* ── Drawers ─────────────────────────────────────────────────── */}
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
