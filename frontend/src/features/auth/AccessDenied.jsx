import AuthLayout from './AuthLayout.jsx'
import { leaveToLogin } from './api.js'

export default function AccessDenied() {
  return (
    <AuthLayout labelledBy="om-auth-title">
      <div className="om-auth__status om-auth__status--blocked" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <rect x="4.5" y="10.5" width="15" height="10" rx="2.5" />
          <path d="M8 10.5V7.5a4 4 0 0 1 8 0v3" />
        </svg>
      </div>
      <header className="om-auth__header">
        <h2 id="om-auth-title">Acesso indisponível</h2>
        <p>Sua conta está desativada ou o período de acesso terminou.</p>
      </header>
      <p className="om-auth__note">
        Para voltar a usar o Chat-bot O&amp;M, procure um administrador do sistema.
      </p>
      <button className="om-auth__button om-auth__button--secondary" type="button" onClick={leaveToLogin}>
        Sair
      </button>
    </AuthLayout>
  )
}
