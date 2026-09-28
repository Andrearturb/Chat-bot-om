const PLACEHOLDERS = {
  corrective: {
    eyebrow: 'Chamados corretivos',
    title: 'Indicador de chamados corretivos',
    description: 'A estrutura já está preparada para receber o BI de manutenção corretiva. Quando você encaminhar o painel, ele será integrado aqui sem alterar o Indicador de Desempenho.',
  },
  preventive: {
    eyebrow: 'Chamados preventivos',
    title: 'Indicador de chamados preventivos',
    description: 'Este espaço está reservado para a visão de manutenções preventivas, mantendo filtros, métricas e gráficos independentes do painel corretivo.',
  },
  financial: {
    eyebrow: 'Financeiro',
    title: 'Indicadores financeiros',
    description: 'Este espaço receberá a visão financeira de Obras & Manutenções, com os indicadores que forem definidos para custos, investimentos, budget, saving e demais análises.',
  },
}

export default function IndicatorPlaceholder({ type }) {
  const content = PLACEHOLDERS[type] ?? PLACEHOLDERS.corrective

  return (
    <section className="indicator-placeholder" aria-live="polite">
      <div className="indicator-placeholder__badge">Próximo painel</div>
      <p className="indicator-placeholder__eyebrow">{content.eyebrow}</p>
      <h2>{content.title}</h2>
      <p>{content.description}</p>
      <div className="indicator-placeholder__status">
        <span aria-hidden="true">+</span>
        <strong>Área preparada para integração</strong>
      </div>
    </section>
  )
}
