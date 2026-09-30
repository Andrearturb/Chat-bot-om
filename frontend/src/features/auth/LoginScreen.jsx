import { useState } from 'react'
import AuthLayout from './AuthLayout.jsx'
import { startLogin } from './api.js'

/**
 * Página /login — apresentação antes do Keycloak. NÃO pede senha:
 * "Entrar" inicia o fluxo OIDC existente (/auth/login) e os campos de
 * usuário e senha ficam na página do Keycloak (tema gentil-om).
 */
export default function LoginScreen({ authError = null, notice = null }) {
  const [redirecting, setRedirecting] = useState(false)

  function handleLogin() {
    setRedirecting(true)
    startLogin()
  }

  return (
    <AuthLayout labelledBy="om-auth-title">
      <header className="om-auth__header">
        <h2 id="om-auth-title">Bem-vindo</h2>
        <p>Entre com sua conta para continuar</p>
      </header>

      {notice && !authError && (
        <div className="om-auth__alert om-auth__alert--success" role="status">
          <span className="om-auth__alert-icon" aria-hidden="true" />
          <span>{notice}</span>
        </div>
      )}

      {authError && (
        <div className="om-auth__alert om-auth__alert--warning" role="alert">
          <span className="om-auth__alert-icon" aria-hidden="true" />
          <span>
            <strong>{authError.title}</strong>
            {authError.message}
          </span>
        </div>
      )}

      <button className="om-auth__button" type="button" onClick={handleLogin} disabled={redirecting}>
        {redirecting ? (
          <><span className="om-auth__spinner" aria-hidden="true" /> Abrindo login seguro…</>
        ) : (
          <>{authError ? 'Entrar novamente' : 'Entrar'} <span className="om-auth__arrow" aria-hidden="true">→</span></>
        )}
      </button>
      <p className="om-auth__hint">
        Você será direcionado à página segura de autenticação da Gentil Negócios.
      </p>
    </AuthLayout>
  )
}
