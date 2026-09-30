import { useEffect, useMemo, useRef, useState } from 'react'
import {
  formatDate,
  formatLastAccess,
  generateTemporaryPassword,
  PASSWORD_MIN_LENGTH,
  PROFILE_OPTIONS,
  usernameFromEmail,
  validateUserForm,
} from '../userUtils.js'
import { StatusBadge, UserAvatar, UsersIcon } from './UserVisuals.jsx'

function FieldError({ id, message }) {
  if (!message) return null
  return <span className="users-field__error" id={id} role="alert">{message}</span>
}

function PasswordField({ id, value, onChange, error, label = 'Senha temporária', autoFocus = false }) {
  const [visible, setVisible] = useState(false)
  const [copied, setCopied] = useState(false)

  async function copy() {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1800)
    } catch { /* área de transferência indisponível */ }
  }

  return (
    <div className="users-field users-field--full">
      <label htmlFor={id}>{label}<b className="users-field__required" aria-hidden="true"> *</b></label>
      <div className="users-password">
        <input
          id={id}
          type={visible ? 'text' : 'password'}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          autoComplete="new-password"
          spellCheck="false"
          autoFocus={autoFocus}
          aria-invalid={Boolean(error)}
          aria-describedby={`${id}-hint${error ? ` ${id}-error` : ''}`}
        />
        <button type="button" className="users-password__action" onClick={() => setVisible((v) => !v)}
                aria-label={visible ? 'Ocultar senha' : 'Mostrar senha'} title={visible ? 'Ocultar senha' : 'Mostrar senha'}>
          <UsersIcon name={visible ? 'eyeOff' : 'eye'} size={17} />
        </button>
        <button type="button" className="users-password__action" onClick={copy}
                aria-label="Copiar senha" title={copied ? 'Copiada!' : 'Copiar senha'}>
          <UsersIcon name={copied ? 'check' : 'copy'} size={17} />
        </button>
        <button type="button" className="users-password__action" onClick={() => { onChange(generateTemporaryPassword()); setVisible(true) }}
                aria-label="Gerar nova senha" title="Gerar nova senha">
          <UsersIcon name="refresh" size={17} />
        </button>
      </div>
      <small className="users-field__hint" id={`${id}-hint`}>
        Mínimo de {PASSWORD_MIN_LENGTH} caracteres. O usuário troca esta senha no primeiro acesso.
        Ela vai direto para o Keycloak e não pode ser consultada depois — copie antes de concluir.
      </small>
      <FieldError id={`${id}-error`} message={error} />
    </div>
  )
}

