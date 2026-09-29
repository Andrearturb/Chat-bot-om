import './auth.css'

export default function AccessPending() {
  return (
    <div className="auth-screen" role="main">
      <div className="auth-card auth-card--warning">
        <span className="auth-card__badge" aria-hidden="true">⏳</span>
        <h1 className="auth-card__title">Acesso pendente</h1>
        <p className="auth-card__message">
          Sua identidade foi autenticada, mas o acesso ao Chat-bot O&M ainda está aguardando liberação do administrador.
        </p>
        <p className="auth-card__footer">
          Em caso de urgência, entre em contato com o responsável pelo sistema.
        </p>
      </div>
    </div>
  )
}
