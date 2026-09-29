import { useMemo, useState } from "react";
import { backendFileUrl } from "../api";

const CATEGORY_LABELS = {
  climatization: "Climatização",
  fire: "Combate a incêndio",
  water: "Purificador / Gelágua",
};

function formatDate(value) {
  if (!value) return "Não informado";
  const date = new Date(
    `${value}${String(value).length === 10 ? "T00:00:00" : ""}`,
  );
  return Number.isNaN(date.getTime())
    ? "Não informado"
    : new Intl.DateTimeFormat("pt-BR").format(date);
}

function normalizeText(value = "") {
  return String(value)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

function documentStatusBucket(status) {
  const normalized = normalizeText(status);
  if (normalized.includes("proximo")) return "expiring";
  if (normalized.includes("vencido")) return "expired";
  if (normalized.includes("valido") && !normalized.includes("sem")) return "valid";
  return "no-expiration";
}

function CategoryIcon({ type }) {
  if (type === "climatization") {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true">
        <path d="M12 2v20M4.93 6l14.14 12M4.93 18 19.07 6M8.5 4.5 12 7l3.5-2.5M8.5 19.5 12 17l3.5 2.5M3.5 9 7 12l-3.5 3M20.5 9 17 12l3.5 3" />
      </svg>
    );
  }
  if (type === "fire") {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M9 5h6M10 2h4v3h-4zM9 8h6a2 2 0 0 1 2 2v10H7V10a2 2 0 0 1 2-2Z" />
        <path d="M17 11h2a2 2 0 0 1 2 2v1M7 13H4M4 13v3M9.5 12.5h5" />
      </svg>
    );
  }
  if (type === "water") {
    return (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M12 2s7 7.2 7 13a7 7 0 0 1-14 0c0-5.8 7-13 7-13Z" />
        <path d="M9 16.5c.8 1 1.8 1.5 3 1.5" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" />
      <path d="M14 2v6h6M8 13h8M8 17h6" />
    </svg>
  );
}

export function AssetGlyph({ type, compact = false }) {
  const cls =
    type === "fire"
      ? "--fire"
      : type === "water"
        ? "--water"
        : type === "documents"
          ? "--documents"
          : "";
  return (
    <span
      className={`assets-glyph assets-glyph${cls}${compact ? " assets-glyph--compact" : ""}`}
      aria-hidden="true"
    >
      <CategoryIcon type={type} />
    </span>
  );
}

/* ── Toast / Confirmation modal ─────────────────────────────────────── */
export function Toast({ toast }) {
  if (!toast) return null;
  if (toast.kind === "confirm") {
    return (
      <div className="assets-overlay assets-overlay--center" role="presentation">
        <div
          className="assets-confirmation"
          role="dialog"
          aria-modal="true"
          aria-labelledby="assets-confirmation-title"
        >
          <span className="assets-confirmation__icon" aria-hidden="true">!</span>
          <h2 id="assets-confirmation-title">Confirmar exclusão</h2>
          <p>{toast.message}</p>
          <div className="assets-drawer__actions">
            <button className="assets-button assets-button--quiet" type="button" onClick={toast.onCancel}>
              Cancelar
            </button>
            <button className="assets-button assets-button--danger" type="button" onClick={toast.onConfirm}>
              Excluir
            </button>
          </div>
        </div>
      </div>
    );
  }
  return (
    <div className={`assets-toast assets-toast--${toast.kind}`} role="status">
      {toast.message}
    </div>
  );
}

function MoreMenu({ label, children }) {
  return (
    <details className="assets-more-menu">
      <summary aria-label={label}>•••</summary>
      <div className="assets-more-menu__popover">{children}</div>
    </details>
  );
}

