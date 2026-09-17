const suggestions = [
  ['Chamados em aberto', 'Quantos chamados estão em aberto atualmente?', '◌'],
  ['Por analista', 'Quantos chamados foram criados por analista?', '⌁'],
  ['Ranking por loja', 'Quais são as 5 lojas com mais chamados?', '↗'],
  ['Sem fornecedor', 'Quantos chamados estão sem fornecedor?', '∅'],
  ['Por categoria', 'Quantos chamados existem por categoria?', '▦'],
  ['Indicadores do mês', 'Faça um resumo dos chamados deste mês.', '◷'],
]

export default function SuggestionChips({ onSelect, active }) {
  return (
    <div className={`suggestions ${active ? 'suggestions--active' : ''}`} aria-label="Sugestões de perguntas">
      {suggestions.map(([label, prompt, icon]) => (
        <button type="button" className="suggestion" key={label} onClick={() => onSelect(prompt)}>
          <span className="suggestion__icon" aria-hidden="true">{icon}</span>
          {label}
        </button>
      ))}
    </div>
  )
}
