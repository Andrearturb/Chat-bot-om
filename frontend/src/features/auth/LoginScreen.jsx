import { startLogin } from './api.js'
import './auth.css'

export default function LoginScreen({ authError = null }) {
  return (
    <div className="auth-screen" role="main">
      <div className="auth-card">
        <div className="auth-card__brand">
          <span className="auth-card__badge" aria-hidden="true">🔒</span>
          <p className="auth-card__label">ACESSO RESTRITO</p>
          <h1 className="auth-card__title">Chat-bot O&amp;M</h1>
          <p className="auth-card__subtitle">
            Ambiente corporativo de Obras &amp; Manutenções.
          </p>
        </div>
        {authError && (
          <div className="auth-card__alert" role="alert">
            <strong>{authError.title}</strong>
            <span>{authError.message}</span>
          </div>
        )}
        <button className="auth-card__btn" type="button" onClick={startLogin}>
          {authError ? 'Tentar novamente' : 'Entrar com conta corporativa'}
        </button>
        <p className="auth-card__footer">
          Gentil Negócios · Acesso restrito a colaboradores autorizados.
        </p>
      </div>
    </div>
  )
}
