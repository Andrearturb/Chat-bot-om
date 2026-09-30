import AuthLayout from './AuthLayout.jsx'
import { leaveToLogin } from './api.js'

export default function AccessPending() {
  return (
    <AuthLayout labelledBy="om-auth-title">
      <div className="om-auth__status om-auth__status--pending" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="8.5" />
          <path d="M12 7.5V12l3 1.8" />
        </svg>
      </div>
      <header className="om-auth__header">
        <h2 id="om-auth-title">Acesso aguardando aprovação</h2>
        <p>Sua conta foi autenticada, mas ainda precisa ser liberada por um administrador.</p>
      </header>
      <p className="om-auth__note">
        Assim que o acesso for liberado, basta entrar novamente. Em caso de urgência,
        procure o responsável pelo Chat-bot O&amp;M.
      </p>
      <button className="om-auth__button om-auth__button--secondary" type="button" onClick={leaveToLogin}>
        Sair
      </button>
    </AuthLayout>
  )
}
