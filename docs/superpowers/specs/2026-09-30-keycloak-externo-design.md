# Keycloak externo e autorização centralizada — Design

**Data:** 2026-09-30
**Status:** aprovado (2026-09-30)
**Escopo:** Chat-bot O&M (este repositório) + novo repositório `keycloak-central`

## 1. Contexto e objetivo

Hoje o Keycloak DEV sobe dentro do `docker-compose` do Chat-bot O&M (mesmo host e
rede, bootstrap com a senha do admin `master`, `start-dev`) e o banco do app é a
fonte da verdade de perfis e permissões (`profiles`, `permissions`, overrides),
editados pela Gestão de Usuários do app. O backend guarda uma credencial com
poder de gerir usuários no Keycloak (`chat-bot-om-admin`).

O frontend **não** concede permissões — toda rota é validada no backend —, mas a
decisão de "quem pode o quê" mora no app, e o app tem poder administrativo sobre
o provedor de identidade.

**Objetivo:** montar agora um Keycloak independente (container e repositório
próprios), já com o formato de produção, e preparar o app para que a migração
para o ambiente da Gentil Negócios seja apenas troca de configuração.

**Critérios de sucesso**

1. O Keycloak roda isolado do app: repositório, compose, rede, banco, volumes e
   segredos próprios, em modo produção.
2. O app não guarda nenhuma credencial administrativa do Keycloak.
3. Perfis, permissões, cadastro, liberação e bloqueio são decididos no Keycloak;
   o backend apenas aplica o que vem no token assinado.
4. Nenhuma regra de acesso depende do frontend.
5. Bloqueio no Keycloak derruba a sessão do app na hora; troca de perfil vale em
   até 5 minutos.
6. Migrar para o ambiente da Gentil = alterar o `.env` do app (sem mudar código).

## 2. Decisões tomadas

| Tema | Decisão |
|---|---|
| Onde roda o Keycloak | Projeto Docker próprio (DEV agora), mesmo formato para produção |
| Versionamento | Repositório separado `keycloak-central`, pasta irmã deste projeto (`...\Projetos\keycloak-central`), sem remoto por enquanto |
| Permissões | Perfis **e** permissões como papéis de client no Keycloak (perfis = papéis compostos) |
| Gestão de usuários | Somente no console do Keycloak; o app mostra uma consulta somente leitura |
| Revogação | Bloqueio imediato (backchannel logout); perfil atualizado em até 5 min (refresh no servidor) |
| Configuração do realm | Como código, com keycloak-config-cli (YAML declarativo e idempotente) |
| Autocadastro | Ligado, com confirmação de e-mail; conta nasce sem perfil; liberação = incluir em grupo |
| Domínio do autocadastro | Livre no DEV; restrição de domínio obrigatória antes de produção |
| Dados existentes | Recriar do zero **somente identidade e acesso**; preservar chamados, Central de Ativos (e arquivos) e n8n |
| Expiração de acesso (`access_expires_at`) | Removida (sem equivalente nativo no Keycloak) |
| Vínculo de identidade | Apenas `issuer + subject` (sem vínculo por e-mail) |

## 3. Arquitetura

```
 keycloak-central (repo próprio)                 Chat-bot O&M (este repo)
 ┌──────────────────────────────┐               ┌────────────────────────────────┐
 │ keycloak (modo produção)     │◀── OIDC ─────▶│ backend FastAPI (BFF)          │
 │ keycloak-db (PostgreSQL)     │  code+PKCE,   │  - valida tokens (JWKS)        │
 │ keycloak-config (job)        │  refresh,     │  - aplica permissões por rota  │
 │ mailpit (somente DEV)        │  JWKS         │  - sessão server-side + cookie │
 │ tema gentil-om               │               │ frontend React (só exibe)      │
 └──────────────────────────────┘── backchannel ▶ PostgreSQL / n8n (inalterados)  │
                                     logout      └────────────────────────────────┘
```

| Componente | Responsabilidade |
|---|---|
| Keycloak | usuários, senha, MFA, autocadastro, perfis, permissões de cada perfil, grupos, bloqueio, sessões SSO |
| Backend do app | validar tokens, manter sessão, aplicar a permissão exigida em cada rota, auditoria, limites de IA por perfil, dados do app |
| Frontend | exibir o que `/auth/me` informa; nenhuma regra de acesso |

**Comunicação**

