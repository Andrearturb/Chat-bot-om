# Keycloak externo e autorização centralizada — Plano de implementação

> **Nome atual:** após a execução deste plano, o repositório `gentil-identity` foi renomeado para `keycloak-central`. Os nomes e caminhos antigos abaixo documentam os passos originais. A instalação DEV preserva o nome anterior do projeto Docker Compose no `.env` local para reutilizar o volume existente.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tirar o Keycloak de dentro do Chat-bot O&M (novo repositório `gentil-identity`, em modo produção) e fazer o Keycloak decidir perfis, permissões, cadastro, liberação e bloqueio; o app vira um cliente OIDC sem credencial administrativa.

**Architecture:** O `gentil-identity` sobe Keycloak 26.5.7 (build otimizado + tema `gentil-om`), PostgreSQL próprio, um job keycloak-config-cli que aplica o realm a partir de YAML e o Mailpit no DEV. O backend FastAPI continua como BFF (código + PKCE + `nonce`, cookie HttpOnly), passa a validar os tokens pelo JWKS e guarda na sessão um retrato dos papéis do client `chat-bot-om-bff`. Esse retrato é renovado a cada 5 min com o refresh token (cifrado com Fernet). O Keycloak derruba sessões pelo backchannel logout.

**Tech Stack:** Keycloak 26.5.7, keycloak-config-cli 6.5.1-26.5.5, Mailpit 1.31.3, PostgreSQL 16, FastAPI + SQLAlchemy 2, Authlib 1.3.2 (JOSE), cryptography 44 (Fernet), httpx (MockTransport nos testes), React + Vite, `node --test`, Playwright (somente no venv de E2E do `gentil-identity`).

**Spec:** `docs/superpowers/specs/2026-09-30-keycloak-externo-design.md`

### Convenções de execução

- Shell: Git Bash. No início de cada bloco de comandos, defina:

  ```bash
  APP="/c/Users/andre.brito/OneDrive - Gentil Negócios/Área de Trabalho/Projetos/Chat-bot-OM"
  IDP="/c/Users/andre.brito/OneDrive - Gentil Negócios/Área de Trabalho/Projetos/gentil-identity"
  PY="$APP/.venv/Scripts/python.exe"
  ```

- Testes do backend: `cd "$APP/backend" && "$PY" -m pytest -q <arquivos>`.
- Testes do frontend: `cd "$APP/frontend" && npm test`.
- Em comandos `docker exec` com caminhos, use `MSYS_NO_PATHCONV=1`.
- Nunca imprima segredos no terminal (`.env`, senhas, client secret).
- Passos marcados com ⚠ são destrutivos: **pare e peça confirmação explícita ao usuário antes de cada um**.
- Commits terminam com a linha `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

### Refinamentos em relação ao spec

- `config/realm-dev.yaml` vira dois arquivos: `config/10-realm.yaml` (vale para produção) e `config/20-dev-users.yaml` (só DEV). Assim a produção aplica o realm sem os usuários DEV.
- `smoke-test.sh` vira `scripts/smoke_test.py` (somente biblioteca padrão; o Windows não tem `jq`). Pelo mesmo motivo, `export-realm.sh` vira `scripts/export_realm.py`. Os scripts de admin compartilham `scripts/kcadmin.py`.
- Busca e filtro da Gestão de Usuários ficam no frontend, sobre a lista completa devolvida por `GET /users` (poucos usuários; o frontend atual já faz isso).
- A restrição de domínio do autocadastro será aplicada por `scripts/restrict_email_domain.py` (validador `pattern` no atributo `email` do *user profile*). Ela vale em todos os contextos, inclusive na criação de usuários pelo console.

## Global Constraints

- Imagens: `quay.io/keycloak/keycloak:26.5.7`, `adorsys/keycloak-config-cli:6.5.1-26.5.5`, `axllent/mailpit:v1.31.3`, `postgres:16`.
- Realm `gentil-dev`; client `chat-bot-om-bff`; issuer DEV final `http://localhost:8081/realms/gentil-dev`.
- Política de senha: `length(12) and notUsername and notEmail and passwordHistory(3)`.
- Tokens e sessões: access token 5 min (300 s); sessão ociosa 30 min (1800 s); sessão máxima 8 h (28800 s); `revokeRefreshToken=true`, `refreshTokenMaxReuse=0`.
- Força bruta: bloqueio temporário progressivo após 5 falhas, no máximo 15 min.
- Eventos de login e de administração (com detalhes) guardados por 90 dias.
- `default-roles-gentil-dev` sem nenhum papel do client `chat-bot-om-bff`.
- App: retrato renovado a cada 300 s; tolerância com Keycloak fora do ar de 15 min; tolerância de relógio de 30 s; registro de login válido por 600 s; logout token com `iat` de no máximo 120 s; JWKS recarregado no máximo 1 vez a cada 60 s.
- Prioridade de perfil: ADMINISTRADOR > GERENTE > ANALISTA > DIRETOR > CONVIDADO. Limite de IA = o maior entre os perfis da pessoa.
- Nenhuma dependência nova de Python ou npm no app (Authlib e cryptography já estão em `backend/requirements.txt`).
- O app não guarda credencial administrativa do Keycloak. O navegador nunca recebe access token nem refresh token.
- Textos de interface em pt-BR; a identidade visual aprovada não muda.
- Dados de negócio preservados: chamados (`services`, `uploads`), Central de Ativos (`asset_stores`, `climate_assets`, `fire_assets`, `water_assets`, `store_documents` e o volume `asset_documents_data`) e n8n. Nunca usar `docker compose down -v` no app.

## Review Focus

1. **Mesmo e-mail com outro `subject`** (conta apagada e recriada no Keycloak): vira um usuário novo no app e não herda conversas nem auditoria do antigo. Teste na Task 7.
2. **Duas abas renovando ao mesmo tempo:** só uma requisição usa o refresh token (de uso único) e as duas continuam autenticadas. Teste na Task 8.
3. **Keycloak fora do ar com sessão ativa:** o retrato atual continua valendo, com no máximo 1 tentativa de renovação a cada 30 s, e a sessão cai após 15 min. Teste na Task 8.
4. **Replay do callback** (mesmo `state` e `code` reenviados): a segunda tentativa volta com `invalid_state` e nenhuma segunda sessão é criada. Teste na Task 9.
5. **Backchannel logout de sessão desconhecida** (`sid` que o app não conhece): responde 200, nada muda e nenhum erro é registrado. Teste na Task 9.

## Mapa de arquivos

**`gentil-identity` (novo repositório, pasta irmã)**

| Arquivo | Responsabilidade |
|---|---|
| `Dockerfile` | Imagem Keycloak com build otimizado e tema embutido |
| `docker-compose.yml` | `keycloak-db`, `keycloak`, `keycloak-config`, `mailpit` (profile `dev`) |
| `docker-compose.prod.yml` | Ajustes de produção (proxy, console interno) |
| `.env.example`, `.gitignore`, `.gitattributes`, `README.md` | Configuração e apresentação |
| `config/10-realm.yaml` | Realm, client, papéis, grupos, SMTP |
| `config/20-dev-users.yaml` | Usuários DEV |
| `themes/gentil-om/` | Tema de login (movido do app), agora com cadastro |
| `scripts/init_env.py` | Cria o `.env` com segredos aleatórios |
| `scripts/kcadmin.py` | Cliente mínimo da Admin API (stdlib) |
| `scripts/smoke_test.py` | Confere realm, client, papéis, grupos, usuários e token |
| `scripts/export_realm.py`, `scripts/backup-db.sh` | Exportação para conferência e backup |
| `scripts/restrict_email_domain.py` | Liga/desliga a restrição de domínio de e-mail |
| `scripts/e2e_flow.py` | Teste ponta a ponta no navegador |
| `docs/OPERACAO.md`, `docs/MIGRACAO_TI.md` | Operação diária e roteiro de produção |

**Chat-bot O&M (este repositório)**

| Arquivo | Ação |
|---|---|
| `backend/app/services/permissions.py` | Criar: catálogo de permissões e perfis, retrato, limites de IA |
| `backend/app/services/oidc.py` | Criar: discovery, JWKS, validação, troca, renovação, revogação |
| `backend/app/services/session_refresh.py` | Criar: renovação do retrato com trava por sessão |
| `backend/app/services/auth.py` | Reescrever: sessões, identidade local, IA, auditoria |
| `backend/app/models/auth.py` | Alterar: remove perfis/permissões/overrides; novos campos de sessão; `OidcLoginRequest` |
| `backend/app/core/config.py` | Alterar: novas variáveis; remove Admin API, bootstrap e DEV |
| `backend/app/api/dependencies.py` | Alterar: sessão renovada, permissão pelo retrato; remove `require_admin` |
| `backend/app/api/routes/auth.py` | Reescrever: login, cadastro, callback, me, logout, backchannel |
| `backend/app/api/routes/users.py` | Reescrever: consulta somente leitura |
| `backend/app/main.py` | Alterar: remove seed e provisionamento; valida a chave de sessão |
| `backend/scripts/reset_identity.sql` | Criar: recriação só de identidade e acesso |
| `backend/app/services/keycloak_admin.py`, `user_admin.py`, `backend/app/db/schema_updates.py` | Remover |
| `backend/tests/oidc_fake.py`, `api_harness.py` | Criar: provedor OIDC simulado e harness do TestClient |
| `backend/tests/test_permissions.py`, `test_oidc.py`, `test_session_refresh.py`, `test_auth_flow.py` | Criar |
| `backend/tests/test_auth_security.py`, `test_api_security.py`, `conftest.py` | Reescrever/ajustar |
| `backend/tests/test_user_management.py` | Remover |
| `frontend/src/features/auth/*` | `not_released`, "Criar conta", `canViewUsers`; remove telas pendente/desativada |
| `frontend/src/features/users/*` | Gestão de Usuários somente leitura |
| `frontend/src/App.jsx`, `features/settings/SettingsModal.jsx` | Ajustes de fiação e texto |
| `docker-compose.yml`, `.env.example`, `SEGURANCA_E_AUTENTICACAO.md` | Sem Keycloak embutido |
| `keycloak/` | Remover (tema vai para o `gentil-identity`) |

**Ordem e estado do app entre tarefas:** as Tasks 1–4 não mexem no app. Nas Tasks 7 e 8 o backend fica temporariamente sem subir (as rotas antigas ainda importam funções removidas), e só os testes indicados em cada tarefa rodam. A Task 9 restaura o app e a suíte completa. O Keycloak antigo do app continua no ar até a Task 13; por isso o `gentil-identity` usa a porta 8082 até lá.

---

### Task 0: Preparação

**Files:** nenhum arquivo versionado.

**Interfaces:**
- Consumes: nada.
- Produces: branch `feature/keycloak-externo`; venv local com Authlib e cryptography.

- [ ] **Step 1: Criar a branch e versionar o plano**

No spec (`docs/superpowers/specs/2026-09-30-keycloak-externo-design.md`), troque a linha `**Status:** aguardando revisão` por `**Status:** aprovado (2026-09-30)`. Depois:

```bash
cd "$APP" && git status --short && git switch -c feature/keycloak-externo
git add docs/superpowers && git commit -m "docs: plano do Keycloak externo e spec aprovado

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Expected: o `git status --short` mostra só o plano (novo) e o spec (modificado); `Switched to a new branch 'feature/keycloak-externo'`; commit criado.

- [ ] **Step 2: Instalar no venv local as versões já fixadas no requirements**

```bash
"$PY" -m pip install "Authlib==1.3.2" "cryptography==44.0.3" python-multipart
"$PY" -c "import authlib, cryptography, sqlite3; print(authlib.__version__, cryptography.__version__, sqlite3.sqlite_version)"
```

Expected: `1.3.2 44.0.3 3.x` com SQLite ≥ 3.35 (necessário para `DELETE ... RETURNING` nos testes).

- [ ] **Step 3: Registrar a linha de base dos testes**

```bash
cd "$APP/backend" && "$PY" -m pytest -q 2>&1 | tail -3
cd "$APP/frontend" && npm test 2>&1 | tail -8
```

Expected: backend `286 passed`; frontend `# pass 25`, `# fail 0`. Anote os números no relatório da tarefa.

---

### Task 1: Repositório `gentil-identity`, imagem e compose

**Files:**
- Create: `$IDP/.gitignore`, `$IDP/.gitattributes`, `$IDP/Dockerfile`, `$IDP/docker-compose.yml`, `$IDP/docker-compose.prod.yml`, `$IDP/.env.example`, `$IDP/scripts/init_env.py`
- Copy: `$APP/keycloak/themes/gentil-om/` → `$IDP/themes/gentil-om/`

**Interfaces:**
- Consumes: tema atual em `$APP/keycloak/themes/gentil-om`.
- Produces: `docker compose up -d` no `$IDP` sobe `keycloak-db`, `keycloak` (saudável) e `mailpit`. Variáveis do `.env` usadas pelas próximas tarefas: `KC_HOSTNAME`, `KC_PUBLIC_PORT`, `KC_BOOTSTRAP_ADMIN_USERNAME`, `KC_BOOTSTRAP_ADMIN_PASSWORD`, `REALM_NAME`, `APP_BASE_URL`, `CHATBOT_CLIENT_SECRET`, `BACKCHANNEL_LOGOUT_URL`, `SMTP_*`, `DEV_*_PASSWORD`.

- [ ] **Step 1: Criar o repositório e copiar o tema**

```bash
mkdir -p "$IDP" && cd "$IDP" && git init -b main
mkdir -p themes config scripts docs backups
cp -r "$APP/keycloak/themes/gentil-om" themes/
```

- [ ] **Step 2: Criar `.gitignore` e `.gitattributes`**

`.gitignore`:

```gitignore
.env
backups/
.venv-e2e/
__pycache__/
e2e-shots/
```

`.gitattributes`:

```gitattributes
* text=auto
*.sh text eol=lf
*.yaml text eol=lf
*.ftl text eol=lf
*.properties text eol=lf
*.png binary
*.woff2 binary
```

- [ ] **Step 3: Criar o `Dockerfile`**

```dockerfile
# Keycloak em modo produção: build otimizado com o tema embutido.
FROM quay.io/keycloak/keycloak:26.5.7 AS builder
ENV KC_DB=postgres \
    KC_HEALTH_ENABLED=true \
    KC_METRICS_ENABLED=true
COPY --chown=keycloak:keycloak themes/gentil-om /opt/keycloak/themes/gentil-om
RUN /opt/keycloak/bin/kc.sh build

FROM quay.io/keycloak/keycloak:26.5.7
COPY --from=builder /opt/keycloak/ /opt/keycloak/
ENTRYPOINT ["/opt/keycloak/bin/kc.sh"]
CMD ["start", "--optimized"]
```

- [ ] **Step 4: Criar o `docker-compose.yml`**

```yaml
name: gentil-identity

services:
  keycloak-db:
    image: postgres:16
    restart: unless-stopped
    environment:
      POSTGRES_DB: keycloak
      POSTGRES_USER: keycloak
      POSTGRES_PASSWORD: ${KC_DB_PASSWORD:?defina KC_DB_PASSWORD no .env}
    volumes:
      - keycloak_db_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U keycloak -d keycloak"]
      interval: 10s
      timeout: 5s
      retries: 10

  keycloak:
    build: .
    image: gentil-identity/keycloak:26.5.7
    restart: unless-stopped
    environment:
      KC_DB_URL: jdbc:postgresql://keycloak-db:5432/keycloak
      KC_DB_USERNAME: keycloak
      KC_DB_PASSWORD: ${KC_DB_PASSWORD}
      # Hostname fixo = "iss" estável nos tokens (o app confere o issuer).
      KC_HOSTNAME: ${KC_HOSTNAME:?defina KC_HOSTNAME no .env}
      KC_HTTP_ENABLED: ${KC_HTTP_ENABLED:-false}
      KC_BOOTSTRAP_ADMIN_USERNAME: ${KC_BOOTSTRAP_ADMIN_USERNAME:-admin}
      KC_BOOTSTRAP_ADMIN_PASSWORD: ${KC_BOOTSTRAP_ADMIN_PASSWORD:?defina KC_BOOTSTRAP_ADMIN_PASSWORD no .env}
    ports:
      # Somente na máquina local; em produção o acesso passa pelo reverse proxy.
      - "127.0.0.1:${KC_PUBLIC_PORT:-8081}:8080"
    extra_hosts:
      # DEV: o backchannel logout alcança o backend do app publicado no host.
      - "host.docker.internal:host-gateway"
    depends_on:
      keycloak-db:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "bash", "-c", "exec 3<>/dev/tcp/127.0.0.1/9000 && printf 'GET /health/ready HTTP/1.1\\r\\nHost: localhost\\r\\nConnection: close\\r\\n\\r\\n' >&3 && grep -q 'HTTP/1.1 200' <&3"]
      interval: 15s
      timeout: 5s
      retries: 20
      start_period: 40s

  keycloak-config:
    image: adorsys/keycloak-config-cli:6.5.1-26.5.5
    restart: "no"
    depends_on:
      keycloak:
        condition: service_healthy
    environment:
      KEYCLOAK_URL: http://keycloak:8080
      KEYCLOAK_USER: ${KC_BOOTSTRAP_ADMIN_USERNAME:-admin}
      KEYCLOAK_PASSWORD: ${KC_BOOTSTRAP_ADMIN_PASSWORD}
      KEYCLOAK_AVAILABILITYCHECK_ENABLED: "true"
      KEYCLOAK_AVAILABILITYCHECK_TIMEOUT: 120s
      IMPORT_FILES_LOCATIONS: ${IMPORT_FILES_LOCATIONS:-/config/10-realm.yaml,/config/20-dev-users.yaml}
      IMPORT_VARSUBSTITUTION_ENABLED: "true"
      REALM_NAME: ${REALM_NAME:-gentil-dev}
      APP_BASE_URL: ${APP_BASE_URL:?defina APP_BASE_URL no .env}
      CHATBOT_CLIENT_SECRET: ${CHATBOT_CLIENT_SECRET:?defina CHATBOT_CLIENT_SECRET no .env}
      BACKCHANNEL_LOGOUT_URL: ${BACKCHANNEL_LOGOUT_URL:?defina BACKCHANNEL_LOGOUT_URL no .env}
      SMTP_HOST: ${SMTP_HOST:?defina SMTP_HOST no .env}
      SMTP_PORT: ${SMTP_PORT:-1025}
      SMTP_FROM: ${SMTP_FROM:?defina SMTP_FROM no .env}
      SMTP_FROM_NAME: ${SMTP_FROM_NAME:-Chat-bot O&M}
      SMTP_STARTTLS: ${SMTP_STARTTLS:-false}
      SMTP_AUTH: ${SMTP_AUTH:-false}
      SMTP_USER: ${SMTP_USER:-}
      SMTP_PASSWORD: ${SMTP_PASSWORD:-}
      DEV_ADMIN_PASSWORD: ${DEV_ADMIN_PASSWORD:-}
      DEV_ANALYST_PASSWORD: ${DEV_ANALYST_PASSWORD:-}
      DEV_MANAGER_PASSWORD: ${DEV_MANAGER_PASSWORD:-}
      DEV_DIRECTOR_PASSWORD: ${DEV_DIRECTOR_PASSWORD:-}
      DEV_GUEST_PASSWORD: ${DEV_GUEST_PASSWORD:-}
    volumes:
      - ./config:/config:ro

  mailpit:
    image: axllent/mailpit:v1.31.3
    profiles: [dev]
    restart: unless-stopped
    ports:
      - "127.0.0.1:${MAILPIT_UI_PORT:-8025}:8025"

volumes:
  keycloak_db_data:
```

- [ ] **Step 5: Criar o `docker-compose.prod.yml`**

```yaml
# Produção: docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
# TLS termina no reverse proxy; o console administrativo fica num endereço interno.
services:
  keycloak:
    environment:
      KC_HTTP_ENABLED: "true"
      KC_PROXY_HEADERS: xforwarded
      KC_HOSTNAME_ADMIN: ${KC_HOSTNAME_ADMIN:?defina KC_HOSTNAME_ADMIN no .env}
```

- [ ] **Step 6: Criar o `.env.example`**

```dotenv
# gentil-identity — copie para .env com: python scripts/init_env.py
# NUNCA versione o .env.

# DEV: sobe o Mailpit. Em produção deixe vazio.
COMPOSE_PROFILES=dev

# ── Keycloak ──────────────────────────────────────────────────────────────────
# URL pública completa; vira o "iss" dos tokens. Produção: https://<sso>
KC_HOSTNAME=http://localhost:8081
KC_PUBLIC_PORT=8081
# DEV sem TLS. Produção: TLS no proxy (ver docker-compose.prod.yml).
KC_HTTP_ENABLED=true
# Produção: endereço do console acessível só pela rede interna.
KC_HOSTNAME_ADMIN=
KC_DB_PASSWORD=
KC_BOOTSTRAP_ADMIN_USERNAME=admin
KC_BOOTSTRAP_ADMIN_PASSWORD=

# ── Realm e client do Chat-bot O&M ────────────────────────────────────────────
REALM_NAME=gentil-dev
APP_BASE_URL=http://localhost:5173
# Mesmo valor vai para OIDC_CLIENT_SECRET no .env do Chat-bot O&M.
CHATBOT_CLIENT_SECRET=
BACKCHANNEL_LOGOUT_URL=http://host.docker.internal:8040/auth/backchannel-logout

# ── SMTP (DEV: Mailpit; produção: SMTP da empresa) ────────────────────────────
SMTP_HOST=mailpit
SMTP_PORT=1025
SMTP_FROM=nao-responda@chatbot-om.local
SMTP_FROM_NAME=Chat-bot O&M
SMTP_STARTTLS=false
SMTP_AUTH=false
SMTP_USER=
SMTP_PASSWORD=

# ── Usuários DEV (config/20-dev-users.yaml; mínimo 12 caracteres) ─────────────
DEV_ADMIN_PASSWORD=
DEV_ANALYST_PASSWORD=
DEV_MANAGER_PASSWORD=
DEV_DIRECTOR_PASSWORD=
DEV_GUEST_PASSWORD=
```

- [ ] **Step 7: Criar `scripts/init_env.py`**

```python
"""Cria o .env a partir do .env.example, gerando segredos aleatórios.

Preenche somente chaves vazias terminadas em _PASSWORD ou _SECRET (exceto
SMTP_PASSWORD). Não sobrescreve um .env existente e não imprime segredos.
"""
from __future__ import annotations

import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP = {"SMTP_PASSWORD"}


def main() -> int:
    target = ROOT / ".env"
    if target.exists():
        print(".env já existe; nada foi alterado.")
        return 1
    lines = []
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and not line.startswith("#") and not value and key not in SKIP \
                and key.endswith(("_PASSWORD", "_SECRET")):
            line = f"{key}={secrets.token_urlsafe(24)}"
        lines.append(line)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(".env criado com segredos aleatórios.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 8: Gerar o `.env` e usar a porta 8082 até a Task 13**

```bash
cd "$IDP" && "$PY" scripts/init_env.py
sed -i 's#^KC_HOSTNAME=.*#KC_HOSTNAME=http://localhost:8082#; s#^KC_PUBLIC_PORT=.*#KC_PUBLIC_PORT=8082#' .env
grep -E "^(KC_HOSTNAME|KC_PUBLIC_PORT)=" .env
```

Expected: `.env criado com segredos aleatórios.`, depois `KC_HOSTNAME=http://localhost:8082` e `KC_PUBLIC_PORT=8082`.

- [ ] **Step 9: Construir e subir (sem o job de configuração)**

```bash
cd "$IDP" && docker compose build keycloak && docker compose up -d keycloak-db keycloak mailpit
docker compose ps --format "table {{.Service}}\t{{.Status}}"
```

Expected (após ~1 min, repita o `ps` se preciso): `keycloak` com `(healthy)`, `keycloak-db` com `(healthy)`, `mailpit` com `Up`.

- [ ] **Step 10: Conferir o issuer do realm master e o Mailpit**

```bash
curl -s http://localhost:8082/realms/master/.well-known/openid-configuration | grep -o '"issuer":"[^"]*"'
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8025/
```

Expected: `"issuer":"http://localhost:8082/realms/master"` e `200`.

- [ ] **Step 11: Commit**

```bash
cd "$IDP" && git add . && git status --short | grep -c "\.env$" ; git commit -m "chore: Keycloak 26.5.7 em modo produção com tema gentil-om e Mailpit

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Expected: o `grep -c` imprime `0` (o `.env` não entra no commit).

---

### Task 2: Realm como código e smoke test

**Files:**
- Create: `$IDP/scripts/kcadmin.py`, `$IDP/scripts/smoke_test.py`, `$IDP/config/10-realm.yaml`, `$IDP/config/20-dev-users.yaml`

**Interfaces:**
- Consumes: `.env` e serviços da Task 1.
- Produces:
  - realm `gentil-dev`: client `chat-bot-om-bff` com 17 papéis de permissão e 5 papéis compostos de perfil; grupos `Chat-bot O&M · Administradores|Analistas|Gerentes|Diretores|Convidados` e `Gestores de acesso`; usuários DEV `admin.om`, `analista.om`, `gerente.om`, `diretor.om`, `convidado.om`.
  - `scripts/kcadmin.py`:
    - `load_env() -> dict[str, str]`;
    - `password_token(base_url, realm, client_id, username, password) -> str`;
    - `class KeycloakAdmin(base_url, *, realm, token)` com `from_env()`, `get(path, **params)`, `put(path, body)`, `post(path, body=None)`, `delete(path)`, `client_uuid(client_id)`, `user_by_username(username)`;
    - `AdminError(status, body)`.

- [ ] **Step 1: Criar `scripts/kcadmin.py`**

```python
"""Cliente mínimo da Admin API do Keycloak (somente biblioteca padrão)."""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class AdminError(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:300]}")
        self.status = status


def load_env(path: Path = ROOT / ".env") -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and not line.lstrip().startswith("#"):
            values[key.strip()] = value.strip()
    return values


def _open(req: urllib.request.Request) -> bytes:
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        raise AdminError(exc.code, exc.read().decode(errors="replace")) from None


def password_token(base_url: str, realm: str, client_id: str, username: str, password: str) -> str:
    data = urllib.parse.urlencode({
        "grant_type": "password", "client_id": client_id,
        "username": username, "password": password,
    }).encode()
    url = f"{base_url.rstrip('/')}/realms/{realm}/protocol/openid-connect/token"
    return json.loads(_open(urllib.request.Request(url, data=data, method="POST")))["access_token"]


class KeycloakAdmin:
    def __init__(self, base_url: str, *, realm: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.realm = realm
        self.token = token

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "KeycloakAdmin":
        env = env or load_env()
        base = f"http://localhost:{env.get('KC_PUBLIC_PORT', '8081')}"
        token = password_token(base, "master", "admin-cli",
                               env["KC_BOOTSTRAP_ADMIN_USERNAME"], env["KC_BOOTSTRAP_ADMIN_PASSWORD"])
        return cls(base, realm=env.get("REALM_NAME", "gentil-dev"), token=token)

    def request(self, method: str, path: str, body=None, *, params: dict | None = None):
        url = f"{self.base_url}/admin/realms/{self.realm}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": f"Bearer {self.token}", "Content-Type": "application/json",
        })
        raw = _open(req)
        return json.loads(raw) if raw else None

    def get(self, path: str, **params):
        return self.request("GET", path, params=params or None)

    def put(self, path: str, body):
        return self.request("PUT", path, body)

    def post(self, path: str, body=None):
        return self.request("POST", path, body)

    def delete(self, path: str):
        return self.request("DELETE", path)

    def client_uuid(self, client_id: str) -> str:
        found = self.get("/clients", clientId=client_id)
        if not found:
            raise AdminError(404, f"client {client_id} não encontrado")
        return found[0]["id"]

    def user_by_username(self, username: str) -> dict | None:
        found = self.get("/users", username=username, exact="true")
        return found[0] if found else None
```

- [ ] **Step 2: Escrever o smoke test (`scripts/smoke_test.py`)**

```python
"""Smoke test do realm: configuração, client, papéis, grupos, usuários DEV e tokens.

Uso: python scripts/smoke_test.py  (lê o .env da raiz; o ambiente precisa estar no ar)
"""
from __future__ import annotations

import re
import sys

from kcadmin import AdminError, KeycloakAdmin, load_env

CLIENT = "chat-bot-om-bff"
PERMISSIONS = {
    "assistant.use", "assistant.history", "indicators.view",
    "assets.view", "assets.create", "assets.edit", "assets.delete", "assets.import",
    "documents.view", "documents.upload", "documents.replace", "documents.delete",
    "audit.view", "users.view", "settings.view", "settings.manage", "sync.tape",
}
PROFILES = {
    "ADMINISTRADOR": PERMISSIONS,
    "ANALISTA": {"assistant.use", "assistant.history", "indicators.view", "assets.view", "assets.create",
                 "assets.edit", "documents.view", "documents.upload", "documents.replace", "settings.view"},
    "GERENTE": {"assistant.use", "assistant.history", "indicators.view", "assets.view", "assets.create",
                "assets.edit", "assets.delete", "assets.import", "documents.view", "documents.upload",
                "documents.replace", "documents.delete", "audit.view", "settings.view"},
    "DIRETOR": {"assistant.use", "assistant.history", "indicators.view", "assets.view", "documents.view",
                "settings.view"},
    "CONVIDADO": {"assistant.use", "assistant.history", "indicators.view", "assets.view"},
}
GROUPS = {
    "Chat-bot O&M · Administradores": "ADMINISTRADOR",
    "Chat-bot O&M · Analistas": "ANALISTA",
    "Chat-bot O&M · Gerentes": "GERENTE",
    "Chat-bot O&M · Diretores": "DIRETOR",
    "Chat-bot O&M · Convidados": "CONVIDADO",
}
MANAGER_GROUP = "Gestores de acesso"
MANAGER_ROLES = {"manage-users", "view-users", "query-users", "query-groups", "view-events"}
DEV_USERS = {"admin.om": "ADMINISTRADOR", "analista.om": "ANALISTA", "gerente.om": "GERENTE",
             "diretor.om": "DIRETOR", "convidado.om": "CONVIDADO"}
PASSWORD_POLICY = "length(12) and notUsername and notEmail and passwordHistory(3)"

failures: list[str] = []


def check(ok: bool, label: str) -> None:
    print(("OK    " if ok else "FALHA ") + label)
    if not ok:
        failures.append(label)


def _policy(value: str | None) -> str:
    return re.sub(r"\(undefined\)", "", value or "")


def check_realm(kc: KeycloakAdmin) -> None:
    realm = kc.get("")
    expected = {
        "enabled": True, "registrationAllowed": True, "verifyEmail": True,
        "loginWithEmailAllowed": True, "duplicateEmailsAllowed": False, "rememberMe": False,
        "resetPasswordAllowed": True, "bruteForceProtected": True, "failureFactor": 5,
        "maxFailureWaitSeconds": 900, "accessTokenLifespan": 300, "ssoSessionIdleTimeout": 1800,
        "ssoSessionMaxLifespan": 28800, "revokeRefreshToken": True, "refreshTokenMaxReuse": 0,
        "eventsEnabled": True, "eventsExpiration": 7776000, "adminEventsEnabled": True,
        "adminEventsDetailsEnabled": True, "loginTheme": "gentil-om", "defaultLocale": "pt-BR",
    }
    for key, value in expected.items():
        check(realm.get(key) == value, f"realm.{key} = {value!r} (atual: {realm.get(key)!r})")
    check(_policy(realm.get("passwordPolicy")) == PASSWORD_POLICY, "realm.passwordPolicy")
    check(bool((realm.get("smtpServer") or {}).get("host")), "realm.smtpServer.host configurado")


