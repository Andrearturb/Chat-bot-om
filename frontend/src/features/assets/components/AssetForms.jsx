import { useState } from "react";
import { buildAssetPayload, buildDocumentFormData } from "../formUtils";

const EMPTY_ASSET = {
  equipment_type: "Ar-condicionado",
  capacity_btu: "",
  location: "",
  brand: "",
  model: "",
  serial_number: "",
  manufacture_year: "",
  installation_year: "",
  voltage: "",
  refrigerant_gas: "",
  status: "Operacional",
  notes: "",
  extinguisher_agent: "",
  capacity: "",
  expiration_date: "",
  hydrostatic_test_date: "",
  last_filter_change: "",
  next_filter_change: "",
};

function Field({ label, type, value, onChange, required = false }) {
  return (
    <label className="assets-field">
      <span>{label}</span>
      {type === "select" ? (
        <select
          value={value || "Operacional"}
          onChange={(event) => onChange(event.target.value)}
        >
          <option>Operacional</option>
          <option>Atenção</option>
          <option>Inativo</option>
        </select>
      ) : type === "select-water" ? (
        <select
          value={value || "Purificador"}
          onChange={(event) => onChange(event.target.value)}
        >
          <option>Purificador</option>
          <option>Gelágua</option>
        </select>
      ) : (
        <input
          type={type}
          value={value ?? ""}
          onChange={(event) => onChange(event.target.value)}
          required={required}
        />
      )}
    </label>
  );
}

/* ── Asset form drawer ──────────────────────────────────────────────── */
export function AssetForm({ category, initial, onCancel, onSave, saving }) {
  const isFire = category === "fire";
  const isWater = category === "water";
  const categoryDefaults = isFire
    ? { equipment_type: "Extintor" }
    : isWater
      ? { equipment_type: "Purificador" }
      : { equipment_type: "Ar-condicionado" };
  const [form, setForm] = useState({
    ...EMPTY_ASSET,
    ...categoryDefaults,
    ...initial,
  });

  const fields = isFire
    ? [
        ["equipment_type", "Tipo", "text", true],
        ["extinguisher_agent", "Agente extintor", "text", false],
        ["capacity", "Capacidade", "text", false],
        ["location", "Localização", "text", true],
        ["manufacture_year", "Ano de fabricação", "number", false],
        ["expiration_date", "Data de validade", "date", false],
        ["hydrostatic_test_date", "Teste hidrostático", "date", false],
        ["status", "Status", "select", false],
      ]
    : isWater
      ? [
          ["equipment_type", "Tipo", "select-water", false],
          ["location", "Localização", "text", true],
          ["brand", "Marca", "text", false],
          ["model", "Modelo", "text", false],
          ["serial_number", "Número de série", "text", false],
          ["manufacture_year", "Ano de fabricação", "number", false],
          ["installation_year", "Ano de instalação", "number", false],
          ["voltage", "Tensão", "text", false],
          ["last_filter_change", "Última troca do filtro", "date", false],
          ["next_filter_change", "Próxima troca do filtro", "date", false],
          ["status", "Status", "select", false],
        ]
      : [
          ["equipment_type", "Tipo de equipamento", "text", true],
          ["capacity_btu", "Capacidade (BTUs)", "number", true],
          ["location", "Localização", "text", true],
          ["status", "Status", "select", false],
          ["brand", "Fabricante", "text", false],
          ["model", "Modelo", "text", false],
          ["serial_number", "Número de série", "text", false],
          ["manufacture_year", "Ano de fabricação", "number", false],
          ["installation_year", "Ano de instalação", "number", false],
          ["voltage", "Tensão", "text", false],
          ["refrigerant_gas", "Gás refrigerante", "text", false],
        ];

  const mainCount = 4;
  const mainFields = fields.slice(0, mainCount);
  const techFields = fields.slice(mainCount);

  function change(key, value) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function submit(event) {
    event.preventDefault();
    onSave(buildAssetPayload(fields, form));
  }

  return (
    <div className="assets-overlay" role="presentation">
      <aside
        className="assets-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="asset-form-title"
      >
        <div className="assets-drawer__header">
          <div>
            <span className="assets-eyebrow">Cadastro técnico</span>
            <h2 id="asset-form-title">
              {initial?.id ? "Editar equipamento" : "Adicionar equipamento"}
            </h2>
          </div>
          <button
            className="assets-icon-button"
            type="button"
            onClick={onCancel}
            aria-label="Fechar drawer"
          >
            ×
          </button>
        </div>
        <form className="assets-form" onSubmit={submit}>
          <fieldset>
            <legend>Informações principais</legend>
            <div className="assets-form-grid">
              {mainFields.map(([key, label, type, req]) => (
                <Field
                  key={key}
                  label={label}
                  type={type}
                  value={form[key]}
                  onChange={(value) => change(key, value)}
                  required={req}
                />
              ))}
            </div>
          </fieldset>
          {techFields.length > 0 && (
            <fieldset>
              <legend>Informações técnicas</legend>
              <div className="assets-form-grid">
                {techFields.map(([key, label, type, req]) => (
                  <Field
                    key={key}
                    label={label}
                    type={type}
                    value={form[key]}
                    onChange={(value) => change(key, value)}
                    required={req}
                  />
                ))}
              </div>
            </fieldset>
          )}
          <label className="assets-field assets-field--full">
            <span>Observações</span>
            <textarea
              value={form.notes ?? ""}
              onChange={(event) => change("notes", event.target.value)}
              rows="3"
            />
          </label>
          <div className="assets-drawer__actions">
            <button
              className="assets-button assets-button--quiet"
              type="button"
              onClick={onCancel}
            >
              Cancelar
            </button>
            <button
              className="assets-button assets-button--primary"
              type="submit"
              disabled={saving}
            >
              {saving ? "Salvando..." : "Salvar equipamento"}
            </button>
          </div>
        </form>
      </aside>
    </div>
  );
}