export default function UserFormDrawer({
  mode,
  user = null,
  presetStatus = null,
  capabilities,
  currentUserId,
  activeAdminCount,
  saving = false,
  error = '',
  onCancel,
  onSubmit,
  onResetPassword,
  onSendPasswordEmail,
}) {
  const isCreate = mode === 'create'
  const emailActions = Boolean(capabilities?.email_actions)
  const identityAdmin = Boolean(capabilities?.identity_admin)

  const [form, setForm] = useState(() => (isCreate
    ? { display_name: '', email: '', username: '', profile: '', status: 'active', temporary_password: generateTemporaryPassword() }
    : { display_name: user.display_name || '', profile: user.profile || '', status: presetStatus || user.status }))
  const [usernameTouched, setUsernameTouched] = useState(false)
  const [passwordMode, setPasswordMode] = useState(emailActions ? 'email' : 'temporary')
  const [showErrors, setShowErrors] = useState(false)
  const [resetOpen, setResetOpen] = useState(false)
  const [resetValue, setResetValue] = useState('')
  const [resetError, setResetError] = useState('')
  const firstFieldRef = useRef(null)

  const isSelf = !isCreate && user.id === currentUserId
  const isActiveAdmin = !isCreate && user.status === 'active' && user.profile === 'ADMINISTRADOR'
  const isOnlyAdmin = isActiveAdmin && activeAdminCount <= 1
  const lockProfile = isSelf && isOnlyAdmin
  const lockStatus = isSelf

  const errors = useMemo(
    () => validateUserForm(form, { mode: isCreate ? 'create' : 'edit', passwordMode }),
    [form, isCreate, passwordMode],
  )
  const visibleErrors = showErrors ? errors : {}

  useEffect(() => { firstFieldRef.current?.focus() }, [])

  useEffect(() => {
    const onKeyDown = (event) => { if (event.key === 'Escape' && !saving) onCancel() }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onCancel, saving])

  function change(key, value) {
    setForm((current) => {
      const next = { ...current, [key]: value }
      if (isCreate && key === 'email' && !usernameTouched) next.username = usernameFromEmail(value)
      return next
    })
  }

  function submit(event) {
    event.preventDefault()
    setShowErrors(true)
    if (Object.keys(errors).length) return

    if (isCreate) {
      onSubmit({
        display_name: form.display_name.trim().replace(/\s+/g, ' '),
        email: form.email.trim().toLowerCase(),
        username: (form.username || usernameFromEmail(form.email)).trim().toLowerCase(),
        profile: form.profile,
        status: form.status,
        password_mode: passwordMode,
        temporary_password: passwordMode === 'temporary' ? form.temporary_password : null,
      })
      return
    }

    const payload = {}
    const name = form.display_name.trim().replace(/\s+/g, ' ')
    if (name !== user.display_name) payload.display_name = name
    if (form.profile !== (user.profile || '')) payload.profile = form.profile
    if (form.status !== user.status) payload.status = form.status
    onSubmit(payload)
  }

  function submitReset() {
    if (resetValue.length < PASSWORD_MIN_LENGTH) {
      setResetError(`A senha temporária deve ter pelo menos ${PASSWORD_MIN_LENGTH} caracteres.`)
      return
    }
    setResetError('')
    onResetPassword(resetValue)
  }

  const title = isCreate ? 'Novo usuário' : 'Editar usuário'
  const statusOptions = [
    ...(!isCreate && user.status === 'pending' ? [{ value: 'pending', label: 'Pendente (aguardando aprovação)' }] : []),
    { value: 'active', label: 'Ativo' },
    { value: 'disabled', label: 'Bloqueado' },
  ]

  return (
    <div className="users-overlay" role="presentation">
      <aside className="users-drawer" role="dialog" aria-modal="true" aria-labelledby="users-drawer-title">
        <div className="users-drawer__header">
          <div>
            <span className="users-eyebrow">{isCreate ? 'Cadastro de acesso' : 'Acesso ao Chat-bot O&M'}</span>
            <h2 id="users-drawer-title">{title}</h2>
            <p>
              {isCreate
                ? 'A conta é criada no Keycloak e o perfil de acesso fica registrado no Chat-bot O&M.'
                : 'Ajuste nome, perfil e status. Credenciais continuam sob responsabilidade do Keycloak.'}
            </p>
          </div>
          <button className="users-icon-button" type="button" onClick={onCancel} aria-label="Fechar" disabled={saving}>×</button>
        </div>

        {!isCreate && (
          <section className="users-identity-card" aria-label="Resumo do usuário">
            <UserAvatar name={user.display_name} profile={user.profile} size="lg" />
            <div className="users-identity-card__main">
              <strong>{user.display_name}{isSelf && <em className="users-self-tag">Você</em>}</strong>
              <span>{user.email}</span>
              <div className="users-identity-card__chips">
                {user.username && <span className="users-chip">@{user.username}</span>}
                <StatusBadge status={user.status} />
              </div>
            </div>
            <dl className="users-identity-card__meta">
              <div><dt>Último acesso</dt><dd>{formatLastAccess(user.last_seen_at)}</dd></div>
              <div><dt>Cadastrado em</dt><dd>{formatDate(user.created_at)}</dd></div>
              <div>
                <dt>Identidade</dt>
                <dd className={user.identity_linked ? 'is-ok' : 'is-muted'}>
                  {user.identity_linked ? 'Vinculada ao Keycloak' : 'Sem vínculo no Keycloak'}
                </dd>
              </div>
            </dl>
          </section>
        )}

        <form className="users-form" onSubmit={submit} noValidate>
          {error && (
            <div className="users-inline-alert users-inline-alert--error" role="alert">
              <UsersIcon name="alert" size={17} />
              <span>{error}</span>
            </div>
          )}

          <fieldset>
            <legend>Dados do usuário</legend>
            <div className="users-form-grid">
              <div className="users-field users-field--full">
                <label htmlFor="user-name">Nome completo<b className="users-field__required" aria-hidden="true"> *</b></label>
                <input id="user-name" ref={firstFieldRef} value={form.display_name}
                       onChange={(event) => change('display_name', event.target.value)}
                       placeholder="Ex.: Maria Oliveira" autoComplete="off" maxLength={200}
                       aria-invalid={Boolean(visibleErrors.display_name)}
                       aria-describedby={visibleErrors.display_name ? 'user-name-error' : undefined} />
                <FieldError id="user-name-error" message={visibleErrors.display_name} />
              </div>

              {isCreate ? (
                <>
                  <div className="users-field users-field--full">
                    <label htmlFor="user-email">E-mail<b className="users-field__required" aria-hidden="true"> *</b></label>
                    <input id="user-email" type="email" value={form.email}
                           onChange={(event) => change('email', event.target.value)}
                           placeholder="nome@gentilnegocios.com.br" autoComplete="off" maxLength={254}
                           aria-invalid={Boolean(visibleErrors.email)}
                           aria-describedby={visibleErrors.email ? 'user-email-error' : undefined} />
                    <FieldError id="user-email-error" message={visibleErrors.email} />
                  </div>
                  <div className="users-field users-field--full">
                    <label htmlFor="user-username">Usuário</label>
                    <div className="users-prefixed">
                      <span aria-hidden="true">@</span>
                      <input id="user-username" value={form.username}
                             onChange={(event) => { setUsernameTouched(true); change('username', event.target.value.toLowerCase()) }}
                             placeholder="gerado a partir do e-mail" autoComplete="off" spellCheck="false" maxLength={64}
                             aria-invalid={Boolean(visibleErrors.username)}
                             aria-describedby={`user-username-hint${visibleErrors.username ? ' user-username-error' : ''}`} />
                    </div>
                    <small className="users-field__hint" id="user-username-hint">
                      Usado para entrar junto com o e-mail. Gerado automaticamente — ajuste se necessário.
                    </small>
                    <FieldError id="user-username-error" message={visibleErrors.username} />
                  </div>
                </>
              ) : null}

              <div className="users-field">
                <label htmlFor="user-profile">Perfil<b className="users-field__required" aria-hidden="true"> *</b></label>
                <select id="user-profile" value={form.profile} onChange={(event) => change('profile', event.target.value)}
                        disabled={lockProfile} aria-invalid={Boolean(visibleErrors.profile)}
                        aria-describedby={lockProfile ? 'user-profile-lock' : visibleErrors.profile ? 'user-profile-error' : undefined}>
                  <option value="" disabled>Selecione um perfil</option>
                  {PROFILE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </select>
                {lockProfile && (
                  <small className="users-field__hint" id="user-profile-lock">
                    Você é o único administrador ativo. Defina outro administrador antes de alterar o seu perfil.
                  </small>
                )}
                <FieldError id="user-profile-error" message={visibleErrors.profile} />
              </div>

              <div className="users-field">
                <label htmlFor="user-status">Status</label>
                <select id="user-status" value={form.status} onChange={(event) => change('status', event.target.value)}
                        disabled={lockStatus} aria-describedby={lockStatus ? 'user-status-lock' : undefined}>
                  {statusOptions.map((option) => (
                    <option key={option.value} value={option.value} disabled={option.value === 'pending'}>{option.label}</option>
                  ))}
                </select>
                {lockStatus && (
                  <small className="users-field__hint" id="user-status-lock">Você não pode desativar a sua própria conta.</small>
                )}
              </div>
            </div>
          </fieldset>

          {isCreate && (
            <fieldset>
              <legend>Acesso inicial</legend>
              {emailActions ? (
                <div className="users-choice" role="radiogroup" aria-label="Forma de acesso inicial">
                  <label className={`users-choice__option${passwordMode === 'email' ? ' is-selected' : ''}`}>
                    <input type="radio" name="password-mode" value="email" checked={passwordMode === 'email'}
                           onChange={() => setPasswordMode('email')} />
                    <UsersIcon name="mail" size={18} />
                    <span><strong>Enviar e-mail</strong><small>O usuário recebe um link para criar a própria senha.</small></span>
                  </label>
                  <label className={`users-choice__option${passwordMode === 'temporary' ? ' is-selected' : ''}`}>
                    <input type="radio" name="password-mode" value="temporary" checked={passwordMode === 'temporary'}
                           onChange={() => setPasswordMode('temporary')} />
                    <UsersIcon name="key" size={18} />
                    <span><strong>Senha temporária</strong><small>Você informa a senha; a troca é obrigatória no 1º acesso.</small></span>
                  </label>
                </div>
              ) : (
                <p className="users-form-note">
                  <UsersIcon name="info" size={16} />
                  O envio de e-mails ainda não está configurado no Keycloak. Defina uma senha temporária —
                  o usuário será obrigado a trocá-la no primeiro acesso.
                </p>
              )}
              {passwordMode === 'temporary' && (
                <PasswordField id="user-temp-password" value={form.temporary_password}
                               onChange={(value) => change('temporary_password', value)}
                               error={visibleErrors.temporary_password} />
              )}
            </fieldset>
          )}

          {!isCreate && (
            <fieldset>
              <legend>Acesso e senha</legend>
              {!user.identity_linked || !identityAdmin ? (
                <p className="users-form-note">
                  <UsersIcon name="info" size={16} />
                  {user.identity_linked
                    ? 'A integração com o Keycloak está indisponível no momento. Tente novamente mais tarde.'
                    : 'Este usuário ainda não possui conta vinculada no Keycloak. A senha é definida quando ele entrar pela primeira vez.'}
                </p>
              ) : (
                <div className="users-access-actions">
                  {!resetOpen ? (
                    <button type="button" className="users-access-action" onClick={() => { setResetOpen(true); setResetValue(generateTemporaryPassword()) }}>
                      <UsersIcon name="key" size={18} />
                      <span><strong>Definir senha temporária</strong><small>A senha atual deixa de valer e as sessões ativas são encerradas.</small></span>
                    </button>
                  ) : (
                    <div className="users-reset-panel">
                      <PasswordField id="user-reset-password" label="Nova senha temporária" value={resetValue}
                                     onChange={setResetValue} error={resetError} autoFocus />
                      <div className="users-reset-panel__actions">
                        <button type="button" className="users-button users-button--quiet" onClick={() => { setResetOpen(false); setResetError('') }}>
                          Cancelar
                        </button>
                        <button type="button" className="users-button users-button--primary" onClick={submitReset} disabled={saving}>
                          Redefinir senha
                        </button>
                      </div>
                    </div>
                  )}
                  {emailActions && (
                    <button type="button" className="users-access-action" onClick={onSendPasswordEmail} disabled={saving}>
                      <UsersIcon name="mail" size={18} />
                      <span><strong>Enviar e-mail de redefinição</strong><small>O usuário recebe um link para criar uma nova senha.</small></span>
                    </button>
                  )}
                </div>
              )}
            </fieldset>
          )}

          <div className="users-drawer__actions">
            <button className="users-button users-button--quiet" type="button" onClick={onCancel} disabled={saving}>Cancelar</button>
            <button className="users-button users-button--primary" type="submit" disabled={saving}>
              {saving ? 'Salvando…' : isCreate ? 'Criar usuário' : 'Salvar alterações'}
            </button>
          </div>
        </form>
      </aside>
    </div>
  )
}
