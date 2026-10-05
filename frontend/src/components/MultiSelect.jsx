import { useEffect, useMemo, useRef, useState } from "react";
import "./MultiSelect.css";

/**
 * Seletor de múltipla escolha com busca opcional. Vazio = "todos".
 *
 * Compartilhado entre a Central de Ativos e a Central de Indicadores — veio
 * de features/assets/components/MultiSelect.jsx. O CSS é autocontido (tokens
 * próprios, não herdados de .assets-page nem .indicators-page), para o
 * componente funcionar igual em qualquer página que o use.
 */
export function MultiSelect({ label, options, selected, onChange, allLabel, unit, filterOption, emptyText = "Nada encontrado." }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const rootRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const onPointerDown = (event) => { if (!rootRef.current?.contains(event.target)) setOpen(false); };
    const onKeyDown = (event) => { if (event.key === "Escape") setOpen(false); };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const visible = useMemo(() => {
    if (!text.trim()) return options;
    return options.filter((option) => (filterOption
      ? filterOption(option, text)
      : String(option.label).toLowerCase().includes(text.trim().toLowerCase())));
  }, [options, text, filterOption]);

  const chosen = options.find((option) => selected.includes(option.value));
  const summary = selected.length === 0
    ? allLabel
    : selected.length === 1 ? (chosen?.label ?? `1 ${unit[0]}`) : `${selected.length} ${unit[1]}`;

  function toggle(value) {
    onChange(selected.includes(value) ? selected.filter((item) => item !== value) : [...selected, value]);
  }

  return (
    <div className="ui-multiselect" ref={rootRef}>
      <button
        type="button"
        className={`ui-multiselect__button${selected.length ? " is-active" : ""}`}
        aria-haspopup="true"
        aria-expanded={open}
        aria-label={label}
        onClick={() => { setOpen((value) => !value); setText(""); }}
      >
        <span className="ui-multiselect__label">{label}</span>
        <strong>{summary}</strong>
        <span aria-hidden="true">▾</span>
      </button>
      {open ? (
        <div className="ui-multiselect__panel" role="group" aria-label={label}>
          {options.length > 8 ? (
            <input type="search" value={text} onChange={(event) => setText(event.target.value)}
                   placeholder="Buscar..." aria-label={`Buscar em ${label}`} autoFocus />
          ) : null}
          <div className="ui-multiselect__list">
            {visible.length === 0 ? <p className="ui-multiselect__empty">{emptyText}</p> : visible.map((option) => (
              <label key={String(option.value)} className="ui-multiselect__option">
                <input type="checkbox" checked={selected.includes(option.value)} onChange={() => toggle(option.value)} />
                <span>{option.label}</span>
                {option.hint ? <small>{option.hint}</small> : null}
              </label>
            ))}
          </div>
          <div className="ui-multiselect__footer">
            <button type="button" onClick={() => onChange([])} disabled={selected.length === 0}>Limpar seleção</button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
