import { useEffect, useRef, useState } from "react";
import { downloadAssetsExport, fetchExportPreview } from "../api";
import { ASSET_TYPE_OPTIONS, exportSummary, isFiltered } from "../filters";

function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function ExportDialog({ filters, filteredCount, totalCount, onClose, onToast }) {
  const filtered = isFiltered(filters);
  const [scope, setScope] = useState(filtered ? "filtered" : "all");
  const [types, setTypes] = useState(ASSET_TYPE_OPTIONS.map((option) => option.value));
  const [result, setResult] = useState({ key: null, preview: null, error: "" });
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState("");
  const closeRef = useRef(null);

  const key = `${scope}|${types.join(",")}`;

  useEffect(() => {
    closeRef.current?.focus();
    const onKeyDown = (event) => { if (event.key === "Escape" && !downloading) onClose(); };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose, downloading]);

  useEffect(() => {
    if (types.length === 0) return undefined;
    const controller = new AbortController();
    fetchExportPreview({ filters, types, scope, signal: controller.signal })
      .then((preview) => setResult({ key, preview, error: "" }))
      .catch((err) => { if (err?.name !== "AbortError") setResult({ key, preview: null, error: err.message }); });
    return () => controller.abort();
  }, [key, filters, types, scope]);

  const current = result.key === key ? result : null;
  const loading = types.length > 0 && !current;
  const preview = current?.preview ?? null;
  const canDownload = !downloading && types.length > 0 && Boolean(preview) && preview.stores > 0;
  const allTypes = types.length === ASSET_TYPE_OPTIONS.length;

  function toggleType(value) {
    setTypes((previous) => (previous.includes(value) ? previous.filter((item) => item !== value) : [...previous, value]));
  }

  async function download() {
    setDownloading(true);
    setDownloadError("");
    try {
      const { blob, filename } = await downloadAssetsExport({ filters, types, scope });
      saveBlob(blob, filename);
      onToast({ kind: "success", message: `Planilha gerada: ${filename}` });
      onClose();
    } catch (err) {
      setDownloadError(err.message || "Não foi possível gerar a planilha.");
      setDownloading(false);
    }
  }

  return (
    <div className="assets-overlay assets-overlay--center" role="presentation"
         onMouseDown={(event) => { if (event.target === event.currentTarget && !downloading) onClose(); }}>
      <div className="assets-export" role="dialog" aria-modal="true" aria-labelledby="assets-export-title">
        <div className="assets-export__header">
          <h2 id="assets-export-title">Exportar ativos</h2>
          <button ref={closeRef} className="assets-export__close" type="button" onClick={onClose}
                  disabled={downloading} aria-label="Fechar">×</button>
        </div>

        <fieldset className="assets-export__group">
          <legend>Lojas</legend>
          <label>
            <input type="radio" name="export-scope" checked={scope === "all"} onChange={() => setScope("all")} />
            <span>Todas as lojas ({totalCount})</span>
          </label>
          <label className={filtered ? "" : "is-disabled"}>
            <input type="radio" name="export-scope" checked={scope === "filtered"} disabled={!filtered}
                   onChange={() => setScope("filtered")} />
            <span>Somente o filtro ativo ({filteredCount} {filteredCount === 1 ? "loja" : "lojas"})</span>
          </label>
        </fieldset>

        <fieldset className="assets-export__group">
          <legend>Ativos</legend>
          <label>
            <input type="checkbox" checked={allTypes}
                   onChange={() => setTypes(allTypes ? [] : ASSET_TYPE_OPTIONS.map((option) => option.value))} />
            <span>Todos</span>
          </label>
          {ASSET_TYPE_OPTIONS.map((option) => (
            <label key={option.value}>
              <input type="checkbox" checked={types.includes(option.value)} onChange={() => toggleType(option.value)} />
              <span>{option.label}</span>
            </label>
          ))}
          {types.length === 0 ? <p className="assets-export__hint">Escolha ao menos um tipo de ativo.</p> : null}
        </fieldset>

        <p className="assets-export__summary" role="status" aria-live="polite">
          {types.length === 0 ? "" : loading ? "Calculando..." : current?.error ? current.error : exportSummary(preview, types)}
        </p>
        {downloadError ? <p className="assets-export__error" role="alert">{downloadError}</p> : null}

        <div className="assets-drawer__actions">
          <button className="assets-button assets-button--quiet" type="button" onClick={onClose} disabled={downloading}>
            Cancelar
          </button>
          <button className="assets-button assets-button--primary" type="button" onClick={download} disabled={!canDownload}>
            {downloading ? "Gerando..." : "Baixar planilha"}
          </button>
        </div>
      </div>
    </div>
  );
}
