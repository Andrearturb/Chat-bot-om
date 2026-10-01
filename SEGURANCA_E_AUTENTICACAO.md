# Segurança e Autenticação — Chat-bot O&M

## Visão geral da arquitetura

```
 keycloak-central (repositório próprio)          Chat-bot O&M (este repositório)
 ┌──────────────────────────────┐               ┌────────────────────────────────┐
 │ Keycloak 26 (modo produção)  │◀── OIDC ─────▶│ backend FastAPI (BFF)          │
 │ PostgreSQL próprio           │  código+PKCE, │  - valida tokens pelo JWKS     │
 │ tema gentil-om               │  renovação,   │  - aplica a permissão por rota │
 │ Mailpit (somente DEV)        │  JWKS         │  - sessão server-side + cookie │
 └──────────────────────────────┘── backchannel ▶ frontend React (só exibe)      │
                                     logout      └────────────────────────────────┘
```

- O Keycloak não roda neste compose: fica no projeto `keycloak-central` (pasta irmã deste repositório).
- O app não guarda nenhuma credencial administrativa do Keycloak.
- Perfis, permissões, cadastro, liberação e bloqueio são decididos no Keycloak. O backend aplica o que vem no token assinado; o frontend só exibe.

## Separação de responsabilidades

| Componente | Responsabilidade |
|---|---|
| Keycloak (`keycloak-central`) | usuários, senhas, MFA, autocadastro, perfis, permissões, grupos, bloqueio, sessões SSO |
| Backend | validar tokens, manter a sessão, exigir a permissão de cada rota, auditoria, limites de IA |
| Frontend | exibir o que `/auth/me` informa; nenhuma regra de acesso |

## Provedor de identidade (`keycloak-central`)

- Subir, parar, backup, e-mails do DEV (Mailpit) e gestão de acesso: `../keycloak-central/docs/OPERACAO.md`.
- Usuários DEV: `admin.om`, `analista.om`, `gerente.om`, `diretor.om`, `convidado.om`. As senhas ficam nas variáveis `DEV_*_PASSWORD` do `.env` do `keycloak-central`.
- Tema de login `gentil-om`: `../keycloak-central/themes/gentil-om`.
- Console do realm (gestores de acesso): `http://localhost:8081/admin/gentil-dev/console/`.

## OIDC configurável

Tudo vem do `.env` do app: `OIDC_ISSUER_URL`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `OIDC_REDIRECT_URI`, `OIDC_POST_LOGOUT_REDIRECT_URI` e `KEYCLOAK_CONSOLE_URL`. Trocar de Keycloak é trocar esses valores.

## BFF (Backend-for-Frontend)

1. `GET /auth/login` (ou `/auth/register`, que abre o cadastro com `prompt=create`) gera `state`, `code_verifier` e `nonce`, grava em `oidc_login_requests` (uso único, 10 min; o `state` só como hash) e redireciona ao Keycloak.
2. `GET /auth/callback` consome o registro, troca o código com PKCE S256 e valida:
   - o access token pelo JWKS: assinatura RS256, `iss`, `aud`, `azp`, `typ=Bearer`, `exp`/`iat` com 30 s de tolerância;
   - o ID token: `typ=ID` e o `nonce`.

   O JWKS é recarregado quando aparece `kid` desconhecido, no máximo 1 vez por minuto.
3. As permissões são os papéis do client `chat-bot-om-bff`. Sem nenhuma permissão, a sessão não é criada: o SSO é encerrado e a pessoa vê "Sua conta ainda não foi liberada" (`auth_error=not_released`).
4. O navegador recebe apenas o cookie de sessão. Access, refresh e ID token nunca vão para o browser (o ID token só aparece como `id_token_hint` na URL de logout).

### Logout

- `POST /auth/logout` (com CSRF): revoga a sessão, revoga o refresh token no Keycloak (RFC 7009) e devolve a URL de logout OIDC com `id_token_hint` e `client_id`, que volta para `/login`.
- `POST /auth/backchannel-logout`: o Keycloak avisa o fim de uma sessão SSO. O backend aceita somente logout token assinado pelo Keycloak, com `iss`, `aud` = client, `iat` de até 2 min, o evento de backchannel logout, `sid` ou `sub` e sem `nonce`. Revoga as sessões do `sid` (ou todas do `sub`). Token inválido → 400 + evento de segurança. Em produção, o proxy expõe esse caminho só para a rede do Keycloak.

## Sessão server-side

