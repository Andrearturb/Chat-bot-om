import { useMemo, useRef, useState } from "react";
import { backendFileUrl } from "../api";
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

function Field({ label, type, value, onChange, required = false, placeholder = "" }) {
  return (
    <label className="assets-field">
      <span>
        {label}
        {required ? <b className="assets-field__required" aria-hidden="true"> *</b> : null}
      </span>
      {type === "select" ? (
        <select value={value || "Operacional"} onChange={(event) => onChange(event.target.value)}>
          <option>Operacional</option>
          <option>Atenção</option>
          <option>Inativo</option>
        </select>
      ) : type === "select-water" ? (
        <select value={value || "Purificador"} onChange={(event) => onChange(event.target.value)}>
          <option>Purificador</option>
          <option>Gelágua</option>
        </select>
      ) : (
        <input
          type={type}
          value={value ?? ""}
          onChange={(event) => onChange(event.target.value)}
          required={required}
          placeholder={placeholder}
        />
      )}
    </label>
  );
}

function hasValue(value) {
  return value !== null && value !== undefined && String(value).trim() !== "";
}

function getAssetFields(category) {
  if (category === "fire") {
    return {
      defaults: { equipment_type: "Extintor" },
      main: [
        ["equipment_type", "Tipo", "text", true],
        ["extinguisher_agent", "Agente extintor", "text", false],
        ["capacity", "Capacidade", "text", false],
        ["location", "Localização", "text", true],
        ["expiration_date", "Data de validade", "date", false],
        ["status", "Status", "select", false],
      ],
      technical: [
        ["manufacture_year", "Ano de fabricação", "number", false],
        ["hydrostatic_test_date", "Teste hidrostático", "date", false],
      ],
    };
  }

  if (category === "water") {
    return {
      defaults: { equipment_type: "Purificador" },
      main: [
        ["equipment_type", "Tipo", "select-water", false],
        ["location", "Localização", "text", true],
        ["status", "Status", "select", false],
        ["next_filter_change", "Próxima troca do filtro", "date", false],
      ],
      technical: [
        ["brand", "Marca", "text", false],
        ["model", "Modelo", "text", false],
        ["serial_number", "Número de série", "text", false],
        ["manufacture_year", "Ano de fabricação", "number", false],
        ["installation_year", "Ano de instalação", "number", false],
        ["voltage", "Tensão", "text", false],
        ["last_filter_change", "Última troca do filtro", "date", false],
      ],
    };
  }

  return {
    defaults: { equipment_type: "Ar-condicionado" },
    main: [
      ["equipment_type", "Tipo de equipamento", "text", true],
      ["capacity_btu", "Capacidade (BTUs)", "number", true],
      ["location", "Localização", "text", true],
      ["status", "Status", "select", false],
    ],
    technical: [
      ["brand", "Fabricante", "text", false],
      ["model", "Modelo", "text", false],
      ["serial_number", "Número de série", "text", false],
      ["manufacture_year", "Ano de fabricação", "number", false],
      ["installation_year", "Ano de instalação", "number", false],
      ["voltage", "Tensão", "text", false],
      ["refrigerant_gas", "Gás refrigerante", "text", false],
    ],
  };
}

