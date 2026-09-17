import { assistantImage } from '../assets/assistantImage'

export default function HeroAssistant({ active }) {
  return (
    <section className={`hero ${active ? 'hero--active' : ''}`} aria-hidden={active}>
      <p className="eyebrow">GENTIL NEGÓCIOS <span /> OBRAS &amp; MANUTENÇÕES</p>
      <h1>Como posso ajudar <em>hoje?</em><b /></h1>
      <p className="hero__subtitle">Consulte chamados e indicadores operacionais usando linguagem natural.</p>
      <div className="hero-stage">
        <div className="line-art line-art--left" aria-hidden="true" />
        <div className="line-art line-art--right" aria-hidden="true" />
        <p className="side-note side-note--left">Informação de hoje.<br />Resultados de amanhã.</p>
        <p className="side-note side-note--right">Obras que mantêm<br />negócios em movimento.</p>
        <div className="assistant-portrait">
        <div className="assistant-portrait__glow" />
        <img src={assistantImage} alt="Assistente de Obras e Manutenções usando capacete amarelo" />
        </div>
      </div>
    </section>
  )
}
