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

export function AssetGlyph({ type }) {
  const map = {
    climatization: { icon: "❄", cls: "" },
    fire: { icon: "🧯", cls: "--fire" },
    water: { icon: "💧", cls: "--water" },
    documents: { icon: "📄", cls: "--documents" },
  };
  const { icon, cls } = map[type] || map.documents;
  return (
    <span className={`assets-glyph assets-glyph${cls}`} aria-hidden="true">
      {icon}
    </span>
  );
}

/* ── Toast / Confirmation modal ─────────────────────────────────────── */
export function Toast({ toast }) {
  if (!toast) return null;
  if (toast.kind === "confirm") {
    return (
      <div
        className="assets-overlay assets-overlay--center"
        role="presentation"
      >
        <div
          className="assets-confirmation"
          role="dialog"
          aria-modal="true"
          aria-labelledby="assets-confirmation-title"
        >
          <span className="assets-glyph assets-glyph--documents">!</span>
          <h2 id="assets-confirmation-title">Confirmar exclusão</h2>
          <p>{toast.message}</p>
          <div className="assets-drawer__actions">
            <button
              className="assets-button assets-button--quiet"
              type="button"
              onClick={toast.onCancel}
            >
              Cancelar
            </button>
            <button
              className="assets-button assets-button--danger"
              type="button"
              onClick={toast.onConfirm}
            >
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
        {item.location ? <span>📍 {item.location}</span> : null}
      </p>
      <div className="assets-item-card__meta">
        {isClimate ? (
          <>
            {(item.brand || item.manufacture_year) && (
              <span>
                {[item.brand, item.manufacture_year].filter(Boolean).join(" · ")}
              </span>
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
              <span>
                {[item.brand, item.manufacture_year].filter(Boolean).join(" · ")}
              </span>
            )}
            {item.model && <span>Modelo: {item.model}</span>}
          </>
        )}
        {item.expiration_date && (
          <span className="assets-item-card__expiry">
            Validade: {formatDate(item.expiration_date)}
          </span>
        )}
        {item.next_filter_change && (
          <span className="assets-item-card__expiry">
            Próxima troca: {formatDate(item.next_filter_change)}
          </span>
        )}
      </div>
      <div className="assets-item-card__actions">
        <button
          type="button"
          aria-label={`Editar ${item.asset_code}`}
          onClick={() => onEdit(item)}
        >
          Editar
        </button>
        <button
          type="button"
          className="danger"
          aria-label={`Excluir ${item.asset_code}`}
          onClick={() => onDelete(item)}
        >
          Excluir
        </button>
      </div>
    </article>
  );
}

/* ── Document card ──────────────────────────────────────────────────── */
function DocumentCard({ document, onEdit, onDelete }) {
  const statusKey = document.status
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, "-")
    .toLowerCase();
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
      <div className="assets-item-card__actions">
        <a
          href={backendFileUrl(document.id)}
          target="_blank"
          rel="noreferrer"
          aria-label={`Visualizar ${document.original_filename}`}
        >
          Visualizar
        </a>
        <a
          href={backendFileUrl(document.id, true)}
          download
          aria-label={`Baixar ${document.original_filename}`}
        >
          Baixar
        </a>
        <button type="button" onClick={() => onEdit(document)}>
          Editar
        </button>
        <button
          type="button"
          className="danger"
          aria-label={`Excluir ${document.original_filename}`}
          onClick={() => onDelete(document)}
        >
          Excluir
        </button>
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
          <p>Cada equipamento possui identificação própria e histórico técnico.</p>
        </div>
        <button
          className="assets-button assets-button--primary"
          type="button"
          onClick={onAdd}
        >
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
        <div className="assets-state">
          <strong>
            Nenhum equipamento de {CATEGORY_LABELS[category].toLowerCase()} cadastrado nesta loja.
          </strong>
          <button
            className="assets-button assets-button--primary"
            type="button"
            onClick={onAdd}
          >
            + Adicionar equipamento
          </button>
        </div>
      )}
    </section>
  );
}

/* ── Documents panel ────────────────────────────────────────────────── */
export function DocumentsPanel({ documents, onAdd, onEdit, onDelete }) {
  return (
    <section className="assets-panel" aria-labelledby="panel-title-documents">
      <div className="assets-panel__heading">
        <div>
          <span className="assets-eyebrow">Arquivo documental</span>
          <h2 id="panel-title-documents">Documentos</h2>
          <p>Certificados e documentos com validade calculada automaticamente.</p>
        </div>
        <button
          className="assets-button assets-button--primary"
          type="button"
          onClick={onAdd}
        >
          + Adicionar documento
        </button>
      </div>
      {documents.length > 0 ? (
        <div className="assets-items-grid">
          {documents.map((doc) => (
            <DocumentCard
              key={doc.id}
              document={doc}
              onEdit={onEdit}
              onDelete={onDelete}
            />
          ))}
        </div>
      ) : (
        <div className="assets-state">
          <strong>Nenhum documento cadastrado.</strong>
          <button
            className="assets-button assets-button--primary"
            type="button"
            onClick={onAdd}
          >
            + Adicionar documento
          </button>
        </div>
      )}
    </section>
  );
}

