# Segurança e Autenticação — Chat-bot O&M

## Visão geral da arquitetura

```
KEYCLOAK (DEV/PROD)
      │
    OIDC (Authorization Code + PKCE)
      │
      ▼
React ── cookie HttpOnly ──▶ FastAPI / BFF
                                  │
                                  ├── /auth/*        (OIDC, sessão, CSRF)
                                  ├── /assistant/*   (Gateway IA)
                                  ├── /services      (indicadores)
                                  ├── /assets/*      (ativos, documentos)
                                  ├── /users/*       (gestão de acessos)
                                  ├── /audit/*       (auditoria)
                                  │
                                  ├──▶ PostgreSQL
                                  └──▶ n8n (chamada interna com X-Internal-API-Key)
```

## Separação de responsabilidades

| Componente | Responsabilidade |
|---|---|
| **Keycloak** | Autenticação, identidade, senhas, MFA |
| **Chat-bot O&M** | Perfis, permissões, quotas IA, auditoria, sessões |

O Keycloak responde: **"Quem é esta pessoa?"**
O backend responde: **"O que esta pessoa pode fazer?"**

---

## Keycloak DEV

- Imagem: `quay.io/keycloak/keycloak:26.2.5` (versão pinada)
- Porta: `127.0.0.1:8081`
- Realm: `gentil-dev`
- Client: `chat-bot-om-bff`
- Fluxo: Authorization Code + PKCE (S256)
- Banco isolado: `keycloak-db` (PostgreSQL separado do principal)
- Volume: `keycloak_postgres_data`

### Usuários DEV

| Identidade DEV | Email configurável | Perfil inicial |
|---|---|---|
| `admin.om` | `DEV_ADMIN_EMAIL` | ADMINISTRADOR via bootstrap |
| `analista.om` | `DEV_ANALYST_EMAIL` | aguarda aprovação |
| `gerente.om` | `DEV_MANAGER_EMAIL` | aguarda aprovação |
| `diretor.om` | `DEV_DIRECTOR_EMAIL` | aguarda aprovação |
| `convidado.om` | `DEV_GUEST_EMAIL` | aguarda aprovação |

> Emails e senhas são definidos via variáveis `DEV_*` no `.env`. O serviço `keycloak-bootstrap` sincroniza o Keycloak DEV existente sem apagar o volume quando esses valores mudam.

---

## OIDC configurável

Todas as configurações OIDC vêm do ambiente. Para migrar para o Keycloak corporativo, basta alterar:

```env
OIDC_ISSUER_URL=https://sso.empresa.com/realms/producao
OIDC_CLIENT_ID=chat-bot-om-bff
OIDC_CLIENT_SECRET=<secret do registro>
OIDC_REDIRECT_URI=https://app.empresa.com/auth/callback
OIDC_POST_LOGOUT_REDIRECT_URI=https://app.empresa.com
```

Nenhuma URL do Keycloak está hardcoded no código.

---

## BFF (Backend-for-Frontend)

O navegador **nunca** recebe access_token ou refresh_token.

Fluxo:
1. `GET /auth/login` → FastAPI gera state + code_verifier, redireciona para Keycloak
2. Keycloak redireciona para `GET /auth/callback?code=...&state=...`
3. FastAPI valida state, troca code por tokens (server-side)
4. FastAPI resolve/cria usuário local, cria sessão, define cookie HttpOnly
5. Browser recebe apenas o cookie — sem tokens no localStorage

---

## Sessão server-side

Tabela: `user_sessions`

- Token opaco gerado com `secrets.token_urlsafe(32)`
- Apenas o hash SHA-256 é armazenado no banco
- Cookie: `HttpOnly=True`, `SameSite=Lax`, `Path=/`
- Em produção: `Secure=True`
- Idle timeout: `SESSION_IDLE_TIMEOUT_MINUTES` (padrão: 30)
- Absolute timeout: `SESSION_ABSOLUTE_TIMEOUT_HOURS` (padrão: 8)

---

## CSRF

- `GET /auth/me` retorna o `csrf_token`
- React mantém o token em memória (AuthProvider)
- Todos os métodos mutáveis (POST/PUT/PATCH/DELETE) exigem `X-CSRF-Token`
- Backend compara com `session.csrf_secret` via `secrets.compare_digest`
- Falha → HTTP 403 + registro em `security_events`

---

## Usuários e perfis

### Vinculação de identidade

1. Login OIDC → FastAPI busca `oidc_identities` por `issuer+subject`
2. Se não existir → busca `app_users` por email
3. Se não existir → cria `app_user` com `status=pending`
4. Bootstrap admin: em produção usa `BOOTSTRAP_ADMIN_EMAIL`; em desenvolvimento usa `DEV_ADMIN_EMAIL` como referência efetiva. A promoção também é reavaliada para uma identidade já vinculada enquanto `bootstrap_admin_granted=false`, permitindo recuperar um primeiro login que ficou `pending` por configuração incompleta.

### Status

- `pending` → aguarda aprovação
- `active` → acesso liberado
- `disabled` → bloqueado

