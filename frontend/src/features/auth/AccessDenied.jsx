import { startLogin } from './api.js'
import './auth.css'

export default function AccessDenied() {
  return (
    <div className="auth-screen" role="main">
      <div className="auth-card auth-card--danger">
        <span className="auth-card__badge" aria-hidden="true">⛔</span>
        <h1 className="auth-card__title">Acesso negado</h1>
        <p className="auth-card__message">
          Sua conta está desativada ou seu período de acesso expirou.
          Contate o administrador do sistema para reativar.
        </p>
        <button className="auth-card__btn auth-card__btn--secondary" type="button" onClick={startLogin}>
          Tentar com outra conta
        </button>
      </div>
    </div>
  )
}