def check_client(kc: KeycloakAdmin) -> str:
    uuid = kc.client_uuid(CLIENT)
    client = kc.get(f"/clients/{uuid}")
    flags = {"publicClient": False, "standardFlowEnabled": True, "implicitFlowEnabled": False,
             "directAccessGrantsEnabled": False, "serviceAccountsEnabled": False, "fullScopeAllowed": False}
    for key, value in flags.items():
        check(client.get(key) == value, f"client.{key} = {value}")
    attrs = client.get("attributes") or {}
    check(attrs.get("pkce.code.challenge.method") == "S256", "client com PKCE S256 obrigatório")
    check(attrs.get("backchannel.logout.session.required") == "true", "backchannel logout com sid")
    check(bool(attrs.get("backchannel.logout.url")), "backchannel logout URL definida")
    check(any(
        m.get("protocolMapper") == "oidc-audience-mapper"
        and (m.get("config") or {}).get("included.client.audience") == CLIENT
        for m in client.get("protocolMappers") or []
    ), f"mapper de audiência {CLIENT}")
    return uuid


def check_roles(kc: KeycloakAdmin, uuid: str) -> None:
    roles = {r["name"] for r in kc.get(f"/clients/{uuid}/roles")}
    check(roles == PERMISSIONS | set(PROFILES), f"papéis do client = 17 permissões + 5 perfis (atual: {len(roles)})")
    for profile, perms in PROFILES.items():
        composites = {r["name"] for r in kc.get(f"/clients/{uuid}/roles/{profile}/composites")}
        check(composites == perms, f"perfil {profile} (diferença: {sorted(composites ^ perms)})")
    defaults = kc.get(f"/roles/default-roles-{kc.realm}/composites")
    check(all(r.get("containerId") != uuid for r in defaults), "default-roles sem papéis do app")


def check_groups(kc: KeycloakAdmin) -> None:
    groups = {g["name"]: g for g in kc.get("/groups", briefRepresentation="false")}
    for name, profile in GROUPS.items():
        roles = ((groups.get(name) or {}).get("clientRoles") or {}).get(CLIENT)
        check(roles == [profile], f"grupo '{name}' → {profile}")
    manager = ((groups.get(MANAGER_GROUP) or {}).get("clientRoles") or {}).get("realm-management") or []
    check(set(manager) == MANAGER_ROLES, f"grupo '{MANAGER_GROUP}' com papéis de gestão de usuários")


def check_users(kc: KeycloakAdmin, uuid: str) -> None:
    for username, profile in DEV_USERS.items():
        user = kc.user_by_username(username)
        check(bool(user and user.get("enabled") and user.get("emailVerified")),
              f"usuário {username} ativo e com e-mail confirmado")
        if not user:
            continue
        token = kc.get(f"/clients/{uuid}/evaluate-scopes/generate-example-access-token",
                       scope="openid", userId=user["id"])
        access = token.get("resource_access") or {}
        roles = set((access.get(CLIENT) or {}).get("roles", []))
        check(roles == PROFILES[profile] | {profile}, f"token de {username}: {profile} e suas permissões")
        aud = token.get("aud")
        check(CLIENT in (aud if isinstance(aud, list) else [aud]), f"token de {username}: aud contém {CLIENT}")
        check(set(access) == {CLIENT}, f"token de {username}: sem papéis de outros clients")
    admin = kc.user_by_username("admin.om")
    if admin:
        names = {g["name"] for g in kc.get(f"/users/{admin['id']}/groups")}
        check(MANAGER_GROUP in names, f"admin.om em '{MANAGER_GROUP}'")


