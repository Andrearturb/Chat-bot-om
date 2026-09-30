/**
 * Layout das telas de acesso (/login, acesso pendente, acesso indisponível).
 *
 * Reproduz a mesma composição do tema de login do Keycloak (gentil-om):
 * área institucional com a Gentileza à esquerda e card à direita — assim a
 * passagem do app para a página de senha não parece uma troca de sistema.
 */

import { assistantImage } from '../../assets/assistantImage'
import './auth.css'

export function LockIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
         strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="4.5" y="10.5" width="15" height="10" rx="2.5" />
      <path d="M8 10.5V7.5a4 4 0 0 1 8 0v3" />
    </svg>
  )
}

export default function AuthLayout({ labelledBy, children }) {
  return (
    <div className="om-auth">
      <span className="om-auth__glow om-auth__glow--blue" aria-hidden="true" />
      <span className="om-auth__glow om-auth__glow--yellow" aria-hidden="true" />

      <main className="om-auth__layout">
        <section className="om-auth__hero" aria-label="Chat-bot O&M">
          <span className="om-auth__ring om-auth__ring--one" aria-hidden="true" />
          <span className="om-auth__ring om-auth__ring--two" aria-hidden="true" />
          <span className="om-auth__grid" aria-hidden="true" />

          <div className="om-auth__wordmark" aria-label="Gentil Negócios">
            <strong>Gentil</strong>
            <strong>Negócios</strong>
            <small><i aria-hidden="true" />Obras &amp; Manutenções</small>
          </div>

          <div className="om-auth__copy">
            <p className="om-auth__eyebrow">
              Gentil Negócios
              <span className="om-auth__eyebrow-area"><span className="om-auth__eyebrow-dot" aria-hidden="true" />Obras &amp; Manutenções</span>
            </p>
            <h1 className="om-auth__title">Chat-bot <em>O&amp;M</em><b aria-hidden="true" /></h1>
            <p className="om-auth__subtitle">Assistente Inteligente de Obras &amp; Manutenções</p>
          </div>

          <div className="om-auth__stage">
            <div className="om-auth__portrait">
              <span className="om-auth__halo" aria-hidden="true" />
              <img src={assistantImage} alt="Gentileza, assistente de Obras e Manutenções, usando capacete amarelo" />
              <p className="om-auth__speech">Informações, chamados e indicadores em um só lugar.</p>
            </div>
          </div>
        </section>

        <section className="om-auth__panel">
          <div className="om-auth__card" role="region" aria-labelledby={labelledBy}>
            <div className="om-auth__brand">
              <span className="om-auth__avatar"><img src={assistantImage} alt="" /></span>
              <span className="om-auth__brand-copy">
                <strong>Chat-bot O&amp;M</strong>
                <small>Assistente Inteligente de Obras &amp; Manutenções</small>
              </span>
            </div>

            {children}

            <footer className="om-auth__footer">
              <LockIcon />
              <span>Acesso exclusivo Gentil Negócios</span>
            </footer>
          </div>
        </section>
      </main>
    </div>
  )
}