- Navegador ↔ Keycloak: somente páginas de login, cadastro, confirmação de e-mail e troca de senha.
- Backend → Keycloak: discovery, troca de código (PKCE), renovação de token, JWKS, revogação de refresh token.
- Keycloak → backend: backchannel logout (`POST /auth/backchannel-logout`).
- DEV: o backend alcança o Keycloak em `http://localhost:8081` (via `extra_hosts: localhost:host-gateway`, como hoje); o Keycloak alcança o backend em `http://host.docker.internal:8040`.

## 4. Projeto `keycloak-central`

### 4.1 Estrutura

```
keycloak-central/
  docker-compose.yml        keycloak, keycloak-db, keycloak-config, mailpit (profile dev)
  Dockerfile                imagem Keycloak com build otimizado e tema embutido
  .env.example              segredos e parâmetros deste projeto
  config/
    realm-dev.yaml          realm gentil-dev completo (client, papéis, grupos, usuários DEV)
  themes/gentil-om/         tema de login (movido do Chat-bot O&M)
  scripts/
    backup-db.sh            pg_dump do banco do Keycloak
    export-realm.sh         exportação do realm para conferência
    smoke-test.sh           valida papéis, grupos e conteúdo do token
  docs/
    OPERACAO.md             subir, parar, backup, onde ver e-mails (Mailpit)
    MIGRACAO_TI.md          roteiro e checklist de produção
```

### 4.2 Execução

- Imagem: `quay.io/keycloak/keycloak:26.5.7` (recomendação: atualizar a partir do
  26.2.5 atual para a versão mais recente suportada oficialmente pelo
  keycloak-config-cli). Build otimizado: `KC_DB=postgres`, `KC_HEALTH_ENABLED=true`,
  `KC_METRICS_ENABLED=true`, tema copiado para `/opt/keycloak/themes/gentil-om`;
  execução `start --optimized`.
- DEV: `KC_HOSTNAME=http://localhost:8081`, `KC_HTTP_ENABLED=true`, porta publicada
  somente em `127.0.0.1:8081`. Hostname fixo garante `iss` estável.
- Produção: `KC_HOSTNAME=https://<sso>`, `KC_PROXY_HEADERS=xforwarded`, HTTPS no
  reverse proxy, `KC_HOSTNAME_ADMIN` apontando para endereço acessível apenas pela
  rede interna.
- `keycloak-db`: PostgreSQL 16 próprio, sem porta publicada, volume próprio.
- Healthcheck pela porta de gerenciamento (9000, interna): `/health/ready`.
- `keycloak-config`: `adorsys/keycloak-config-cli:6.5.1-26.5.5`, executa após o
  Keycloak ficar saudável, aplica `config/*.yaml` com substituição de variáveis de
  ambiente (segredos nunca ficam no YAML). DEV autentica com o admin de bootstrap.
- `mailpit` (somente DEV): `axllent/mailpit:v1.31.3`, SMTP interno na porta 1025,
  interface web em `127.0.0.1:8025`.

### 4.3 Realm `gentil-dev` (principais configurações)

| Configuração | Valor |
|---|---|
| Tema de login | `gentil-om`, idioma `pt-BR` |
| Autocadastro | `registrationAllowed=true`, `verifyEmail=true` |
| Login | por usuário ou e-mail; e-mails duplicados proibidos; "manter conectado" desligado |
| Esqueci minha senha | ligado (SMTP presente: Mailpit no DEV, SMTP da empresa em produção) |
| Força bruta | ligada; bloqueio temporário progressivo após 5 falhas (máx. 15 min) |
| Política de senha | `length(12) and notUsername and notEmail and passwordHistory(3)` |
| Tokens e sessões | access token 5 min; sessão ociosa 30 min; sessão máxima 8 h |
| Refresh token | rotação obrigatória (`revokeRefreshToken=true`, `refreshTokenMaxReuse=0`) |
| Eventos | eventos de login e de administração (com detalhes) guardados por 90 dias |
| Papéis padrão | `default-roles-gentil-dev` **sem** nenhum papel do client `chat-bot-om-bff` |

### 4.4 Client `chat-bot-om-bff`

- Confidencial; *standard flow* com PKCE `S256` obrigatório; *direct access grants*,
  *implicit* e *service account* desligados.
- `fullScopeAllowed=false`: o token só carrega papéis deste client.
- Mapper de audiência: `aud` contém `chat-bot-om-bff`.
- Redirect URIs, web origins e post-logout URIs do DEV (`http://localhost:5173/...`),
  parametrizados por variável.
- Backchannel logout: `http://host.docker.internal:8040/auth/backchannel-logout`
  (variável), `backchannel.logout.session.required=true`.

