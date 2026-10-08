export default function IndicatorLoadingState({ title = 'Carregando indicador' }) {
  return (
    <section className="indicators-state" aria-live="polite" role="status">
      <span className="indicators-loader" aria-hidden="true" />
      <div><h2>{title}</h2><p>Consultando os dados do Gentileza...</p></div>
    </section>
  )
}