### Expiração (Convidados)

Campo `access_expires_at` — verificado a cada request. Após expirar → HTTP 403 automático.

---

## Perfis e permissões

### Perfis

| Perfil | IA/dia | IA/min |
|---|---|---|
| ADMINISTRADOR | 200 | 20 |
| ANALISTA | 150 | 10 |
| GERENTE | 120 | 10 |
| DIRETOR | 80 | 8 |
| CONVIDADO | 20 | 3 |

### Permissões granulares

`assistant.use`, `assistant.history`, `indicators.view`, `assets.view`, `assets.create`,
`assets.edit`, `assets.delete`, `assets.import`, `documents.view`, `documents.upload`,
`documents.replace`, `documents.delete`, `audit.view`, `users.manage`, `settings.view`,
`settings.manage`, `sync.tape`

### Overrides individuais

Tabela `user_permission_overrides` — efeito `allow` ou `deny`.
Precedência: **deny individual > allow individual > perfil**

---

## Controle de uso da IA

1. Usuário autenticado e ativo?
2. Permissão `assistant.use`?
3. Limite por minuto não atingido?
4. Limite diário não atingido?
5. → Chama n8n

Se limite atingido → HTTP 429 com payload amigável.
Registros na tabela `ai_usage`.

---

## Gateway do assistente

`POST /assistant/chat` — substitui a chamada direta do frontend ao n8n.

O frontend **nunca** chama o n8n. A variável `VITE_N8N_WEBHOOK_URL` foi removida do frontend.
O backend usa `N8N_CHAT_WEBHOOK_URL` (apenas no servidor).

---

## Conversas no PostgreSQL

Tabelas: `assistant_conversations`, `assistant_messages`

- Conversas criadas no banco, não no localStorage
- `localStorage` mantém apenas preferências visuais não-sensíveis
- Isolamento: `WHERE conversation.user_id = current_user.id`
- Acesso a conversa alheia → HTTP 404 (não revela existência)
- ADMINISTRADOR não tem acesso automático a conversas de terceiros

---

## Proteção do n8n

O workflow n8n chama `POST /chatbot/structured-query` com header `X-Internal-API-Key`.
- Sem chave → 401
- Chave errada → 401
- A chave **não está** no JSON do workflow; usa Credential do n8n

---

## Auditoria

Tabela `audit_logs` registra:
`ASSET_CREATE`, `ASSET_UPDATE`, `ASSET_DELETE`,
`DOCUMENT_UPLOAD`, `DOCUMENT_REPLACE`, `DOCUMENT_DELETE`, `DOCUMENT_VIEW`, `DOCUMENT_DOWNLOAD`,
`USER_ACTIVATE`, `USER_DISABLE`, `USER_ROLE_CHANGE`, `USER_PERMISSION_OVERRIDE`, `USER_AI_LIMIT_CHANGE`,
`LOGIN_SUCCESS`, `LOGOUT`, `SYNC_TAPE`

Tabela `security_events` registra:
`LOGIN_FAILED`, `ACCESS_DENIED`, `SESSION_EXPIRED`, `CSRF_REJECTED`, `AI_RATE_LIMIT`, `AI_DAILY_LIMIT`,
`INVALID_INTERNAL_API_KEY`

Nunca são gravados: tokens, cookies, senhas, secrets, base64 de arquivos.

---

## Headers de segurança

```
X-Content-Type-Options: nosniff
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: camera=(), microphone=(), geolocation=()
X-Frame-Options: DENY
Content-Security-Policy: default-src 'self'; frame-ancestors 'none'; ...
Strict-Transport-Security: max-age=63072000 (apenas em produção)
```

---

## Migração para Keycloak corporativo

1. TI registra o client `chat-bot-om-bff` no Keycloak corporativo
2. TI informa: issuer URL, client ID, client secret, redirect URIs
3. Atualizar `.env` de produção com os novos valores OIDC
4. Garantir HTTPS nas redirect URIs e `SESSION_COOKIE_SECURE=true`
5. Testar login com uma conta corporativa
6. Verificar que `iss` do token JWT bate com `OIDC_ISSUER_URL`
7. Vincular identidades (novos `oidc_identities` são criados automaticamente pelo email)

Perfis, permissões e quotas **permanecem no banco do Chat-bot O&M** — não precisam ser reconfigurados.

---

## Variáveis de ambiente relevantes

Ver `.env.example` para lista completa e descrições.

| Variável | Descrição |
|---|---|
| `OIDC_ISSUER_URL` | URL do realm Keycloak |
| `OIDC_CLIENT_SECRET` | Secret do client BFF |
| `SESSION_SECRET` | Chave de assinatura de sessão |
| `INTERNAL_API_KEY` | Chave n8n → backend |
| `BOOTSTRAP_ADMIN_EMAIL` | Email de bootstrap em produção; em DEV prevalece `DEV_ADMIN_EMAIL` |
| `DEV_ADMIN_EMAIL` | Email do usuário `admin.om` no Keycloak DEV e referência de bootstrap local |
| `FRONTEND_ORIGINS` | Origins CORS permitidas |