/* ── Asset form drawer ──────────────────────────────────────────────── */
export function AssetForm({ category, initial, onCancel, onSave, saving }) {
  const config = useMemo(() => getAssetFields(category), [category]);
  const allFields = useMemo(() => [...config.main, ...config.technical], [config]);
  const [form, setForm] = useState({
    ...EMPTY_ASSET,
    ...config.defaults,
    ...initial,
  });
  const [showTechnical, setShowTechnical] = useState(() =>
    Boolean(initial?.id && config.technical.some(([key]) => hasValue(initial?.[key]))),
  );

  function change(key, value) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function submit(event) {
    event.preventDefault();
    onSave(buildAssetPayload(allFields, form));
  }

  return (
    <div className="assets-overlay" role="presentation">
      <aside className="assets-drawer" role="dialog" aria-modal="true" aria-labelledby="asset-form-title">
        <div className="assets-drawer__header">
          <div>
            <span className="assets-eyebrow">Cadastro técnico</span>
            <h2 id="asset-form-title">{initial?.id ? "Editar equipamento" : "Adicionar equipamento"}</h2>
            <p>Preencha primeiro o essencial. Os dados técnicos complementares são opcionais.</p>
          </div>
          <button className="assets-icon-button" type="button" onClick={onCancel} aria-label="Fechar formulário">
            ×
          </button>
        </div>
        <form className="assets-form" onSubmit={submit}>
          <fieldset>
            <legend>Informações principais</legend>
            <div className="assets-form-grid">
              {config.main.map(([key, label, type, req]) => (
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

          {config.technical.length > 0 && (
            <section className={`assets-form-disclosure${showTechnical ? " is-open" : ""}`}>
              <button
                className="assets-form-disclosure__trigger"
                type="button"
                onClick={() => setShowTechnical((current) => !current)}
                aria-expanded={showTechnical}
              >
                <span>
                  <strong>Mais informações técnicas</strong>
                  <small>Fabricante, modelo, série, ano e demais especificações.</small>
                </span>
                <b aria-hidden="true">⌄</b>
              </button>
              {showTechnical && (
                <div className="assets-form-disclosure__content">
                  <div className="assets-form-grid">
                    {config.technical.map(([key, label, type, req]) => (
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
                </div>
              )}
            </section>
          )}

          <label className="assets-field assets-field--full">
            <span>Observações</span>
            <textarea
              value={form.notes ?? ""}
              onChange={(event) => change("notes", event.target.value)}
              rows="3"
              placeholder="Inclua somente informações úteis para futuras consultas ou manutenções."
            />
          </label>
          <div className="assets-drawer__actions">
            <button className="assets-button assets-button--quiet" type="button" onClick={onCancel}>
              Cancelar
            </button>
            <button className="assets-button assets-button--primary" type="submit" disabled={saving}>
              {saving ? "Salvando..." : "Salvar equipamento"}
            </button>
          </div>
        </form>
      </aside>
    </div>
  );
}

function FileUpload({ initial, file, onFileChange, missingFile = false }) {
  const inputRef = useRef(null);
  const [dragging, setDragging] = useState(false);
  const [fileError, setFileError] = useState("");

  function selectFile(nextFile) {
    if (!nextFile) return;
    const allowedExtensions = ["pdf", "jpg", "jpeg", "png"];
    const extension = nextFile.name.split(".").pop()?.toLowerCase();
    if (!allowedExtensions.includes(extension)) {
      setFileError("Formato não permitido. Envie PDF, JPG, JPEG ou PNG.");
      return;
    }
    if (nextFile.size > 15 * 1024 * 1024) {
      setFileError("O arquivo deve ter no máximo 15 MB.");
      return;
    }
    setFileError("");
    onFileChange(nextFile);
  }

  function handleDrop(event) {
    event.preventDefault();
    setDragging(false);
    selectFile(event.dataTransfer.files?.[0]);
  }

  return (
    <div className="assets-file-section">
      {initial?.id && (
        <div className="assets-current-file">
          <span className="assets-current-file__icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" />
              <path d="M14 2v6h6M8 13h8M8 17h6" />
            </svg>
          </span>
          <span>
            <small>Arquivo atual</small>
            <strong title={initial.original_filename}>{initial.original_filename}</strong>
          </span>
          <a href={backendFileUrl(initial.id)} target="_blank" rel="noreferrer">Visualizar</a>
        </div>
      )}

      <div
        className={`assets-file-dropzone${dragging ? " is-dragging" : ""}${file ? " has-file" : ""}`}
        onDragEnter={(event) => { event.preventDefault(); setDragging(true); }}
        onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
        onDragLeave={(event) => { event.preventDefault(); setDragging(false); }}
        onDrop={handleDrop}
      >
        <input
          ref={inputRef}
          className="assets-file-input"
          type="file"
          accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
          onChange={(event) => selectFile(event.target.files?.[0])}
        />
        <span className="assets-file-dropzone__icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 16V4M7 9l5-5 5 5" />
            <path d="M5 20h14a2 2 0 0 0 2-2v-3M3 15v3a2 2 0 0 0 2 2" />
          </svg>
        </span>
        {file ? (
          <>
            <strong>{file.name}</strong>
            <span>{(file.size / 1024 / 1024).toLocaleString("pt-BR", { maximumFractionDigits: 2 })} MB · pronto para envio</span>
            <button type="button" onClick={() => inputRef.current?.click()}>Trocar arquivo</button>
          </>
        ) : (
          <>
            <strong>{initial?.id ? "Arraste um novo arquivo para substituir" : "Arraste o documento até aqui"}</strong>
            <span>ou selecione no seu computador</span>
            <button type="button" onClick={() => inputRef.current?.click()}>Selecionar arquivo</button>
            <small>PDF, JPG ou PNG · máximo 15 MB</small>
          </>
        )}
      </div>
      {fileError ? <p className="assets-file-error" role="alert">{fileError}</p> : null}
      {!fileError && missingFile ? <p className="assets-file-error" role="alert">Selecione um arquivo para cadastrar o documento.</p> : null}
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
  const [missingFile, setMissingFile] = useState(false);

  function change(key, value) {
    if (key === "file" && value) setMissingFile(false);
    setForm((current) => ({ ...current, [key]: value }));
  }

  function submit(event) {
    event.preventDefault();
    if (!initial?.id && !form.file) {
      setMissingFile(true);
      return;
    }
    onSave(buildDocumentFormData(form, { isEdit: Boolean(initial?.id) }));
  }

  return (
    <div className="assets-overlay" role="presentation">
      <aside className="assets-drawer" role="dialog" aria-modal="true" aria-labelledby="document-form-title">
        <div className="assets-drawer__header">
          <div>
            <span className="assets-eyebrow">Arquivo persistente</span>
            <h2 id="document-form-title">{initial?.id ? "Editar documento" : "Adicionar documento"}</h2>
            <p>Cadastre as informações principais e mantenha o arquivo da loja sempre atualizado.</p>
          </div>
          <button className="assets-icon-button" type="button" onClick={onCancel} aria-label="Fechar formulário">
            ×
          </button>
        </div>
        <form className="assets-form" onSubmit={submit}>
          <fieldset>
            <legend>Informações do documento</legend>
            <div className="assets-form-grid">
              <label className="assets-field">
                <span>Tipo do documento</span>
                <select value={form.document_type} onChange={(event) => change("document_type", event.target.value)}>
                  <option>AVCB</option>
                  <option>Certificado de Dedetização</option>
                  <option>Outro</option>
                </select>
              </label>
              {form.document_type === "Outro" && (
                <label className="assets-field">
                  <span>Nome do documento <b className="assets-field__required">*</b></span>
                  <input
                    value={form.custom_document_type || ""}
                    onChange={(event) => change("custom_document_type", event.target.value)}
                    required
                    placeholder="Ex: Alvará de funcionamento"
                  />
                </label>
              )}
              <label className="assets-field">
                <span>Número / identificação</span>
                <input value={form.document_number || ""} onChange={(event) => change("document_number", event.target.value)} />
              </label>
              <label className="assets-field">
                <span>Data de emissão</span>
                <input type="date" value={form.issue_date || ""} onChange={(event) => change("issue_date", event.target.value)} />
              </label>
              <label className="assets-field">
                <span>Data de validade</span>
                <input type="date" value={form.expiration_date || ""} onChange={(event) => change("expiration_date", event.target.value)} />
              </label>
              <label className="assets-field assets-field--full">
                <span>Órgão / fornecedor emissor</span>
                <input value={form.issuer || ""} onChange={(event) => change("issuer", event.target.value)} />
              </label>
            </div>
          </fieldset>

          <FileUpload initial={initial} file={form.file} onFileChange={(file) => change("file", file)} missingFile={missingFile} />

          <label className="assets-field assets-field--full">
            <span>Observações</span>
            <textarea
              value={form.notes || ""}
              onChange={(event) => change("notes", event.target.value)}
              rows="3"
              placeholder="Inclua observações úteis sobre o documento, renovação ou responsável."
            />
          </label>
          <div className="assets-drawer__actions">
            <button className="assets-button assets-button--quiet" type="button" onClick={onCancel}>
              Cancelar
            </button>
            <button className="assets-button assets-button--primary" type="submit" disabled={saving}>
              {saving ? "Enviando..." : "Salvar documento"}
            </button>
          </div>
        </form>
      </aside>
    </div>
  );
}