function AssetCard({ item, category, onEdit, onDelete }) {
  const statusCls =
    item.status === "Atenção"
      ? "assets-status--warning"
      : item.status === "Inativo"
        ? "assets-status--inactive"
        : "assets-status--ok";

  const isClimate = category === "climatization";
  const isFire = category === "fire";
  const climateCapacity = item.capacity_btu
    ? `${Number(item.capacity_btu).toLocaleString("pt-BR")} BTUs`
    : "Capacidade não informada";

  return (
    <article className="assets-item-card">
      <div className="assets-item-card__top">
        <AssetGlyph type={category} />
        <span className={`assets-status ${statusCls}`}>{item.status}</span>
      </div>
      <h3>{item.asset_code}</h3>
      <p className="assets-item-card__identity">
        <strong>
          {item.equipment_type}
          {isClimate ? ` · ${climateCapacity}` : ""}
        </strong>
        {item.location ? (
          <span className="assets-location">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M20 10c0 5-8 12-8 12S4 15 4 10a8 8 0 1 1 16 0Z" />
              <circle cx="12" cy="10" r="2.5" />
            </svg>
            {item.location}
          </span>
        ) : null}
      </p>
      <div className="assets-item-card__meta">
        {isClimate ? (
          <>
            {(item.brand || item.manufacture_year) && (
              <span>{[item.brand, item.manufacture_year].filter(Boolean).join(" · ")}</span>
            )}
            {item.model && <span>Modelo: {item.model}</span>}
          </>
        ) : isFire ? (
          <>
            {item.extinguisher_agent && <span>Agente: {item.extinguisher_agent}</span>}
            {item.capacity && <span>Capacidade: {item.capacity}</span>}
          </>
        ) : (
          <>
            {(item.brand || item.manufacture_year) && (
              <span>{[item.brand, item.manufacture_year].filter(Boolean).join(" · ")}</span>
            )}
            {item.model && <span>Modelo: {item.model}</span>}
          </>
        )}
        {item.expiration_date && (
          <span className="assets-item-card__expiry">Validade: {formatDate(item.expiration_date)}</span>
        )}
        {item.next_filter_change && (
          <span className="assets-item-card__expiry">Próxima troca: {formatDate(item.next_filter_change)}</span>
        )}
      </div>
      <div className="assets-item-card__actions assets-item-card__actions--clean">
        <button type="button" className="assets-action-primary" onClick={() => onEdit(item)}>
          Editar
        </button>
        <MoreMenu label={`Mais ações para ${item.asset_code}`}>
          <button type="button" className="danger" onClick={() => onDelete(item)}>
            Excluir equipamento
          </button>
        </MoreMenu>
      </div>
    </article>
  );
}

/* ── Document card ──────────────────────────────────────────────────── */
function DocumentCard({ document, onEdit, onDelete }) {
  const statusKey = normalizeText(document.status).replace(/\s+/g, "-");
  return (
    <article className="assets-document-card">
      <div className="assets-document-card__top">
        <AssetGlyph type="documents" />
        <span className={`assets-document-status assets-document-status--${statusKey}`}>
          {document.status}
        </span>
      </div>
      <h3>
        {document.document_type === "Outro"
          ? (document.custom_document_type || "Outro")
          : document.document_type}
      </h3>
      <p>{document.document_number || "Sem número informado"}</p>
      <dl>
        {document.expiration_date && (
          <div>
            <dt>Validade</dt>
            <dd>{formatDate(document.expiration_date)}</dd>
          </div>
        )}
        <div>
          <dt>Arquivo</dt>
          <dd title={document.original_filename}>{document.original_filename}</dd>
        </div>
      </dl>
      <div className="assets-item-card__actions assets-item-card__actions--document">
        <a
          className="assets-action-primary"
          href={backendFileUrl(document.id)}
          target="_blank"
          rel="noreferrer"
          aria-label={`Visualizar ${document.original_filename}`}
        >
          Visualizar
        </a>
        <a
          className="assets-action-icon"
          href={backendFileUrl(document.id, true)}
          download
          aria-label={`Baixar ${document.original_filename}`}
          title="Baixar documento"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M12 3v12M7 10l5 5 5-5M5 21h14" />
          </svg>
        </a>
        <MoreMenu label={`Mais ações para ${document.original_filename}`}>
          <button type="button" onClick={() => onEdit(document)}>Editar informações</button>
          <button type="button" className="danger" onClick={() => onDelete(document)}>Excluir documento</button>
        </MoreMenu>
      </div>
    </article>
  );
}