### 4.5 Contas administrativas

- DEV: o admin de bootstrap do realm `master` permanece (somente `127.0.0.1`) e é
  usado pelo job de configuração.
- Produção: admin nomeado com MFA no `master`; bootstrap removido; o job de
  configuração usa uma service account própria com administração restrita ao realm.
- Grupo **"Gestores de acesso"** no realm, com papéis de `realm-management`:
  `manage-users`, `view-users`, `query-users`, `query-groups`, `view-events`. Seus
  membros usam o console do realm (`/admin/gentil-dev/console/`) para cadastrar,
  liberar, bloquear e redefinir senhas. Não alteram clients nem configurações do realm.

### 4.6 Usuários DEV

`admin.om`, `analista.om`, `gerente.om`, `diretor.om`, `convidado.om`, criados pelo
YAML DEV com e-mail confirmado, senha vinda do `.env` e no grupo do respectivo perfil;
`admin.om` também em "Gestores de acesso". As senhas precisam atender à política
(mínimo 12 caracteres). A configuração de produção não inclui esses usuários.

## 5. Modelo de autorização

### 5.1 Papéis do client `chat-bot-om-bff`

**Permissões** (papéis simples): `assistant.use`, `assistant.history`,
`indicators.view`, `assets.view`, `assets.create`, `assets.edit`, `assets.delete`,
`assets.import`, `documents.view`, `documents.upload`, `documents.replace`,
`documents.delete`, `audit.view`, `users.view`, `settings.view`, `settings.manage`,
`sync.tape`.

**Perfis** (papéis compostos, mesma composição de hoje; `users.manage` → `users.view`):

| Perfil | Permissões |
|---|---|
| ADMINISTRADOR | todas |
| ANALISTA | assistant.use, assistant.history, indicators.view, assets.view, assets.create, assets.edit, documents.view, documents.upload, documents.replace, settings.view |
| GERENTE | assistant.use, assistant.history, indicators.view, assets.view, assets.create, assets.edit, assets.delete, assets.import, documents.view, documents.upload, documents.replace, documents.delete, audit.view, settings.view |
| DIRETOR | assistant.use, assistant.history, indicators.view, assets.view, documents.view, settings.view |
| CONVIDADO | assistant.use, assistant.history, indicators.view, assets.view |

**Grupos** (liberação): "Chat-bot O&M · Administradores", "· Analistas", "· Gerentes",
"· Diretores", "· Convidados", cada um com o papel do perfil. Permissão avulsa =
atribuir o papel de permissão direto à pessoa.

### 5.2 Uso do token no backend

1. Validação: assinatura via JWKS do Keycloak (cache; recarga quando aparece `kid`
   desconhecido, no máximo 1 vez/min), `iss` igual ao issuer configurado, `aud`
   contém o client, `azp` = client, `exp`/`iat` com tolerância de 30 s, tipo
   `Bearer`/`ID` conforme o token. No ID token, `nonce` igual ao enviado.
2. Extração: `resource_access["chat-bot-om-bff"].roles` → separa permissões (nomes
   da lista 5.1) e perfis (ADMINISTRADOR…CONVIDADO); papéis desconhecidos são ignorados.
3. Sem nenhuma permissão → nenhuma sessão; tela "Sua conta ainda não foi liberada".
4. Retrato na sessão: permissões, perfis e horário da última renovação.
5. Perfil exibido: o de maior prioridade (ADMINISTRADOR > GERENTE > ANALISTA >
   DIRETOR > CONVIDADO); limite de IA: o maior entre os perfis da pessoa.

## 6. Mudanças no Chat-bot O&M

### 6.1 Backend

**Novo módulo `app/services/oidc.py`**: discovery, cache de JWKS, validação de
tokens (Authlib, já instalado), troca de código, renovação, revogação (RFC 7009) e
validação de logout token.

**Login**
- `GET /auth/login`: gera `state`, `code_verifier` e `nonce`; grava em
  `oidc_login_requests` (uso único, validade 10 min) — substitui o dicionário em memória.
- `GET /auth/register`: igual, com `prompt=create` (abre o cadastro do Keycloak).
- `GET /auth/callback`: consome o registro de login, troca o código, valida os
  tokens (5.2) e, havendo permissão, cria a sessão guardando refresh token
  **criptografado** (Fernet, chave `SESSION_ENCRYPTION_KEY`), `id_token_hint`, `sid`
  e o retrato. Sem permissão: encerra o SSO (como hoje para usuários negados) e
  volta para `/login?auth_error=not_released`.