/* ── Document form drawer ───────────────────────────────────────────── */
export function DocumentForm({ initial, onCancel, onSave, saving }) {
  const [form, setForm] = useState({
    document_type: "AVCB",
    custom_document_type: "",
    document_number: "",
    issue_date: "",
    expiration_date: "",
    issuer: "",
    notes: "",
    file: null,
    ...initial,
  });

  function change(key, value) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function submit(event) {
    event.preventDefault();
    onSave(buildDocumentFormData(form, { isEdit: Boolean(initial?.id) }));
  }

  return (
    <div className="assets-overlay" role="presentation">
      <aside
        className="assets-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="document-form-title"
      >
        <div className="assets-drawer__header">
          <div>
            <span className="assets-eyebrow">Arquivo persistente</span>
            <h2 id="document-form-title">
              {initial?.id ? "Editar documento" : "Adicionar documento"}
            </h2>
          </div>
          <button
            className="assets-icon-button"
            type="button"
            onClick={onCancel}
            aria-label="Fechar drawer"
          >
            ×
          </button>
        </div>
        <form className="assets-form" onSubmit={submit}>
          <fieldset>
            <legend>Informações do documento</legend>
            <div className="assets-form-grid">
              <label className="assets-field">
                <span>Tipo do documento</span>
                <select
                  value={form.document_type}
                  onChange={(event) =>
                    change("document_type", event.target.value)
                  }
                >
                  <option>AVCB</option>
                  <option>Certificado de Dedetização</option>
                  <option>Outro</option>
                </select>
              </label>
              {form.document_type === "Outro" && (
                <label className="assets-field">
                  <span>Nome do documento</span>
                  <input
                    value={form.custom_document_type || ""}
                    onChange={(event) =>
                      change("custom_document_type", event.target.value)
                    }
                    required
                    placeholder="Ex: Alvará de funcionamento"
                  />
                </label>
              )}
              <label className="assets-field">
                <span>Número / identificação</span>
                <input
                  value={form.document_number || ""}
                  onChange={(event) =>
                    change("document_number", event.target.value)
                  }
                />
              </label>
              <label className="assets-field">
                <span>Data de emissão</span>
                <input
                  type="date"
                  value={form.issue_date || ""}
                  onChange={(event) => change("issue_date", event.target.value)}
                />
              </label>
              <label className="assets-field">
                <span>Data de validade</span>
                <input
                  type="date"
                  value={form.expiration_date || ""}
                  onChange={(event) =>
                    change("expiration_date", event.target.value)
                  }
                />
              </label>
              <label className="assets-field assets-field--full">
                <span>Órgão / fornecedor emissor</span>
                <input
                  value={form.issuer || ""}
                  onChange={(event) => change("issuer", event.target.value)}
                />
              </label>
            </div>
          </fieldset>
          <label className="assets-field assets-field--full">
            <span>
              {initial?.id
                ? "Substituir arquivo (opcional)"
                : "Arquivo (PDF, JPG, JPEG ou PNG — máx. 15 MB)"}
            </span>
            <input
              type="file"
              accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
              required={!initial?.id}
              onChange={(event) =>
                change("file", event.target.files?.[0] || null)
              }
            />
          </label>
          <label className="assets-field assets-field--full">
            <span>Observações</span>
            <textarea
              value={form.notes || ""}
              onChange={(event) => change("notes", event.target.value)}
              rows="3"
            />
          </label>
          <div className="assets-drawer__actions">
            <button
              className="assets-button assets-button--quiet"
              type="button"
              onClick={onCancel}
            >
              Cancelar
            </button>
            <button
              className="assets-button assets-button--primary"
              type="submit"
              disabled={saving}
            >
              {saving ? "Enviando..." : "Salvar documento"}
            </button>
          </div>
        </form>
      </aside>
    </div>
  );
}