def main() -> int:
    try:
        kc = KeycloakAdmin.from_env(load_env())
        check_realm(kc)
        uuid = check_client(kc)
        check_roles(kc, uuid)
        check_groups(kc)
        check_users(kc, uuid)
    except AdminError as exc:
        check(False, f"Admin API: {exc}")
    print(f"\n{len(failures)} falha(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Rodar o smoke test e ver falhar**

```bash
cd "$IDP" && "$PY" scripts/smoke_test.py; echo "exit=$?"
```

Expected: `FALHA Admin API: HTTP 404: ...` (o realm ainda não existe), `1 falha(s).`, `exit=1`.

- [ ] **Step 4: Criar `config/10-realm.yaml`**

```yaml
# Realm do Chat-bot O&M. Vale para DEV e produção; segredos vêm do ambiente.
realm: "$(env:REALM_NAME:-gentil-dev)"
enabled: true
displayName: "Chat-bot O&M"
loginTheme: gentil-om
internationalizationEnabled: true
supportedLocales: [pt-BR]
defaultLocale: pt-BR

registrationAllowed: true
registrationEmailAsUsername: false
verifyEmail: true
loginWithEmailAllowed: true
duplicateEmailsAllowed: false
rememberMe: false
resetPasswordAllowed: true
editUsernameAllowed: false

bruteForceProtected: true
permanentLockout: false
failureFactor: 5
waitIncrementSeconds: 60
maxFailureWaitSeconds: 900
maxDeltaTimeSeconds: 43200
minimumQuickLoginWaitSeconds: 60
quickLoginCheckMilliSeconds: 1000
passwordPolicy: "length(12) and notUsername and notEmail and passwordHistory(3)"

accessTokenLifespan: 300
ssoSessionIdleTimeout: 1800
ssoSessionMaxLifespan: 28800
revokeRefreshToken: true
refreshTokenMaxReuse: 0

eventsEnabled: true
eventsExpiration: 7776000
adminEventsEnabled: true
adminEventsDetailsEnabled: true

smtpServer:
  host: "$(env:SMTP_HOST)"
  port: "$(env:SMTP_PORT)"
  from: "$(env:SMTP_FROM)"
  fromDisplayName: "$(env:SMTP_FROM_NAME)"
  starttls: "$(env:SMTP_STARTTLS)"
  auth: "$(env:SMTP_AUTH)"
  user: "$(env:SMTP_USER:-)"
  password: "$(env:SMTP_PASSWORD:-)"

clients:
  - clientId: chat-bot-om-bff
    name: "Chat-bot O&M"
    enabled: true
    protocol: openid-connect
    publicClient: false
    clientAuthenticatorType: client-secret
    secret: "$(env:CHATBOT_CLIENT_SECRET)"
    standardFlowEnabled: true
    implicitFlowEnabled: false
    directAccessGrantsEnabled: false
    serviceAccountsEnabled: false
    frontchannelLogout: false
    # O token só carrega papéis deste client.
    fullScopeAllowed: false
    redirectUris:
      - "$(env:APP_BASE_URL)/auth/callback"
    webOrigins: []
    attributes:
      pkce.code.challenge.method: S256
      # "/login*" aceita /login?auth_error=not_released.
      post.logout.redirect.uris: "$(env:APP_BASE_URL)/login*"
      backchannel.logout.url: "$(env:BACKCHANNEL_LOGOUT_URL)"
      backchannel.logout.session.required: "true"
      backchannel.logout.revoke.offline.tokens: "false"
    protocolMappers:
      # aud = chat-bot-om-bff mesmo para quem ainda não tem papel (conta não liberada).
      - name: audience-chat-bot-om-bff
        protocol: openid-connect
        protocolMapper: oidc-audience-mapper
        config:
          included.client.audience: chat-bot-om-bff
          id.token.claim: "false"
          access.token.claim: "true"
          introspection.token.claim: "true"

roles:
  client:
    chat-bot-om-bff:
      - { name: assistant.use, description: "Usar o assistente IA" }
      - { name: assistant.history, description: "Ver histórico de conversas" }
      - { name: indicators.view, description: "Ver Central de Indicadores" }
      - { name: assets.view, description: "Ver Central de Ativos" }
      - { name: assets.create, description: "Cadastrar ativos e equipamentos" }
      - { name: assets.edit, description: "Editar ativos e equipamentos" }
      - { name: assets.delete, description: "Excluir ativos e equipamentos" }
      - { name: assets.import, description: "Importar ativos via Excel" }
      - { name: documents.view, description: "Ver documentos da loja" }
      - { name: documents.upload, description: "Fazer upload de documento" }
      - { name: documents.replace, description: "Substituir arquivo de documento" }
      - { name: documents.delete, description: "Excluir documento" }
      - { name: audit.view, description: "Ver log de auditoria" }
      - { name: users.view, description: "Consultar usuários e acessos" }
      - { name: settings.view, description: "Ver configurações" }
      - { name: settings.manage, description: "Alterar configurações" }
      - { name: sync.tape, description: "Executar sincronização da Tape" }
      - name: ADMINISTRADOR
        description: "Perfil Administrador"
        composite: true
        composites:
          client:
            chat-bot-om-bff: [assistant.use, assistant.history, indicators.view, assets.view, assets.create,
                              assets.edit, assets.delete, assets.import, documents.view, documents.upload,
                              documents.replace, documents.delete, audit.view, users.view, settings.view,
                              settings.manage, sync.tape]
      - name: ANALISTA
        description: "Perfil Analista"
        composite: true
        composites:
          client:
            chat-bot-om-bff: [assistant.use, assistant.history, indicators.view, assets.view, assets.create,
                              assets.edit, documents.view, documents.upload, documents.replace, settings.view]
      - name: GERENTE
        description: "Perfil Gerente"
        composite: true
        composites:
          client:
            chat-bot-om-bff: [assistant.use, assistant.history, indicators.view, assets.view, assets.create,
                              assets.edit, assets.delete, assets.import, documents.view, documents.upload,
                              documents.replace, documents.delete, audit.view, settings.view]
      - name: DIRETOR
        description: "Perfil Diretor"
        composite: true
        composites:
          client:
            chat-bot-om-bff: [assistant.use, assistant.history, indicators.view, assets.view, documents.view,
                              settings.view]
      - name: CONVIDADO
        description: "Perfil Convidado"
        composite: true
        composites:
          client:
            chat-bot-om-bff: [assistant.use, assistant.history, indicators.view, assets.view]

# Liberação de acesso = incluir a pessoa no grupo do perfil.
groups:
  - name: "Chat-bot O&M · Administradores"
    clientRoles: { chat-bot-om-bff: [ADMINISTRADOR] }
  - name: "Chat-bot O&M · Analistas"
    clientRoles: { chat-bot-om-bff: [ANALISTA] }
  - name: "Chat-bot O&M · Gerentes"
    clientRoles: { chat-bot-om-bff: [GERENTE] }
  - name: "Chat-bot O&M · Diretores"
    clientRoles: { chat-bot-om-bff: [DIRETOR] }
  - name: "Chat-bot O&M · Convidados"
    clientRoles: { chat-bot-om-bff: [CONVIDADO] }
  # Usam o console do realm (/admin/gentil-dev/console/) para cadastrar, liberar,
  # bloquear e redefinir senhas. Não alteram clients nem configurações do realm.
  - name: "Gestores de acesso"
    clientRoles:
      realm-management: [manage-users, view-users, query-users, query-groups, view-events]
```

- [ ] **Step 5: Criar `config/20-dev-users.yaml`**

```yaml
# Usuários DEV. A produção NÃO aplica este arquivo (IMPORT_FILES_LOCATIONS só com 10-realm.yaml).
realm: "$(env:REALM_NAME:-gentil-dev)"
users:
  - username: admin.om
    email: admin.om@chatbot-om.local
    firstName: Administrador
    lastName: "O&M"
    enabled: true
    emailVerified: true
    credentials:
      - { type: password, value: "$(env:DEV_ADMIN_PASSWORD)", temporary: false }
    groups: ["Chat-bot O&M · Administradores", "Gestores de acesso"]
  - username: analista.om
    email: analista.om@chatbot-om.local
    firstName: Analista
    lastName: "O&M"
    enabled: true
    emailVerified: true
    credentials:
      - { type: password, value: "$(env:DEV_ANALYST_PASSWORD)", temporary: false }
    groups: ["Chat-bot O&M · Analistas"]
  - username: gerente.om
    email: gerente.om@chatbot-om.local
    firstName: Gerente
    lastName: "O&M"
    enabled: true
    emailVerified: true
    credentials:
      - { type: password, value: "$(env:DEV_MANAGER_PASSWORD)", temporary: false }
    groups: ["Chat-bot O&M · Gerentes"]
  - username: diretor.om
    email: diretor.om@chatbot-om.local
    firstName: Diretor
    lastName: "O&M"
    enabled: true
    emailVerified: true
    credentials:
      - { type: password, value: "$(env:DEV_DIRECTOR_PASSWORD)", temporary: false }
    groups: ["Chat-bot O&M · Diretores"]
  - username: convidado.om
    email: convidado.om@chatbot-om.local
    firstName: Convidado
    lastName: "O&M"
    enabled: true
    emailVerified: true
    credentials:
      - { type: password, value: "$(env:DEV_GUEST_PASSWORD)", temporary: false }
    groups: ["Chat-bot O&M · Convidados"]
```

- [ ] **Step 6: Aplicar a configuração**

```bash
cd "$IDP" && docker compose run --rm keycloak-config 2>&1 | tail -5; echo "exit=${PIPESTATUS[0]}"
```

Expected: a última linha do log contém `keycloak-config-cli ran in`; `exit=0`. Se falhar, leia a mensagem do config-cli (ela indica a chave do YAML) e corrija o YAML; não altere o smoke test para passar.

- [ ] **Step 7: Rodar o smoke test e ver passar**

```bash
cd "$IDP" && "$PY" scripts/smoke_test.py; echo "exit=$?"
```

Expected: todas as linhas com `OK`, `0 falha(s).`, `exit=0`.

- [ ] **Step 8: Conferir idempotência e o issuer do realm**

```bash
cd "$IDP" && docker compose run --rm keycloak-config >/dev/null 2>&1; echo "exit=$?"
"$PY" scripts/smoke_test.py | tail -1
curl -s http://localhost:8082/realms/gentil-dev/.well-known/openid-configuration | grep -o '"issuer":"[^"]*"'
```

Expected: `exit=0`, `0 falha(s).`, `"issuer":"http://localhost:8082/realms/gentil-dev"`.

- [ ] **Step 9: Commit**

```bash
cd "$IDP" && git add config scripts && git commit -m "feat: realm gentil-dev como código (papéis, grupos, usuários DEV) e smoke test

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Tema com autocadastro

**Files:**
- Modify: `$IDP/themes/gentil-om/login/login.ftl` (comentário do topo, `displayInfo` e nova seção `info`)
- Create: `$IDP/themes/gentil-om/login/register.ftl`
- Modify: `$IDP/themes/gentil-om/login/messages/messages_pt_BR.properties`, `messages_en.properties` (mesmo conteúdo)
- Modify: `$IDP/themes/gentil-om/login/resources/css/gentil-om.css` (bloco no final)
- Modify: `$IDP/themes/gentil-om/README.md` (seção de cadastro)

**Interfaces:**
- Consumes: realm com `registrationAllowed=true` e `verifyEmail=true` (Task 2).
- Produces: página de login com link "Criar conta"; página de cadastro no layout `gentil-om`; `prompt=create` abre o cadastro direto; chave de mensagem `omEmailDomainNotAllowed` (usada na Task 4).

- [ ] **Step 1: Confirmar que o cadastro ainda não tem o layout do tema**

```bash
URL='http://localhost:8082/realms/gentil-dev/protocol/openid-connect/auth?client_id=chat-bot-om-bff&response_type=code&scope=openid&redirect_uri=http%3A%2F%2Flocalhost%3A5173%2Fauth%2Fcallback&code_challenge=E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM&code_challenge_method=S256&state=t&nonce=n'
curl -s "$URL" | grep -c "Ainda não tem conta"
curl -s "$URL&prompt=create" | grep -c "omRegisterSubtitle\|om-register"
```

Expected: `0` e `0`.

- [ ] **Step 2: Mostrar o link de cadastro no `login.ftl`**

Substitua o comentário do topo e a abertura do layout:

```ftl
<#--
  Página de login do Chat-bot O&M. Os campos de usuário e senha pertencem
  exclusivamente ao Keycloak — o frontend React nunca recebe a senha.
  O link "Criar conta" aparece quando o realm permite autocadastro; a conta
  nasce sem perfil e só acessa o app depois da liberação por um gestor.
-->
<@layout.registrationLayout displayMessage=!messagesPerField.existsError('username','password') displayInfo=(realm.password && realm.registrationAllowed && !registrationDisabled??); section>
```

E, logo antes de `<#elseif section = "socialProviders" >`, acrescente:

```ftl
    <#elseif section = "info">
        <#if realm.password && realm.registrationAllowed && !registrationDisabled??>
            <p class="om-info__text">
                <span>${msg("noAccount")}</span>
                <a tabindex="7" class="om-link" href="${url.registrationUrl}">${msg("omCreateAccount")}</a>
            </p>
        </#if>
```

- [ ] **Step 3: Criar `register.ftl`**

```ftl
<#import "template.ftl" as layout>
<#import "user-profile-commons.ftl" as userProfileCommons>
<#import "register-commons.ftl" as registerCommons>
<#--
  Autocadastro do Chat-bot O&M. A conta nasce sem perfil: o acesso ao app só
  existe depois que um gestor de acesso inclui a pessoa no grupo do perfil.
-->
<@layout.registrationLayout displayMessage=messagesPerField.exists('global') displayRequiredFields=true; section>
    <#if section = "header">
        <#if messageHeader??>${kcSanitize(msg("${messageHeader}"))?no_esc}<#else>${msg("registerTitle")}</#if>
    <#elseif section = "subtitle">
        ${msg("omRegisterSubtitle")}
    <#elseif section = "form">
        <form id="kc-register-form" class="${properties.kcFormClass!} om-form om-register" action="${url.registrationAction}" method="post" novalidate
              onsubmit="register.disabled = true; register.classList.add('om-button--loading'); return true;">
            <@userProfileCommons.userProfileFormFields; callback, attribute>
                <#if callback = "afterField">
                    <#if passwordRequired?? && (attribute.name == 'username' || (attribute.name == 'email' && realm.registrationEmailAsUsername))>
                        <div class="${properties.kcFormGroupClass!}">
                            <label for="password" class="${properties.kcLabelClass!}">${msg("password")} <span class="required">*</span></label>
                            <div class="${properties.kcInputGroup!} om-input-shell" dir="ltr">
                                <span class="om-icon om-icon--lock om-input-shell__icon" aria-hidden="true"></span>
                                <input type="password" id="password" name="password" class="${properties.kcInputClass!}" autocomplete="new-password"
                                       aria-describedby="om-password-hint"
                                       aria-invalid="<#if messagesPerField.existsError('password','password-confirm')>true</#if>"/>
                                <button class="${properties.kcFormPasswordVisibilityButtonClass!}" type="button" aria-label="${msg('showPassword')}"
                                        aria-controls="password" data-password-toggle
                                        data-icon-show="${properties.kcFormPasswordVisibilityIconShow!}" data-icon-hide="${properties.kcFormPasswordVisibilityIconHide!}"
                                        data-label-show="${msg('showPassword')}" data-label-hide="${msg('hidePassword')}">
                                    <i class="${properties.kcFormPasswordVisibilityIconShow!}" aria-hidden="true"></i>
                                </button>
                            </div>
                            <#if messagesPerField.existsError('password')>
                                <span id="input-error-password" class="${properties.kcInputErrorMessageClass!}" aria-live="polite">
                                    ${kcSanitize(messagesPerField.get('password'))?no_esc}
                                </span>
                            </#if>
                            <span id="om-password-hint" class="om-helper-text">${msg("omPasswordPolicyHint")}</span>
                        </div>

                        <div class="${properties.kcFormGroupClass!}">
                            <label for="password-confirm" class="${properties.kcLabelClass!}">${msg("passwordConfirm")} <span class="required">*</span></label>
                            <div class="${properties.kcInputGroup!} om-input-shell" dir="ltr">
                                <span class="om-icon om-icon--lock om-input-shell__icon" aria-hidden="true"></span>
                                <input type="password" id="password-confirm" name="password-confirm" class="${properties.kcInputClass!}" autocomplete="new-password"
                                       aria-invalid="<#if messagesPerField.existsError('password-confirm')>true</#if>"/>
                                <button class="${properties.kcFormPasswordVisibilityButtonClass!}" type="button" aria-label="${msg('showPassword')}"
                                        aria-controls="password-confirm" data-password-toggle
                                        data-icon-show="${properties.kcFormPasswordVisibilityIconShow!}" data-icon-hide="${properties.kcFormPasswordVisibilityIconHide!}"
                                        data-label-show="${msg('showPassword')}" data-label-hide="${msg('hidePassword')}">
                                    <i class="${properties.kcFormPasswordVisibilityIconShow!}" aria-hidden="true"></i>
                                </button>
                            </div>
                            <#if messagesPerField.existsError('password-confirm')>
                                <span id="input-error-password-confirm" class="${properties.kcInputErrorMessageClass!}" aria-live="polite">
                                    ${kcSanitize(messagesPerField.get('password-confirm'))?no_esc}
                                </span>
                            </#if>
                        </div>
                    </#if>
                </#if>
            </@userProfileCommons.userProfileFormFields>

            <@registerCommons.termsAcceptance/>

            <div id="kc-form-buttons" class="${properties.kcFormButtonsClass!}">
                <button name="register" class="${properties.kcButtonClass!} ${properties.kcButtonPrimaryClass!} ${properties.kcButtonBlockClass!} ${properties.kcButtonLargeClass!}" type="submit">
                    <span>${msg("doRegister")}</span>
                    <span class="om-button__arrow" aria-hidden="true">→</span>
                </button>
                <a class="om-button om-button--secondary om-button--block" href="${url.loginUrl}">${msg("omAlreadyHaveAccount")}</a>
            </div>
        </form>
        <script type="module" src="${url.resourcesPath}/js/passwordVisibility.js"></script>
    </#if>
</@layout.registrationLayout>
```

- [ ] **Step 4: Acrescentar as mensagens (nos dois arquivos `messages_pt_BR.properties` e `messages_en.properties`, ao final)**

```properties
# ── Autocadastro ───────────────────────────────────────────────────────────────
registerTitle=Criar conta
omRegisterSubtitle=Preencha seus dados. Depois de confirmar o e-mail, um gestor de acesso libera o seu perfil.
doRegister=Criar conta
noAccount=Ainda não tem conta?
omCreateAccount=Criar conta
omAlreadyHaveAccount=Já tenho conta
firstName=Nome
lastName=Sobrenome
passwordConfirm=Confirmar senha
omPasswordPolicyHint=Mínimo de 12 caracteres, diferente do usuário e do e-mail.
emailVerifyTitle=Confirme seu e-mail
emailVerifyInstruction1=Enviamos para {0} um link de confirmação. Abra o e-mail para continuar.
emailVerifyInstruction2=Não recebeu o e-mail?
doClickHere=Clique aqui
emailVerifyInstruction3=para reenviar.
omEmailDomainNotAllowed=Use o seu e-mail corporativo para criar a conta.
```

- [ ] **Step 5: Estilos do cadastro (final de `resources/css/gentil-om.css`)**

```css
/* ── Autocadastro ───────────────────────────────────────────────────────────
   Campos gerados pelo user profile do Keycloak (user-profile-commons.ftl). */
.om-label-wrapper {
  display: flex;
  align-items: baseline;
  gap: 4px;
}

.om-input-wrapper {
  display: grid;
  gap: 6px;
}

.om-register .om-form-group + .om-form-group { margin-top: 2px; }

.om-info__text {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 6px;
  margin: 0;
  text-align: center;
}
```

No `README.md` do tema, substitua a frase que diz que não há cadastro público por: "O autocadastro fica em `register.ftl`: a conta nasce sem perfil e só acessa o Chat-bot O&M depois que um gestor de acesso a inclui no grupo do perfil."

- [ ] **Step 6: Reconstruir a imagem e conferir login e cadastro**

```bash
cd "$IDP" && docker compose up -d --build keycloak
until docker compose ps keycloak --format "{{.Status}}" | grep -q healthy; do sleep 5; done
curl -s "$URL" | grep -c "Ainda não tem conta"
curl -s "$URL&prompt=create" | grep -o 'id="kc-register-form"\|Depois de confirmar o e-mail' | sort -u
```

(`URL` definido no Step 1.) Expected: `1`; depois `Depois de confirmar o e-mail` e `id="kc-register-form"`.

- [ ] **Step 7: Revisão visual rápida no navegador**

Abra `$URL` e `$URL&prompt=create` no Chrome em 1440×900 e 390×844. Confira que o cadastro usa o mesmo cartão, fonte e botões do login; que "Criar conta" aparece abaixo do botão Entrar; e que não há rolagem horizontal. Anote os problemas encontrados e corrija só CSS do bloco do Step 5.

- [ ] **Step 8: Commit**

```bash
cd "$IDP" && git add themes && git commit -m "feat(tema): autocadastro com o layout gentil-om

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Scripts de operação e documentação

**Files:**
- Create: `$IDP/scripts/restrict_email_domain.py`, `$IDP/scripts/export_realm.py`, `$IDP/scripts/backup-db.sh`
- Create: `$IDP/docs/OPERACAO.md`, `$IDP/docs/MIGRACAO_TI.md`, `$IDP/README.md`

**Interfaces:**
- Consumes: `scripts/kcadmin.py` (Task 2); mensagem `omEmailDomainNotAllowed` (Task 3).
- Produces: `restrict_email_domain.py --domain D [--domain D2]` e `--remove`; `export_realm.py`; `backup-db.sh`.

- [ ] **Step 1: Criar `scripts/restrict_email_domain.py`**

```python
"""Liga ou desliga a restrição de domínio de e-mail do realm.

Uso:
  python scripts/restrict_email_domain.py --domain gentilnegocios.com.br [--domain outro.com.br]
  python scripts/restrict_email_domain.py --remove

A regra é um validador "pattern" no atributo email do user profile. Vale em
todos os contextos: autocadastro, conta do usuário e criação pelo console.
Obrigatória antes de produção (docs/MIGRACAO_TI.md).
"""
from __future__ import annotations

import argparse
import re
import sys

from kcadmin import KeycloakAdmin, load_env

ERROR_KEY = "omEmailDomainNotAllowed"


def build_pattern(domains: list[str]) -> str:
    alternatives = "|".join(re.escape(d.strip().lower()) for d in domains if d.strip())
    return rf"(?i)^[^@\s]+@({alternatives})$"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Restrição de domínio de e-mail do realm.")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--domain", action="append", help="domínio permitido (repita para vários)")
    action.add_argument("--remove", action="store_true", help="remove a restrição")
    args = parser.parse_args(argv)

    kc = KeycloakAdmin.from_env(load_env())
    profile = kc.get("/users/profile")
    email = next(a for a in profile["attributes"] if a["name"] == "email")
    validations = email.setdefault("validations", {})
    if args.remove:
        validations.pop("pattern", None)
        message = "Restrição de domínio removida."
    else:
        validations["pattern"] = {"pattern": build_pattern(args.domain), "error-message": ERROR_KEY}
        message = "Restrição aplicada: " + ", ".join(args.domain)
    kc.put("/users/profile", profile)
    print(message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Testar aplicar e remover**

```bash
cd "$IDP/scripts" && "$PY" restrict_email_domain.py --domain exemplo.com.br
"$PY" - <<'EOF'
from kcadmin import AdminError, KeycloakAdmin
kc = KeycloakAdmin.from_env()
try:
    kc.post("/users", {"username": "teste.dominio", "email": "teste@outro.com", "enabled": True})
    print("CRIOU (erro: a restrição não funcionou)")
    kc.delete(f"/users/{kc.user_by_username('teste.dominio')['id']}")
except AdminError as exc:
    print("RECUSOU", exc.status, "omEmailDomainNotAllowed" in str(exc))
EOF
"$PY" restrict_email_domain.py --remove
"$PY" -c "from kcadmin import KeycloakAdmin; kc=KeycloakAdmin.from_env(); a=[x for x in kc.get('/users/profile')['attributes'] if x['name']=='email'][0]; print('pattern' in a.get('validations', {}))"
```

Expected: `Restrição aplicada: exemplo.com.br`, `RECUSOU 400 True`, `Restrição de domínio removida.`, `False`.

- [ ] **Step 3: Criar `scripts/export_realm.py` e `scripts/backup-db.sh`**

`scripts/export_realm.py`:

```python
"""Exporta o realm para conferência em backups/ (o Keycloak mascara os segredos)."""
from __future__ import annotations

import json
from datetime import datetime

from kcadmin import ROOT, KeycloakAdmin, load_env


def main() -> None:
    kc = KeycloakAdmin.from_env(load_env())
    data = kc.request("POST", "/partial-export", params={"exportClients": "true", "exportGroupsAndRoles": "true"})
    target = ROOT / "backups" / f"realm-{kc.realm}-{datetime.now():%Y%m%d-%H%M%S}.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Exportado em {target.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
```

`scripts/backup-db.sh`:

```bash
#!/usr/bin/env bash
# Backup do banco do Keycloak (pg_dump formato custom) em backups/.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p backups
file="backups/keycloak-$(date +%Y%m%d-%H%M%S).dump"
docker compose exec -T keycloak-db pg_dump -U keycloak -d keycloak --format=custom > "$file"
echo "Backup salvo em $file"
```

Rode os dois:

```bash
cd "$IDP" && "$PY" scripts/export_realm.py && bash scripts/backup-db.sh && ls backups
grep -o '"secret": "[^"]*"' backups/realm-*.json
```

Expected: um `realm-gentil-dev-*.json` e um `keycloak-*.dump` em `backups/`; o `grep` mostra `"secret": "**********"` (segredo do client mascarado).

- [ ] **Step 4: Escrever `docs/OPERACAO.md`**

```markdown
# Operação do gentil-identity (DEV)

## Primeira vez
1. `python scripts/init_env.py` — cria o `.env` com segredos aleatórios.
2. `docker compose up -d --build` — sobe banco, Keycloak e Mailpit e aplica o realm.
3. `python scripts/smoke_test.py` — tudo precisa terminar em `0 falha(s).`
4. Copie `CHATBOT_CLIENT_SECRET` para `OIDC_CLIENT_SECRET` no `.env` do Chat-bot O&M.

Senhas dos usuários DEV (`admin.om`, `analista.om`, `gerente.om`, `diretor.om`,
`convidado.om`): variáveis `DEV_*_PASSWORD` do `.env`.

## Dia a dia
| Ação | Comando |
|---|---|
| Subir / parar | `docker compose up -d` / `docker compose stop` |
| Reaplicar o realm (após editar `config/*.yaml`) | `docker compose run --rm keycloak-config` |
| Conferir | `python scripts/smoke_test.py` |
| Ver e-mails (DEV) | http://localhost:8025 |
| Console do realm (gestores) | http://localhost:8081/admin/gentil-dev/console/ |
| Console master (admin de bootstrap) | http://localhost:8081/admin/ |
| Backup do banco | `bash scripts/backup-db.sh` |
| Exportar o realm para conferência | `python scripts/export_realm.py` |

Restaurar um backup (Keycloak parado):
`docker compose stop keycloak && docker compose exec -T keycloak-db pg_restore -U keycloak -d keycloak --clean --if-exists < backups/<arquivo>.dump && docker compose start keycloak`

Nunca use `docker compose down -v`: apaga o banco do Keycloak (usuários, senhas e grupos).

## Gestão de acesso (membros do grupo "Gestores de acesso")
Tudo no console do realm, menu **Users**:

| Quero… | Faça | Efeito no Chat-bot O&M |
|---|---|---|
| Liberar uma conta nova | Usuário → aba **Groups** → **Join group** → grupo do perfil (ex.: "Chat-bot O&M · Analistas") | Próximo login já entra |
| Trocar o perfil | Sair do grupo antigo e entrar no novo | Vale em até 5 minutos |
| Retirar o acesso | Sair do grupo do perfil | Em até 5 minutos a sessão cai |
| **Bloquear na hora** | Desligar **Enabled** e, na aba **Sessions**, **Sign out** (encerrar sessões) | Imediato (backchannel logout) |
| Redefinir senha | Aba **Credentials** → **Reset password** (temporária) ou **Credential reset** por e-mail | Próximo login |
| Permissão avulsa | Aba **Role mapping** → **Assign role** → papel do client `chat-bot-om-bff` | Vale em até 5 minutos |

Só desligar **Enabled**, sem encerrar as sessões, derruba o acesso ao app em até 5 minutos, quando o app tenta renovar o token.

## Restrição de domínio do autocadastro
- Ligar: `python scripts/restrict_email_domain.py --domain gentilnegocios.com.br`
- Desligar: `python scripts/restrict_email_domain.py --remove`
Vale para todos os cadastros, inclusive os feitos pelo console. Obrigatória antes de produção.
```

- [ ] **Step 5: Escrever `docs/MIGRACAO_TI.md`**

```markdown
# Migração do gentil-identity para o ambiente da Gentil Negócios

O Chat-bot O&M só precisa de três informações: **URL do emissor**
(`https://<sso>/realms/<realm>`), **segredo do client** `chat-bot-om-bff` e
**URL do console** do realm. Nenhuma mudança de código.

## Subida
1. Copie este repositório para o servidor e crie o `.env` a partir do `.env.example`:
   - `COMPOSE_PROFILES=` (vazio: sem Mailpit);
   - `KC_HOSTNAME=https://<sso>`, `KC_HOSTNAME_ADMIN=https://<console-interno>`;
   - `APP_BASE_URL=https://<chatbot>`, `BACKCHANNEL_LOGOUT_URL=https://<chatbot>/auth/backchannel-logout`;
   - SMTP da empresa (`SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM`, `SMTP_STARTTLS=true`, `SMTP_AUTH=true`, `SMTP_USER`, `SMTP_PASSWORD`);
   - segredos novos (`KC_DB_PASSWORD`, `KC_BOOTSTRAP_ADMIN_PASSWORD`, `CHATBOT_CLIENT_SECRET`);
   - `IMPORT_FILES_LOCATIONS=/config/10-realm.yaml` (sem os usuários DEV).
2. `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`
3. Reverse proxy com HTTPS encaminhando para a porta 8080 do container, com cabeçalhos `X-Forwarded-*`.
4. Alternativa: aplicar os mesmos `config/*.yaml` num Keycloak corporativo existente com o keycloak-config-cli.

## Checklist obrigatório
- [ ] HTTPS e `KC_HOSTNAME` definitivos; console administrativo só na rede interna.
- [ ] SMTP da empresa configurado; Mailpit desligado.
- [ ] Restrição de domínio de e-mail ligada (`scripts/restrict_email_domain.py --domain ...`).
- [ ] Nenhum usuário DEV no realm; admin nomeado com MFA no `master`; admin de bootstrap removido.
- [ ] Job de configuração usando uma service account própria com administração restrita ao realm (não o admin de bootstrap).
- [ ] `BACKCHANNEL_LOGOUT_URL` alcançável pelo Keycloak e exposto no proxy do app **somente** para a rede do Keycloak.
- [ ] Redirect URI (`/auth/callback`) e post-logout URI (`/login*`) de produção registradas (vêm de `APP_BASE_URL`).
- [ ] App com `SESSION_COOKIE_SECURE=true`, `OIDC_CLIENT_SECRET` novo e `SESSION_ENCRYPTION_KEY` nova.
- [ ] `python scripts/smoke_test.py` sem falhas (ajuste o endereço em `kcadmin.py` se o acesso for pelo proxy).
- [ ] Rotina de backup (`scripts/backup-db.sh`) agendada.
```

- [ ] **Step 6: Escrever `README.md`**

```markdown
# gentil-identity

Provedor de identidade (Keycloak 26.5.7) da Gentil Negócios, hoje usado pelo Chat-bot O&M.

- Keycloak em modo produção com o tema `gentil-om` (`Dockerfile`).
- Realm, client, papéis, grupos e usuários DEV como código (`config/*.yaml`, keycloak-config-cli).
- Perfis e permissões do Chat-bot O&M são papéis do client `chat-bot-om-bff`; liberar acesso = incluir a pessoa no grupo do perfil.
- Mailpit no DEV para os e-mails de confirmação e de senha.

Comece por `docs/OPERACAO.md`. Para produção, `docs/MIGRACAO_TI.md`.
```

- [ ] **Step 7: Commit**

```bash
cd "$IDP" && chmod +x scripts/backup-db.sh && git add scripts docs README.md && git commit -m "docs: operação, migração para TI e scripts de backup, exportação e domínio

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Catálogo de permissões e perfis (`services/permissions.py`)

**Files:**
- Create: `backend/app/services/permissions.py`
- Test: `backend/tests/test_permissions.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `PERMISSIONS: frozenset[str]` (17 códigos, com `users.view`);
  - `PROFILE_PRIORITY: tuple[str, ...]`, `PROFILE_DISPLAY: dict[str, str]`;
  - `AI_LIMITS: dict[str, tuple[int, int]]` e `DEFAULT_AI_LIMITS = (10, 2)`, no formato `(diário, por minuto)`;
  - `RoleSnapshot(permissions: frozenset[str], profiles: tuple[str, ...])` com a propriedade `has_access`;
  - `snapshot_from_roles(roles: Iterable) -> RoleSnapshot`;
  - `primary_profile(profiles: Iterable[str]) -> str | None`;
  - `ai_limits_for(profiles: Iterable[str]) -> tuple[int, int]`.

- [ ] **Step 1: Escrever os testes**

```python
"""Interpretação dos papéis do client chat-bot-om-bff (app/services/permissions.py)."""
from app.services.permissions import (
    AI_LIMITS,
    DEFAULT_AI_LIMITS,
    PERMISSIONS,
    PROFILE_PRIORITY,
    ai_limits_for,
    primary_profile,
    snapshot_from_roles,
)


def test_catalogo_tem_17_permissoes_com_users_view():
    assert len(PERMISSIONS) == 17
    assert "users.view" in PERMISSIONS
    assert "users.manage" not in PERMISSIONS


def test_retrato_separa_permissoes_e_perfis_e_ignora_papeis_desconhecidos():
    snap = snapshot_from_roles(["ANALISTA", "assets.view", "uma_authorization", "offline_access", "admin"])
    assert snap.permissions == frozenset({"assets.view"})
    assert snap.profiles == ("ANALISTA",)
    assert snap.has_access


def test_perfis_ficam_em_ordem_de_prioridade():
    snap = snapshot_from_roles(["CONVIDADO", "ADMINISTRADOR", "GERENTE", "assistant.use"])
    assert snap.profiles == ("ADMINISTRADOR", "GERENTE", "CONVIDADO")


def test_sem_permissao_nao_ha_acesso_mesmo_com_nome_de_perfil():
    assert not snapshot_from_roles(["ANALISTA"]).has_access
    assert not snapshot_from_roles([]).has_access


def test_valores_que_nao_sao_texto_sao_ignorados():
    snap = snapshot_from_roles(["assets.view", None, 42, {"x": 1}])
    assert snap.permissions == frozenset({"assets.view"})


def test_perfil_principal_segue_a_prioridade():
    assert primary_profile(["DIRETOR", "GERENTE"]) == "GERENTE"
    assert primary_profile(["ANALISTA", "DIRETOR"]) == "ANALISTA"
    assert primary_profile([]) is None


def test_limite_de_ia_e_o_maior_entre_os_perfis():
    assert ai_limits_for(["CONVIDADO"]) == (20, 3)
    assert ai_limits_for(["GERENTE", "ANALISTA"]) == (150, 10)
    assert ai_limits_for(["DIRETOR", "CONVIDADO"]) == (80, 8)
    assert ai_limits_for([]) == DEFAULT_AI_LIMITS == (10, 2)


def test_tabelas_mantem_os_valores_atuais():
    assert AI_LIMITS == {"ADMINISTRADOR": (200, 20), "ANALISTA": (150, 10), "GERENTE": (120, 10),
                         "DIRETOR": (80, 8), "CONVIDADO": (20, 3)}
    assert PROFILE_PRIORITY == ("ADMINISTRADOR", "GERENTE", "ANALISTA", "DIRETOR", "CONVIDADO")
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd "$APP/backend" && "$PY" -m pytest -q tests/test_permissions.py`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.services.permissions'`.

- [ ] **Step 3: Implementar `backend/app/services/permissions.py`**

```python
"""
Catálogo de permissões e perfis do Chat-bot O&M.

Perfis e permissões são papéis do client ``chat-bot-om-bff`` no Keycloak
(gentil-identity/config/10-realm.yaml). Este módulo apenas interpreta os papéis
recebidos no token assinado; nada aqui concede acesso.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

PERMISSIONS: frozenset[str] = frozenset({
    "assistant.use", "assistant.history",
    "indicators.view",
    "assets.view", "assets.create", "assets.edit", "assets.delete", "assets.import",
    "documents.view", "documents.upload", "documents.replace", "documents.delete",
    "audit.view", "users.view",
    "settings.view", "settings.manage",
    "sync.tape",
})

# Ordem de exibição: o perfil de maior prioridade vira o "perfil" da pessoa.
PROFILE_PRIORITY: tuple[str, ...] = ("ADMINISTRADOR", "GERENTE", "ANALISTA", "DIRETOR", "CONVIDADO")

PROFILE_DISPLAY: dict[str, str] = {
    "ADMINISTRADOR": "Administrador",
    "GERENTE": "Gerente",
    "ANALISTA": "Analista",
    "DIRETOR": "Diretor",
    "CONVIDADO": "Convidado",
}

# (limite diário, limite por minuto) de uso da IA.
AI_LIMITS: dict[str, tuple[int, int]] = {
    "ADMINISTRADOR": (200, 20),
    "ANALISTA": (150, 10),
    "GERENTE": (120, 10),
    "DIRETOR": (80, 8),
    "CONVIDADO": (20, 3),
}
DEFAULT_AI_LIMITS: tuple[int, int] = (10, 2)


@dataclass(frozen=True)
class RoleSnapshot:
    """Retrato do acesso extraído do token: permissões e perfis (por prioridade)."""

    permissions: frozenset[str]
    profiles: tuple[str, ...]

    @property
    def has_access(self) -> bool:
        return bool(self.permissions)


def snapshot_from_roles(roles: Iterable) -> RoleSnapshot:
    names = {role for role in roles if isinstance(role, str)}
    return RoleSnapshot(
        permissions=frozenset(names & PERMISSIONS),
        profiles=tuple(profile for profile in PROFILE_PRIORITY if profile in names),
    )


def primary_profile(profiles: Iterable[str]) -> str | None:
    present = set(profiles)
    return next((profile for profile in PROFILE_PRIORITY if profile in present), None)


def ai_limits_for(profiles: Iterable[str]) -> tuple[int, int]:
    limits = [AI_LIMITS[profile] for profile in set(profiles) if profile in AI_LIMITS]
    if not limits:
        return DEFAULT_AI_LIMITS
    return max(daily for daily, _ in limits), max(per_minute for _, per_minute in limits)
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd "$APP/backend" && "$PY" -m pytest -q tests/test_permissions.py`
Expected: `8 passed`.

- [ ] **Step 5: Commit**

```bash
cd "$APP" && git add backend/app/services/permissions.py backend/tests/test_permissions.py
git commit -m "feat(auth): catálogo de permissões e perfis vindos do Keycloak

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Cliente OIDC (`services/oidc.py`) e provedor simulado

**Files:**
- Modify: `backend/app/core/config.py` (novas variáveis; nada é removido nesta tarefa)
- Create: `backend/app/services/oidc.py`
- Create: `backend/tests/oidc_fake.py`
- Modify: `backend/tests/conftest.py` (fixture `provider`)
- Test: `backend/tests/test_oidc.py`

**Interfaces:**
- Consumes: `app.core.config` (lido **como módulo**, `config.X`, a cada chamada).
- Produces (usados nas Tasks 7–9):
  - `oidc.transport`, `oidc.clock`, `oidc.reset_cache()`, `oidc.is_configured() -> bool`, `oidc.issuer() -> str`, `oidc.discovery() -> dict`.
  - Validação: `oidc.verify_access_token(token) -> dict`, `oidc.verify_id_token(token, *, nonce: str | None) -> dict`, `oidc.verify_logout_token(token) -> dict`, `oidc.roles_from_access_claims(claims) -> list[str]`.
  - Fluxo: `oidc.code_challenge(verifier) -> str`, `oidc.authorization_url(*, state, nonce, code_verifier, register=False) -> str`, `oidc.exchange_code(code, *, code_verifier, nonce) -> TokenSet`, `oidc.refresh(refresh_token, *, expected_sub) -> TokenSet`, `oidc.revoke_refresh_token(refresh_token) -> None`, `oidc.end_session_url(*, id_token_hint, post_logout_redirect_uri) -> str`.
  - `TokenSet(access_token, refresh_token, id_token, access_claims, id_claims)`.
  - Exceções: `OidcError(code)`; subclasses `OidcRejected` (o provedor recusou, ex.: `invalid_grant`) e `OidcUnavailable` (fora do ar ou não configurado).
  - Config nova: `OIDC_TOKEN_REFRESH_SECONDS=300`, `OIDC_OFFLINE_GRACE_MINUTES=15`, `OIDC_CLOCK_SKEW_SECONDS=30`, `OIDC_LOGIN_REQUEST_TTL_SECONDS=600`, `KEYCLOAK_CONSOLE_URL`, `SESSION_ENCRYPTION_KEY`.
  - `tests/oidc_fake.py`:
    - constantes `ISSUER`, `CLIENT_ID`, `CLIENT_SECRET`, `REDIRECT_URI`, `ENCRYPTION_KEY`, `ANALISTA`, `ADMINISTRADOR` (listas de papéis);
    - `FakeProvider` com `sign(claims, *, kid=None, key=None, alg="RS256")`, `access_claims(sub, roles, *, sid=None, **extra)`, `id_claims(sub, *, nonce, sid=None, **extra)`, `logout_claims(*, sid=None, sub=None, **extra)`, `issue_code(sub, roles, *, nonce, code_challenge, sid=None)`, `rotate_key(*, keep_old=False)`, `handler(request)`;
    - atributos `roles_by_sub`, `disabled_subs`, `revoked`, `offline`, `attempts`, `jwks_requests`, `token_requests`;
    - funções `s256(verifier)`, `authorization_params(url) -> dict`, `login_tokens(provider, sub, roles, *, sid=None) -> TokenSet`, `install(monkeypatch, provider)`;
    - fixture `provider` no `conftest.py`.

- [ ] **Step 1: Acrescentar as variáveis novas em `backend/app/core/config.py`**

Logo após `OIDC_POST_LOGOUT_REDIRECT_URI = ...`, acrescente:

```python
# Tempos do fluxo OIDC (valores definidos no spec do Keycloak externo).
OIDC_TOKEN_REFRESH_SECONDS = int(os.getenv("OIDC_TOKEN_REFRESH_SECONDS", "300"))
OIDC_OFFLINE_GRACE_MINUTES = int(os.getenv("OIDC_OFFLINE_GRACE_MINUTES", "15"))
OIDC_CLOCK_SKEW_SECONDS = int(os.getenv("OIDC_CLOCK_SKEW_SECONDS", "30"))
OIDC_LOGIN_REQUEST_TTL_SECONDS = int(os.getenv("OIDC_LOGIN_REQUEST_TTL_SECONDS", "600"))
# Link do console do realm exibido a quem tem users.view. É só um link: o app
# não guarda credencial administrativa do Keycloak.
KEYCLOAK_CONSOLE_URL = os.getenv("KEYCLOAK_CONSOLE_URL", "").strip()
```

E logo após `SESSION_ABSOLUTE_TIMEOUT_HOURS = ...`:

```python
# Chave Fernet que cifra o refresh token guardado na sessão (server-side).
# Gere: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
SESSION_ENCRYPTION_KEY = os.getenv("SESSION_ENCRYPTION_KEY", "").strip()
```

- [ ] **Step 2: Criar o provedor simulado `backend/tests/oidc_fake.py`**

```python
"""
Provedor OIDC simulado (Keycloak) para os testes.

Assina tokens RS256 com chaves RSA reais e responde discovery, JWKS, token e
revogação via httpx.MockTransport. Os contadores permitem conferir quantas
vezes o backend falou com o provedor.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
import uuid
from urllib.parse import parse_qs, urlsplit

import httpx
from authlib.jose import JsonWebKey, jwt
from cryptography.fernet import Fernet

ISSUER = "http://kc.test/realms/gentil-dev"
CLIENT_ID = "chat-bot-om-bff"
CLIENT_SECRET = "segredo-teste"
REDIRECT_URI = "http://localhost:5173/auth/callback"
ENCRYPTION_KEY = Fernet.generate_key().decode()
BACKCHANNEL_EVENT = "http://schemas.openid.net/event/backchannel-logout"

ANALISTA = ["ANALISTA", "assistant.use", "assistant.history", "indicators.view", "assets.view",
            "assets.create", "assets.edit", "documents.view", "documents.upload", "documents.replace",
            "settings.view"]
ADMINISTRADOR = ["ADMINISTRADOR", "assistant.use", "assistant.history", "indicators.view", "assets.view",
                 "assets.create", "assets.edit", "assets.delete", "assets.import", "documents.view",
                 "documents.upload", "documents.replace", "documents.delete", "audit.view", "users.view",
                 "settings.view", "settings.manage", "sync.tape"]


def s256(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


def authorization_params(url: str) -> dict[str, str]:
    return {key: values[0] for key, values in parse_qs(urlsplit(url).query).items()}


def _new_key():
    return JsonWebKey.generate_key("RSA", 2048, is_private=True)


class FakeProvider:
    def __init__(self) -> None:
        self.kid = "kid-1"
        self.key = _new_key()
        self.published: list[tuple[str, object]] = [(self.kid, self.key)]
        self.codes: dict[str, dict] = {}
        self.refresh_tokens: dict[str, dict] = {}
        self.roles_by_sub: dict[str, list[str]] = {}
        self.disabled_subs: set[str] = set()
        self.revoked: list[str] = []
        self.offline = False
        self.attempts = 0          # toda chamada, inclusive com o provedor fora do ar
        self.jwks_requests = 0
        self.token_requests = 0

    # ── Chaves ────────────────────────────────────────────────────────────────
    def rotate_key(self, *, keep_old: bool = False) -> None:
        self.kid = f"kid-{int(self.kid.split('-')[1]) + 1}"
        self.key = _new_key()
        self.published = (self.published if keep_old else []) + [(self.kid, self.key)]

    def jwks(self) -> dict:
        keys = []
        for kid, key in self.published:
            jwk = key.as_dict(is_private=False)
            jwk.update({"kid": kid, "use": "sig", "alg": "RS256"})
            keys.append(jwk)
        # Como o Keycloak, publica também uma chave de criptografia (não serve para assinatura).
        keys.append({**keys[-1], "kid": "kid-enc", "use": "enc", "alg": "RSA-OAEP"})
        return {"keys": keys}

    def discovery(self) -> dict:
        base = ISSUER + "/protocol/openid-connect"
        return {"issuer": ISSUER, "authorization_endpoint": base + "/auth",
                "token_endpoint": base + "/token", "jwks_uri": base + "/certs",
                "end_session_endpoint": base + "/logout", "revocation_endpoint": base + "/revoke"}

    # ── Tokens ────────────────────────────────────────────────────────────────
    def sign(self, claims: dict, *, kid: str | None = None, key=None, alg: str = "RS256") -> str:
        header = {"alg": alg, "typ": "JWT", "kid": kid or self.kid}
        payload = {name: value for name, value in claims.items() if value is not None}
        return jwt.encode(header, payload, key if key is not None else self.key).decode()

    def access_claims(self, sub: str, roles: list[str], *, sid: str | None = None, **extra) -> dict:
        now = int(time.time())
        return {"iss": ISSUER, "sub": sub, "aud": [CLIENT_ID], "azp": CLIENT_ID, "typ": "Bearer",
                "iat": now, "exp": now + 300, "jti": str(uuid.uuid4()), "sid": sid or f"sid-{sub}",
                "resource_access": {CLIENT_ID: {"roles": list(roles)}},
                "email": f"{sub}@exemplo.local", "preferred_username": sub, "name": f"Pessoa {sub}",
                **extra}

    def id_claims(self, sub: str, *, nonce: str | None, sid: str | None = None, **extra) -> dict:
        now = int(time.time())
        return {"iss": ISSUER, "sub": sub, "aud": CLIENT_ID, "azp": CLIENT_ID, "typ": "ID",
                "iat": now, "exp": now + 300, "nonce": nonce, "sid": sid or f"sid-{sub}",
                "email": f"{sub}@exemplo.local", "preferred_username": sub, "name": f"Pessoa {sub}",
                **extra}

    def logout_claims(self, *, sid: str | None = None, sub: str | None = None, **extra) -> dict:
        now = int(time.time())
        return {"iss": ISSUER, "aud": CLIENT_ID, "typ": "Logout", "iat": now, "exp": now + 120,
                "jti": str(uuid.uuid4()), "events": {BACKCHANNEL_EVENT: {}}, "sid": sid, "sub": sub,
                **extra}

    def issue_code(self, sub: str, roles: list[str], *, nonce: str, code_challenge: str,
                   sid: str | None = None) -> str:
        code = secrets.token_urlsafe(16)
        self.roles_by_sub[sub] = list(roles)
        self.codes[code] = {"sub": sub, "nonce": nonce, "challenge": code_challenge, "sid": sid or f"sid-{sub}"}
        return code

    # ── HTTP ──────────────────────────────────────────────────────────────────
    def handler(self, request: httpx.Request) -> httpx.Response:
        self.attempts += 1
        if self.offline:
            raise httpx.ConnectError("provedor fora do ar", request=request)
        path = request.url.path
        form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()} if request.method == "POST" else {}
        if path.endswith("/.well-known/openid-configuration"):
            return httpx.Response(200, json=self.discovery())
        if path.endswith("/certs"):
            self.jwks_requests += 1
            return httpx.Response(200, json=self.jwks())
        if path.endswith("/token"):
            self.token_requests += 1
            return self._token(form)
        if path.endswith("/revoke"):
            self.revoked.append(form.get("token", ""))
            self.refresh_tokens.pop(form.get("token", ""), None)
            return httpx.Response(200)
        return httpx.Response(404)

    def _token(self, form: dict) -> httpx.Response:
        if form.get("client_id") != CLIENT_ID or form.get("client_secret") != CLIENT_SECRET:
            return httpx.Response(401, json={"error": "unauthorized_client"})
        grant = form.get("grant_type")
        if grant == "authorization_code":
            record = self.codes.pop(form.get("code", ""), None)
            if (record is None or form.get("redirect_uri") != REDIRECT_URI
                    or s256(form.get("code_verifier", "")) != record["challenge"]):
                return httpx.Response(400, json={"error": "invalid_grant"})
            return self._issue(record["sub"], record["sid"], nonce=record["nonce"])
        if grant == "refresh_token":
            # Rotação: cada refresh token vale uma única vez.
            record = self.refresh_tokens.pop(form.get("refresh_token", ""), None)
            if record is None or record["sub"] in self.disabled_subs:
                return httpx.Response(400, json={"error": "invalid_grant"})
            return self._issue(record["sub"], record["sid"], nonce=None)
        return httpx.Response(400, json={"error": "unsupported_grant_type"})

    def _issue(self, sub: str, sid: str, *, nonce: str | None) -> httpx.Response:
        refresh_token = secrets.token_urlsafe(24)
        self.refresh_tokens[refresh_token] = {"sub": sub, "sid": sid}
        roles = self.roles_by_sub.get(sub, [])
        return httpx.Response(200, json={
            "access_token": self.sign(self.access_claims(sub, roles, sid=sid)),
            "id_token": self.sign(self.id_claims(sub, nonce=nonce, sid=sid)),
            "refresh_token": refresh_token, "token_type": "Bearer", "expires_in": 300,
        })


def login_tokens(provider: FakeProvider, sub: str, roles: list[str], *, sid: str | None = None):
    """Faz o login completo (código + PKCE + nonce) e devolve o TokenSet validado."""
    from app.services import oidc

    verifier, nonce = secrets.token_urlsafe(48), secrets.token_urlsafe(16)
    code = provider.issue_code(sub, roles, nonce=nonce, code_challenge=s256(verifier), sid=sid)
    return oidc.exchange_code(code, code_verifier=verifier, nonce=nonce)


def install(monkeypatch, provider: FakeProvider) -> None:
    from app.core import config
    from app.services import oidc

    monkeypatch.setattr(config, "OIDC_ISSUER_URL", ISSUER)
    monkeypatch.setattr(config, "OIDC_CLIENT_ID", CLIENT_ID)
    monkeypatch.setattr(config, "OIDC_CLIENT_SECRET", CLIENT_SECRET)
    monkeypatch.setattr(config, "OIDC_REDIRECT_URI", REDIRECT_URI)
    monkeypatch.setattr(config, "SESSION_ENCRYPTION_KEY", ENCRYPTION_KEY)
    monkeypatch.setattr(oidc, "transport", httpx.MockTransport(provider.handler))
    oidc.reset_cache()
```

- [ ] **Step 3: Fixture `provider` no final de `backend/tests/conftest.py`**

```python
@pytest.fixture
def provider(monkeypatch):
    """Keycloak simulado instalado no app (config + transporte HTTP do módulo oidc)."""
    from app.services import oidc
    from tests.oidc_fake import FakeProvider, install

    fake = FakeProvider()
    install(monkeypatch, fake)
    yield fake
    oidc.reset_cache()
```

- [ ] **Step 4: Escrever os testes `backend/tests/test_oidc.py`**

```python
"""Validação de tokens e chamadas ao provedor (app/services/oidc.py)."""

from __future__ import annotations

import base64
import json
import time

import pytest

from app.services import oidc
from tests.oidc_fake import (
    ANALISTA,
    CLIENT_ID,
    ISSUER,
    FakeProvider,
    authorization_params,
    login_tokens,
    s256,
)


def _unsigned(claims: dict) -> str:
    def b64(obj) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()
    return f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64(claims)}."


def _code(exc_info) -> str:
    return exc_info.value.code


class TestAccessToken:
    def test_token_valido_devolve_claims_e_papeis(self, provider):
        claims = oidc.verify_access_token(provider.sign(provider.access_claims("u1", ANALISTA)))
        assert claims["sub"] == "u1"
        assert oidc.roles_from_access_claims(claims) == ANALISTA

    @pytest.mark.parametrize("change, code", [
        (lambda now: {"iss": "http://outro/realms/gentil-dev"}, "invalid_issuer"),
        (lambda now: {"aud": ["account"]}, "invalid_audience"),
        (lambda now: {"azp": "outro-client"}, "invalid_azp"),
        (lambda now: {"typ": "ID"}, "invalid_token_type"),
        (lambda now: {"exp": now - 60}, "token_expired"),
        (lambda now: {"iat": now + 60}, "invalid_iat"),
        (lambda now: {"sub": None}, "missing_subject"),
    ])
    def test_claims_invalidas_sao_recusadas(self, provider, change, code):
        claims = provider.access_claims("u1", ANALISTA)
        claims.update(change(int(time.time())))
        with pytest.raises(oidc.OidcError) as exc:
            oidc.verify_access_token(provider.sign(claims))
        assert _code(exc) == code

    def test_tolerancia_de_relogio_de_30_segundos(self, provider):
        now = int(time.time())
        claims = provider.access_claims("u1", ANALISTA)
        claims.update({"exp": now - 20, "iat": now + 20})
        assert oidc.verify_access_token(provider.sign(claims))["sub"] == "u1"

    def test_assinatura_de_outra_chave_com_o_mesmo_kid_e_recusada(self, provider):
        intruso = FakeProvider()  # outra chave RSA, mesmo kid "kid-1"
        with pytest.raises(oidc.OidcError) as exc:
            oidc.verify_access_token(intruso.sign(provider.access_claims("u1", ANALISTA)))
        assert _code(exc) == "invalid_token"

    def test_hs256_e_alg_none_sao_recusados(self, provider):
        claims = provider.access_claims("u1", ANALISTA)
        hs256 = provider.sign(claims, alg="HS256", key="chave-simetrica-de-teste-com-32-bytes")
        for token in (hs256, _unsigned(claims), "nao-e-um-jwt"):
            with pytest.raises(oidc.OidcError) as exc:
                oidc.verify_access_token(token)
            assert _code(exc) == "invalid_token"


class TestJwks:
    def test_kid_desconhecido_recarrega_no_maximo_uma_vez_por_minuto(self, provider, monkeypatch):
        now = [1000.0]
        monkeypatch.setattr(oidc, "clock", lambda: now[0])
        oidc.verify_access_token(provider.sign(provider.access_claims("u1", ANALISTA)))
        token = provider.sign(provider.access_claims("u1", ANALISTA), kid="kid-inexistente")
        with pytest.raises(oidc.OidcError) as exc:
            oidc.verify_access_token(token)
        assert _code(exc) == "unknown_signing_key"
        assert provider.jwks_requests == 1  # carregado há menos de 1 minuto
        now[0] += 61
        for _ in range(3):
            with pytest.raises(oidc.OidcError):
                oidc.verify_access_token(token)
        assert provider.jwks_requests == 2  # uma única recarga no novo minuto

    def test_rotacao_de_chave_e_aceita_depois_da_recarga(self, provider, monkeypatch):
        now = [1000.0]
        monkeypatch.setattr(oidc, "clock", lambda: now[0])
        oidc.verify_access_token(provider.sign(provider.access_claims("u1", ANALISTA)))
        provider.rotate_key()
        now[0] += 61
        claims = oidc.verify_access_token(provider.sign(provider.access_claims("u1", ANALISTA)))
        assert claims["sub"] == "u1" and provider.jwks_requests == 2

    def test_chave_de_criptografia_nao_valida_assinatura(self, provider):
        token = provider.sign(provider.access_claims("u1", ANALISTA), kid="kid-enc")
        with pytest.raises(oidc.OidcError) as exc:
            oidc.verify_access_token(token)
        assert _code(exc) == "unknown_signing_key"


class TestIdToken:
    def test_nonce_confere(self, provider):
        token = provider.sign(provider.id_claims("u1", nonce="n-1"))
        assert oidc.verify_id_token(token, nonce="n-1")["sub"] == "u1"

    def test_nonce_diferente_ou_ausente_e_recusado(self, provider):
        for claims in (provider.id_claims("u1", nonce="outro"), provider.id_claims("u1", nonce=None)):
            with pytest.raises(oidc.OidcError) as exc:
                oidc.verify_id_token(provider.sign(claims), nonce="n-1")
            assert _code(exc) == "invalid_nonce"

    def test_access_token_nao_serve_como_id_token(self, provider):
        with pytest.raises(oidc.OidcError) as exc:
            oidc.verify_id_token(provider.sign(provider.access_claims("u1", ANALISTA)), nonce="n")
        assert _code(exc) == "invalid_token_type"


class TestLogoutToken:
    def test_valido_com_sid_e_dentro_da_tolerancia(self, provider):
        claims = provider.logout_claims(sid="s-1")
        claims["iat"] = int(time.time()) - 140  # 2 min + parte dos 30 s de tolerância
        assert oidc.verify_logout_token(provider.sign(claims))["sid"] == "s-1"

    @pytest.mark.parametrize("change, code", [
        (lambda now: {"iat": now - 151}, "logout_token_too_old"),
        (lambda now: {"events": {}}, "invalid_logout_event"),
        (lambda now: {"nonce": "n"}, "nonce_not_allowed"),
        (lambda now: {"sid": None, "sub": None}, "missing_sid_and_sub"),
        (lambda now: {"typ": "Bearer"}, "invalid_token_type"),
        (lambda now: {"aud": "outro-client"}, "invalid_audience"),
    ])
    def test_invalidos_sao_recusados(self, provider, change, code):
        claims = provider.logout_claims(sid="s-1")
        claims.update(change(int(time.time())))
        with pytest.raises(oidc.OidcError) as exc:
            oidc.verify_logout_token(provider.sign(claims))
        assert _code(exc) == code


class TestTokenEndpoint:
    def test_troca_de_codigo_com_pkce_e_nonce(self, provider):
        tokens = login_tokens(provider, "u1", ANALISTA)
        assert tokens.access_claims["sub"] == "u1"
        assert tokens.refresh_token and tokens.id_token and tokens.id_claims["sid"] == "sid-u1"

    def test_codigo_reutilizado_e_recusado(self, provider):
        verifier = "v" * 64
        code = provider.issue_code("u1", ANALISTA, nonce="n", code_challenge=s256(verifier))
        oidc.exchange_code(code, code_verifier=verifier, nonce="n")
        with pytest.raises(oidc.OidcRejected) as exc:
            oidc.exchange_code(code, code_verifier=verifier, nonce="n")
        assert _code(exc) == "invalid_grant"

    def test_code_verifier_errado_e_recusado(self, provider):
        code = provider.issue_code("u1", ANALISTA, nonce="n", code_challenge=s256("v" * 64))
        with pytest.raises(oidc.OidcRejected):
            oidc.exchange_code(code, code_verifier="x" * 64, nonce="n")

    def test_nonce_diferente_do_login_e_recusado(self, provider):
        verifier = "v" * 64
        code = provider.issue_code("u1", ANALISTA, nonce="do-provedor", code_challenge=s256(verifier))
        with pytest.raises(oidc.OidcError) as exc:
            oidc.exchange_code(code, code_verifier=verifier, nonce="do-login")
        assert _code(exc) == "invalid_nonce"

    def test_renovacao_gira_o_refresh_token(self, provider):
        tokens = login_tokens(provider, "u1", ANALISTA)
        renewed = oidc.refresh(tokens.refresh_token, expected_sub="u1")
        assert renewed.refresh_token != tokens.refresh_token
        with pytest.raises(oidc.OidcRejected):
            oidc.refresh(tokens.refresh_token, expected_sub="u1")

    def test_renovacao_de_outro_subject_e_recusada(self, provider):
        tokens = login_tokens(provider, "u1", ANALISTA)
        with pytest.raises(oidc.OidcError) as exc:
            oidc.refresh(tokens.refresh_token, expected_sub="u2")
        assert _code(exc) == "subject_mismatch"

    def test_provedor_fora_do_ar(self, provider):
        tokens = login_tokens(provider, "u1", ANALISTA)
        provider.offline = True
        with pytest.raises(oidc.OidcUnavailable):
            oidc.refresh(tokens.refresh_token, expected_sub="u1")

    def test_revogacao_e_melhor_esforco(self, provider):
        tokens = login_tokens(provider, "u1", ANALISTA)
        oidc.revoke_refresh_token(tokens.refresh_token)
        assert provider.revoked == [tokens.refresh_token]
        provider.offline = True
        oidc.revoke_refresh_token("qualquer")  # não levanta exceção


class TestUrls:
    def test_login_com_pkce_s256_nonce_e_state(self, provider):
        url = oidc.authorization_url(state="st", nonce="no", code_verifier="v" * 64)
        params = authorization_params(url)
        assert url.startswith(ISSUER + "/protocol/openid-connect/auth?")
        assert params["code_challenge"] == s256("v" * 64)
        assert params["code_challenge_method"] == "S256"
        assert params["state"] == "st" and params["nonce"] == "no"
        assert params["client_id"] == CLIENT_ID and params["scope"] == "openid email profile"
        assert "prompt" not in params

    def test_cadastro_usa_prompt_create(self, provider):
        url = oidc.authorization_url(state="s", nonce="n", code_verifier="v" * 64, register=True)
        assert authorization_params(url)["prompt"] == "create"

    def test_issuer_divergente_no_discovery_e_recusado(self, provider, monkeypatch):
        monkeypatch.setattr(provider, "discovery", lambda: {**FakeProvider.discovery(provider), "issuer": "http://outro"})
        oidc.reset_cache()
        with pytest.raises(oidc.OidcError) as exc:
            oidc.discovery()
        assert _code(exc) == "issuer_mismatch"

    def test_sem_configuracao_o_provedor_fica_indisponivel(self, provider, monkeypatch):
        from app.core import config
        monkeypatch.setattr(config, "OIDC_ISSUER_URL", "")
        oidc.reset_cache()
        with pytest.raises(oidc.OidcUnavailable):
            oidc.discovery()

    def test_url_de_logout_com_hint_e_client_id(self, provider):
        url = oidc.end_session_url(id_token_hint="tok", post_logout_redirect_uri="http://localhost:5173/login")
        assert url.startswith(ISSUER + "/protocol/openid-connect/logout?")
        assert authorization_params(url) == {"post_logout_redirect_uri": "http://localhost:5173/login",
                                             "client_id": CLIENT_ID, "id_token_hint": "tok"}
```

- [ ] **Step 5: Rodar e ver falhar**

Run: `cd "$APP/backend" && "$PY" -m pytest -q tests/test_oidc.py`
Expected: FAIL com `ImportError: cannot import name 'oidc' from 'app.services'`.

- [ ] **Step 6: Implementar `backend/app/services/oidc.py`**

```python
"""
Cliente OIDC do BFF (Keycloak).

Discovery, JWKS, validação de tokens, troca de código (PKCE), renovação,
revogação (RFC 7009) e validação de logout token. Nenhum token sai deste
backend para o navegador. A configuração é lida de ``app.core.config`` a cada
chamada (os testes a substituem).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
from authlib.jose import JsonWebKey, JsonWebToken
from authlib.jose.errors import JoseError

from app.core import config

logger = logging.getLogger(__name__)

BACKCHANNEL_LOGOUT_EVENT = "http://schemas.openid.net/event/backchannel-logout"
JWKS_MIN_REFRESH_SECONDS = 60
LOGOUT_TOKEN_MAX_AGE_SECONDS = 120
HTTP_TIMEOUT_SECONDS = 10

# Substituíveis nos testes: transporte HTTP (httpx.MockTransport) e relógio do JWKS.
transport: httpx.BaseTransport | None = None
clock = time.monotonic

_jwt = JsonWebToken(["RS256"])
_lock = threading.Lock()
_discovery: dict | None = None
_keys: dict[str, object] = {}
_keys_loaded_at: float | None = None


class OidcError(Exception):
    """Token ou resposta inválida. ``code`` é curto e seguro para log."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class OidcRejected(OidcError):
    """O provedor recusou a operação (ex.: invalid_grant, conta bloqueada)."""


class OidcUnavailable(OidcError):
    """Provedor inacessível ou não configurado."""


@dataclass(frozen=True)
class TokenSet:
    access_token: str
    refresh_token: str | None
    id_token: str | None
    access_claims: dict
    id_claims: dict | None


def reset_cache() -> None:
    global _discovery, _keys, _keys_loaded_at
    with _lock:
        _discovery = None
        _keys = {}
        _keys_loaded_at = None


def is_configured() -> bool:
    return bool(config.OIDC_ISSUER_URL)


def issuer() -> str:
    return config.OIDC_ISSUER_URL.rstrip("/")


def _http() -> httpx.Client:
    return httpx.Client(timeout=HTTP_TIMEOUT_SECONDS, transport=transport)


def _get_json(url: str, code: str) -> dict:
    try:
        with _http() as client:
            resp = client.get(url)
    except httpx.HTTPError as exc:
        raise OidcUnavailable(code) from exc
    if resp.status_code != 200:
        raise OidcUnavailable(code)
    return resp.json()


# ─── Discovery e JWKS ─────────────────────────────────────────────────────────

def discovery() -> dict:
    global _discovery
    if not is_configured():
        raise OidcUnavailable("not_configured")
    if _discovery is None:
        data = _get_json(issuer() + "/.well-known/openid-configuration", "discovery_failed")
        if str(data.get("issuer", "")).rstrip("/") != issuer():
            raise OidcError("issuer_mismatch")
        _discovery = data
    return _discovery


def _load_keys(*, force: bool = False) -> dict[str, object]:
    """Chaves RS256 de assinatura. Recarga forçada no máximo 1 vez por minuto."""
    global _keys, _keys_loaded_at
    with _lock:
        now = clock()
        if _keys_loaded_at is not None and (not force or now - _keys_loaded_at < JWKS_MIN_REFRESH_SECONDS):
            return _keys
        data = _get_json(discovery()["jwks_uri"], "jwks_failed")
        keys = {}
        for jwk in data.get("keys", []):
            if (jwk.get("kty") == "RSA" and jwk.get("use", "sig") == "sig"
                    and jwk.get("alg", "RS256") == "RS256" and jwk.get("kid")):
                keys[jwk["kid"]] = JsonWebKey.import_key(jwk)
        _keys, _keys_loaded_at = keys, now
        return _keys


def _signing_key(kid: str | None):
    if not kid:
        raise OidcError("missing_kid")
    key = _load_keys().get(kid)
    if key is None:
        key = _load_keys(force=True).get(kid)
    if key is None:
        raise OidcError("unknown_signing_key")
    return key


# ─── Validação ────────────────────────────────────────────────────────────────

def _decode(token: str) -> dict:
    if not isinstance(token, str) or not token:
        raise OidcError("invalid_token")
    try:
        claims = _jwt.decode(token, lambda header, payload: _signing_key(header.get("kid")))
    except OidcError:
        raise
    except (JoseError, ValueError, TypeError, KeyError) as exc:
        raise OidcError("invalid_token") from exc
    return dict(claims)


def _check_claims(claims: dict, *, typ: str, require_exp: bool = True) -> None:
    now = time.time()
    skew = config.OIDC_CLOCK_SKEW_SECONDS
    if claims.get("iss") != issuer():
        raise OidcError("invalid_issuer")
    aud = claims.get("aud")
    if config.OIDC_CLIENT_ID not in (aud if isinstance(aud, list) else [aud]):
        raise OidcError("invalid_audience")
    if claims.get("typ") != typ:
        raise OidcError("invalid_token_type")
    iat = claims.get("iat")
    if not isinstance(iat, (int, float)) or iat > now + skew:
        raise OidcError("invalid_iat")
    exp = claims.get("exp")
    if exp is None and not require_exp:
        return
    if not isinstance(exp, (int, float)) or exp < now - skew:
        raise OidcError("token_expired")


def verify_access_token(token: str) -> dict:
    claims = _decode(token)
    _check_claims(claims, typ="Bearer")
    if claims.get("azp") != config.OIDC_CLIENT_ID:
        raise OidcError("invalid_azp")
    if not claims.get("sub"):
        raise OidcError("missing_subject")
    return claims


def verify_id_token(token: str, *, nonce: str | None) -> dict:
    """``nonce=None`` somente na renovação; no login o nonce é obrigatório."""
    claims = _decode(token)
    _check_claims(claims, typ="ID")
    if nonce is not None and not hmac.compare_digest(str(claims.get("nonce", "")).encode(), nonce.encode()):
        raise OidcError("invalid_nonce")
    return claims


def verify_logout_token(token: str) -> dict:
    claims = _decode(token)
    _check_claims(claims, typ="Logout", require_exp=False)
    if claims["iat"] < time.time() - LOGOUT_TOKEN_MAX_AGE_SECONDS - config.OIDC_CLOCK_SKEW_SECONDS:
        raise OidcError("logout_token_too_old")
    events = claims.get("events")
    if not isinstance(events, dict) or BACKCHANNEL_LOGOUT_EVENT not in events:
        raise OidcError("invalid_logout_event")
    if "nonce" in claims:
        raise OidcError("nonce_not_allowed")
    if not claims.get("sid") and not claims.get("sub"):
        raise OidcError("missing_sid_and_sub")
    return claims


def roles_from_access_claims(claims: dict) -> list[str]:
    client = (claims.get("resource_access") or {}).get(config.OIDC_CLIENT_ID) or {}
    return [role for role in client.get("roles") or [] if isinstance(role, str)]


# ─── Fluxo de autorização ─────────────────────────────────────────────────────

def code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def authorization_url(*, state: str, nonce: str, code_verifier: str, register: bool = False) -> str:
    params = {
        "response_type": "code",
        "client_id": config.OIDC_CLIENT_ID,
        "redirect_uri": config.OIDC_REDIRECT_URI,
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge(code_verifier),
        "code_challenge_method": "S256",
    }
    if register:
        params["prompt"] = "create"  # abre direto o cadastro do Keycloak
    return discovery()["authorization_endpoint"] + "?" + urlencode(params)


def _token_request(data: dict) -> dict:
    endpoint = discovery()["token_endpoint"]
    payload = {**data, "client_id": config.OIDC_CLIENT_ID, "client_secret": config.OIDC_CLIENT_SECRET}
    try:
        with _http() as client:
            resp = client.post(endpoint, data=payload)
    except httpx.HTTPError as exc:
        raise OidcUnavailable("token_endpoint_unreachable") from exc
    if resp.status_code >= 500:
        raise OidcUnavailable("token_endpoint_error")
    if resp.status_code != 200:
        try:
            error = str(resp.json().get("error") or "rejected")
        except ValueError:
            error = "rejected"
        raise OidcRejected(error[:60])
    return resp.json()


def _token_set(data: dict, *, nonce: str | None, expected_sub: str | None = None) -> TokenSet:
    access_token = data.get("access_token")
    if not access_token:
        raise OidcError("missing_access_token")
    access_claims = verify_access_token(access_token)
    id_token = data.get("id_token")
    id_claims = None
    if id_token:
        id_claims = verify_id_token(id_token, nonce=nonce)
        if id_claims.get("sub") != access_claims["sub"]:
            raise OidcError("subject_mismatch")
    elif nonce is not None:
        raise OidcError("missing_id_token")
    if expected_sub is not None and access_claims["sub"] != expected_sub:
        raise OidcError("subject_mismatch")
    return TokenSet(access_token, data.get("refresh_token"), id_token, access_claims, id_claims)


def exchange_code(code: str, *, code_verifier: str, nonce: str) -> TokenSet:
    data = _token_request({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": config.OIDC_REDIRECT_URI,
        "code_verifier": code_verifier,
    })
    return _token_set(data, nonce=nonce)


def refresh(refresh_token: str, *, expected_sub: str) -> TokenSet:
    data = _token_request({"grant_type": "refresh_token", "refresh_token": refresh_token})
    return _token_set(data, nonce=None, expected_sub=expected_sub)


def revoke_refresh_token(refresh_token: str | None) -> None:
    """Revogação RFC 7009. Melhor esforço: nunca impede o logout local."""
    if not refresh_token or not is_configured():
        return
    try:
        endpoint = discovery().get("revocation_endpoint")
        if not endpoint:
            return
        with _http() as client:
            client.post(endpoint, data={
                "token": refresh_token, "token_type_hint": "refresh_token",
                "client_id": config.OIDC_CLIENT_ID, "client_secret": config.OIDC_CLIENT_SECRET,
            })
    except (OidcError, httpx.HTTPError):
        logger.warning("OIDC: revogação do refresh token falhou; a sessão SSO expira no Keycloak.")


def end_session_url(*, id_token_hint: str | None, post_logout_redirect_uri: str) -> str:
    endpoint = discovery().get("end_session_endpoint")
    if not endpoint:
        return post_logout_redirect_uri
    params = {"post_logout_redirect_uri": post_logout_redirect_uri, "client_id": config.OIDC_CLIENT_ID}
    if id_token_hint:
        params["id_token_hint"] = id_token_hint
    return endpoint + "?" + urlencode(params)
```

- [ ] **Step 7: Rodar e ver passar**

Run: `cd "$APP/backend" && "$PY" -m pytest -q tests/test_oidc.py tests/test_permissions.py`
Expected: `45 passed` (37 de `test_oidc.py`, contando cada caso parametrizado, + 8).

- [ ] **Step 8: Commit**

```bash
cd "$APP" && git add backend/app/core/config.py backend/app/services/oidc.py backend/tests/oidc_fake.py backend/tests/conftest.py backend/tests/test_oidc.py
git commit -m "feat(auth): cliente OIDC com validação de tokens pelo JWKS e provedor simulado

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Modelo de dados e serviços de sessão/identidade

**Files:**
- Modify: `backend/app/models/auth.py`: substitui do início do arquivo até o fim da classe `UserPermissionOverride` (linhas 1–164). As classes de `# ─── Conversas` em diante ficam iguais.
- Rewrite: `backend/app/services/auth.py`
- Create: `backend/scripts/reset_identity.sql`
- Modify: `backend/tests/conftest.py` (imports de modelos)
- Rewrite: `backend/tests/test_auth_security.py`

**Interfaces:**
- Consumes:
  - `app.services.permissions.RoleSnapshot` e `ai_limits_for` (Task 5);
  - `app.services.oidc.TokenSet` (Task 6);
  - `tests.oidc_fake.login_tokens`, `ANALISTA`, `ISSUER` e a fixture `provider` (Task 6).
- Produces:
  - Modelos:
    - `AppUser` (sem `profile_id`/`status`/`access_expires_at`/limites/bootstrap; `email` não único; `last_profiles: list | None`);
    - `UserSession` com `sid`, `refresh_token_enc`, `permissions: list`, `profiles: list`, `snapshot_refreshed_at`, `refresh_failed_since`, `refresh_attempted_at`;
    - `OidcLoginRequest(state_hash, code_verifier, nonce, created_at, expires_at)`;
    - sem `Profile`, `Permission`, `ProfilePermission`, `UserPermissionOverride`.
  - `app.services.auth`:
    - segredo da sessão: `encrypt_secret(value) -> str | None`, `decrypt_secret(value) -> str | None`;
    - login: `create_login_request(db) -> tuple[state, code_verifier, nonce]`, `consume_login_request(db, state) -> tuple[code_verifier, nonce] | None`;
    - identidade: `upsert_user(db, claims, *, profiles) -> AppUser`;
    - sessão: `create_session(db, user, *, tokens, snapshot, ip=None, ua=None) -> str` (só `flush`; quem chama faz `commit`), `get_session(db, token) -> UserSession | None`, `touch_session(db, session)`, `revoke_session(db, session)` (só `flush`), `revoke_sessions_for_logout(db, *, issuer, sid, subject) -> int` (só `flush`);
    - IA: `get_ai_limits(user) -> tuple[int, int]`, `check_ai_rate_limit(db, user) -> dict` (mesmo formato de hoje);
    - auditoria: `record_audit(...)`, `record_security_event(...)` (assinaturas de hoje);
    - `post_logout_redirect_uri() -> str`.

> Depois desta tarefa o app não sobe até a Task 9 (rotas e dependências ainda importam nomes antigos). Rode só os testes indicados.

- [ ] **Step 1: Reescrever os testes `backend/tests/test_auth_security.py`**

```python
"""Sessões, identidade local, registro de login, limites de IA e auditoria (app/services/auth.py)."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import func, select

from app.core import config
from app.models.auth import (
    AiUsage,
    AppUser,
    AssistantConversation,
    AuditLog,
    OidcIdentity,
    OidcLoginRequest,
    SecurityEvent,
    UserSession,
)
from app.services import auth
from app.services.permissions import snapshot_from_roles
from tests.oidc_fake import ANALISTA, ISSUER, login_tokens


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _claims(sub: str = "sub-1", email: str | None = "pessoa@exemplo.local", **extra) -> dict:
    return {"iss": ISSUER, "sub": sub, "email": email, "preferred_username": "pessoa",
            "name": "Pessoa Teste", **extra}


def _user(db, sub: str = "sub-1", email: str | None = "pessoa@exemplo.local", profiles=("ANALISTA",)) -> AppUser:
    user = auth.upsert_user(db, _claims(sub, email), profiles=profiles)
    db.commit()
    return user


def _session(db, provider, *, sub: str = "sub-1", roles=ANALISTA, sid: str | None = None):
    user = _user(db, sub=sub)
    tokens = login_tokens(provider, sub, roles, sid=sid)
    token = auth.create_session(db, user, tokens=tokens, snapshot=snapshot_from_roles(roles))
    db.commit()
    session = db.scalar(select(UserSession).where(UserSession.session_token_hash == _sha256(token)))
    return user, token, session


# ── Sessão ────────────────────────────────────────────────────────────────────

def test_token_da_sessao_guardado_somente_como_hash(db, provider):
    _, token, session = _session(db, provider)
    assert session.session_token_hash == _sha256(token)
    assert token not in (session.session_token_hash, session.csrf_secret)


def test_refresh_token_guardado_cifrado(db, provider):
    _, _, session = _session(db, provider)
    [refresh_token] = provider.refresh_tokens
    assert refresh_token not in session.refresh_token_enc
    assert auth.decrypt_secret(session.refresh_token_enc) == refresh_token


def test_sessao_guarda_retrato_sid_e_id_token(db, provider):
    _, _, session = _session(db, provider, sid="sid-abc")
    assert session.permissions == sorted(set(ANALISTA) - {"ANALISTA"})
    assert session.profiles == ["ANALISTA"]
    assert session.sid == "sid-abc"
    assert session.id_token_hint and session.snapshot_refreshed_at is not None


def test_get_session_valida_e_token_desconhecido(db, provider):
    _, token, session = _session(db, provider)
    assert auth.get_session(db, token) is session
    assert auth.get_session(db, "token-desconhecido") is None


@pytest.mark.parametrize("field", ["expires_at", "absolute_expires_at"])
def test_sessao_expirada(db, provider, field):
    _, token, session = _session(db, provider)
    setattr(session, field, datetime.utcnow() - timedelta(seconds=1))
    db.commit()
    assert auth.get_session(db, token) is None


def test_revogar_sessao_apaga_segredos(db, provider):
    _, token, session = _session(db, provider)
    auth.revoke_session(db, session)
    db.commit()
    assert session.revoked_at is not None
    assert session.id_token_hint is None and session.refresh_token_enc is None
    assert auth.get_session(db, token) is None


def test_backchannel_revoga_por_sid_ou_por_subject(db, provider):
    _session(db, provider, sid="s-a")
    _session(db, provider, sid="s-b")
    _session(db, provider, sub="sub-2", sid="s-c")
    assert auth.revoke_sessions_for_logout(db, issuer=ISSUER, sid="s-a", subject=None) == 1
    assert auth.revoke_sessions_for_logout(db, issuer=ISSUER, sid=None, subject="sub-1") == 1
    assert auth.revoke_sessions_for_logout(db, issuer=ISSUER, sid="desconhecido", subject=None) == 0
    db.commit()
    ativas = db.scalars(select(UserSession).where(UserSession.revoked_at.is_(None))).all()
    assert [s.sid for s in ativas] == ["s-c"]


# ── Cifra do refresh token ────────────────────────────────────────────────────

def test_cifra_e_decifra(provider):
    cipher = auth.encrypt_secret("segredo")
    assert cipher != "segredo" and auth.decrypt_secret(cipher) == "segredo"
    assert auth.encrypt_secret(None) is None and auth.decrypt_secret(None) is None


def test_chave_diferente_nao_decifra(provider, monkeypatch):
    cipher = auth.encrypt_secret("segredo")
    monkeypatch.setattr(config, "SESSION_ENCRYPTION_KEY", Fernet.generate_key().decode())
    assert auth.decrypt_secret(cipher) is None


def test_sem_chave_nao_cifra(monkeypatch):
    monkeypatch.setattr(config, "SESSION_ENCRYPTION_KEY", "")
    with pytest.raises(RuntimeError):
        auth.encrypt_secret("segredo")


# ── Registro de login (state, code_verifier, nonce) ───────────────────────────

def test_registro_de_login_e_de_uso_unico(db):
    state, verifier, nonce = auth.create_login_request(db)
    assert auth.consume_login_request(db, state) == (verifier, nonce)
    assert auth.consume_login_request(db, state) is None


def test_state_guardado_como_hash(db):
    state, _, _ = auth.create_login_request(db)
    row = db.scalar(select(OidcLoginRequest))
    assert row.state_hash == _sha256(state)


def test_state_vazio_ou_desconhecido(db):
    assert auth.consume_login_request(db, None) is None
    assert auth.consume_login_request(db, "desconhecido") is None


def test_registro_expirado_e_recusado_e_apagado(db):
    state, _, _ = auth.create_login_request(db)
    db.scalar(select(OidcLoginRequest)).expires_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    assert auth.consume_login_request(db, state) is None
    assert db.scalar(select(func.count(OidcLoginRequest.id))) == 0


def test_registros_expirados_sao_limpos_ao_criar_outro(db):
    auth.create_login_request(db)
    db.scalar(select(OidcLoginRequest)).expires_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    auth.create_login_request(db)
    assert db.scalar(select(func.count(OidcLoginRequest.id))) == 1


# ── Identidade local (issuer + subject) ───────────────────────────────────────

def test_primeiro_login_cria_usuario_e_identidade(db):
    user = _user(db)
    identity = db.scalar(select(OidcIdentity))
    assert (identity.issuer, identity.subject, identity.user_id) == (ISSUER, "sub-1", user.id)
    assert user.email == "pessoa@exemplo.local" and user.username == "pessoa"
    assert user.display_name == "Pessoa Teste" and user.last_profiles == ["ANALISTA"]


def test_login_seguinte_atualiza_os_dados_do_mesmo_registro(db):
    first = _user(db)
    again = auth.upsert_user(db, _claims(email="novo@exemplo.local", name="Nome Novo"), profiles=("GERENTE",))
    db.commit()
    assert again.id == first.id
    assert again.email == "novo@exemplo.local" and again.display_name == "Nome Novo"
    assert again.last_profiles == ["GERENTE"]


def test_mesmo_email_com_outro_subject_vira_outro_usuario(db):
    antigo = _user(db, sub="sub-antigo", email="pessoa@exemplo.local")
    db.add(AssistantConversation(id="c-1", user_id=antigo.id, n8n_session_id="n-1"))
    db.commit()
    novo = _user(db, sub="sub-novo", email="pessoa@exemplo.local")
    assert novo.id != antigo.id
    assert db.scalar(select(func.count(AssistantConversation.id))
                     .where(AssistantConversation.user_id == novo.id)) == 0
    assert db.scalar(select(func.count(OidcIdentity.id))) == 2


def test_usuario_sem_email_usa_o_login_como_nome(db):
    user = auth.upsert_user(db, _claims(email=None, name=None), profiles=())
    db.commit()
    assert user.email == "" and user.display_name == "pessoa" and user.last_profiles == []


# ── Limites de IA ─────────────────────────────────────────────────────────────

def test_limites_pelos_perfis_do_ultimo_login(db):
    assert auth.get_ai_limits(_user(db, profiles=("GERENTE", "ANALISTA"))) == (150, 10)
    assert auth.get_ai_limits(_user(db, sub="sub-2", profiles=())) == (10, 2)


def _uso(db, user, quantidade, *, status="success", ha=timedelta(seconds=5)):
    for i in range(quantidade):
        db.add(AiUsage(user_id=user.id, request_id=f"r-{status}-{i}-{ha.total_seconds()}", status=status,
                       created_at=datetime.utcnow() - ha))
    db.commit()


def test_limite_diario_atingido(db):
    user = _user(db, profiles=("CONVIDADO",))
    _uso(db, user, 20, ha=timedelta(seconds=90))  # fora da janela de 1 min, dentro do dia
    rate = auth.check_ai_rate_limit(db, user)
    assert rate["allowed"] is False and rate["reason"] == "daily_limit" and rate["daily_limit"] == 20


def test_limite_por_minuto_atingido(db):
    user = _user(db, profiles=("CONVIDADO",))
    _uso(db, user, 3)
    rate = auth.check_ai_rate_limit(db, user)
    assert rate["allowed"] is False and rate["reason"] == "per_minute_limit"


def test_erros_nao_contam_no_limite(db):
    user = _user(db, profiles=("CONVIDADO",))
    _uso(db, user, 25, status="error")
    assert auth.check_ai_rate_limit(db, user)["allowed"] is True


# ── Auditoria ─────────────────────────────────────────────────────────────────

def test_auditoria_e_evento_de_seguranca(db):
    user = _user(db)
    auth.record_audit(db, user_id=user.id, action="LOGIN_SUCCESS", entity_type="app_user", entity_id=str(user.id))
    auth.record_security_event(db, event_type="ACCESS_DENIED", user_id=user.id, metadata={"path": "/x"})
    db.commit()
    assert db.scalar(select(AuditLog.action)) == "LOGIN_SUCCESS"
    assert db.scalar(select(SecurityEvent.event_type)) == "ACCESS_DENIED"
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd "$APP/backend" && "$PY" -m pytest -q tests/test_auth_security.py`
Expected: FAIL na importação (`ImportError: cannot import name 'OidcLoginRequest'`).

- [ ] **Step 3: Novo topo de `backend/app/models/auth.py` (linhas 1–164)**

```python
"""
Modelos de identidade local, sessões, conversas, uso da IA e auditoria.

Perfis e permissões moram no Keycloak (papéis do client chat-bot-om-bff). O app
guarda só o registro de identidade (issuer + subject) e, na sessão, o retrato
dos papéis recebidos no token assinado.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


# ─── Usuário da aplicação (registro de identidade) ────────────────────────────

class AppUser(Base):
    __tablename__ = "app_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Informativo (vem do token) e pode repetir: a âncora é oidc_identities (issuer + subject).
    email: Mapped[str] = mapped_column(String(255), nullable=False, default="", index=True)
    username: Mapped[str | None] = mapped_column(String(150), nullable=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    # Perfis vistos no último login/renovação: exibição e limites de IA. Não concede acesso.
    last_profiles: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    oidc_identities: Mapped[list["OidcIdentity"]] = relationship(
        "OidcIdentity", back_populates="user", cascade="all, delete-orphan"
    )
    sessions: Mapped[list["UserSession"]] = relationship(
        "UserSession", back_populates="user", cascade="all, delete-orphan"
    )


# ─── Identidade OIDC ──────────────────────────────────────────────────────────

class OidcIdentity(Base):
    __tablename__ = "oidc_identities"
    __table_args__ = (UniqueConstraint("issuer", "subject"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False)
    issuer: Mapped[str] = mapped_column(String(512), nullable=False)
    subject: Mapped[str] = mapped_column(String(512), nullable=False)
    email_at_link: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["AppUser"] = relationship("AppUser", back_populates="oidc_identities")


# ─── Login em andamento ───────────────────────────────────────────────────────

class OidcLoginRequest(Base):
    """state (hash), code_verifier e nonce de um login em andamento. Uso único, validade curta."""

    __tablename__ = "oidc_login_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    state_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    code_verifier: Mapped[str] = mapped_column(String(128), nullable=False)
    nonce: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)


# ─── Sessões ──────────────────────────────────────────────────────────────────

class UserSession(Base):
    __tablename__ = "user_sessions"
    __table_args__ = (Index("ix_user_sessions_token_hash", "session_token_hash"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False)
    # Hash SHA-256 do token opaco — nunca o token em texto puro
    session_token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    csrf_secret: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)        # idle expiry
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # id_token do login, usado somente como id_token_hint no logout OIDC.
    # Nunca é enviado ao navegador fora do redirect de logout e é apagado na revogação.
    id_token_hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Sessão SSO do Keycloak (claim "sid"): alvo do backchannel logout.
    sid: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    # Refresh token cifrado (Fernet, SESSION_ENCRYPTION_KEY). Apagado na revogação.
    refresh_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Retrato do acesso: papéis do client chat-bot-om-bff recebidos no token.
    permissions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    profiles: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    snapshot_refreshed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    # Keycloak inacessível: início da falha e última tentativa de renovação.
    refresh_failed_since: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    refresh_attempted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["AppUser"] = relationship("AppUser", back_populates="sessions")
```

- [ ] **Step 4: Ajustar os imports de modelos em `backend/tests/conftest.py`**

Troque o bloco `from app.models.auth import (...)` por:

```python
from app.models.auth import (                   # noqa: F401
    AppUser, OidcIdentity, OidcLoginRequest, UserSession,
    AssistantConversation, AssistantMessage, AiUsage, AuditLog, SecurityEvent,
)
```

- [ ] **Step 5: Reescrever `backend/app/services/auth.py`**

```python
"""
Sessões server-side, identidade local, limites de IA e auditoria.

Quem pode o quê é decidido no Keycloak (papéis do client chat-bot-om-bff). Aqui
guardamos apenas o retrato recebido no token assinado e o refresh token cifrado.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit, urlunsplit

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core import config
from app.models.auth import (
    AiUsage,
    AppUser,
    AuditLog,
    OidcIdentity,
    OidcLoginRequest,
    SecurityEvent,
    UserSession,
)
from app.services.permissions import RoleSnapshot, ai_limits_for

if TYPE_CHECKING:
    from app.services.oidc import TokenSet


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


# ─── Cifra do refresh token ───────────────────────────────────────────────────

def _fernet() -> Fernet:
    if not config.SESSION_ENCRYPTION_KEY:
        raise RuntimeError("SESSION_ENCRYPTION_KEY não configurada.")
    return Fernet(config.SESSION_ENCRYPTION_KEY.encode())


def encrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        return None


# ─── Login em andamento (state / code_verifier / nonce) ───────────────────────

def create_login_request(db: Session) -> tuple[str, str, str]:
    """Cria o registro de uso único do login. Retorna (state, code_verifier, nonce)."""
    now = datetime.utcnow()
    db.execute(delete(OidcLoginRequest).where(OidcLoginRequest.expires_at < now))
    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    nonce = secrets.token_urlsafe(32)
    db.add(OidcLoginRequest(
        state_hash=_sha256(state),
        code_verifier=code_verifier,
        nonce=nonce,
        created_at=now,
        expires_at=now + timedelta(seconds=config.OIDC_LOGIN_REQUEST_TTL_SECONDS),
    ))
    db.commit()
    return state, code_verifier, nonce


def consume_login_request(db: Session, state: str | None) -> tuple[str, str] | None:
    """Apaga o registro do ``state`` numa única instrução (uso único mesmo com
    requisições simultâneas). Retorna (code_verifier, nonce) se ainda válido."""
    if not state:
        return None
    row = db.execute(
        delete(OidcLoginRequest)
        .where(OidcLoginRequest.state_hash == _sha256(state))
        .returning(OidcLoginRequest.code_verifier, OidcLoginRequest.nonce, OidcLoginRequest.expires_at)
    ).first()
    db.commit()
    if row is None or row.expires_at < datetime.utcnow():
        return None
    return row.code_verifier, row.nonce


# ─── Identidade local ─────────────────────────────────────────────────────────

def upsert_user(db: Session, claims: dict, *, profiles: tuple[str, ...] | list[str]) -> AppUser:
    """Localiza ou cria o registro local pela âncora issuer + subject.

    Nunca vincula por e-mail: uma conta recriada no Keycloak (novo subject) vira
    um registro novo, sem herdar conversas nem auditoria do anterior.
    """
    now = datetime.utcnow()
    email = (claims.get("email") or "").strip().lower()
    username = (claims.get("preferred_username") or "").strip().lower() or None
    display_name = (claims.get("name") or username or email or claims["sub"])[:200]

    identity = db.scalar(
        select(OidcIdentity)
        .where(OidcIdentity.issuer == claims["iss"])
        .where(OidcIdentity.subject == claims["sub"])
    )
    if identity is None:
        user = AppUser(email=email, created_at=now)
        db.add(user)
        db.flush()
        identity = OidcIdentity(user_id=user.id, issuer=claims["iss"], subject=claims["sub"],
                                email_at_link=email, created_at=now)
        db.add(identity)
    else:
        user = db.get(AppUser, identity.user_id)

    user.email = email
    user.username = username
    user.display_name = display_name
    user.last_profiles = list(profiles)
    user.last_seen_at = now
    identity.last_seen_at = now
    db.flush()
    return user


# ─── Sessões ──────────────────────────────────────────────────────────────────

def create_session(
    db: Session,
    user: AppUser,
    *,
    tokens: "TokenSet",
    snapshot: RoleSnapshot,
    ip: str | None = None,
    ua: str | None = None,
) -> str:
    """Cria a sessão server-side e devolve o token opaco do cookie (sem commit)."""
    token = secrets.token_urlsafe(32)
    now = datetime.utcnow()
    sid = (tokens.id_claims or {}).get("sid") or tokens.access_claims.get("sid")
    db.add(UserSession(
        user_id=user.id,
        session_token_hash=_sha256(token),
        csrf_secret=secrets.token_urlsafe(32),
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(minutes=config.SESSION_IDLE_TIMEOUT_MINUTES),
        absolute_expires_at=now + timedelta(hours=config.SESSION_ABSOLUTE_TIMEOUT_HOURS),
        ip_hash=_sha256(ip) if ip else None,
        user_agent_hash=_sha256(ua) if ua else None,
        id_token_hint=tokens.id_token,
        sid=sid,
        refresh_token_enc=encrypt_secret(tokens.refresh_token),
        permissions=sorted(snapshot.permissions),
        profiles=list(snapshot.profiles),
        snapshot_refreshed_at=now,
    ))
    db.flush()
    return token


def get_session(db: Session, token: str) -> UserSession | None:
    session = db.scalar(select(UserSession).where(UserSession.session_token_hash == _sha256(token)))
    if session is None or session.revoked_at is not None:
        return None
    now = datetime.utcnow()
    if now > session.expires_at or now > session.absolute_expires_at:
        return None
    return session


def touch_session(db: Session, session: UserSession) -> None:
    """Atualiza last_seen e a expiração ociosa, no máximo uma vez por minuto."""
    now = datetime.utcnow()
    if (now - session.last_seen_at).total_seconds() > 60:
        session.last_seen_at = now
        session.expires_at = now + timedelta(minutes=config.SESSION_IDLE_TIMEOUT_MINUTES)
        db.commit()


def revoke_session(db: Session, session: UserSession) -> None:
    session.revoked_at = datetime.utcnow()
    session.id_token_hint = None
    session.refresh_token_enc = None
    db.flush()


def revoke_sessions_for_logout(db: Session, *, issuer: str, sid: str | None, subject: str | None) -> int:
    """Backchannel logout: revoga as sessões do ``sid`` (ou, sem sid, todas do ``subject``)."""
    query = select(UserSession).where(UserSession.revoked_at.is_(None))
    if sid:
        query = query.where(UserSession.sid == sid)
    else:
        query = (query.join(OidcIdentity, OidcIdentity.user_id == UserSession.user_id)
                 .where(OidcIdentity.issuer == issuer, OidcIdentity.subject == subject))
    sessions = db.scalars(query).all()
    for session in sessions:
        revoke_session(db, session)
    return len(sessions)


def post_logout_redirect_uri() -> str:
    """URI de retorno após o logout — sempre a página ``/login`` do frontend."""
    parts = urlsplit(config.OIDC_POST_LOGOUT_REDIRECT_URI)
    if parts.path in ("", "/"):
        parts = parts._replace(path="/login")
    return urlunsplit(parts)


# ─── Limites de IA ────────────────────────────────────────────────────────────

def get_ai_limits(user: AppUser) -> tuple[int, int]:
    """(diário, por minuto): o maior limite entre os perfis vistos no último token."""
    return ai_limits_for(user.last_profiles or [])


def check_ai_rate_limit(db: Session, user: AppUser) -> dict[str, Any]:
    """
    Verifica limites de IA. Retorna:
    {"allowed": bool, "used_today": int, "daily_limit": int,
     "used_this_minute": int, "per_minute_limit": int,
     "resets_at": str, "reason": str | None}
    """
    daily_limit, per_min_limit = get_ai_limits(user)
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    minute_start = now - timedelta(seconds=60)

    def _count(since: datetime) -> int:
        return db.scalar(
            select(func.count(AiUsage.id))
            .where(AiUsage.user_id == user.id)
            .where(AiUsage.created_at >= since)
            .where(AiUsage.status != "error")
        ) or 0

    used_today = _count(today_start)
    used_this_minute = _count(minute_start)
    result = {
        "allowed": True,
        "used_today": used_today,
        "daily_limit": daily_limit,
        "used_this_minute": used_this_minute,
        "per_minute_limit": per_min_limit,
        "resets_at": (today_start + timedelta(days=1)).isoformat(),
        "reason": None,
    }
    if used_today >= daily_limit:
        result.update(allowed=False, reason="daily_limit")
    elif used_this_minute >= per_min_limit:
        result.update(allowed=False, reason="per_minute_limit",
                      resets_at=(now + timedelta(seconds=60)).isoformat())
    return result


# ─── Auditoria ────────────────────────────────────────────────────────────────

def record_audit(
    db: Session,
    *,
    user_id: int | None,
    action: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    store_id: int | None = None,
    old_values: dict | None = None,
    new_values: dict | None = None,
    metadata: dict | None = None,
) -> None:
    db.add(AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        store_id=store_id,
        old_values=old_values,
        new_values=new_values,
        metadata_=metadata,
    ))
    db.flush()


def record_security_event(
    db: Session,
    *,
    event_type: str,
    severity: str = "medium",
    user_id: int | None = None,
    metadata: dict | None = None,
) -> None:
    db.add(SecurityEvent(
        user_id=user_id,
        event_type=event_type,
        severity=severity,
        metadata_=metadata,
    ))
    db.flush()
```

- [ ] **Step 6: Criar `backend/scripts/reset_identity.sql`**

```sql
-- Recria SOMENTE identidade e acesso do Chat-bot O&M (spec, seção 7).
-- Chamados (services, uploads), Central de Ativos e n8n NÃO são tocados.
-- Rode com o backend parado; ele recria as tabelas no formato novo ao iniciar.
BEGIN;
DROP TABLE IF EXISTS
    user_permission_overrides,
    profile_permissions,
    permissions,
    profiles,
    user_sessions,
    oidc_identities,
    ai_usage,
    assistant_messages,
    assistant_conversations,
    audit_logs,
    security_events,
    app_users
    CASCADE;
DROP TYPE IF EXISTS override_effect;
DROP TYPE IF EXISTS message_role;
COMMIT;
```

- [ ] **Step 7: Rodar e ver passar**

Run: `cd "$APP/backend" && "$PY" -m pytest -q tests/test_auth_security.py tests/test_oidc.py tests/test_permissions.py`
Expected: `70 passed` (25 de `test_auth_security.py`, contando os 2 casos parametrizados, + 45).

- [ ] **Step 8: Commit**

```bash
cd "$APP" && git add backend/app/models/auth.py backend/app/services/auth.py backend/scripts/reset_identity.sql backend/tests/conftest.py backend/tests/test_auth_security.py
git commit -m "refactor(auth): sessão com retrato do Keycloak e refresh token cifrado

Remove perfis, permissões e overrides do banco; identidade só por issuer+subject.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Renovação do retrato e dependências da API

**Files:**
- Create: `backend/app/services/session_refresh.py`
- Rewrite: `backend/app/api/dependencies.py`
- Test: `backend/tests/test_session_refresh.py`

**Interfaces:**
- Consumes:
  - `app.services.oidc`: `refresh`, `roles_from_access_claims`, `revoke_refresh_token`, `issuer`, `OidcError`, `OidcUnavailable`;
  - `app.services.auth`: `decrypt_secret`, `encrypt_secret`, `revoke_session`, `record_security_event`, `get_session`, `touch_session`;
  - `snapshot_from_roles`.
- Produces:
  - `session_refresh.ensure_fresh_snapshot(db, session) -> UserSession`, `session_refresh.SessionRevoked(reason)`, `session_refresh.REFRESH_RETRY_SECONDS = 30`.
  - `dependencies.get_valid_session`: sessão válida, sem renovar; usada por logout e CSRF.
  - `dependencies.get_current_session`: renova o retrato e responde 401 se a sessão cair.
  - `dependencies.get_current_user` e `dependencies.require_permission(code)`: a permissão vem do retrato da sessão.
  - `dependencies.verify_csrf`, `verificar_api_key` e `verificar_internal_api_key` mantêm a assinatura; `require_admin` deixa de existir.

- [ ] **Step 1: Escrever os testes `backend/tests/test_session_refresh.py`**

```python
"""Renovação do retrato de acesso da sessão (app/services/session_refresh.py)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models.auth import AppUser, SecurityEvent, UserSession
from app.services import auth
from app.services.permissions import snapshot_from_roles
from app.services.session_refresh import REFRESH_RETRY_SECONDS, SessionRevoked, ensure_fresh_snapshot
from tests.oidc_fake import ANALISTA, login_tokens

CONVIDADO = ["CONVIDADO", "assistant.use", "assistant.history", "indicators.view", "assets.view"]


def _login(db, provider, sub: str = "u1", roles=ANALISTA) -> UserSession:
    tokens = login_tokens(provider, sub, roles)
    snapshot = snapshot_from_roles(roles)
    user = auth.upsert_user(db, tokens.access_claims, profiles=snapshot.profiles)
    token = auth.create_session(db, user, tokens=tokens, snapshot=snapshot)
    db.commit()
    return auth.get_session(db, token)


def _age(db, session: UserSession, minutes: int = 6) -> None:
    session.snapshot_refreshed_at = datetime.utcnow() - timedelta(minutes=minutes)
    db.commit()


def _events(db, event_type: str) -> list[SecurityEvent]:
    return db.scalars(select(SecurityEvent).where(SecurityEvent.event_type == event_type)).all()


def test_retrato_recente_nao_chama_o_keycloak(db, provider):
    session = _login(db, provider)
    before = provider.token_requests
    assert ensure_fresh_snapshot(db, session) is session
    assert provider.token_requests == before


def test_retrato_vencido_renova_e_aplica_a_troca_de_perfil(db, provider):
    session = _login(db, provider)
    old_refresh = session.refresh_token_enc
    provider.roles_by_sub["u1"] = CONVIDADO
    _age(db, session)
    result = ensure_fresh_snapshot(db, session)
    assert result.profiles == ["CONVIDADO"]
    assert "assets.create" not in result.permissions and "assets.view" in result.permissions
    assert result.refresh_token_enc != old_refresh
    assert result.snapshot_refreshed_at > datetime.utcnow() - timedelta(minutes=1)
    assert db.get(AppUser, result.user_id).last_profiles == ["CONVIDADO"]


def test_renovacao_recusada_revoga_a_sessao(db, provider):
    session = _login(db, provider)
    provider.disabled_subs.add("u1")
    _age(db, session)
    with pytest.raises(SessionRevoked) as exc:
        ensure_fresh_snapshot(db, session)
    assert exc.value.reason == "invalid_grant"
    assert session.revoked_at is not None and session.refresh_token_enc is None
    assert len(_events(db, "SESSION_REVOKED")) == 1


def test_sem_permissao_no_keycloak_revoga_e_devolve_o_refresh_token(db, provider):
    session = _login(db, provider)
    provider.roles_by_sub["u1"] = []
    _age(db, session)
    with pytest.raises(SessionRevoked) as exc:
        ensure_fresh_snapshot(db, session)
    assert exc.value.reason == "access_removed"
    assert len(provider.revoked) == 1
    assert len(_events(db, "ACCESS_REMOVED")) == 1


def test_duas_abas_usam_o_refresh_token_uma_unica_vez(db, provider):
    session = _login(db, provider)
    _age(db, session)
    outra_conexao = sessionmaker(bind=db.get_bind(), autoflush=False)()
    aba_b = outra_conexao.get(UserSession, session.id)  # carregada antes da renovação da aba A
    before = provider.token_requests

    ensure_fresh_snapshot(db, session)                  # aba A renova
    result = ensure_fresh_snapshot(outra_conexao, aba_b)  # aba B ainda tem o retrato velho em memória

    assert provider.token_requests == before + 1
    assert result.revoked_at is None
    assert result.snapshot_refreshed_at > datetime.utcnow() - timedelta(minutes=1)
    outra_conexao.close()


def test_keycloak_fora_do_ar_mantem_o_retrato_e_limita_as_tentativas(db, provider):
    session = _login(db, provider)
    _age(db, session)
    provider.offline = True
    attempts = provider.attempts

    result = ensure_fresh_snapshot(db, session)
    assert result.revoked_at is None and result.refresh_failed_since is not None
    assert "assets.create" in result.permissions
    assert provider.attempts == attempts + 1

    for _ in range(3):
        ensure_fresh_snapshot(db, session)
    assert provider.attempts == attempts + 1  # no máximo 1 tentativa a cada 30 s

    session.refresh_attempted_at -= timedelta(seconds=REFRESH_RETRY_SECONDS + 1)
    db.commit()
    ensure_fresh_snapshot(db, session)
    assert provider.attempts == attempts + 2


def test_keycloak_fora_do_ar_por_15_minutos_encerra_a_sessao(db, provider):
    session = _login(db, provider)
    _age(db, session)
    provider.offline = True
    ensure_fresh_snapshot(db, session)
    session.refresh_failed_since = datetime.utcnow() - timedelta(minutes=15, seconds=1)
    db.commit()
    with pytest.raises(SessionRevoked) as exc:
        ensure_fresh_snapshot(db, session)
    assert exc.value.reason == "provider_unavailable"
    assert session.revoked_at is not None


def test_keycloak_de_volta_limpa_a_falha(db, provider):
    session = _login(db, provider)
    _age(db, session)
    provider.offline = True
    ensure_fresh_snapshot(db, session)
    provider.offline = False
    session.refresh_attempted_at -= timedelta(seconds=REFRESH_RETRY_SECONDS + 1)
    db.commit()
    result = ensure_fresh_snapshot(db, session)
    assert result.refresh_failed_since is None and result.refresh_attempted_at is None


def test_sessao_revogada_por_outra_requisicao_nao_renova(db, provider):
    session = _login(db, provider)
    _age(db, session)
    outra_conexao = sessionmaker(bind=db.get_bind(), autoflush=False)()
    auth.revoke_session(outra_conexao, outra_conexao.get(UserSession, session.id))
    outra_conexao.commit()
    outra_conexao.close()
    before = provider.token_requests
    with pytest.raises(SessionRevoked) as exc:
        ensure_fresh_snapshot(db, session)
    assert exc.value.reason == "revoked"
    assert provider.token_requests == before
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd "$APP/backend" && "$PY" -m pytest -q tests/test_session_refresh.py`
Expected: FAIL com `ModuleNotFoundError: No module named 'app.services.session_refresh'`.

- [ ] **Step 3: Implementar `backend/app/services/session_refresh.py`**

```python
"""
Renovação do retrato de acesso da sessão.

A cada OIDC_TOKEN_REFRESH_SECONDS o backend usa o refresh token (cifrado na
sessão) para obter novos tokens do Keycloak e atualizar permissões e perfis.
Uma trava por sessão (SELECT ... FOR UPDATE) garante que o refresh token, de
uso único, seja usado por uma só requisição.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import NoReturn

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import config
from app.models.auth import AppUser, OidcIdentity, UserSession
from app.services import oidc
from app.services.auth import decrypt_secret, encrypt_secret, record_security_event, revoke_session
from app.services.permissions import snapshot_from_roles

logger = logging.getLogger(__name__)

# Keycloak fora do ar: no máximo uma tentativa de renovação a cada 30 s por sessão.
REFRESH_RETRY_SECONDS = 30


class SessionRevoked(Exception):
    """A sessão foi encerrada durante a renovação."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _is_fresh(session: UserSession, now: datetime) -> bool:
    return now - session.snapshot_refreshed_at < timedelta(seconds=config.OIDC_TOKEN_REFRESH_SECONDS)


def _retry_throttled(session: UserSession, now: datetime) -> bool:
    return (session.refresh_failed_since is not None and session.refresh_attempted_at is not None
            and now - session.refresh_attempted_at < timedelta(seconds=REFRESH_RETRY_SECONDS))


def _revoke(db: Session, session: UserSession, reason: str) -> NoReturn:
    revoke_session(db, session)
    record_security_event(
        db,
        event_type="ACCESS_REMOVED" if reason == "access_removed" else "SESSION_REVOKED",
        severity="medium",
        user_id=session.user_id,
        metadata={"reason": reason},
    )
    db.commit()
    raise SessionRevoked(reason)


def _enforce_grace(db: Session, session: UserSession, now: datetime) -> None:
    started = session.refresh_failed_since
    if started is not None and now - started >= timedelta(minutes=config.OIDC_OFFLINE_GRACE_MINUTES):
        _revoke(db, session, "provider_unavailable")


def ensure_fresh_snapshot(db: Session, session: UserSession) -> UserSession:
    """Devolve a sessão com o retrato em dia ou levanta ``SessionRevoked``."""
    now = datetime.utcnow()
    if _is_fresh(session, now):
        return session
    if _retry_throttled(session, now):
        _enforce_grace(db, session, now)
        return session

    locked = db.scalar(
        select(UserSession)
        .where(UserSession.id == session.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if locked is None or locked.revoked_at is not None:
        db.commit()
        raise SessionRevoked("revoked")
    if _is_fresh(locked, now):
        db.commit()  # outra requisição renovou enquanto esperávamos: libera a trava
        return locked
    if _retry_throttled(locked, now):
        _enforce_grace(db, locked, now)
        db.commit()
        return locked

    refresh_token = decrypt_secret(locked.refresh_token_enc)
    subject = db.scalar(
        select(OidcIdentity.subject)
        .where(OidcIdentity.user_id == locked.user_id, OidcIdentity.issuer == oidc.issuer())
    )
    if not refresh_token or not subject:
        _revoke(db, locked, "refresh_token_missing")

    try:
        tokens = oidc.refresh(refresh_token, expected_sub=subject)
    except oidc.OidcUnavailable:
        locked.refresh_failed_since = locked.refresh_failed_since or now
        locked.refresh_attempted_at = now
        _enforce_grace(db, locked, now)
        db.commit()
        logger.warning("SESSÃO %s: Keycloak indisponível; retrato atual mantido.", locked.id)
        return locked
    except oidc.OidcError as exc:
        _revoke(db, locked, exc.code)

    snapshot = snapshot_from_roles(oidc.roles_from_access_claims(tokens.access_claims))
    if not snapshot.has_access:
        oidc.revoke_refresh_token(tokens.refresh_token)
        _revoke(db, locked, "access_removed")

    locked.refresh_token_enc = encrypt_secret(tokens.refresh_token)
    if tokens.id_token:
        locked.id_token_hint = tokens.id_token
    locked.permissions = sorted(snapshot.permissions)
    locked.profiles = list(snapshot.profiles)
    locked.snapshot_refreshed_at = now
    locked.refresh_failed_since = None
    locked.refresh_attempted_at = None
    user = db.get(AppUser, locked.user_id)
    if user is not None:
        user.last_profiles = list(snapshot.profiles)
    db.commit()
    return locked
```

- [ ] **Step 4: Rodar e ver passar**

Run: `cd "$APP/backend" && "$PY" -m pytest -q tests/test_session_refresh.py tests/test_auth_security.py tests/test_oidc.py tests/test_permissions.py`
Expected: `79 passed` (9 + 70).

- [ ] **Step 5: Reescrever `backend/app/api/dependencies.py`**

Mantenha sem alteração as funções `verificar_api_key` e `verificar_internal_api_key` (e seus comentários). Troque os imports do topo e todo o conteúdo a partir de `# ─── Sessão / usuário autenticado` por:

```python
"""
Dependências compartilhadas da API.
"""

from __future__ import annotations

import secrets

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import API_KEY, INTERNAL_API_KEY, SESSION_COOKIE_NAME
from app.db.session import get_db
from app.models.auth import AppUser, UserSession
from app.services.auth import get_session, record_security_event, touch_session
from app.services.session_refresh import SessionRevoked, ensure_fresh_snapshot
```

```python
# ─── Sessão / usuário autenticado ────────────────────────────────────────────

def _extract_token(request: Request) -> str | None:
    return request.cookies.get(SESSION_COOKIE_NAME)


def get_valid_session(request: Request, db: Session = Depends(get_db)) -> UserSession:
    """Sessão válida pelo cookie, sem renovar o retrato (logout e CSRF)."""
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Não autenticado.")
    session = get_session(db, token)
    if session is None:
        record_security_event(
            db,
            event_type="SESSION_EXPIRED",
            severity="low",
            metadata={"path": str(request.url.path)},
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sessão expirada ou inválida.")
    return session


def get_current_session(
    session: UserSession = Depends(get_valid_session),
    db: Session = Depends(get_db),
) -> UserSession:
    """Sessão com o retrato de acesso em dia (renovado no Keycloak a cada 5 min)."""
    try:
        session = ensure_fresh_snapshot(db, session)
    except SessionRevoked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão encerrada. Entre novamente.",
        ) from None
    touch_session(db, session)
    return session


def get_current_user(
    session: UserSession = Depends(get_current_session),
    db: Session = Depends(get_db),
) -> AppUser:
    user = db.get(AppUser, session.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário não encontrado.")
    return user


# ─── Permissões ───────────────────────────────────────────────────────────────

def require_permission(permission_code: str):
    """
    Factory de dependência. A permissão vem do retrato da sessão, isto é, dos
    papéis do client chat-bot-om-bff no token assinado pelo Keycloak.

    Uso:
        @router.get("/...", dependencies=[Depends(require_permission("assets.view"))])
    """
    def _checker(
        request: Request,
        session: UserSession = Depends(get_current_session),
        db: Session = Depends(get_db),
    ) -> None:
        if permission_code not in (session.permissions or []):
            record_security_event(
                db,
                event_type="ACCESS_DENIED",
                severity="medium",
                user_id=session.user_id,
                metadata={"permission": permission_code, "path": str(request.url.path)},
            )
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permissão necessária: {permission_code}",
            )
    return _checker


# ─── CSRF ─────────────────────────────────────────────────────────────────────

def verify_csrf(
    request: Request,
    x_csrf_token: str = Header(default="", alias="x-csrf-token"),
    session: UserSession = Depends(get_valid_session),
    db: Session = Depends(get_db),
) -> None:
    """
    Valida CSRF para métodos mutáveis (POST/PUT/PATCH/DELETE).
    GETs são ignorados.
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    if not secrets.compare_digest(x_csrf_token, session.csrf_secret):
        record_security_event(
            db,
            event_type="CSRF_REJECTED",
            severity="high",
            user_id=session.user_id,
            metadata={"path": str(request.url.path)},
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token CSRF inválido ou ausente.",
        )
```

- [ ] **Step 6: Conferir que o módulo importa**

Run: `cd "$APP/backend" && DATABASE_URL=sqlite:// "$PY" -c "import app.api.dependencies; print('ok')"`
Expected: `ok`.

- [ ] **Step 7: Commit**

```bash
cd "$APP" && git add backend/app/services/session_refresh.py backend/app/api/dependencies.py backend/tests/test_session_refresh.py
git commit -m "feat(auth): renova o retrato no Keycloak a cada 5 min com trava por sessão

Permissões por rota passam a vir do retrato da sessão; require_admin sai.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Rotas de autenticação, consulta de usuários e limpeza do modelo antigo

**Files:**
- Create: `backend/tests/api_harness.py` (harness que hoje está no topo de `test_api_security.py`)
- Modify: `backend/tests/test_api_security.py` (usa o harness; o teste do callback vai para `test_auth_flow.py`)
- Create: `backend/tests/test_auth_flow.py`
- Rewrite: `backend/app/api/routes/auth.py`, `backend/app/api/routes/users.py`
- Modify: `backend/app/main.py`, `backend/app/core/config.py`
- Delete: `backend/app/services/keycloak_admin.py`, `backend/app/services/user_admin.py`, `backend/app/db/schema_updates.py`, `backend/tests/test_user_management.py`

**Interfaces:**
- Consumes: tudo das Tasks 5–8.
- Produces (HTTP):
  - `GET /auth/login` e `GET /auth/register` → 302 para o Keycloak; com o provedor fora do ar, 302 para `/login?auth_error=provider_unavailable`.
  - `GET /auth/callback` → 302 para o frontend com cookie, ou para `/login?auth_error=invalid_state|provider_error|token_exchange|provider_unavailable`; sem papel do app, 302 para o logout OIDC que volta em `/login?auth_error=not_released`.
  - `GET /auth/me` → campos atuais **sem** `status`/`access_expires_at` e **com** `profiles` e `keycloak_console_url`.
  - `POST /auth/logout` → `{"logout_url": ...}`.
  - `POST /auth/backchannel-logout` (form `logout_token`) → 200 ou 400.
  - `GET /auth/usage` (igual).
  - `GET /users` (exige `users.view`) → lista de `{id, display_name, email, username, profile, profiles, last_seen_at, created_at, active_session}`.
- Produces (testes): `tests.api_harness` com `fastapi_app`, `TestSession`, `test_engine`, `SESSION_COOKIE`, `INTERNAL_KEY`, `reset_database()` e `seed_session(permissions, profiles=("ANALISTA",), email="api@test.com") -> (token, csrf)`.

- [ ] **Step 1: Criar `backend/tests/api_harness.py`**

```python
"""
Harness do TestClient: SQLite em memória no lugar do PostgreSQL.

Importe este módulo antes de qualquer import de ``app.main``: ele define o
ambiente de teste e troca o engine do banco. O OIDC fica desligado por padrão;
os testes de fluxo instalam o Keycloak simulado com a fixture ``provider``.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_api.db")
os.environ.setdefault("INTERNAL_API_KEY", "test-internal-key-xyz")
os.environ.setdefault("API_KEY", "test-api-key-xyz")
os.environ.setdefault("OIDC_ISSUER_URL", "")
os.environ.setdefault("SESSION_SECRET", "test-secret")
os.environ.setdefault("FRONTEND_ORIGINS", "http://localhost:5173")
os.environ.setdefault("TAPE_SYNC_SCHEDULE_ENABLED", "false")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

import app.db.session as _db_session  # noqa: E402

_db_session.engine = test_engine
_db_session.SessionLocal = TestSession

import app.api.routes.health as _health  # noqa: E402
import app.models.asset_store  # noqa: F401,E402
import app.models.auth  # noqa: F401,E402
import app.models.climate_asset  # noqa: F401,E402
import app.models.fire_asset  # noqa: F401,E402
import app.models.service  # noqa: F401,E402
import app.models.store_document  # noqa: F401,E402
import app.models.upload  # noqa: F401,E402
import app.models.water_asset  # noqa: F401,E402
from app.core import config  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.models.auth import AppUser, UserSession  # noqa: E402

_health.engine = test_engine
# Independe do .env local: OIDC desligado até um teste instalar o provedor simulado.
config.OIDC_ISSUER_URL = ""

SESSION_COOKIE = "om_session"
INTERNAL_KEY = os.environ["INTERNAL_API_KEY"]


def _override_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


fastapi_app.dependency_overrides[get_db] = _override_db


def reset_database() -> None:
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)


def seed_session(permissions, profiles=("ANALISTA",), email: str = "api@test.com") -> tuple[str, str]:
    """Usuário + sessão com retrato em dia (não consulta o Keycloak). Retorna (token, csrf)."""
    db = TestSession()
    try:
        user = AppUser(email=email, display_name="API Test", last_profiles=list(profiles))
        db.add(user)
        db.flush()
        token, csrf, now = secrets.token_urlsafe(32), secrets.token_urlsafe(32), datetime.utcnow()
        db.add(UserSession(
            user_id=user.id, session_token_hash=hashlib.sha256(token.encode()).hexdigest(),
            csrf_secret=csrf, created_at=now, last_seen_at=now,
            expires_at=now + timedelta(hours=1), absolute_expires_at=now + timedelta(hours=8),
            permissions=sorted(permissions), profiles=list(profiles), snapshot_refreshed_at=now,
        ))
        db.commit()
        return token, csrf
    finally:
        db.close()
```

- [ ] **Step 2: Trocar o topo de `backend/tests/test_api_security.py` (linhas 1–124) pelo harness**

```python
"""
Testes de segurança via TestClient (harness em tests/api_harness.py).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.api_harness import INTERNAL_KEY, SESSION_COOKIE, fastapi_app, reset_database, seed_session
from tests.oidc_fake import ANALISTA

ANALISTA_PERMISSIONS = [role for role in ANALISTA if role != "ANALISTA"]


@pytest.fixture(autouse=True)
def clean():
    reset_database()
    yield
    reset_database()


@pytest.fixture
def client():
    with TestClient(fastapi_app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def authed():
    token, csrf = seed_session(ANALISTA_PERMISSIONS)
    with TestClient(fastapi_app, raise_server_exceptions=False) as c:
        c.cookies.set(SESSION_COOKIE, token)
        c._csrf = csrf
        yield c
```

Depois, apague o método `test_callback_define_cookie_na_resposta_302` da classe `TestAuthEndpoints` (o comportamento passa a ser testado em `test_auth_flow.py`). As demais classes ficam iguais.

- [ ] **Step 3: Escrever `backend/tests/test_auth_flow.py`**

```python
"""Fluxo OIDC completo no backend, com o Keycloak simulado (tests/oidc_fake.py)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core import config
from app.models.auth import AppUser, OidcLoginRequest, SecurityEvent, UserSession
from tests.api_harness import TestSession, fastapi_app, reset_database
from tests.oidc_fake import ADMINISTRADOR, ANALISTA, CLIENT_ID, ISSUER, authorization_params

FRONTEND = "http://localhost:5173"
CONVIDADO = ["CONVIDADO", "assistant.use", "assistant.history", "indicators.view", "assets.view"]


@pytest.fixture(autouse=True)
def clean():
    reset_database()
    yield
    reset_database()


@pytest.fixture
def client(provider):
    with TestClient(fastapi_app, raise_server_exceptions=False) as c:
        yield c


def _start(client, path: str = "/auth/login") -> dict:
    r = client.get(path, follow_redirects=False)
    assert r.status_code == 302
    return authorization_params(r.headers["location"])


def _login(client, provider, *, sub: str = "u1", roles=ANALISTA, sid: str | None = None):
    params = _start(client)
    code = provider.issue_code(sub, roles, nonce=params["nonce"], code_challenge=params["code_challenge"], sid=sid)
    r = client.get(f"/auth/callback?code={code}&state={params['state']}", follow_redirects=False)
    return r, params, code


def _count(model, *where) -> int:
    query = select(func.count()).select_from(model)
    if where:
        query = query.where(*where)
    with TestSession() as db:
        return db.scalar(query)


def _age_snapshots() -> None:
    with TestSession() as db:
        for session in db.scalars(select(UserSession)):
            session.snapshot_refreshed_at = datetime.utcnow() - timedelta(minutes=6)
        db.commit()


def _csrf(client) -> str:
    return client.get("/auth/me").json()["csrf_token"]


# ── Início do login ───────────────────────────────────────────────────────────

def test_login_redireciona_com_pkce_nonce_e_state(client):
    params = _start(client)
    assert params["code_challenge_method"] == "S256" and params["code_challenge"]
    assert params["nonce"] and params["state"] and "prompt" not in params
    assert _count(OidcLoginRequest) == 1


def test_cadastro_abre_o_keycloak_com_prompt_create(client):
    assert _start(client, "/auth/register")["prompt"] == "create"


def test_login_com_keycloak_fora_do_ar_volta_ao_login(client, provider):
    provider.offline = True
    r = client.get("/auth/login", follow_redirects=False)
    assert r.headers["location"] == f"{FRONTEND}/login?auth_error=provider_unavailable"


# ── Callback ──────────────────────────────────────────────────────────────────

def test_callback_cria_sessao_com_cookie_seguro_e_sem_tokens_no_navegador(client, provider):
    r, _, _ = _login(client, provider)
    assert r.status_code == 302 and r.headers["location"] == FRONTEND
    assert r.headers["cache-control"] == "no-store"
    cookie = r.headers["set-cookie"]
    assert "om_session=" in cookie and "HttpOnly" in cookie and "Path=/" in cookie and "SameSite=lax" in cookie

    me = client.get("/auth/me").json()
    assert set(me) == {"id", "email", "username", "display_name", "profile", "profile_display", "profiles",
                       "permissions", "csrf_token", "keycloak_console_url", "ai_usage"}
    assert me["profile"] == "ANALISTA" and me["profile_display"] == "Analista"
    assert me["profiles"] == ["ANALISTA"] and "assets.create" in me["permissions"]
    assert me["keycloak_console_url"] is None


def test_quem_tem_users_view_recebe_o_link_do_console(client, provider, monkeypatch):
    monkeypatch.setattr(config, "KEYCLOAK_CONSOLE_URL", "http://kc.test/admin/gentil-dev/console/")
    _login(client, provider, sub="adm", roles=ADMINISTRADOR)
    me = client.get("/auth/me").json()
    assert me["profile"] == "ADMINISTRADOR"
    assert me["keycloak_console_url"] == "http://kc.test/admin/gentil-dev/console/"


def test_replay_do_callback_nao_cria_segunda_sessao(client, provider):
    _, params, code = _login(client, provider)
    r = client.get(f"/auth/callback?code={code}&state={params['state']}", follow_redirects=False)
    assert r.headers["location"] == f"{FRONTEND}/login?auth_error=invalid_state"
    assert _count(UserSession) == 1


def test_state_desconhecido_e_recusado(client):
    r = client.get("/auth/callback?code=x&state=nao-existe", follow_redirects=False)
    assert r.headers["location"] == f"{FRONTEND}/login?auth_error=invalid_state"
    assert _count(UserSession) == 0


def test_erro_do_provedor_consome_o_state(client, provider):
    params = _start(client)
    r = client.get(f"/auth/callback?error=access_denied&state={params['state']}", follow_redirects=False)
    assert r.headers["location"] == f"{FRONTEND}/login?auth_error=provider_error"
    code = provider.issue_code("u1", ANALISTA, nonce=params["nonce"], code_challenge=params["code_challenge"])
    r = client.get(f"/auth/callback?code={code}&state={params['state']}", follow_redirects=False)
    assert r.headers["location"] == f"{FRONTEND}/login?auth_error=invalid_state"


def test_nonce_divergente_nao_cria_sessao(client, provider):
    params = _start(client)
    code = provider.issue_code("u1", ANALISTA, nonce="outro", code_challenge=params["code_challenge"])
    r = client.get(f"/auth/callback?code={code}&state={params['state']}", follow_redirects=False)
    assert r.headers["location"] == f"{FRONTEND}/login?auth_error=token_exchange"
    assert _count(UserSession) == 0


def test_conta_sem_perfil_nao_cria_sessao_e_encerra_o_sso(client, provider):
    r, _, _ = _login(client, provider, roles=[])
    location = r.headers["location"]
    assert location.startswith(ISSUER + "/protocol/openid-connect/logout?")
    params = authorization_params(location)
    assert params["post_logout_redirect_uri"] == f"{FRONTEND}/login?auth_error=not_released"
    assert params["client_id"] == CLIENT_ID and params["id_token_hint"]
    assert "set-cookie" not in r.headers
    assert _count(UserSession) == 0 and _count(AppUser) == 1
    assert len(provider.revoked) == 1


def test_keycloak_fora_do_ar_no_callback(client, provider):
    params = _start(client)
    code = provider.issue_code("u1", ANALISTA, nonce=params["nonce"], code_challenge=params["code_challenge"])
    provider.offline = True
    r = client.get(f"/auth/callback?code={code}&state={params['state']}", follow_redirects=False)
    assert r.headers["location"] == f"{FRONTEND}/login?auth_error=provider_unavailable"


# ── Renovação pelo uso da API ─────────────────────────────────────────────────

def test_troca_de_perfil_no_keycloak_vale_na_renovacao(client, provider):
    _login(client, provider)
    provider.roles_by_sub["u1"] = CONVIDADO
    _age_snapshots()
    assert client.get("/auth/me").json()["profile"] == "CONVIDADO"
    assert client.get("/assets/stores").status_code == 200
    assert client.get("/health").status_code == 403  # settings.view: Analista tinha, Convidado não


def test_acesso_retirado_no_keycloak_derruba_a_sessao(client, provider):
    _login(client, provider)
    provider.roles_by_sub["u1"] = []
    _age_snapshots()
    assert client.get("/auth/me").status_code == 401


# ── Logout ────────────────────────────────────────────────────────────────────

def test_logout_revoga_sessao_e_refresh_token(client, provider):
    _login(client, provider)
    r = client.post("/auth/logout", headers={"X-CSRF-Token": _csrf(client)})
    assert r.status_code == 200 and "Max-Age=0" in r.headers["set-cookie"]
    url = r.json()["logout_url"]
    assert url.startswith(ISSUER + "/protocol/openid-connect/logout?")
    params = authorization_params(url)
    assert params["post_logout_redirect_uri"] == f"{FRONTEND}/login" and params["id_token_hint"]
    assert len(provider.revoked) == 1
    assert _count(UserSession, UserSession.revoked_at.is_(None)) == 0


# ── Backchannel logout ────────────────────────────────────────────────────────

def _backchannel(client, token: str):
    cookies = dict(client.cookies)
    client.cookies.clear()  # chamada servidor a servidor: sem cookie nem CSRF
    try:
        return client.post("/auth/backchannel-logout", data={"logout_token": token})
    finally:
        for name, value in cookies.items():
            client.cookies.set(name, value)


def test_backchannel_com_sid_derruba_a_sessao_na_hora(client, provider):
    _login(client, provider, sid="sid-x")
    r = _backchannel(client, provider.sign(provider.logout_claims(sid="sid-x")))
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert client.get("/auth/me").status_code == 401


def test_backchannel_so_com_sub_derruba_todas_as_sessoes(client, provider):
    _login(client, provider, sid="sid-a")
    _login(client, provider, sid="sid-b")
    assert _backchannel(client, provider.sign(provider.logout_claims(sub="u1"))).status_code == 200
    assert _count(UserSession, UserSession.revoked_at.is_(None)) == 0


def test_backchannel_de_sessao_desconhecida_responde_200_sem_efeito(client, provider):
    _login(client, provider, sid="sid-x")
    assert _backchannel(client, provider.sign(provider.logout_claims(sid="sid-outra"))).status_code == 200
    assert client.get("/auth/me").status_code == 200
    assert _count(SecurityEvent, SecurityEvent.event_type == "BACKCHANNEL_LOGOUT_REJECTED") == 0


def test_logout_token_invalido_e_recusado(client, provider):
    _login(client, provider, sid="sid-x")
    for token in ("invalido", "", provider.sign(provider.logout_claims(sid="sid-x", nonce="n"))):
        assert _backchannel(client, token).status_code == 400
    assert client.get("/auth/me").status_code == 200
    assert _count(SecurityEvent, SecurityEvent.event_type == "BACKCHANNEL_LOGOUT_REJECTED") == 3


# ── Consulta de usuários ──────────────────────────────────────────────────────

def test_users_exige_users_view(client, provider):
    _login(client, provider)
    assert client.get("/users").status_code == 403


def test_users_somente_leitura_para_quem_tem_users_view(client, provider):
    with TestSession() as db:
        db.add(AppUser(email="nova@exemplo.local", display_name="Conta Nova", last_profiles=[]))
        db.commit()
    _login(client, provider, sub="adm", roles=ADMINISTRADOR)
    users = {u["email"]: u for u in client.get("/users").json()}
    assert users["adm@exemplo.local"]["profile"] == "ADMINISTRADOR"
    assert users["adm@exemplo.local"]["active_session"] is True
    assert users["nova@exemplo.local"]["profile"] is None
    assert users["nova@exemplo.local"]["active_session"] is False
    assert users["adm@exemplo.local"]["last_seen_at"].endswith("Z")
    assert client.post("/users", json={}, headers={"X-CSRF-Token": _csrf(client)}).status_code == 405


# ── Subida do backend ─────────────────────────────────────────────────────────

def test_backend_nao_sobe_sem_chave_de_sessao_valida(provider, monkeypatch):
    monkeypatch.setattr(config, "SESSION_ENCRYPTION_KEY", "invalida")
    with pytest.raises(RuntimeError, match="SESSION_ENCRYPTION_KEY"):
        with TestClient(fastapi_app):
            pass
```

- [ ] **Step 4: Rodar e ver falhar**

Run: `cd "$APP/backend" && "$PY" -m pytest -q tests/test_auth_flow.py tests/test_api_security.py`
Expected: FAIL na coleta com `ImportError` (as rotas ainda importam `check_user_active`, `require_admin` etc.).

- [ ] **Step 5: Reescrever `backend/app/api/routes/auth.py`**

```python
"""
Rotas de autenticação — BFF para o fluxo OIDC com o Keycloak.

O navegador NUNCA recebe access_token nem refresh_token: troca de código,
renovação e revogação acontecem aqui. Perfis e permissões vêm dos papéis do
client chat-bot-om-bff no token assinado.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_session, get_current_user, get_valid_session, verify_csrf
from app.core import config
from app.core.config import FRONTEND_ORIGINS, SESSION_COOKIE_NAME, SESSION_COOKIE_SECURE
from app.db.session import get_db
from app.models.auth import AppUser, UserSession
from app.services import oidc
from app.services.auth import (
    check_ai_rate_limit,
    consume_login_request,
    create_login_request,
    create_session,
    decrypt_secret,
    post_logout_redirect_uri,
    record_audit,
    record_security_event,
    revoke_session,
    revoke_sessions_for_logout,
    upsert_user,
)
from app.services.permissions import PROFILE_DISPLAY, primary_profile, snapshot_from_roles

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])

_FRONTEND_ORIGIN = FRONTEND_ORIGINS[0] if FRONTEND_ORIGINS else "http://localhost:5173"
_NO_STORE = {"Cache-Control": "no-store"}


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=SESSION_COOKIE_SECURE,
        path="/",
        max_age=None,  # session cookie
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=SESSION_COOKIE_NAME, httponly=True, samesite="lax", path="/")


def _login_page_url(auth_error: str | None = None) -> str:
    url = f"{_FRONTEND_ORIGIN.rstrip('/')}/login"
    return f"{url}?auth_error={auth_error}" if auth_error else url


def _redirect_auth_error(code: str) -> RedirectResponse:
    return RedirectResponse(url=_login_page_url(code), status_code=302, headers=_NO_STORE)


def _redirect_denied_after_login(code: str, id_token: str | None) -> RedirectResponse:
    """Encerra a sessão SSO recém-criada no Keycloak e volta para /login?auth_error=<code>.

    Assim a conta autenticada, mas sem papel do app, não fica com sessão pela
    metade e o próximo "Entrar" pede as credenciais de novo.
    """
    target = _login_page_url(code)
    try:
        url = oidc.end_session_url(id_token_hint=id_token, post_logout_redirect_uri=target)
    except oidc.OidcError:
        url = target
    return RedirectResponse(url=url, status_code=302, headers=_NO_STORE)


def _login_failed(db: Session, reason: str, severity: str = "high", **metadata) -> None:
    record_security_event(db, event_type="LOGIN_FAILED", severity=severity,
                          metadata={"reason": reason, **metadata})
    db.commit()


def _start_login(db: Session, *, register: bool) -> RedirectResponse:
    if not oidc.is_configured():
        return _redirect_auth_error("provider_unavailable")
    state, code_verifier, nonce = create_login_request(db)
    try:
        url = oidc.authorization_url(state=state, nonce=nonce, code_verifier=code_verifier, register=register)
    except oidc.OidcError as exc:
        logger.warning("LOGIN: provedor de identidade indisponível (%s).", exc.code)
        return _redirect_auth_error("provider_unavailable")
    return RedirectResponse(url=url, status_code=302, headers=_NO_STORE)


@router.get("/login")
def login(db: Session = Depends(get_db)) -> Response:
    """Inicia o login no Keycloak (código + PKCE S256 + nonce)."""
    return _start_login(db, register=False)


@router.get("/register")
def register(db: Session = Depends(get_db)) -> Response:
    """Abre o autocadastro do Keycloak (prompt=create). A conta nasce sem perfil."""
    return _start_login(db, register=True)


@router.get("/callback")
def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
) -> Response:
    """Recebe o código, valida os tokens e, havendo papel do app, cria a sessão."""
    pending = consume_login_request(db, state)  # uso único, inclusive quando o provedor devolve erro
    if error:
        logger.warning("CALLBACK: provedor retornou erro: %s", error[:60])
        _login_failed(db, "provider_error", "medium", error=error[:60])
        return _redirect_auth_error("provider_error")
    if pending is None or not code:
        logger.warning("CALLBACK: state inválido, expirado ou reutilizado.")
        _login_failed(db, "invalid_state")
        return _redirect_auth_error("invalid_state")

    code_verifier, nonce = pending
    try:
        tokens = oidc.exchange_code(code, code_verifier=code_verifier, nonce=nonce)
    except oidc.OidcUnavailable:
        _login_failed(db, "provider_unavailable", "medium")
        return _redirect_auth_error("provider_unavailable")
    except oidc.OidcError as exc:
        logger.warning("CALLBACK: tokens recusados (%s).", exc.code)
        _login_failed(db, "token_exchange_failed", detail=exc.code)
        return _redirect_auth_error("token_exchange")

    snapshot = snapshot_from_roles(oidc.roles_from_access_claims(tokens.access_claims))
    user = upsert_user(db, tokens.access_claims, profiles=snapshot.profiles)
    if not snapshot.has_access:
        record_security_event(db, event_type="LOGIN_DENIED", severity="low", user_id=user.id,
                              metadata={"reason": "not_released"})
        db.commit()
        oidc.revoke_refresh_token(tokens.refresh_token)
        return _redirect_denied_after_login("not_released", tokens.id_token)

    ip = request.client.host if request.client else None
    token = create_session(db, user, tokens=tokens, snapshot=snapshot, ip=ip,
                           ua=request.headers.get("user-agent"))
    record_audit(db, user_id=user.id, action="LOGIN_SUCCESS", entity_type="app_user", entity_id=str(user.id))
    db.commit()

    # O Set-Cookie vai na própria resposta 302 (cookie host-only da origem do frontend).
    resp = RedirectResponse(url=_FRONTEND_ORIGIN, status_code=302, headers=_NO_STORE)
    _set_session_cookie(resp, token)
    return resp


@router.get("/me")
def me(
    session: UserSession = Depends(get_current_session),
    user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Usuário atual, perfis e permissões (retrato vindo do Keycloak) e token CSRF."""
    permissions = sorted(session.permissions or [])
    profiles = list(session.profiles or [])
    profile = primary_profile(profiles)
    rate = check_ai_rate_limit(db, user)
    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "display_name": user.display_name,
        "profile": profile,
        "profile_display": PROFILE_DISPLAY.get(profile) if profile else None,
        "profiles": profiles,
        "permissions": permissions,
        "csrf_token": session.csrf_secret,
        "keycloak_console_url": (config.KEYCLOAK_CONSOLE_URL or None) if "users.view" in permissions else None,
        "ai_usage": {
            "used_today": rate["used_today"],
            "daily_limit": rate["daily_limit"],
            "remaining": max(0, rate["daily_limit"] - rate["used_today"]),
            "per_minute_limit": rate["per_minute_limit"],
            "used_this_minute": rate["used_this_minute"],
            "resets_at": rate["resets_at"],
        },
    }


@router.post("/logout", dependencies=[Depends(verify_csrf)])
def logout(
    response: Response,
    session: UserSession = Depends(get_valid_session),
    db: Session = Depends(get_db),
) -> dict:
    """Revoga a sessão do app e o refresh token no Keycloak; devolve a URL de logout OIDC."""
    id_token_hint = session.id_token_hint
    refresh_token = decrypt_secret(session.refresh_token_enc)
    record_audit(db, user_id=session.user_id, action="LOGOUT",
                 entity_type="app_user", entity_id=str(session.user_id))
    revoke_session(db, session)
    db.commit()
    oidc.revoke_refresh_token(refresh_token)
    _clear_session_cookie(response)

    target = post_logout_redirect_uri()
    try:
        logout_url = oidc.end_session_url(id_token_hint=id_token_hint, post_logout_redirect_uri=target)
    except oidc.OidcError:
        logger.warning("LOGOUT: provedor indisponível; retornando direto ao /login.")
        logout_url = target
    return {"logout_url": logout_url}


@router.post("/backchannel-logout")
def backchannel_logout(logout_token: str = Form(default=""), db: Session = Depends(get_db)) -> Response:
    """Keycloak → app: encerra as sessões do ``sid`` (ou, sem sid, todas do ``sub``).

    Chamada servidor a servidor, autenticada pela assinatura do logout token
    (sem cookie nem CSRF). Em produção, o proxy expõe este caminho só para a
    rede do Keycloak.
    """
    try:
        claims = oidc.verify_logout_token(logout_token)
    except oidc.OidcError as exc:
        record_security_event(db, event_type="BACKCHANNEL_LOGOUT_REJECTED", severity="high",
                              metadata={"reason": exc.code})
        db.commit()
        return Response(status_code=400, headers=_NO_STORE)
    revoked = revoke_sessions_for_logout(db, issuer=claims["iss"], sid=claims.get("sid"),
                                         subject=claims.get("sub"))
    record_security_event(db, event_type="BACKCHANNEL_LOGOUT", severity="low", metadata={"sessions": revoked})
    db.commit()
    return Response(status_code=200, headers=_NO_STORE)


@router.get("/usage")
def ai_usage(
    user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Retorna sumário de uso da IA do usuário atual."""
    rate = check_ai_rate_limit(db, user)
    return {
        "used_today": rate["used_today"],
        "daily_limit": rate["daily_limit"],
        "remaining": max(0, rate["daily_limit"] - rate["used_today"]),
        "resets_at": rate["resets_at"],
    }
```

- [ ] **Step 6: Reescrever `backend/app/api/routes/users.py`**

```python
"""
Gestão de Usuários — consulta somente leitura.

Cadastro, liberação, bloqueio e senhas são feitos no console do Keycloak por um
gestor de acesso. Aqui a lista mostra quem já entrou no Chat-bot O&M, o último
perfil visto e se há sessão ativa.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import require_permission
from app.db.session import get_db
from app.models.auth import AppUser, UserSession
from app.services.permissions import primary_profile

router = APIRouter(prefix="/users", tags=["Users"], dependencies=[Depends(require_permission("users.view"))])


def _iso(value: datetime | None) -> str | None:
    # Datas gravadas em UTC sem fuso: explicita o "Z" para o navegador.
    return value.isoformat() + "Z" if value else None


@router.get("")
def list_users(db: Session = Depends(get_db)) -> list[dict]:
    now = datetime.utcnow()
    with_session = set(db.scalars(
        select(UserSession.user_id).where(
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
            UserSession.absolute_expires_at > now,
        )
    ).all())
    users = db.scalars(select(AppUser).order_by(AppUser.display_name)).all()
    return [
        {
            "id": user.id,
            "display_name": user.display_name,
            "email": user.email,
            "username": user.username,
            "profile": primary_profile(user.last_profiles or []),
            "profiles": list(user.last_profiles or []),
            "last_seen_at": _iso(user.last_seen_at),
            "created_at": _iso(user.created_at),
            "active_session": user.id in with_session,
        }
        for user in users
    ]
```

- [ ] **Step 7: Ajustar `backend/app/main.py`**

1. Troque `from app.core.config import APP_NAME, APP_VERSION, DEV_PROVISION_USERS, FRONTEND_ORIGINS` por:

```python
from app.core import config
from app.core.config import APP_NAME, APP_VERSION, FRONTEND_ORIGINS
```

2. Troque o bloco `from app.models.auth import (...)` por:

```python
from app.models.auth import (                   # noqa: F401
    AppUser, OidcIdentity, OidcLoginRequest, UserSession,
    AssistantConversation, AssistantMessage, AiUsage, AuditLog, SecurityEvent,
)
```

3. Acima de `@app.on_event("startup")`, acrescente:

```python
def _check_session_encryption_key() -> None:
    """Sem chave válida o backend não consegue guardar o refresh token: falha na subida."""
    if not config.OIDC_ISSUER_URL:
        return
    from cryptography.fernet import Fernet
    try:
        Fernet(config.SESSION_ENCRYPTION_KEY.encode())
    except (ValueError, TypeError) as exc:
        raise RuntimeError(
            "SESSION_ENCRYPTION_KEY ausente ou inválida. Gere com: python -c "
            "\"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        ) from exc
```

4. Em `on_startup`, chame `_check_session_encryption_key()` como primeira linha depois de `logger = ...` e **remova** três blocos: o `try` de `apply_schema_updates`, o `try` de `seed_profiles_and_permissions` e o `if DEV_PROVISION_USERS:` inteiro. Ficam `create_all`, a extensão `unaccent` e o agendador da Tape.

- [ ] **Step 8: Limpar `backend/app/core/config.py`**

Remova os blocos inteiros:
- `# ─── Keycloak Admin API (gestão de usuários, somente server-side)` (`KEYCLOAK_ADMIN_*`, `KEYCLOAK_REALM`, `KEYCLOAK_ACTION_EMAIL_LIFESPAN_SECONDS`);
- `# ─── bootstrap` (`DEV_ADMIN_EMAIL`, `_CONFIGURED_BOOTSTRAP_ADMIN_EMAIL`, `BOOTSTRAP_ADMIN_EMAIL`);
- `DEV_PROVISION_USERS` e seu comentário.

- [ ] **Step 9: Remover o código do modelo antigo**

```bash
cd "$APP" && git rm -q backend/app/services/keycloak_admin.py backend/app/services/user_admin.py backend/app/db/schema_updates.py backend/tests/test_user_management.py
grep -rnE "keycloak_admin|user_admin|schema_updates|require_admin|BOOTSTRAP_ADMIN_EMAIL|DEV_PROVISION_USERS|DEV_ADMIN_EMAIL|get_user_permissions|check_user_active|seed_profiles|Profile\b|UserPermissionOverride|_pending_states" backend/app backend/tests
```

Expected: o `grep` não imprime nada.

- [ ] **Step 10: Rodar a suíte completa do backend**

Run: `cd "$APP/backend" && "$PY" -m pytest -q`
Expected: `303 passed`. São os 182 testes que não tratam de autenticação (inalterados) mais os 121 desta mudança: 8 de permissões, 37 do OIDC, 25 de sessão/identidade, 9 de renovação, 21 de `test_api_security.py` e 21 de `test_auth_flow.py`.

- [ ] **Step 11: Commit**

```bash
cd "$APP" && git add -A backend
git commit -m "feat(auth): app como cliente OIDC do Keycloak externo

- login e autocadastro com PKCE + nonce e state de uso único no banco
- conta sem papel do app não cria sessão (auth_error=not_released)
- backchannel logout, revogação do refresh token no logout
- /users somente leitura (users.view); sem Admin API do Keycloak

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Frontend — login, "Criar conta" e conta não liberada

**Files:**
- Modify: `frontend/src/features/auth/authErrors.js`, `authErrors.test.js`, `api.js`, `LoginScreen.jsx`, `UserMenu.jsx`, `auth.css`
- Rewrite: `frontend/src/features/auth/AuthProvider.jsx`
- Create: `frontend/src/features/auth/AccountNotReleased.jsx`
- Delete: `frontend/src/features/auth/AccessPending.jsx`, `frontend/src/features/auth/AccessDenied.jsx`
- Modify: `frontend/src/App.jsx`, `frontend/src/features/settings/SettingsModal.jsx`

**Interfaces:**
- Consumes: `/auth/me` da Task 9 (com `profiles` e `keycloak_console_url`, sem `status`/`access_expires_at`); `/auth/register`; `auth_error=not_released|provider_unavailable`.
- Produces:
  - `useAuth()` devolve `auth_status` (`'loading' | 'redirecting' | 'authenticated' | 'unauthenticated' | 'not_released'`), `user`, `profile`, `profiles`, `permissions`, `keycloakConsoleUrl`, `hasPermission(code)`, `canViewUsers` e `refresh()`. `isAdmin` deixa de existir.
  - `api.js` exporta `startRegister()`.
  - `<UsersPage currentUserId consoleUrl />` (a página é da Task 11).

- [ ] **Step 1: Atualizar o teste `frontend/src/features/auth/authErrors.test.js`**

```js
import test from 'node:test'
import assert from 'node:assert/strict'
import { AUTH_ERROR_MESSAGES, getAuthError } from './authErrors.js'

test('auth_error not_released explica que falta a liberação do perfil', () => {
  const err = getAuthError('not_released')
  assert.match(err.title, /não foi liberada/i)
  assert.match(err.message, /gestor de acesso/i)
})

test('auth_error provider_unavailable pede para tentar mais tarde', () => {
  const err = getAuthError('provider_unavailable')
  assert.match(err.title, /indisponível/i)
  assert.match(err.message, /tente novamente/i)
})

test('códigos do modelo antigo deixam de existir', () => {
  for (const code of ['pending', 'disabled', 'no_user']) assert.equal(AUTH_ERROR_MESSAGES[code], undefined)
})

test('auth_error técnico desconhecido recebe fallback amigável', () => {
  const err = getAuthError('qualquer_erro')
  assert.match(err.title, /acesso/i)
  assert.match(err.message, /autenticação/i)
})
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd "$APP/frontend" && node --test src/features/auth/authErrors.test.js`
Expected: FAIL em `not_released`, `provider_unavailable` e `códigos do modelo antigo`.

- [ ] **Step 3: Atualizar `authErrors.js`**

Apague as entradas `no_user`, `pending` e `disabled`. Depois de `token_exchange`, acrescente:

```js
  not_released: {
    title: 'Sua conta ainda não foi liberada',
    message: 'Seu cadastro está confirmado, mas um gestor de acesso ainda precisa liberar o seu perfil no Chat-bot O&M.',
  },
  provider_unavailable: {
    title: 'Login indisponível no momento',
    message: 'Não foi possível contatar o serviço de autenticação. Tente novamente em alguns minutos.',
  },
```

Run: `cd "$APP/frontend" && node --test src/features/auth/authErrors.test.js`
Expected: `# pass 4`, `# fail 0`.

- [ ] **Step 4: `startRegister` em `frontend/src/features/auth/api.js`**

Logo depois de `startLogin`, acrescente:

```js
/** Abre o autocadastro do Keycloak (/auth/register → prompt=create). */
export function startRegister() {
  writeStorage(REDIRECT_KEY, String(Date.now()))
  window.location.assign('/auth/register')
}
```

E troque o comentário de `leaveToLogin` por `/** Volta para /login sem sessão (usado na tela de conta não liberada). */`.

- [ ] **Step 5: Reescrever `frontend/src/features/auth/AuthProvider.jsx`**

```jsx
/**
 * AuthProvider — estado global de autenticação.
 *
 * auth_status: 'loading' | 'redirecting' | 'authenticated' | 'unauthenticated' | 'not_released'
 *
 * Perfis e permissões vêm do Keycloak, via /auth/me (retrato da sessão no
 * backend). O frontend só exibe: toda regra de acesso é validada no backend.
 *
 * Navegação sem sessão:
 * - "/" (ou qualquer tela do app) → vai direto para o login do Keycloak;
 * - "/login" → página de apresentação (retorno do logout e erros), sem
 *   redirecionamento automático para não criar laços.
 */

import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import {
  clearLoginMarker,
  consumeLoggedOutNotice,
  fetchMe,
  isLoginPath,
  LOGIN_PATH,
  loginRecentlyStarted,
  startLogin,
} from './api.js'
import { setCsrfToken } from '../../lib/apiClient.js'
import { getAuthError } from './authErrors.js'

const AuthContext = createContext(null)

const EMPTY_SESSION = {
  user: null,
  profile: null,
  profiles: [],
  permissions: new Set(),
  keycloakConsoleUrl: null,
  csrf_token: '',
  ai_usage: null,
}

function replaceUrl(path) {
  if (typeof window === 'undefined') return
  if (window.location.pathname + window.location.search !== path) {
    window.history.replaceState({}, '', path)
  }
}

function initialAuthState() {
  const base = { auth_status: 'loading', ...EMPTY_SESSION, auth_error: null, notice: null }
  if (typeof window === 'undefined') return base

  const params = new URLSearchParams(window.location.search)
  const authErrorCode = params.get('auth_error')
  if (!authErrorCode) {
    const notice = isLoginPath() && consumeLoggedOutNotice() ? 'Você saiu com segurança.' : null
    return { ...base, notice }
  }

  // O callback informou um problema: nenhuma sessão foi criada nesse fluxo.
  clearLoginMarker()
  replaceUrl(LOGIN_PATH)
  const authError = getAuthError(authErrorCode)
  if (authErrorCode === 'not_released') return { ...base, auth_status: 'not_released', auth_error: authError }
  return { ...base, auth_status: 'unauthenticated', auth_error: authError }
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth deve ser usado dentro de <AuthProvider>')
  return ctx
}

export function AuthProvider({ children }) {
  const [state, setState] = useState(initialAuthState)
  const abortRef = useRef(null)
  const callbackErrorRef = useRef(state.auth_status !== 'loading')

  const refresh = useCallback(async () => {
    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl
    setState(s => ({ ...s, auth_status: 'loading', auth_error: null }))

    try {
      const me = await fetchMe(ctrl.signal)
      setCsrfToken(me.csrf_token || '')
      clearLoginMarker()
      if (isLoginPath()) replaceUrl('/')
      setState({
        auth_status: 'authenticated',
        user: { id: me.id, email: me.email, username: me.username, display_name: me.display_name },
        profile: { name: me.profile, display_name: me.profile_display },
        profiles: me.profiles || [],
        permissions: new Set(me.permissions || []),
        keycloakConsoleUrl: me.keycloak_console_url || null,
        csrf_token: me.csrf_token || '',
        ai_usage: me.ai_usage || null,
        auth_error: null,
        notice: null,
      })
    } catch (err) {
      if (err?.name === 'AbortError') return
      setCsrfToken('')
      const status = err?.status

      if (status === 401 && !isLoginPath()) {
        if (loginRecentlyStarted()) {
          // Voltou do Keycloak sem sessão válida: mostra o motivo em vez de repetir o login.
          clearLoginMarker()
          replaceUrl(LOGIN_PATH)
          setState({ auth_status: 'unauthenticated', ...EMPTY_SESSION,
                     auth_error: getAuthError('session_not_started'), notice: null })
          return
        }
        // Sessão encerrada (logout em outro lugar, acesso retirado no Keycloak): novo login.
        setState(s => ({ ...s, auth_status: 'redirecting' }))
        startLogin()
        return
      }

      replaceUrl(LOGIN_PATH)
      setState(s => ({
        auth_status: 'unauthenticated',
        ...EMPTY_SESSION,
        auth_error: status === 401 ? null : getAuthError('unavailable'),
        notice: status === 401 ? s.notice : null,
      }))
    }
  }, [])

  useEffect(() => {
    // Quando o callback retornou auth_error, preservamos a mensagem na tela e
    // não fazemos /auth/me porque nenhuma sessão foi criada nesse fluxo.
    if (!callbackErrorRef.current) refresh()
    return () => abortRef.current?.abort()
  }, [refresh])

  const hasPermission = useCallback(code => state.permissions.has(code), [state.permissions])
  const canViewUsers = state.permissions.has('users.view')

  return (
    <AuthContext.Provider value={{ ...state, hasPermission, canViewUsers, refresh }}>
      {children}
    </AuthContext.Provider>
  )
}
```

- [ ] **Step 6: Criar `frontend/src/features/auth/AccountNotReleased.jsx` e apagar as telas antigas**

```jsx
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
```

```bash
cd "$APP" && git rm -q frontend/src/features/auth/AccessPending.jsx frontend/src/features/auth/AccessDenied.jsx
```

- [ ] **Step 7: "Criar conta" no `LoginScreen.jsx`**

Troque o import por `import { startLogin, startRegister } from './api.js'`, acrescente a função abaixo de `handleLogin`:

```jsx
  function handleRegister() {
    setRedirecting(true)
    startRegister()
  }
```

e, entre o `</button>` do Entrar e o `<p className="om-auth__hint">`, acrescente:

```jsx
      <button className="om-auth__register" type="button" onClick={handleRegister} disabled={redirecting}>
        Ainda não tem conta? <strong>Criar conta</strong>
      </button>
```

No final de `frontend/src/features/auth/auth.css`, acrescente:

```css
/* ── Autocadastro e conta não liberada ─────────────────────────────────────── */
.om-auth__register {
  display: block;
  width: 100%;
  margin: 14px 0 0;
  padding: 8px;
  border: 0;
  border-radius: 8px;
  background: none;
  color: #5d6a80;
  font-size: 13px;
  text-align: center;
  cursor: pointer;
}

.om-auth__register strong { color: var(--om-navy-soft); font-weight: 750; }

.om-auth__register:hover:not(:disabled) strong,
.om-auth__register:focus-visible strong { text-decoration: underline; }

.om-auth__register:focus-visible { outline: 2px solid var(--om-yellow); outline-offset: 2px; }

.om-auth__register:disabled { cursor: wait; opacity: 0.7; }

.om-auth__button + .om-auth__button { margin-top: 10px; }
```

- [ ] **Step 8: `UserMenu.jsx`, `App.jsx` e `SettingsModal.jsx`**

`UserMenu.jsx`: troque `const { user, profile, hasPermission, isAdmin } = useAuth()` por `const { user, profile, hasPermission, canViewUsers } = useAuth()` e `{isAdmin && (` por `{canViewUsers && (`.

`App.jsx`:
1. Troque as duas linhas `import AccessPending ...` e `import AccessDenied ...` por `import AccountNotReleased from './features/auth/AccountNotReleased.jsx'`.
2. Troque `const { auth_status, user, hasPermission, isAdmin, auth_error, notice, refresh } = useAuth()` por `const { auth_status, user, hasPermission, canViewUsers, keycloakConsoleUrl, auth_error, notice } = useAuth()`.
3. Troque as linhas `if (auth_status === 'pending') ...` e `if (auth_status === 'disabled') ...` por `if (auth_status === 'not_released')   return <AccountNotReleased />`.
4. Troque o comentário e a linha do `section` por:

```jsx
  // Gestão de Usuários (consulta) exige users.view — o backend também valida:
  // se a permissão sair no Keycloak, a tela volta ao assistente.
  const section = activeSection === 'users' && !canViewUsers ? 'assistant' : activeSection
```

5. Troque `) : section === 'users' && isAdmin ? (` por `) : section === 'users' && canViewUsers ? (` e a linha do `<UsersPage ... />` por `<UsersPage currentUserId={user?.id} consoleUrl={keycloakConsoleUrl} />`.
6. Troque `onOpenUsers={isAdmin ? openUsers : undefined}` por `onOpenUsers={canViewUsers ? openUsers : undefined}`.

`SettingsModal.jsx`: no cartão "Gestão de Usuários", troque o texto do `<small>` por `Consulte quem acessa o Chat-bot O&amp;M e abra o console do Keycloak para liberar ou bloquear contas.`

- [ ] **Step 9: Conferir que não sobrou referência antiga e que o app compila**

```bash
cd "$APP/frontend" && grep -rnE "isAdmin|AccessPending|AccessDenied|access_expires_at|auth_status === '(pending|disabled)'" src --include=*.js --include=*.jsx | grep -v "features/users/"
cd "$APP" && docker compose exec -T frontend npx vite build --outDir /tmp/om-build-check --emptyOutDir 2>&1 | tail -3
```

Expected: o `grep` não imprime nada (a pasta `features/users` muda na Task 11); o build termina com `✓ built in`.

- [ ] **Step 10: Rodar os testes do frontend e fazer o commit**

Run: `cd "$APP/frontend" && npm test 2>&1 | grep -E "^# (pass|fail)"`
Expected: `# pass 27`, `# fail 0` (25 − 2 + 4).

```bash
cd "$APP" && git add -A frontend/src/features/auth frontend/src/App.jsx frontend/src/features/settings/SettingsModal.jsx
git commit -m "feat(frontend): criar conta pelo Keycloak e tela de conta não liberada

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: Frontend — Gestão de Usuários somente leitura

**Files:**
- Rewrite: `frontend/src/features/users/userUtils.js`, `users.test.js`, `api.js`, `components/UserVisuals.jsx`, `UsersPage.jsx`
- Modify: `frontend/src/features/users/users.css`
- Delete: `frontend/src/features/users/components/UserFormDrawer.jsx`

**Interfaces:**
- Consumes: `GET /users` (Task 9); props `currentUserId` e `consoleUrl` (Task 10).
- Produces: `userUtils` com `NO_PROFILE`, `PROFILE_OPTIONS`, `PROFILE_LABELS`, `profileLabel`, `normalizeText`, `filterUsers(users, {query, profile})`, `sortUsers(users)`, `summarizeUsers(users) -> {total, activeSessions, withoutProfile}`, `initials`, `formatLastAccess`.

- [ ] **Step 1: Reescrever o teste `frontend/src/features/users/users.test.js`**

```js
import test from 'node:test'
import assert from 'node:assert/strict'
import {
  filterUsers,
  formatLastAccess,
  initials,
  NO_PROFILE,
  profileLabel,
  sortUsers,
  summarizeUsers,
} from './userUtils.js'

const USERS = [
  { id: 1, display_name: 'Administrador OM', email: 'admin.om@chatbot-om.local', username: 'admin.om',
    profile: 'ADMINISTRADOR', profiles: ['ADMINISTRADOR'], active_session: true },
  { id: 2, display_name: 'João Araújo', email: 'joao@empresa.com', username: 'joao.araujo',
    profile: 'GERENTE', profiles: ['GERENTE', 'ANALISTA'], active_session: false },
  { id: 3, display_name: 'Maria Souza', email: 'maria@empresa.com', username: 'maria',
    profile: null, profiles: [], active_session: false },
]

test('perfis são exibidos de forma amigável', () => {
  assert.equal(profileLabel('ADMINISTRADOR'), 'Administrador')
  assert.equal(profileLabel('CONVIDADO'), 'Convidado')
  assert.equal(profileLabel(null), 'Sem perfil')
})

test('busca por nome, e-mail e usuário ignora acentos e caixa', () => {
  assert.deepEqual(filterUsers(USERS, { query: 'joao araujo' }).map(u => u.id), [2])
  assert.deepEqual(filterUsers(USERS, { query: 'MARIA@' }).map(u => u.id), [3])
  assert.deepEqual(filterUsers(USERS, { query: 'admin.om' }).map(u => u.id), [1])
  assert.equal(filterUsers(USERS, { query: 'inexistente' }).length, 0)
})

test('filtro de perfil considera todos os perfis da pessoa', () => {
  assert.deepEqual(filterUsers(USERS, { profile: 'ANALISTA' }).map(u => u.id), [2])
  assert.deepEqual(filterUsers(USERS, { profile: 'GERENTE', query: 'joão' }).map(u => u.id), [2])
})

test('filtro "Sem perfil" mostra as contas ainda não liberadas', () => {
  assert.deepEqual(filterUsers(USERS, { profile: NO_PROFILE }).map(u => u.id), [3])
})

test('resumo conta total, sessões ativas e contas sem perfil', () => {
  assert.deepEqual(summarizeUsers(USERS), { total: 3, activeSessions: 1, withoutProfile: 1 })
  assert.deepEqual(summarizeUsers([]), { total: 0, activeSessions: 0, withoutProfile: 0 })
})

test('ordenação mostra primeiro quem aguarda liberação e depois por nome', () => {
  assert.deepEqual(sortUsers(USERS).map(u => u.id), [3, 1, 2])
})

test('iniciais do nome', () => {
  assert.equal(initials('João Araújo'), 'JA')
  assert.equal(initials('Maria'), 'M')
  assert.equal(initials(''), '?')
})

test('último acesso em linguagem amigável', () => {
  const now = new Date(2026, 8, 30, 15, 0)
  assert.equal(formatLastAccess(null, now), 'Nunca acessou')
  assert.equal(formatLastAccess(new Date(2026, 8, 30, 9, 5).toISOString(), now), 'Hoje, 09:05')
  assert.match(formatLastAccess(new Date(2026, 8, 29, 9, 5).toISOString(), now), /^Ontem, 09:05$/)
})
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd "$APP/frontend" && node --test src/features/users/users.test.js`
Expected: FAIL com `SyntaxError: The requested module './userUtils.js' does not provide an export named 'NO_PROFILE'`.

- [ ] **Step 3: Reescrever `frontend/src/features/users/userUtils.js`**

```js
/**
 * Utilitários puros da Gestão de Usuários — consulta somente leitura
 * (testáveis com node --test). Perfis vêm do Keycloak, via /users.
 */

export const NO_PROFILE = 'SEM_PERFIL'

export const PROFILE_OPTIONS = [
  { value: 'ADMINISTRADOR', label: 'Administrador' },
  { value: 'GERENTE', label: 'Gerente' },
  { value: 'ANALISTA', label: 'Analista' },
  { value: 'DIRETOR', label: 'Diretor' },
  { value: 'CONVIDADO', label: 'Convidado' },
]

export const PROFILE_LABELS = Object.fromEntries(PROFILE_OPTIONS.map(({ value, label }) => [value, label]))

export function profileLabel(profile) {
  return PROFILE_LABELS[profile] || 'Sem perfil'
}

export function normalizeText(value = '') {
  return String(value ?? '')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .trim()
}

/** Busca por nome, e-mail ou usuário; filtro por qualquer perfil da pessoa ou "Sem perfil". */
export function filterUsers(users = [], { query = '', profile = '' } = {}) {
  const term = normalizeText(query)
  return users.filter((user) => {
    const profiles = user.profiles || []
    if (profile === NO_PROFILE && profiles.length) return false
    if (profile && profile !== NO_PROFILE && !profiles.includes(profile)) return false
    if (!term) return true
    return [user.display_name, user.email, user.username].some((field) => normalizeText(field).includes(term))
  })
}

/** Quem ainda não tem perfil (aguardando liberação) vem primeiro; depois, ordem alfabética. */
export function sortUsers(users = []) {
  return [...users].sort((a, b) =>
    Number((a.profiles || []).length > 0) - Number((b.profiles || []).length > 0)
    || String(a.display_name).localeCompare(String(b.display_name), 'pt-BR', { sensitivity: 'base' }))
}

export function summarizeUsers(users = []) {
  return users.reduce(
    (acc, user) => {
      acc.total += 1
      if (user.active_session) acc.activeSessions += 1
      if (!(user.profiles || []).length) acc.withoutProfile += 1
      return acc
    },
    { total: 0, activeSessions: 0, withoutProfile: 0 },
  )
}

export function initials(name = '', fallback = '?') {
  const parts = String(name).trim().split(/\s+/).filter(Boolean)
  if (!parts.length) return fallback
  const first = parts[0][0] || ''
  const last = parts.length > 1 ? parts[parts.length - 1][0] : ''
  return (first + last).toUpperCase()
}

/** Formata "Último acesso" a partir de ISO UTC ("...Z"). */
export function formatLastAccess(value, now = new Date()) {
  if (!value) return 'Nunca acessou'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Nunca acessou'
  const time = new Intl.DateTimeFormat('pt-BR', { hour: '2-digit', minute: '2-digit' }).format(date)
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const diffDays = Math.floor((startOfToday - new Date(date.getFullYear(), date.getMonth(), date.getDate())) / 86_400_000)
  if (diffDays <= 0) return `Hoje, ${time}`
  if (diffDays === 1) return `Ontem, ${time}`
  return new Intl.DateTimeFormat('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric' }).format(date) + `, ${time}`
}
```

Run: `cd "$APP/frontend" && node --test src/features/users/users.test.js`
Expected: `# pass 8`, `# fail 0`.

- [ ] **Step 4: Reescrever `frontend/src/features/users/api.js`**

```js
/**
 * Gestão de Usuários — consulta ao BFF (somente leitura).
 * Cadastro, liberação e bloqueio são feitos no console do Keycloak.
 */

import { api } from '../../lib/apiClient.js'

export const fetchUsers = (signal) => api.get('/users', { signal })
```

- [ ] **Step 5: Reescrever `frontend/src/features/users/components/UserVisuals.jsx`**

```jsx
import { initials, profileLabel } from '../userUtils.js'

const ICON_PATHS = {
  search: <><circle cx="11" cy="11" r="7" /><path d="m20 20-3.6-3.6" /></>,
  users: <><circle cx="9" cy="8" r="3.5" /><path d="M2.5 19.5c1-3.4 3.6-5.2 6.5-5.2s5.5 1.8 6.5 5.2" /><path d="M16 4.8a3.3 3.3 0 0 1 0 6.4M17.6 14.6c2 .7 3.3 2.3 3.9 4.9" /></>,
  shield: <><path d="M12 3 5 6v5.5c0 4.3 2.9 8 7 9.5 4.1-1.5 7-5.2 7-9.5V6l-7-3Z" /><path d="m9 12 2 2 4-4" /></>,
  alert: <><circle cx="12" cy="12" r="9" /><path d="M12 7.5v5.5M12 16.5h.01" /></>,
  info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v5.5M12 7.5h.01" /></>,
}

export function UsersIcon({ name, size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {ICON_PATHS[name] || ICON_PATHS.info}
    </svg>
  )
}

export function ProfileBadge({ profile }) {
  const tone = profile ? profile.toLowerCase() : 'none'
  return <span className={`users-profile users-profile--${tone}`}>{profileLabel(profile)}</span>
}

export function SessionBadge({ active }) {
  return (
    <span className={`users-status users-status--${active ? 'active' : 'idle'}`}>
      <i aria-hidden="true" />
      {active ? 'Sessão ativa' : 'Sem sessão'}
    </span>
  )
}

export function UserAvatar({ name, profile, size = 'md' }) {
  const tone = profile ? profile.toLowerCase() : 'none'
  return (
    <span className={`users-avatar users-avatar--${size} users-avatar--${tone}`} aria-hidden="true">
      {initials(name)}
    </span>
  )
}
```

- [ ] **Step 6: Reescrever `frontend/src/features/users/UsersPage.jsx`**

```jsx
/**
 * Gestão de Usuários — consulta somente leitura (permissão users.view).
 *
 * Cadastro, liberação, bloqueio e senhas ficam no console do Keycloak, com os
 * gestores de acesso. Aqui a lista mostra quem já entrou no Chat-bot O&M, o
 * perfil do último acesso e se há sessão ativa. Quem garante o acesso é o backend.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import mascot from '../../assets/gentileza-indicadores.png'
import { fetchUsers } from './api.js'
import { ProfileBadge, SessionBadge, UserAvatar, UsersIcon } from './components/UserVisuals.jsx'
import {
  filterUsers,
  formatLastAccess,
  NO_PROFILE,
  PROFILE_OPTIONS,
  sortUsers,
  summarizeUsers,
} from './userUtils.js'
import './users.css'

function friendlyError(error) {
  if (error?.kind === 'network') return 'Não foi possível conectar ao servidor. Verifique sua conexão e tente novamente.'
  if (error?.status === 403) return 'Você não tem permissão para consultar os usuários.'
  return 'Não foi possível carregar os usuários. Tente novamente.'
}

function StatCard({ label, value, tone, active = false, onClick }) {
  const content = (
    <>
      <span className="users-stat__label">{label}</span>
      <strong className="users-stat__value">{value ?? <span className="users-stat__loading" aria-label="Carregando" />}</strong>
    </>
  )
  if (!onClick) return <div className={`users-stat users-stat--${tone}`}>{content}</div>
  return (
    <button type="button" className={`users-stat users-stat--${tone}${active ? ' is-active' : ''}`}
            onClick={onClick} aria-pressed={active}>
      {content}
    </button>
  )
}

export default function UsersPage({ currentUserId, consoleUrl }) {
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [query, setQuery] = useState('')
  const [profileFilter, setProfileFilter] = useState('')
  const loadRef = useRef(null)

  // initial: o primeiro carregamento já nasce com loading=true (sem setState síncrono no efeito).
  const load = useCallback(async ({ initial = false } = {}) => {
    loadRef.current?.abort()
    const ctrl = new AbortController()
    loadRef.current = ctrl
    if (!initial) {
      setLoading(true)
      setLoadError('')
    }
    try {
      setUsers(sortUsers((await fetchUsers(ctrl.signal)) || []))
    } catch (error) {
      if (error?.name === 'AbortError') return
      setLoadError(friendlyError(error))
    } finally {
      if (loadRef.current === ctrl) {
        loadRef.current = null
        setLoading(false)
      }
    }
  }, [])

  useEffect(() => {
    load({ initial: true })
    return () => loadRef.current?.abort()
  }, [load])

  const summary = useMemo(() => summarizeUsers(users), [users])
  const visibleUsers = useMemo(
    () => filterUsers(users, { query, profile: profileFilter }),
    [users, query, profileFilter],
  )
  const hasFilters = Boolean(query.trim() || profileFilter)
  const initialLoading = loading && users.length === 0

  function clearFilters() {
    setQuery('')
    setProfileFilter('')
  }

  return (
    <section className="users-page" aria-labelledby="users-title">
      <header className="users-hero">
        <div className="users-hero__mascot" aria-hidden="true">
          <span className="users-hero__ring users-hero__ring--one" />
          <span className="users-hero__ring users-hero__ring--two" />
          <img src={mascot} alt="" />
        </div>
        <div className="users-hero__copy">
          <p className="users-hero__eyebrow">Configurações <span aria-hidden="true" /> Acessos</p>
          <h1 id="users-title">Gestão de Usuários</h1>
          <p>Veja quem acessa o Chat-bot O&amp;M. Cadastro, liberação e bloqueio são feitos no Keycloak.</p>
          {consoleUrl && (
            <a className="users-hero__cta" href={consoleUrl} target="_blank" rel="noopener noreferrer">
              <UsersIcon name="shield" size={17} /> Gerenciar no Keycloak
            </a>
          )}
        </div>
        <div className="users-hero__stats" role="group" aria-label="Resumo dos acessos">
          <StatCard label="Usuários" tone="total" value={initialLoading ? null : summary.total}
                    active={!profileFilter} onClick={() => setProfileFilter('')} />
          <StatCard label="Com sessão ativa" tone="active" value={initialLoading ? null : summary.activeSessions} />
          <StatCard label="Sem perfil" tone="pending" value={initialLoading ? null : summary.withoutProfile}
                    active={profileFilter === NO_PROFILE}
                    onClick={() => setProfileFilter(profileFilter === NO_PROFILE ? '' : NO_PROFILE)} />
        </div>
      </header>

      <section className="users-panel" aria-labelledby="users-list-title">
        <div className="users-panel__heading">
          <div>
            <span className="users-eyebrow">Acessos ao Chat-bot O&amp;M</span>
            <h2 id="users-list-title">Quem já entrou</h2>
            <p>O perfil mostrado é o do último acesso de cada pessoa.</p>
          </div>
        </div>

        <div className="users-inline-alert users-inline-alert--info" role="note">
          <UsersIcon name="info" size={17} />
          <span>
            Para liberar uma conta nova, um gestor de acesso inclui a pessoa no grupo do perfil no Keycloak.
            A troca de perfil vale em até 5 minutos; o bloqueio com encerramento das sessões vale na hora.
          </span>
        </div>

        <div className="users-toolbar">
          <label className="users-search">
            <span className="users-search__icon"><UsersIcon name="search" size={18} /></span>
            <input value={query} onChange={(event) => setQuery(event.target.value)}
                   placeholder="Buscar usuário" aria-label="Buscar usuário por nome, e-mail ou usuário" autoComplete="off" />
            {query && (
              <button type="button" className="users-search__clear" onClick={() => setQuery('')} aria-label="Limpar busca">×</button>
            )}
          </label>
          <select value={profileFilter} onChange={(event) => setProfileFilter(event.target.value)} aria-label="Filtrar por perfil">
            <option value="">Todos os perfis</option>
            {PROFILE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            <option value={NO_PROFILE}>Sem perfil</option>
          </select>
        </div>

        <div className="users-meta" aria-live="polite">
          <span>
            <strong>{visibleUsers.length}</strong> {visibleUsers.length === 1 ? 'usuário' : 'usuários'}
            {hasFilters ? ` de ${users.length}` : ''}
          </span>
          {hasFilters && <button type="button" className="users-link-button" onClick={clearFilters}>Limpar filtros</button>}
        </div>

        {initialLoading ? (
          <div className="users-state" role="status">
            <span className="users-loader" aria-hidden="true" />
            <strong>Carregando usuários...</strong>
          </div>
        ) : loadError ? (
          <div className="users-state users-state--error" role="alert">
            <span className="users-state__icon users-state__icon--error"><UsersIcon name="alert" size={22} /></span>
            <strong>{loadError}</strong>
            <button className="users-button users-button--primary" type="button" onClick={() => load()}>Tentar novamente</button>
          </div>
        ) : visibleUsers.length === 0 ? (
          <div className="users-state">
            <span className="users-state__icon"><UsersIcon name="users" size={22} /></span>
            <strong>Nenhum usuário encontrado.</strong>
            <span>{hasFilters ? 'Ajuste a busca ou limpe os filtros para ver outros usuários.' : 'Ninguém entrou no Chat-bot O&M ainda.'}</span>
            {hasFilters && <button className="users-button users-button--quiet" type="button" onClick={clearFilters}>Limpar filtros</button>}
          </div>
        ) : (
          <div className={`users-table-wrap${loading ? ' is-refreshing' : ''}`}>
            <table className="users-table">
              <thead>
                <tr>
                  <th scope="col">Nome</th>
                  <th scope="col">E-mail</th>
                  <th scope="col">Usuário</th>
                  <th scope="col">Perfil</th>
                  <th scope="col">Sessão</th>
                  <th scope="col">Último acesso</th>
                </tr>
              </thead>
              <tbody>
                {visibleUsers.map((user) => (
                  <tr key={user.id}>
                    <td data-label="Nome">
                      <div className="users-person">
                        <UserAvatar name={user.display_name} profile={user.profile} />
                        <span className="users-person__copy">
                          <strong>{user.display_name}{user.id === currentUserId && <em className="users-self-tag">Você</em>}</strong>
                          <small>{user.email}</small>
                          {user.username && <small className="users-person__username">@{user.username}</small>}
                        </span>
                      </div>
                    </td>
                    <td data-label="E-mail" className="users-table__email">{user.email}</td>
                    <td data-label="Usuário" className="users-table__username">{user.username ? `@${user.username}` : '—'}</td>
                    <td data-label="Perfil"><ProfileBadge profile={user.profile} /></td>
                    <td data-label="Sessão"><SessionBadge active={user.active_session} /></td>
                    <td data-label="Último acesso" className="users-table__date">{formatLastAccess(user.last_seen_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </section>
  )
}
```

- [ ] **Step 7: Limpar `users.css` e apagar o drawer**

```bash
cd "$APP" && git rm -q frontend/src/features/users/components/UserFormDrawer.jsx
```

Em `frontend/src/features/users/users.css`:
1. Apague toda regra, inclusive dentro de `@media`, cujo seletor use as classes do modo de edição removido: `users-drawer*`, `users-form*`, `users-password*`, `users-confirmation*`, `users-toast*`, `users-overlay*`, `users-identity-card*`, `users-access-action*`, `users-choice*`, `users-prefixed*`, `users-reset-panel*`, `users-field*`, `users-icon-button*`, `users-dialog-actions*`, `users-action*`, `users-table__actions`, `users-button--danger`, `users-status--pending`, `users-status--disabled`, `users-status--unknown`, `users-stat--disabled` e `tr.is-disabled`. Em seletor agrupado (`a, b { }`), apague só a parte removida.
2. Na regra `.users-person:hover .users-person__copy strong` e na `.users-person:focus-visible`: apague as duas (o bloco deixou de ser botão).
3. Acrescente no final:

```css
/* ── Consulta somente leitura (gestão no console do Keycloak) ──────────────── */
a.users-hero__cta { text-decoration: none; }
.users-person { cursor: default; }
.users-status--idle { color: #607693; background: #eff4fa; }
.users-inline-alert--info { color: #28527a; background: #eef5fc; border-color: #d6e6f7; }
```

Confira:

```bash
cd "$APP/frontend" && grep -cE "users-(drawer|form|password|confirmation|toast|overlay|identity-card|access-action|choice|prefixed|reset-panel|field|icon-button|dialog-actions|action|table__actions|button--danger|status--(pending|disabled|unknown)|stat--disabled)|is-disabled" src/features/users/users.css
grep -rnE "UserFormDrawer|StatusBadge|ConfirmDialog|UsersToast|generateTemporaryPassword|validateUserForm|statusLabel" src
```

Expected: `0`; o segundo `grep` não imprime nada.

- [ ] **Step 8: Compilar, rodar os testes e fazer o commit**

```bash
cd "$APP" && docker compose exec -T frontend npx vite build --outDir /tmp/om-build-check --emptyOutDir 2>&1 | tail -3
cd "$APP/frontend" && npm test 2>&1 | grep -E "^# (pass|fail)"
```

Expected: `✓ built in`; `# pass 26`, `# fail 0` (27 − 9 + 8).

```bash
cd "$APP" && git add -A frontend/src/features/users
git commit -m "feat(frontend): Gestão de Usuários somente leitura com atalho para o console do Keycloak

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: Compose, `.env.example` e documentação do app sem Keycloak embutido

**Files:**
- Modify: `docker-compose.yml`
- Modify: `.env.example`
- Modify: `SEGURANCA_E_AUTENTICACAO.md`
- Delete: `keycloak/` (o tema já está no `gentil-identity` desde a Task 1)

**Interfaces:**
- Consumes: variáveis da Task 9 (`SESSION_ENCRYPTION_KEY`, `KEYCLOAK_CONSOLE_URL`).
- Produces: compose do app com `db`, `backend`, `frontend`, `n8n` e `qa`. O backend exige `OIDC_CLIENT_SECRET` e `SESSION_ENCRYPTION_KEY` no `.env`.

> Nesta tarefa **não** rode `docker compose up`: os containers antigos continuam no ar até a Task 13.

- [ ] **Step 1: Remover os serviços do Keycloak do `docker-compose.yml`**

1. Apague do comentário `# ── Banco de dados do Keycloak (isolado)` até a linha anterior a `# ── Backend (FastAPI)`. Isso tira os serviços `keycloak-db`, `keycloak` e `keycloak-bootstrap`.
2. Em `volumes:` (fim do arquivo), apague `keycloak_postgres_data:`.
3. No `backend`, troque o trecho de `# OIDC — usa localhost:8081 ...` até `DEV_ADMIN_EMAIL: ...` (inclusive) por:

```yaml
      # OIDC — Keycloak do projeto gentil-identity (fora deste compose).
      # DEV: localhost:8081 é o issuer que o Keycloak coloca nos tokens; o backend
      # alcança o host pelo extra_hosts (localhost → host-gateway).
      OIDC_ISSUER_URL: ${OIDC_ISSUER_URL:-http://localhost:8081/realms/gentil-dev}
      OIDC_CLIENT_ID: ${OIDC_CLIENT_ID:-chat-bot-om-bff}
      OIDC_CLIENT_SECRET: ${OIDC_CLIENT_SECRET:?defina OIDC_CLIENT_SECRET no .env}
      OIDC_REDIRECT_URI: ${OIDC_REDIRECT_URI:-http://localhost:5173/auth/callback}
      OIDC_POST_LOGOUT_REDIRECT_URI: ${OIDC_POST_LOGOUT_REDIRECT_URI:-http://localhost:5173/login}
      KEYCLOAK_CONSOLE_URL: ${KEYCLOAK_CONSOLE_URL:-http://localhost:8081/admin/gentil-dev/console/}
      SESSION_SECRET: ${SESSION_SECRET:?defina SESSION_SECRET no .env}
      SESSION_ENCRYPTION_KEY: ${SESSION_ENCRYPTION_KEY:?defina SESSION_ENCRYPTION_KEY no .env}
      SESSION_COOKIE_SECURE: ${SESSION_COOKIE_SECURE:-false}
      SESSION_IDLE_TIMEOUT_MINUTES: ${SESSION_IDLE_TIMEOUT_MINUTES:-30}
      SESSION_ABSOLUTE_TIMEOUT_HOURS: ${SESSION_ABSOLUTE_TIMEOUT_HOURS:-8}
      FRONTEND_ORIGINS: ${FRONTEND_ORIGINS:-http://localhost:5173,http://127.0.0.1:5173,http://frontend:5173}
```

(A linha `TZ: America/Fortaleza` que vinha depois fica.)

4. No `depends_on` do `backend`, apague o item `keycloak-bootstrap` e sua condição (fica só `db`).
5. Troque o comentário acima de `extra_hosts` do backend por:

```yaml
    # Permite que o container resolva "localhost" como o host Docker para
    # alcançar o Keycloak do gentil-identity em localhost:8081 (DEV).
```

- [ ] **Step 2: Validar o compose sem subir nada**

```bash
cd "$APP" && SESSION_ENCRYPTION_KEY=validacao docker compose config --quiet && echo "compose ok"
docker compose config --services
grep -nE "keycloak|KEYCLOAK_ADMIN|DEV_|BOOTSTRAP" docker-compose.yml
```

Expected: `compose ok`; serviços `db`, `backend`, `frontend`, `n8n` (e `qa` só com o profile); o `grep` mostra apenas as linhas de `KEYCLOAK_CONSOLE_URL`.

- [ ] **Step 3: Reescrever o trecho de identidade do `.env.example`**

Troque do comentário `# ── OIDC / Keycloak` até a linha `DEV_GUEST_PASSWORD=...` (inclusive) por:

```dotenv
# ── OIDC / Keycloak (projeto gentil-identity) ──────────────────────────────────
# O Keycloak roda fora deste compose. Migrar para o ambiente da Gentil = trocar
# estes valores; nenhuma mudança de código.
OIDC_ISSUER_URL=http://localhost:8081/realms/gentil-dev
OIDC_CLIENT_ID=chat-bot-om-bff
# Mesmo valor de CHATBOT_CLIENT_SECRET no .env do gentil-identity.
OIDC_CLIENT_SECRET=troque_este_secret_oidc
OIDC_REDIRECT_URI=http://localhost:5173/auth/callback
# Após o logout o usuário volta para a página /login do frontend.
OIDC_POST_LOGOUT_REDIRECT_URI=http://localhost:5173/login
# Link "Gerenciar no Keycloak", exibido só a quem tem users.view.
KEYCLOAK_CONSOLE_URL=http://localhost:8081/admin/gentil-dev/console/

# ── Sessão ─────────────────────────────────────────────────────────────────────
# Gere: python -c "import secrets; print(secrets.token_urlsafe(64))"
SESSION_SECRET=troque_este_secret_de_sessao
# Cifra o refresh token guardado na sessão. Gere:
# python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
SESSION_ENCRYPTION_KEY=
SESSION_COOKIE_SECURE=false
SESSION_IDLE_TIMEOUT_MINUTES=30
SESSION_ABSOLUTE_TIMEOUT_HOURS=8

# ── CORS ───────────────────────────────────────────────────────────────────────
FRONTEND_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://frontend:5173
```

(O bloco `# ── Frontend` que vem depois fica igual.)

- [ ] **Step 4: Atualizar `SEGURANCA_E_AUTENTICACAO.md`**

Mantenha como estão as seções `## CSRF`, `## Gateway do assistente`, `## Conversas no PostgreSQL`, `## Proteção do n8n`, `## Auditoria` e `## Headers de segurança`. Substitua todo o resto pelo conteúdo abaixo, nesta ordem, encaixando as seções mantidas onde está indicado:

````markdown
# Segurança e Autenticação — Chat-bot O&M

## Visão geral da arquitetura

```
 gentil-identity (repositório próprio)          Chat-bot O&M (este repositório)
 ┌──────────────────────────────┐               ┌────────────────────────────────┐
 │ Keycloak 26 (modo produção)  │◀── OIDC ─────▶│ backend FastAPI (BFF)          │
 │ PostgreSQL próprio           │  código+PKCE, │  - valida tokens pelo JWKS     │
 │ tema gentil-om               │  renovação,   │  - aplica a permissão por rota │
 │ Mailpit (somente DEV)        │  JWKS         │  - sessão server-side + cookie │
 └──────────────────────────────┘── backchannel ▶ frontend React (só exibe)      │
                                     logout      └────────────────────────────────┘
```

- O Keycloak não roda neste compose: fica no projeto `gentil-identity` (pasta irmã deste repositório).
- O app não guarda nenhuma credencial administrativa do Keycloak.
- Perfis, permissões, cadastro, liberação e bloqueio são decididos no Keycloak. O backend aplica o que vem no token assinado; o frontend só exibe.

## Separação de responsabilidades

| Componente | Responsabilidade |
|---|---|
| Keycloak (`gentil-identity`) | usuários, senhas, MFA, autocadastro, perfis, permissões, grupos, bloqueio, sessões SSO |
| Backend | validar tokens, manter a sessão, exigir a permissão de cada rota, auditoria, limites de IA |
| Frontend | exibir o que `/auth/me` informa; nenhuma regra de acesso |

## Provedor de identidade (`gentil-identity`)

- Subir, parar, backup, e-mails do DEV (Mailpit) e gestão de acesso: `../gentil-identity/docs/OPERACAO.md`.
- Usuários DEV: `admin.om`, `analista.om`, `gerente.om`, `diretor.om`, `convidado.om`. As senhas ficam nas variáveis `DEV_*_PASSWORD` do `.env` do `gentil-identity`.
- Tema de login `gentil-om`: `../gentil-identity/themes/gentil-om`.
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
- A cada 5 min de uso, o backend renova os tokens no Keycloak e atualiza o retrato. Uma trava por sessão (`SELECT ... FOR UPDATE`) impede que duas abas usem o mesmo refresh token.
- Renovação recusada (conta bloqueada, sessão encerrada, acesso retirado) → sessão revogada e 401.
- Keycloak fora do ar → o retrato atual vale por até 15 min, com uma tentativa a cada 30 s. Depois disso, a sessão cai.
- Ociosidade de 30 min e duração máxima de 8 h, como antes.

<!-- aqui entra a seção "## CSRF", sem alteração -->

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

<!-- aqui entram, sem alteração, "## Gateway do assistente", "## Conversas no PostgreSQL",
     "## Proteção do n8n", "## Auditoria" e "## Headers de segurança" -->

## Migração para o Keycloak da Gentil

Roteiro e checklist obrigatório: `../gentil-identity/docs/MIGRACAO_TI.md`. No app, basta atualizar o `.env`:
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
````

- [ ] **Step 5: Remover a pasta `keycloak/` e fazer o commit**

```bash
cd "$APP" && git rm -r -q keycloak
git add docker-compose.yml .env.example SEGURANCA_E_AUTENTICACAO.md
git commit -m "chore: Keycloak sai do compose do app (agora no gentil-identity)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 13: Virada no ambiente DEV (passos destrutivos, com confirmação)

**Files:** nenhum arquivo versionado. Muda o `.env` local do app e o do `gentil-identity`, os containers, um volume e as tabelas de identidade.

**Interfaces:**
- Consumes: `backend/scripts/reset_identity.sql` (Task 7), compose novo (Task 12), `gentil-identity` (Tasks 1–4).
- Produces: `gentil-identity` em `http://localhost:8081`; app no ar usando o Keycloak externo; dados de negócio intactos.

> Com o compose da Task 12, todo comando `docker compose` no app exige `SESSION_ENCRYPTION_KEY` no `.env`. Por isso o `.env` é atualizado primeiro (Step 2): os containers antigos continuam rodando com o ambiente de quando foram criados até o Step 8.

- [ ] **Step 1: ⚠ Pedir confirmação ao usuário**

Mostre ao usuário, antes de qualquer comando, o que será feito:
1. `.env` do app atualizado (segredo do client, chave nova, variáveis antigas removidas);
2. backup completo do banco do app;
3. remoção dos containers antigos do Keycloak e do volume `chat-bot-om_keycloak_postgres_data`;
4. `gentil-identity` passa para a porta 8081;
5. remoção **somente** das tabelas de identidade e acesso (lista do `reset_identity.sql`).

Diga que chamados, Central de Ativos e n8n não são tocados. Siga só com um "sim" explícito. Peça confirmação de novo antes dos Steps 5 e 7.

- [ ] **Step 2: Atualizar o `.env` do app (sem imprimir segredos)**

```bash
cd "$APP" && cp .env "$APP/../backup/chatbot-om.env.antes-keycloak-externo"
"$PY" - <<'EOF'
from pathlib import Path
from cryptography.fernet import Fernet

app_env = Path(".env")
idp_env = dict(
    line.split("=", 1) for line in Path("../gentil-identity/.env").read_text(encoding="utf-8").splitlines()
    if "=" in line and not line.startswith("#")
)
obsolete = ("KEYCLOAK_DB", "KEYCLOAK_ADMIN", "KEYCLOAK_SMTP_", "KEYCLOAK_REALM", "DEV_", "BOOTSTRAP_ADMIN_EMAIL")
values = {
    "OIDC_ISSUER_URL": "http://localhost:8081/realms/gentil-dev",
    "OIDC_CLIENT_SECRET": idp_env["CHATBOT_CLIENT_SECRET"],
    "SESSION_ENCRYPTION_KEY": Fernet.generate_key().decode(),
    "KEYCLOAK_CONSOLE_URL": "http://localhost:8081/admin/gentil-dev/console/",
}
out, seen = [], set()
for line in app_env.read_text(encoding="utf-8").splitlines():
    key = line.split("=", 1)[0]
    if key.startswith(obsolete):
        continue
    if key in values:
        out.append(f"{key}={values[key]}")
        seen.add(key)
    else:
        out.append(line)
out += [f"{key}={value}" for key, value in values.items() if key not in seen]
app_env.write_text("\n".join(out) + "\n", encoding="utf-8")
print("atualizadas:", ", ".join(values))
EOF
grep -cE "^(KEYCLOAK_DB|KEYCLOAK_ADMIN|KEYCLOAK_SMTP|KEYCLOAK_REALM|DEV_|BOOTSTRAP)" .env
docker compose config --quiet && echo "compose ok"
```

Expected: `atualizadas: OIDC_ISSUER_URL, OIDC_CLIENT_SECRET, SESSION_ENCRYPTION_KEY, KEYCLOAK_CONSOLE_URL`, depois `0` e `compose ok`. A cópia do `.env` antigo fica em `../backup/` (fora do repositório).

- [ ] **Step 3: Backup do banco do app e contagem dos dados de negócio**

```bash
cd "$APP" && STAMP=$(date +%Y%m%d-%H%M%S)
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$APP/../backup/chatbot-om-antes-keycloak-externo-$STAMP.dump"
ls -la "$APP/../backup" | tail -3
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At' <<'SQL' | tee "$APP/../backup/contagem-antes.txt"
SELECT 'services', count(*) FROM services
UNION ALL SELECT 'uploads', count(*) FROM uploads
UNION ALL SELECT 'asset_stores', count(*) FROM asset_stores
UNION ALL SELECT 'climate_assets', count(*) FROM climate_assets
UNION ALL SELECT 'fire_assets', count(*) FROM fire_assets
UNION ALL SELECT 'water_assets', count(*) FROM water_assets
UNION ALL SELECT 'store_documents', count(*) FROM store_documents;
SQL
```

Expected: arquivo `.dump` com tamanho maior que zero; sete linhas `tabela|quantidade`.

- [ ] **Step 4: Parar o backend do app**

```bash
cd "$APP" && docker compose stop backend
```

- [ ] **Step 5: ⚠ Remover os containers antigos do Keycloak e o volume**

```bash
for svc in keycloak keycloak-bootstrap keycloak-db; do
  docker ps -aq --filter label=com.docker.compose.project=chat-bot-om --filter label=com.docker.compose.service=$svc
done | xargs -r docker rm -f
docker volume ls --format "{{.Name}}" | grep -i keycloak
docker volume rm chat-bot-om_keycloak_postgres_data
```

Expected: IDs dos containers removidos. A listagem mostra `chat-bot-om_keycloak_postgres_data` e `gentil-identity_keycloak_db_data`; este segundo **fica**. O último comando imprime o nome do volume removido.

- [ ] **Step 6: Passar o `gentil-identity` para a porta 8081**

```bash
cd "$IDP" && sed -i 's#^KC_HOSTNAME=.*#KC_HOSTNAME=http://localhost:8081#; s#^KC_PUBLIC_PORT=.*#KC_PUBLIC_PORT=8081#' .env
docker compose up -d --build
until docker compose ps keycloak --format "{{.Status}}" | grep -q healthy; do sleep 5; done
sleep 20 && docker compose ps -a keycloak-config --format "{{.Status}}"
"$PY" scripts/smoke_test.py | tail -1
curl -s http://localhost:8081/realms/gentil-dev/.well-known/openid-configuration | grep -o '"issuer":"[^"]*"'
```

Expected: `Exited (0) ...`, `0 falha(s).` e `"issuer":"http://localhost:8081/realms/gentil-dev"`.

- [ ] **Step 7: ⚠ Recriar só as tabelas de identidade e acesso**

```bash
cd "$APP" && docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1' < backend/scripts/reset_identity.sql
```

Expected: `BEGIN`, `DROP TABLE`, `DROP TYPE`, `DROP TYPE`, `COMMIT`.

- [ ] **Step 8: Subir o app e conferir o backend**

```bash
cd "$APP" && docker compose up -d --build --remove-orphans && docker compose restart frontend
docker compose ps --format "table {{.Service}}\t{{.Status}}"
docker compose logs backend --tail 40 | grep -iE "error|traceback|SESSION_ENCRYPTION_KEY"; echo "fim"
docker compose exec -T backend python -c "import httpx; print(httpx.get('http://localhost:8081/realms/gentil-dev/.well-known/openid-configuration').json()['issuer'])"
```

Expected: `db`, `backend`, `frontend` e `n8n` com `Up`; nenhuma linha antes de `fim`; `http://localhost:8081/realms/gentil-dev`.

- [ ] **Step 9: Conferir que os dados de negócio ficaram intactos**

```bash
cd "$APP" && docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At' <<'SQL' > "$APP/../backup/contagem-depois.txt"
SELECT 'services', count(*) FROM services
UNION ALL SELECT 'uploads', count(*) FROM uploads
UNION ALL SELECT 'asset_stores', count(*) FROM asset_stores
UNION ALL SELECT 'climate_assets', count(*) FROM climate_assets
UNION ALL SELECT 'fire_assets', count(*) FROM fire_assets
UNION ALL SELECT 'water_assets', count(*) FROM water_assets
UNION ALL SELECT 'store_documents', count(*) FROM store_documents;
SQL
diff "$APP/../backup/contagem-antes.txt" "$APP/../backup/contagem-depois.txt" && echo "dados de negócio preservados"
docker volume ls --format "{{.Name}}" | grep -E "asset_documents_data|n8n_data"
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT count(*) FROM oidc_login_requests"'
```

Expected: `dados de negócio preservados`; os dois volumes listados; `0` (tabela nova criada pelo backend).

- [ ] **Step 10: Conferir que o Keycloak alcança o backchannel do app**

```bash
cd "$IDP" && docker compose exec -T keycloak bash -c 'exec 3<>/dev/tcp/host.docker.internal/8040 && printf "POST /auth/backchannel-logout HTTP/1.1\r\nHost: host.docker.internal\r\nContent-Type: application/x-www-form-urlencoded\r\nContent-Length: 14\r\nConnection: close\r\n\r\nlogout_token=x" >&3 && head -1 <&3'
```

Expected: `HTTP/1.1 400 Bad Request` (chegou ao backend, que recusou o token falso).

- [ ] **Step 11: Login manual rápido**

Abra `http://localhost:5173` e entre com `admin.om` (senha `DEV_ADMIN_PASSWORD` do `.env` do `gentil-identity`). Confira que o app abre e que "Gestão de Usuários" mostra o botão "Gerenciar no Keycloak". Esta tarefa não tem commit: só mudaram arquivos locais.

---

### Task 14: Ponta a ponta no navegador e verificações finais

**Files:**
- Create: `$IDP/scripts/e2e_flow.py`

**Interfaces:**
- Consumes: ambiente completo da Task 13; `scripts/kcadmin.py`; Mailpit em `http://localhost:8025`; Google Chrome instalado (Playwright com `channel="chrome"`, porque o Chromium do Playwright falha no caminho longo desta máquina).
- Produces: `e2e-shots/*.png` (ignorado pelo git) e o relatório final.

- [ ] **Step 1: Criar o venv de E2E (fora do app; nenhuma dependência nova no Chat-bot O&M)**

```bash
cd "$IDP" && "$PY" -m venv .venv-e2e && .venv-e2e/Scripts/python.exe -m pip install --quiet playwright
.venv-e2e/Scripts/python.exe -c "import playwright; print('playwright ok')"
```

Expected: `playwright ok`.

- [ ] **Step 2: Escrever `scripts/e2e_flow.py`**

```python
"""
Teste ponta a ponta no navegador (DEV).

autocadastro → e-mail no Mailpit → "conta não liberada" → gestor vê a conta
→ gestor libera (grupo) → login com acesso → gestor retira do grupo → acesso cai
em até 5 min → gestor bloqueia e encerra as sessões → sessão do app cai na hora
→ logout volta ao /login.

Pré-requisitos: gentil-identity e Chat-bot O&M no ar; Google Chrome instalado.
Uso: .venv-e2e/Scripts/python.exe scripts/e2e_flow.py   (leva cerca de 7 minutos)
Screenshots em e2e-shots/ (desktop 1440×900 e mobile 390×844).
"""

from __future__ import annotations

import json
import re
import secrets
import sys
import time
import urllib.parse
import urllib.request

from playwright.sync_api import Browser, Page, expect, sync_playwright

from kcadmin import ROOT, AdminError, KeycloakAdmin, load_env, password_token

APP = "http://localhost:5173"
KC = "http://localhost:8081"
MAILPIT = "http://localhost:8025"
SHOTS = ROOT / "e2e-shots"
ANALYST_GROUP = "Chat-bot O&M · Analistas"
DESKTOP = {"width": 1440, "height": 900}
MOBILE = {"width": 390, "height": 844}
ACCESS_REMOVAL_LIMIT_SECONDS = 330  # retrato de 5 min + folga do intervalo de consulta


def step(message: str) -> None:
    print(f"==> {message}", flush=True)


def shot(page: Page, name: str) -> None:
    SHOTS.mkdir(exist_ok=True)
    page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=True)


def me_status(page: Page) -> int:
    return page.request.get(f"{APP}/auth/me").status


# ── Ações do gestor de acesso (mesmas permissões do console do realm) ─────────

def gestor(env: dict) -> KeycloakAdmin:
    token = password_token(KC, env["REALM_NAME"], "admin-cli", "admin.om", env["DEV_ADMIN_PASSWORD"])
    return KeycloakAdmin(KC, realm=env["REALM_NAME"], token=token)


def set_group(env: dict, username: str, *, member: bool) -> None:
    kc = gestor(env)
    user = kc.user_by_username(username)
    group = next(g for g in kc.get("/groups", search=ANALYST_GROUP) if g["name"] == ANALYST_GROUP)
    path = f"/users/{user['id']}/groups/{group['id']}"
    if member:
        kc.put(path, None)
    else:
        kc.delete(path)


def set_enabled(env: dict, username: str, enabled: bool, *, sign_out: bool = False) -> None:
    kc = gestor(env)
    user = kc.user_by_username(username)
    user["enabled"] = enabled
    kc.put(f"/users/{user['id']}", user)
    if sign_out:
        kc.post(f"/users/{user['id']}/logout")  # "Sign out" do console: dispara o backchannel logout


def cleanup(env: dict, username: str) -> None:
    try:
        kc = gestor(env)
        user = kc.user_by_username(username)
        if user:
            kc.delete(f"/users/{user['id']}")
            print(f"    usuário {username} removido do Keycloak")
    except AdminError as exc:
        print(f"    aviso: não foi possível remover {username}: {exc}")


# ── Navegador ─────────────────────────────────────────────────────────────────

def mail_link(email: str, timeout: int = 60) -> str:
    deadline = time.time() + timeout
    query = urllib.parse.quote(f'to:"{email}"')
    while time.time() < deadline:
        found = json.load(urllib.request.urlopen(f"{MAILPIT}/api/v1/search?query={query}"))
        if found.get("messages"):
            message = json.load(urllib.request.urlopen(f"{MAILPIT}/api/v1/message/{found['messages'][0]['ID']}"))
            match = re.search(r"https?://[^\s\"'<>]+/login-actions/action-token\?[^\s\"'<>]+", message.get("Text", ""))
            if match:
                return match.group(0).replace("&amp;", "&")
        time.sleep(2)
    raise AssertionError(f"e-mail de confirmação não chegou para {email}")


def login(page: Page, username: str, password: str) -> None:
    page.goto(f"{APP}/login")
    page.get_by_role("button", name=re.compile(r"^Entrar")).click()
    page.wait_for_url(re.compile(rf"^({re.escape(KC)}/realms/|{re.escape(APP)}/$)"))
    if page.url.startswith(KC):
        page.fill("#username", username)
        page.fill("#password", password)
        page.click("#kc-login")
    page.wait_for_url(f"{APP}/")
    assert me_status(page) == 200, f"sessão de {username} não foi criada"


def check_users_page(page: Page, env: dict, username: str, expected_profile: str, shot_name: str) -> None:
    login(page, "admin.om", env["DEV_ADMIN_PASSWORD"])
    page.click(".user-menu__trigger")
    page.get_by_role("menuitem", name="Gestão de Usuários").click()
    expect(page.get_by_role("heading", name="Gestão de Usuários")).to_be_visible()
    expect(page.locator("tr", has_text=f"@{username}")).to_contain_text(expected_profile)
    link = page.get_by_role("link", name=re.compile("Gerenciar no Keycloak"))
    expect(link).to_have_attribute("href", f"{KC}/admin/{env['REALM_NAME']}/console/")
    shot(page, shot_name)


def run(browser: Browser, env: dict, user: dict) -> None:
    page = browser.new_context(viewport=DESKTOP, locale="pt-BR").new_page()

    step("1. /login do app e cadastro no Keycloak")
    page.goto(f"{APP}/login")
    shot(page, "01-login-app-desktop")
    page.get_by_role("button", name=re.compile("Criar conta")).click()
    page.wait_for_selector("#kc-register-form")
    shot(page, "02-cadastro-desktop")
    for field, value in (("firstName", "Teste"), ("lastName", "E2E"), ("email", user["email"]),
                         ("username", user["username"]), ("password", user["password"]),
                         ("password-confirm", user["password"])):
        page.fill(f"#{field}", value)
    page.click("button[name=register]")
    expect(page.get_by_text("Confirme seu e-mail")).to_be_visible()
    shot(page, "03-confirme-email")

    step("2. confirmação pelo link do e-mail (Mailpit) → conta não liberada")
    page.goto(mail_link(user["email"]))
    proceed = page.locator("a[href*='login-actions']")
    if page.url.startswith(KC) and proceed.count():
        proceed.first.click()  # variante do Keycloak que pede um clique para continuar
    expect(page.get_by_text("Sua conta ainda não foi liberada")).to_be_visible(timeout=30_000)
    assert me_status(page) == 401
    shot(page, "04-conta-nao-liberada")

    step("3. gestor vê a conta nova sem perfil")
    admin = browser.new_context(viewport=DESKTOP, locale="pt-BR").new_page()
    check_users_page(admin, env, user["username"], "Sem perfil", "05-gestao-usuarios-desktop")
    admin.context.close()

    step("4. gestor libera (grupo Analistas) → login com acesso")
    set_group(env, user["username"], member=True)
    login(page, user["username"], user["password"])
    assert page.request.get(f"{APP}/auth/me").json()["profile"] == "ANALISTA"
    shot(page, "06-app-analista")

    step("5. gestor retira do grupo → acesso cai em até 5 min")
    set_group(env, user["username"], member=False)
    started = time.time()
    while me_status(page) == 200:
        assert time.time() - started < ACCESS_REMOVAL_LIMIT_SECONDS, "o acesso não caiu em 5 minutos"
        time.sleep(15)
    print(f"    acesso retirado em {time.time() - started:.0f} s")

    step("6. gestor libera de novo, depois bloqueia e encerra as sessões → queda imediata")
    set_group(env, user["username"], member=True)
    login(page, user["username"], user["password"])
    set_enabled(env, user["username"], False, sign_out=True)
    started = time.time()
    while me_status(page) == 200:
        assert time.time() - started < 10, "o backchannel logout não derrubou a sessão"
        time.sleep(1)
    print(f"    sessão encerrada em {time.time() - started:.1f} s")

    step("7. desbloqueia → logout pelo menu volta ao /login")
    set_enabled(env, user["username"], True)
    login(page, user["username"], user["password"])
    page.click(".user-menu__trigger")
    page.get_by_role("menuitem", name="Sair").click()
    page.wait_for_url(f"{APP}/login")
    expect(page.get_by_text("Você saiu com segurança.")).to_be_visible()
    assert me_status(page) == 401
    shot(page, "07-logout")

    step("8. telas no mobile")
    mobile = browser.new_context(viewport=MOBILE, locale="pt-BR", is_mobile=True, has_touch=True).new_page()
    mobile.goto(f"{APP}/login")
    shot(mobile, "08-login-app-mobile")
    mobile.get_by_role("button", name=re.compile("Criar conta")).click()
    mobile.wait_for_selector("#kc-register-form")
    shot(mobile, "09-cadastro-mobile")
    mobile.goto(f"{APP}/login")
    mobile.get_by_role("button", name=re.compile(r"^Entrar")).click()
    mobile.wait_for_selector("#kc-login")
    shot(mobile, "10-login-keycloak-mobile")
    check_users_page(mobile, env, user["username"], "Analista", "11-gestao-usuarios-mobile")

    step("9. console do realm para o gestor de acesso")
    console = browser.new_context(viewport=DESKTOP, locale="pt-BR").new_page()
    console.goto(f"{KC}/admin/{env['REALM_NAME']}/console/")
    console.fill("#username", "admin.om")
    console.fill("#password", env["DEV_ADMIN_PASSWORD"])
    console.click("#kc-login")
    expect(console.get_by_text(re.compile("^(Users|Usuários)$")).first).to_be_visible(timeout=30_000)
    shot(console, "12-console-gestor")


def main() -> int:
    env = load_env()
    stamp = time.strftime("%H%M%S")
    user = {"username": f"e2e.{stamp}", "email": f"e2e.{stamp}@exemplo.local",
            "password": secrets.token_urlsafe(18)}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        try:
            run(browser, env, user)
        finally:
            cleanup(env, user["username"])
            browser.close()
    print("\nE2E concluído com sucesso.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Rodar o E2E**

```bash
cd "$IDP" && .venv-e2e/Scripts/python.exe scripts/e2e_flow.py 2>&1 | tail -25
```

Expected: as etapas `==> 1.` a `==> 9.`, `acesso retirado em N s` com N ≤ 330, `sessão encerrada em N s` com N < 10, `usuário e2e.<hora> removido do Keycloak` e `E2E concluído com sucesso.`. Se uma etapa falhar, trate como bug: investigue a causa (logs em `docker compose logs backend` e `docker compose -f "$IDP/docker-compose.yml" logs keycloak`), corrija com teste quando for código do app e rode de novo. Nunca afrouxe as asserções.

- [ ] **Step 4: Revisão visual dos screenshots**

Abra cada arquivo de `$IDP/e2e-shots/` (01 a 12) e confira:
- mesma identidade visual do login aprovado (cartão, fonte Manrope, cores e botões) nas telas do Keycloak, inclusive cadastro e "Confirme seu e-mail";
- textos em pt-BR, sem chave de mensagem crua (por exemplo, `omRegisterSubtitle`);
- sem rolagem horizontal nem texto cortado no mobile;
- Gestão de Usuários sem botões de edição, com os selos "Sem perfil"/perfil e "Sessão ativa"/"Sem sessão".

Corrija o que estiver fora do padrão. CSS do tema: `$IDP/themes/.../gentil-om.css`, com `docker compose up -d --build keycloak`. CSS do app: `users.css` e `auth.css`, com `docker compose restart frontend`. Depois rode o Step 3 de novo e faça o commit das correções no repositório correspondente.

- [ ] **Step 5: Verificações finais**

```bash
cd "$APP/backend" && "$PY" -m pytest -q 2>&1 | tail -1
cd "$APP/frontend" && npm test 2>&1 | grep -E "^# (pass|fail)"
cd "$IDP" && "$PY" scripts/smoke_test.py | tail -1
cd "$APP" && docker compose down && docker compose up -d
cd "$IDP" && docker compose down && docker compose up -d
until docker compose ps keycloak --format "{{.Status}}" | grep -q healthy; do sleep 5; done
"$PY" scripts/smoke_test.py | tail -1
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5173/login
curl -s -o /dev/null -w "%{http_code} %{redirect_url}\n" http://localhost:5173/auth/login
```

Expected: `303 passed`; `# pass 26` e `# fail 0`; `0 falha(s).` antes e depois do ciclo `down`/`up` (sem `-v`: dados preservados); `200`; `302 http://localhost:8081/realms/gentil-dev/protocol/openid-connect/auth?...`.

- [ ] **Step 6: Commit do E2E e relatório final**

```bash
cd "$IDP" && git add scripts/e2e_flow.py && git commit -m "test: fluxo ponta a ponta de cadastro, liberação, bloqueio e logout

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
cd "$APP" && git status --short && git log --oneline main..HEAD
```

No relatório ao usuário, informe:
- o que mudou em cada repositório;
- os resultados dos testes (backend, frontend, smoke e E2E, com os tempos medidos de queda do acesso);
- como entrar (`admin.om` + `DEV_ADMIN_PASSWORD` do `.env` do `gentil-identity`) e onde fica o console;
- que bloquear na hora = desligar **Enabled** e encerrar as sessões; só desligar vale em até 5 min;
- que a restrição de domínio (`scripts/restrict_email_domain.py`) é obrigatória antes de produção;
- que o registro local da conta de teste do E2E continua em `app_users` (o Keycloak já não tem a conta);
- que a branch `feature/keycloak-externo` está pronta para revisão e merge.