/* ── Category panel ─────────────────────────────────────────────────── */
export function CategoryPanel({ category, items, onAdd, onEdit, onDelete }) {
  return (
    <section className="assets-panel" aria-labelledby={`panel-title-${category}`}>
      <div className="assets-panel__heading">
        <div>
          <span className="assets-eyebrow">Inventário individual</span>
          <h2 id={`panel-title-${category}`}>{CATEGORY_LABELS[category]}</h2>
          <p>{items.length} {items.length === 1 ? "equipamento cadastrado" : "equipamentos cadastrados"} nesta loja.</p>
        </div>
        <button className="assets-button assets-button--primary" type="button" onClick={onAdd}>
          + Adicionar equipamento
        </button>
      </div>
      {items.length > 0 ? (
        <div className="assets-items-grid">
          {items.map((item) => (
            <AssetCard
              key={item.id}
              item={item}
              category={category}
              onEdit={onEdit}
              onDelete={onDelete}
            />
          ))}
        </div>
      ) : (
        <div className="assets-state assets-state--compact">
          <AssetGlyph type={category} />
          <strong>Nenhum equipamento de {CATEGORY_LABELS[category].toLowerCase()} cadastrado nesta loja.</strong>
          <span>Comece adicionando o primeiro item deste inventário.</span>
          <button className="assets-button assets-button--primary" type="button" onClick={onAdd}>
            + Adicionar equipamento
          </button>
        </div>
      )}
    </section>
  );
}

/* ── Documents panel ────────────────────────────────────────────────── */
export function DocumentsPanel({ documents, onAdd, onEdit, onDelete }) {
  const [filter, setFilter] = useState("all");

  const counts = useMemo(() => {
    const next = { all: documents.length, expired: 0, expiring: 0, valid: 0, "no-expiration": 0 };
    documents.forEach((document) => {
      next[documentStatusBucket(document.status)] += 1;
    });
    return next;
  }, [documents]);

  const visibleDocuments = useMemo(
    () => documents.filter((document) => filter === "all" || documentStatusBucket(document.status) === filter),
    [documents, filter],
  );

  const filters = [
    ["all", "Todos"],
    ["expired", "Vencidos"],
    ["expiring", "Vencendo"],
    ["valid", "Válidos"],
  ];

  return (
    <section className="assets-panel" aria-labelledby="panel-title-documents">
      <div className="assets-panel__heading">
        <div>
          <span className="assets-eyebrow">Arquivo documental</span>
          <h2 id="panel-title-documents">Documentos</h2>
          <p>Consulte rapidamente validade, arquivo e situação documental da loja.</p>
        </div>
        <button className="assets-button assets-button--primary" type="button" onClick={onAdd}>
          + Adicionar documento
        </button>
      </div>

      {documents.length > 0 ? (
        <>
          <div className="assets-document-filters" aria-label="Filtrar documentos por status">
            {filters.map(([id, label]) => (
              <button
                key={id}
                type="button"
                className={filter === id ? "is-active" : ""}
                onClick={() => setFilter(id)}
                aria-pressed={filter === id}
              >
                {label} <strong>{counts[id]}</strong>
              </button>
            ))}
          </div>
          {visibleDocuments.length > 0 ? (
            <div className="assets-items-grid">
              {visibleDocuments.map((doc) => (
                <DocumentCard
                  key={doc.id}
                  document={doc}
                  onEdit={onEdit}
                  onDelete={onDelete}
                />
              ))}
            </div>
          ) : (
            <div className="assets-state assets-state--compact">
              <AssetGlyph type="documents" />
              <strong>Nenhum documento neste filtro.</strong>
              <span>Selecione outro status para visualizar os demais documentos.</span>
            </div>
          )}
        </>
      ) : (
        <div className="assets-state assets-state--compact">
          <AssetGlyph type="documents" />
          <strong>Nenhum documento cadastrado.</strong>
          <span>Adicione AVCB, certificado de dedetização ou outro documento da loja.</span>
          <button className="assets-button assets-button--primary" type="button" onClick={onAdd}>
            + Adicionar documento
          </button>
        </div>
      )}
    </section>
  );
}
