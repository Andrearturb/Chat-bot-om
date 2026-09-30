import AuthLayout from './AuthLayout.jsx'
import { leaveToLogin, startLogin } from './api.js'

/**
 * Conta autenticada no Keycloak, mas ainda sem papel do Chat-bot O&M.
 * A liberação é feita por um gestor de acesso no console do Keycloak.
 */
export default function AccountNotReleased() {
  return (
    <AuthLayout labelledBy="om-auth-title">
      <div className="om-auth__status om-auth__status--pending" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="8.5" />
          <path d="M12 7.5V12l3 1.8" />
        </svg>
      </div>
      <header className="om-auth__header">
        <h2 id="om-auth-title">Sua conta ainda não foi liberada</h2>
        <p>Seu cadastro está confirmado. Falta um gestor de acesso liberar o seu perfil no Chat-bot O&amp;M.</p>
      </header>
      <p className="om-auth__note">
        Quando a liberação acontecer, é só entrar novamente. Em caso de urgência,
        procure o responsável pelo Chat-bot O&amp;M.
      </p>
      <button className="om-auth__button" type="button" onClick={startLogin}>
        Entrar novamente <span className="om-auth__arrow" aria-hidden="true">→</span>
      </button>
      <button className="om-auth__button om-auth__button--secondary" type="button" onClick={leaveToLogin}>
        Voltar ao início
      </button>
    </AuthLayout>
  )
}