- Cookie `om_session`: HttpOnly, SameSite=Lax, `Secure` em produção. No banco fica só o hash SHA-256 do token.
- A sessão guarda o **retrato** do acesso (permissões e perfis do token), o `sid` do Keycloak e o refresh token **cifrado** (Fernet, `SESSION_ENCRYPTION_KEY`).
- A cada 5 min de uso, o backend renova os tokens no Keycloak e atualiza o retrato. Uma trava por sessão (`SELECT ... FOR UPDATE SKIP LOCKED`) impede que duas abas usem o mesmo refresh token; a segunda aba usa o retrato atual enquanto a renovação termina.
- Renovação recusada (conta bloqueada, sessão encerrada, acesso retirado) → sessão revogada e 401.
- Keycloak fora do ar → o retrato atual vale por até 15 min, com uma tentativa a cada 30 s. Depois disso, a sessão cai.
- Ociosidade de 30 min e duração máxima de 8 h, como antes.

## CSRF

- `GET /auth/me` retorna o `csrf_token`
- React mantém o token em memória (AuthProvider)
- Todos os métodos mutáveis (POST/PUT/PATCH/DELETE) exigem `X-CSRF-Token`
- Backend compara com `session.csrf_secret` via `secrets.compare_digest`
- Falha → HTTP 403 + registro em `security_events`

---

## Usuários e perfis

- **Vínculo de identidade:** somente `issuer + subject` (`oidc_identities`). O e-mail é informativo e nunca é usado para vincular. Uma conta recriada no Keycloak vira um registro novo.
- **Conta nova:** o autocadastro exige confirmação de e-mail e nasce sem perfil. Um gestor de acesso libera incluindo a pessoa no grupo do perfil.
- **Gestão de Usuários (Configurações):** consulta somente leitura, com a permissão `users.view`. Mostra quem já entrou, o perfil do último acesso e se há sessão ativa, e tem o botão "Gerenciar no Keycloak".
- **Bloqueio imediato:** no console, desligar **Enabled** e encerrar as sessões (**Sign out**). Só desligar derruba o acesso em até 5 min.

## Perfis e permissões

Perfis e permissões são papéis do client `chat-bot-om-bff`. Os perfis são papéis compostos:

| Perfil | Permissões |
|---|---|
| ADMINISTRADOR | todas |
| GERENTE | assistant.use, assistant.history, indicators.view, assets.view, assets.create, assets.edit, assets.delete, assets.import, documents.view, documents.upload, documents.replace, documents.delete, audit.view, settings.view |
| ANALISTA | assistant.use, assistant.history, indicators.view, assets.view, assets.create, assets.edit, documents.view, documents.upload, documents.replace, settings.view |
| DIRETOR | assistant.use, assistant.history, indicators.view, assets.view, documents.view, settings.view |
| CONVIDADO | assistant.use, assistant.history, indicators.view, assets.view |

- Liberação = grupo `Chat-bot O&M · <Perfil>`. Permissão avulsa = atribuir o papel de permissão direto à pessoa no Keycloak.
- Perfil exibido: o de maior prioridade (ADMINISTRADOR > GERENTE > ANALISTA > DIRETOR > CONVIDADO).
- Toda rota protegida usa `require_permission("<código>")` sobre o retrato da sessão.

## Controle de uso da IA

Limites por perfil (diário / por minuto): Administrador 200/20, Analista 150/10, Gerente 120/10, Diretor 80/8, Convidado 20/3; sem perfil conhecido, 10/2. Quem tem mais de um perfil fica com o maior limite. Chamadas com erro não contam.

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

## Migração para o Keycloak da Gentil

Roteiro e checklist obrigatório: `../keycloak-central/docs/MIGRACAO_TI.md`. No app, basta atualizar o `.env`:
`OIDC_ISSUER_URL`, `OIDC_CLIENT_SECRET` (novo), `OIDC_REDIRECT_URI`, `OIDC_POST_LOGOUT_REDIRECT_URI`, `KEYCLOAK_CONSOLE_URL`, `SESSION_ENCRYPTION_KEY` (nova) e `SESSION_COOKIE_SECURE=true`.

## Variáveis de ambiente relevantes

| Variável | Uso |
|---|---|
| `OIDC_ISSUER_URL`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET` | Client `chat-bot-om-bff` no Keycloak |
| `OIDC_REDIRECT_URI`, `OIDC_POST_LOGOUT_REDIRECT_URI` | Retorno do login e do logout |
| `KEYCLOAK_CONSOLE_URL` | Link do console para quem tem `users.view` |
| `SESSION_SECRET`, `SESSION_ENCRYPTION_KEY` | Sessão e cifra do refresh token |
| `SESSION_COOKIE_SECURE`, `SESSION_IDLE_TIMEOUT_MINUTES`, `SESSION_ABSOLUTE_TIMEOUT_HOURS` | Cookie e tempos da sessão |
| `FRONTEND_ORIGINS` | CORS e destino após o login |
