export default function ChatComposer({ value, onChange, onSubmit, loading }) {
  return (
    <form className="composer" onSubmit={onSubmit}>
      <textarea
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="Pergunte sobre chamados, lojas, analistas, fornecedores ou indicadores..."
        rows="2"
        aria-label="Pergunta para o assistente"
        disabled={loading}
      />
      <div className="composer__footer">
        <span className="composer__hint">Obras &amp; Manutenções <span>·</span> Respostas baseadas nos dados operacionais</span>
        <button className="send-button" type="submit" disabled={!value.trim() || loading} aria-label="Enviar pergunta">
          {loading ? <span className="spinner" aria-hidden="true" /> : <span aria-hidden="true">↑</span>}
        </button>
      </div>
    </form>
  )
}