**Sessão e renovação**
- Em toda requisição autenticada, se o retrato tiver mais de 5 min, o backend
  renova com o refresh token, com trava por sessão (`SELECT ... FOR UPDATE`), grava o
  novo refresh token e atualiza o retrato. Depois de obter a trava, se outra
  requisição já renovou o retrato, não renova de novo (evita reuso do refresh token
  de uso único).
- Renovação **recusada** (ex.: `invalid_grant`, conta bloqueada) → sessão revogada, 401.
- Keycloak **inacessível** → mantém o retrato atual por no máximo 15 min desde a
  primeira falha (`refresh_failed_since`); depois, sessão revogada.
- `require_permission(código)` passa a consultar o retrato da sessão.

**Backchannel logout**: `POST /auth/backchannel-logout` (form `logout_token`), fora
de CSRF/CORS. Aceita somente logout token assinado pelo Keycloak, com `iss`, `aud`
= client, `iat` de no máximo 2 min (tolerância de 30 s), evento `http://schemas.openid.net/event/backchannel-logout`,
`sid` ou `sub`, e sem `nonce`. Revoga as sessões do `sid` (ou, sem `sid`, todas do
`sub`). Resposta 200; token inválido → 400 e evento de segurança. Em produção o
proxy deve expor esse caminho apenas para a rede do Keycloak.

**Logout**: como hoje (revoga a sessão, apaga o cookie, devolve URL de logout OIDC
com `id_token_hint` + `client_id`), e também revoga o refresh token no Keycloak.

**`/auth/me`**: mantém o formato atual (`profile`, `profile_display`,
`permissions`, `csrf_token`, `ai_usage`…) a partir do retrato; acrescenta `profiles`
e `keycloak_console_url` (somente se o usuário tiver `users.view`).

**Gestão de Usuários (somente leitura)**: `GET /users` exige `users.view`; lista
`app_users` com nome, e-mail, usuário, último perfil visto, último acesso e se há
sessão ativa. Busca por nome, e-mail ou usuário; filtro por perfil.

**Modelo de dados**
- `app_users` (registro de identidade): `id`, `email`, `username`,
  `display_name`, `last_profiles` (JSON), `created_at`, `updated_at`, `last_seen_at`.
  Saem `profile_id`, `status`, `access_expires_at`, limites individuais de IA e
  `bootstrap_admin_granted`.
- `oidc_identities`: inalterada (âncora `issuer + subject`).
- `user_sessions`: + `refresh_token_enc`, `sid` (indexado), `permissions` (JSON),
  `profiles` (JSON), `snapshot_refreshed_at`, `refresh_failed_since`.
- Nova `oidc_login_requests`: `state_hash`, `code_verifier`, `nonce`, `created_at`, `expires_at`.
- Removidas: `profiles`, `permissions`, `profile_permissions`, `user_permission_overrides`.
- Limites de IA: tabela fixa no código por perfil (valores atuais).

**Removido**: `services/keycloak_admin.py`, `services/user_admin.py`,
`seed_profiles_and_permissions`, pré-provisionamento DEV, bootstrap admin por
e-mail, `require_admin`, endpoints de criação/edição/ativação/senha/overrides/
expiração/limite de IA, status `pending`/`disabled` do app.

### 6.2 Frontend

- `/login`: mantém o layout; acrescenta ação secundária **"Criar conta"** →
  `/auth/register`; nova mensagem para `auth_error=not_released`
  ("Sua conta ainda não foi liberada").
- Tela "Acesso aguardando aprovação" passa a ser **"Conta ainda não liberada"**; a
  tela de conta desativada sai (o próprio Keycloak recusa o login e informa).
- Gestão de Usuários: somente leitura (sem "Novo usuário", sem drawer de edição,
  sem desativar); botão **"Gerenciar no Keycloak"** (abre `keycloak_console_url`).
  Visível apenas com `users.view`.
- 401 após falha de renovação leva ao login, com a proteção contra laço existente.

### 6.3 Docker Compose e configuração do app

- Saem `keycloak`, `keycloak-db`, `keycloak-bootstrap`, o volume
  `keycloak_postgres_data` e a pasta `keycloak/` do repositório.
- `.env` do app — permanecem: `OIDC_ISSUER_URL`, `OIDC_CLIENT_ID`,
  `OIDC_CLIENT_SECRET`, `OIDC_REDIRECT_URI`, `OIDC_POST_LOGOUT_REDIRECT_URI`, `SESSION_*`.
  Entram: `SESSION_ENCRYPTION_KEY`, `KEYCLOAK_CONSOLE_URL`. Saem: `KEYCLOAK_ADMIN_*`,
  `KEYCLOAK_DB*`, `KEYCLOAK_SMTP_*`, `DEV_*`, `BOOTSTRAP_ADMIN_EMAIL`, `DEV_PROVISION_USERS`.

