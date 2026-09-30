import { assistantImage } from '../../assets/assistantImage'
import './auth.css'

/** Estado intermediário (verificando sessão / abrindo o login seguro). */
export default function AuthLoading({ message = 'Verificando acesso…' }) {
  return (
    <div className="om-auth-loading" role="status" aria-live="polite">
      <span className="om-auth-loading__avatar"><img src={assistantImage} alt="" /></span>
      <strong>Chat-bot O&amp;M</strong>
      <span className="om-auth-loading__message">
        <span className="om-auth__spinner om-auth__spinner--dark" aria-hidden="true" />
        {message}
      </span>
    </div>
  )
}