## 7. Recriação dos dados de identidade (DEV)

Executada durante a implementação, com confirmação explícita antes de cada passo destrutivo:

1. Subir o `keycloak-central` e validar (smoke test).
2. Parar e remover os containers de Keycloak do compose do app; remover o volume
   `keycloak_postgres_data`.
3. Rodar `backend/scripts/reset_identity.sql`, que remove **somente** as tabelas de
   identidade e acesso: `user_permission_overrides`, `profile_permissions`,
   `permissions`, `profiles`, `user_sessions`, `oidc_identities`, `ai_usage`,
   `assistant_messages`, `assistant_conversations`, `audit_logs`, `security_events`,
   `app_users`. O backend recria as tabelas no novo formato ao iniciar.
4. Preservados: chamados (`services`, `uploads`), Central de Ativos (lojas,
   equipamentos, documentos e o volume `asset_documents_data`) e n8n.

## 8. Migração para o ambiente da Gentil

A TI sobe o `keycloak-central` (ou aplica o mesmo YAML num Keycloak corporativo) e
entrega ao app: URL do emissor, segredo do client e URL do console. Checklist
obrigatório (em `docs/MIGRACAO_TI.md`):

1. HTTPS e `KC_HOSTNAME` definitivos; console administrativo só na rede interna.
2. SMTP da empresa configurado; Mailpit desligado.
3. **Restrição de domínio de e-mail no autocadastro** (validador do atributo `email`).
4. Usuários DEV ausentes; admin nomeado com MFA; bootstrap removido.
5. Backchannel URL do app alcançável pelo Keycloak e restrita a ele no proxy.
6. Redirect e post-logout URIs de produção registradas.
7. App com `SESSION_COOKIE_SECURE=true` e novos segredos (`OIDC_CLIENT_SECRET`, `SESSION_ENCRYPTION_KEY`).

## 9. Tratamento de falhas

| Situação | Comportamento |
|---|---|
| Keycloak fora do ar no login | `/login` com mensagem amigável; sem sessão |
| Keycloak fora do ar com sessão ativa | retrato mantido por até 15 min; depois, novo login |
| Renovação recusada | sessão revogada imediatamente (401 → login) |
| `kid` desconhecido | recarga do JWKS (limitada a 1/min); persistindo, token recusado |
| Logout token inválido | 400 + evento de segurança; nenhuma sessão alterada |
| `state` inválido, expirado ou reutilizado | `/login?auth_error=invalid_state` |
| Usuário sem papel do app | sem sessão; "Sua conta ainda não foi liberada" |

## 10. Testes

- **Backend** (pytest, provedor OIDC simulado com chaves RSA reais assinando tokens):
  assinatura/`iss`/`aud`/`exp`/`nonce` inválidos; extração de permissões; sem papel →
  sem sessão; renovação (sucesso, recusa, uso único, concorrência de duas abas,
  janela de 15 min); backchannel válido e inválido; logout (sessão e refresh
  revogados); `state` de uso único; todas as rotas protegidas continuam exigindo a
  permissão; `/users` exige `users.view`. Testes do modelo antigo (Admin API,
  provisionamento, overrides) são removidos junto com o código.
- **Frontend** (`node --test`): utilitários da tela somente leitura e mensagens de
  `auth_error`.
- **keycloak-central**: `smoke-test.sh` sobe o ambiente, aplica o YAML, obtém um
  token do `analista.om` e confere perfis, permissões, `aud` e ausência de papéis
  de outros clients.
- **Ponta a ponta** (navegador): autocadastro → e-mail no Mailpit → "conta não
  liberada" → gestor inclui no grupo pelo console → login com acesso → retirada do
  grupo → perde acesso em até 5 min → bloqueio no console → sessão do app cai na
  hora → logout volta ao `/login`. Revisão visual das telas do tema (inclusive
  cadastro e confirmação de e-mail) em desktop e mobile.

## 11. Fora de escopo

- Federação com diretório corporativo (Microsoft/Google/AD) — possível depois, sem mudar o app.
- Captcha no cadastro.
- Tema de e-mail personalizado.
- Alta disponibilidade/cluster do Keycloak.
- Extensões (SPI) do Keycloak.
