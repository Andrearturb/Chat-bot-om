# Sem gestão de usuários no Chat-bot O&M — Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tirar do Chat-bot O&M toda a gestão de usuários (tela, rota, permissão, link para o console do Keycloak) — o app fica isolado, usando só login, logout, cadastro e os papéis que vêm no token.

**Architecture:** Remoção pura: nenhuma tela, rota ou variável nova. `/auth/me` para de carregar `keycloak_console_url`; a permissão `users.view` some do catálogo; a rota `/users` deixa de existir. O texto de "conta não liberada" já não cita console nem link — não muda.

**Tech Stack:** FastAPI/SQLAlchemy (backend), React 19 + Vite (frontend), pytest, `node --test`, oxlint.

**Spec:** `../keycloak-central/docs/superpowers/specs/2026-10-01-acessos-isolados-design.md` (Parte 3 — Chat-bot O&M).

## Global Constraints

- Isolamento: o app não ganha nenhum link novo (nem para o Painel, nem para o Keycloak) — só remove o que já existia.
- `login`, `logout`, `/auth/register` (cadastro pela página do Keycloak) e os papéis do token continuam exatamente como estão.
- `AccountNotReleased.jsx` e `authErrors.js` não mudam de texto (já não citam console nem link).
- Testes do backend: `cd backend && ../.venv/Scripts/python.exe -m pytest -q`. Frontend: `docker exec chatbot-frontend npm test`; lint: `docker exec chatbot-frontend npx oxlint`; build: `docker exec chatbot-frontend npm run build`.
- Depois de mudar código do backend, `docker compose up -d --build backend` antes de verificar no navegador.
- Commits em português, terminados com `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.

## Review Focus

1. Alguém com `users.view` guardado numa sessão antiga (criada antes desta mudança): a rota `/users` precisa sumir mesmo assim (404), não travar por causa de uma permissão que o retrato ainda carrega.
2. `/auth/me` não pode quebrar para ninguém: o campo some da resposta, mas a resposta continua 200 com todo o resto.
3. O item "Gestão de Usuários" não pode sobrar visível em nenhum lugar (menu do usuário, Configurações) mesmo para quem tenha a permissão antiga no token.
4. Nenhum arquivo deixa de referência morta: nada mais importa `features/users/`, nada mais lê `KEYCLOAK_CONSOLE_URL`.
5. O build do frontend não pode falhar por import quebrado depois de apagar `features/users/`.

---

## Mapa de arquivos

**Backend (`backend/`):** remover `app/api/routes/users.py`, `tests/test_users_listagem.py`; modificar `app/main.py`, `app/services/permissions.py`, `app/core/config.py`, `app/api/routes/auth.py`, `tests/api_harness.py`, `tests/oidc_fake.py`, `tests/test_permissions.py`, `tests/test_auth_flow.py`, `tests/test_api_security.py`.

**Frontend (`frontend/src/`):** remover `features/users/` (inteiro); modificar `App.jsx`, `features/auth/AuthProvider.jsx`, `features/auth/UserMenu.jsx`, `features/settings/SettingsModal.jsx`, `features/settings/settings.css`; modificar `frontend/package.json`.

**Config e docs:** modificar `docker-compose.yml`, `.env.example`, `SEGURANCA_E_AUTENTICACAO.md`.

---

### Task 1: Remover a gestão de usuários do backend

**Files:**
- Delete: `backend/app/api/routes/users.py`, `backend/tests/test_users_listagem.py`
- Modify: `backend/app/main.py`, `backend/app/services/permissions.py`, `backend/app/core/config.py`, `backend/app/api/routes/auth.py`, `backend/tests/api_harness.py`, `backend/tests/oidc_fake.py`, `backend/tests/test_permissions.py`, `backend/tests/test_auth_flow.py`, `backend/tests/test_api_security.py`

**Interfaces:**
- Produces: `GET /users` → 404; `GET /auth/me` sem o campo `keycloak_console_url`; `"users.view"` fora de `app.services.permissions.PERMISSIONS` (16 permissões).

- [ ] **Step 1: Escrever os testes que vão falhar**

Em `backend/tests/test_permissions.py`, substitua `test_catalogo_tem_17_permissoes_com_users_view`:

```python
def test_catalogo_tem_16_permissoes_sem_users_view():
    assert len(PERMISSIONS) == 16
    assert "users.view" not in PERMISSIONS
    assert "users.manage" not in PERMISSIONS
```

Em `backend/tests/test_auth_flow.py`, na função `test_callback_cria_sessao_com_cookie_seguro_e_sem_tokens_no_navegador`, troque:

```python
    me = me_response.json()
    assert set(me) == {"id", "email", "username", "display_name", "profile", "profile_display", "profiles",
                       "permissions", "csrf_token", "keycloak_console_url", "ai_usage"}
    assert me["profile"] == "ANALISTA" and me["profile_display"] == "Analista"
    assert me["profiles"] == ["ANALISTA"] and "assets.create" in me["permissions"]
    assert me["keycloak_console_url"] is None
```

por:

```python
    me = me_response.json()
    assert set(me) == {"id", "email", "username", "display_name", "profile", "profile_display", "profiles",
                       "permissions", "csrf_token", "ai_usage"}
    assert me["profile"] == "ANALISTA" and me["profile_display"] == "Analista"
    assert me["profiles"] == ["ANALISTA"] and "assets.create" in me["permissions"]
```

Ainda em `backend/tests/test_auth_flow.py`, apague inteiras as duas funções (de `def test_sem_users_view_nao_recebe_link_do_console_configurado` até o fim de `test_quem_tem_users_view_recebe_o_link_do_console`, inclusive a linha em branco entre elas e a linha em branco antes de `def test_replay_do_callback_nao_cria_segunda_sessao`):

```python
def test_sem_users_view_nao_recebe_link_do_console_configurado(client, provider, monkeypatch):
    monkeypatch.setattr(config, "KEYCLOAK_CONSOLE_URL", "http://kc.test/admin/gentil-dev/console/")
    _login(client, provider, roles=ANALISTA)
    assert client.get("/auth/me").json()["keycloak_console_url"] is None


def test_quem_tem_users_view_recebe_o_link_do_console(client, provider, monkeypatch):
    monkeypatch.setattr(config, "KEYCLOAK_CONSOLE_URL", "http://kc.test/admin/gentil-dev/console/")
    _login(client, provider, sub="adm", roles=ADMINISTRADOR)
    me = client.get("/auth/me").json()
    assert me["profile"] == "ADMINISTRADOR"
    assert me["keycloak_console_url"] == "http://kc.test/admin/gentil-dev/console/"
```

Acrescente ao final de `backend/tests/test_auth_flow.py` (fora de qualquer classe, no nível do módulo):

```python
def test_rota_de_usuarios_nao_existe_mais(client, provider):
    _login(client, provider)
    assert client.get("/users").status_code == 404
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd backend && ../.venv/Scripts/python.exe -m pytest -q tests/test_permissions.py tests/test_auth_flow.py`
Expected: FAIL (`PERMISSIONS` ainda tem 17 itens com `users.view`; `/auth/me` ainda traz `keycloak_console_url`; `/users` ainda responde 200).

- [ ] **Step 3: Remover a rota e o registro**

Delete `backend/app/api/routes/users.py`.

Em `backend/app/main.py`, remova a linha:

```python
from app.api.routes.users import router as users_router
```

e a linha:

```python
app.include_router(users_router)
```

- [ ] **Step 4: Tirar `users.view` do catálogo de permissões**

Em `backend/app/services/permissions.py`, troque:

```python
    "audit.view", "users.view",
```

por:

```python
    "audit.view",
```

- [ ] **Step 5: Tirar o link do console de `/auth/me`**

Em `backend/app/core/config.py`, remova as três linhas:

```python
# Link do console do realm exibido a quem tem users.view. É só um link: o app
# não guarda credencial administrativa do Keycloak.
KEYCLOAK_CONSOLE_URL = os.getenv("KEYCLOAK_CONSOLE_URL", "").strip()
```

Em `backend/app/api/routes/auth.py`, remova a linha:

```python
        "keycloak_console_url": (config.KEYCLOAK_CONSOLE_URL or None) if "users.view" in permissions else None,
```

- [ ] **Step 6: Limpar os arquivos de teste que citavam a feature removida**

Delete `backend/tests/test_users_listagem.py`.

Em `backend/tests/test_auth_flow.py`, apague a seção inteira "Consulta de usuários" — o cabeçalho e as duas funções, da linha `# ── Consulta de usuários ──...` até a linha em branco antes de `# ── Subida do backend ──` (mantenha as duas linhas em branco entre as seções, como já eram):

```python
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
```

Essas duas funções testavam a rota `/users` que acabou de sair (uma esperava 403, a outra lia a lista) — ficariam quebradas sem sentido. `AppUser` continua importado no arquivo (usado em outros testes, ex.: linha com `_count(AppUser)`), não mexa no import.

Em `backend/tests/test_api_security.py`, na classe `TestPermissions`, remova o método:

```python
    def test_users_sem_permissao_403(self, authed):
        assert authed.get("/users").status_code == 403
```

(fica só `test_analista_nao_deleta_asset` e `test_audit_sem_permissao_403` na classe.)

Em `backend/tests/api_harness.py`, remova a linha:

```python
os.environ["KEYCLOAK_CONSOLE_URL"] = ""
```

Em `backend/tests/oidc_fake.py`, na lista `ADMINISTRADOR`, troque:

```python
ADMINISTRADOR = ["ADMINISTRADOR", "assistant.use", "assistant.history", "indicators.view", "assets.view",
                 "assets.create", "assets.edit", "assets.delete", "assets.import", "documents.view",
                 "documents.upload", "documents.replace", "documents.delete", "audit.view", "users.view",
                 "settings.view", "settings.manage", "sync.tape"]
```

por:

```python
ADMINISTRADOR = ["ADMINISTRADOR", "assistant.use", "assistant.history", "indicators.view", "assets.view",
                 "assets.create", "assets.edit", "assets.delete", "assets.import", "documents.view",
                 "documents.upload", "documents.replace", "documents.delete", "audit.view",
                 "settings.view", "settings.manage", "sync.tape"]
```

- [ ] **Step 7: Rodar e ver passar**

Run: `cd backend && ../.venv/Scripts/python.exe -m pytest -q`
Expected: todos passam, sem avisos.

- [ ] **Step 8: Commit**

```bash
git add backend
git commit -m "feat(backend): remove a gestão de usuários (tela fica só no keycloak-central)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: Remover a gestão de usuários do frontend

**Files:**
- Delete: `frontend/src/features/users/` (diretório inteiro: `UsersPage.jsx`, `api.js`, `userUtils.js`, `users.css`, `users.test.js`, `components/UserVisuals.jsx`)
- Modify: `frontend/src/App.jsx`, `frontend/src/features/auth/AuthProvider.jsx`, `frontend/src/features/auth/UserMenu.jsx`, `frontend/src/features/settings/SettingsModal.jsx`, `frontend/src/features/settings/settings.css`, `frontend/package.json`

**Interfaces:**
- Consumes: Task 1 (`/auth/me` sem `keycloak_console_url`; `/users` 404).
- Produces: nenhum componente ou rota nova acessa `/users` nem referencia `features/users/`.

Sem teste unitário de componente (como no resto do app): a verificação é pelo build, pelo lint e pela checagem no navegador (Task 3).

- [ ] **Step 1: Apagar a pasta da feature**

```bash
git rm -r frontend/src/features/users
```

- [ ] **Step 2: Tirar a entrada do script de testes**

Em `frontend/package.json`, no script `"test"`, remova ` src/features/users/users.test.js` do final da linha.

- [ ] **Step 3: Limpar `App.jsx`**

Remova a linha:

```jsx
const UsersPage = lazy(() => import('./features/users/UsersPage.jsx'))
```

Troque:

```jsx
const VALID_SECTIONS = new Set(['assistant', 'indicators', 'assets', 'users'])
```

por:

```jsx
const VALID_SECTIONS = new Set(['assistant', 'indicators', 'assets'])
```

Troque:

```jsx
  const { auth_status, user, hasPermission, canViewUsers, keycloakConsoleUrl, auth_error, notice } = useAuth()
```

por:

```jsx
  const { auth_status, user, hasPermission, auth_error, notice } = useAuth()
```

Remova a função inteira:

```jsx
  function openUsers() {
    setSettingsOpen(false)
    setHistoryOpen(false)
    setActiveSection('users')
  }

```

Troque:

```jsx
  // Gestão de Usuários (consulta) exige users.view — o backend também valida:
  // se a permissão sair no Keycloak, a tela volta ao assistente.
  const section = activeSection === 'users' && !canViewUsers ? 'assistant' : activeSection
```

por:

```jsx
  const section = activeSection
```

Troque o className do workspace:

```jsx
        <div className={`workspace ${section === 'assistant' && active ? 'workspace--active' : ''} ${section === 'indicators' ? 'workspace--indicators' : ''} ${section === 'assets' ? 'workspace--assets' : ''} ${section === 'users' ? 'workspace--users' : ''}`}>
```

por:

```jsx
        <div className={`workspace ${section === 'assistant' && active ? 'workspace--active' : ''} ${section === 'indicators' ? 'workspace--indicators' : ''} ${section === 'assets' ? 'workspace--assets' : ''}`}>
```

Troque:

```jsx
          historyOpen={historyOpen} settingsOpen={settingsOpen || section === 'users'}
```

por:

```jsx
          historyOpen={historyOpen} settingsOpen={settingsOpen}
```

Troque:

```jsx
              <UserMenu
                onOpenUsers={openUsers}
                onOpenAudit={() => setAuditOpen(true)}
                onOpenSettings={() => setSettingsOpen(true)}
              />
```

por:

```jsx
              <UserMenu
                onOpenAudit={() => setAuditOpen(true)}
                onOpenSettings={() => setSettingsOpen(true)}
              />
```

Troque o final da cadeia de seções (o ramo de "assets" fica, o de "users" sai):

```jsx
          ) : section === 'assets' && canSeeAssets ? (
            <Suspense fallback={<div className="permission-denied" role="status">Carregando ativos...</div>}>
              <AssetsPage />
            </Suspense>
          ) : section === 'users' && canViewUsers ? (
            <Suspense fallback={<div className="permission-denied" role="status">Carregando usuários...</div>}>
              <UsersPage currentUserId={user?.id} consoleUrl={keycloakConsoleUrl} />
            </Suspense>
          ) : null}
```

por:

```jsx
          ) : section === 'assets' && canSeeAssets ? (
            <Suspense fallback={<div className="permission-denied" role="status">Carregando ativos...</div>}>
              <AssetsPage />
            </Suspense>
          ) : null}
```

Troque:

```jsx
      <SettingsModal
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        onOpenUsers={canViewUsers ? openUsers : undefined}
      />
```

por:

```jsx
      <SettingsModal
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
      />
```

- [ ] **Step 4: Limpar `AuthProvider.jsx`**

Remova a linha `keycloakConsoleUrl: null,` de `EMPTY_SESSION`.

Troque, dentro de `refresh()`:

```jsx
        profiles: me.profiles || [],
        permissions: new Set(me.permissions || []),
        keycloakConsoleUrl: me.keycloak_console_url || null,
        csrf_token: me.csrf_token || '',
```

por:

```jsx
        profiles: me.profiles || [],
        permissions: new Set(me.permissions || []),
        csrf_token: me.csrf_token || '',
```

Remova a linha:

```jsx
  const canViewUsers = state.permissions.has('users.view')
```

Troque:

```jsx
    <AuthContext.Provider value={{ ...state, hasPermission, canViewUsers, refresh }}>
```

por:

```jsx
    <AuthContext.Provider value={{ ...state, hasPermission, refresh }}>
```

- [ ] **Step 5: Limpar `UserMenu.jsx`**

Troque:

```jsx
export default function UserMenu({ onOpenUsers, onOpenAudit, onOpenSettings }) {
  const { user, profile, hasPermission, canViewUsers } = useAuth()
```

por:

```jsx
export default function UserMenu({ onOpenAudit, onOpenSettings }) {
  const { user, profile, hasPermission } = useAuth()
```

Remova o bloco:

```jsx
              {canViewUsers && (
                <button className="user-menu__item" role="menuitem" type="button"
                        onClick={() => { setOpen(false); onOpenUsers?.() }}>
                  Gestão de Usuários
                </button>
              )}
```

- [ ] **Step 6: Limpar `SettingsModal.jsx`**

Remova o `if` inteiro do ícone de usuários (em `Icon(...)`):

```jsx
  if (name === 'users') {
    return (
      <svg {...common}>
        <circle cx="9" cy="8" r="3.5" />
        <path d="M2.5 19.5c1-3.4 3.6-5.2 6.5-5.2s5.5 1.8 6.5 5.2" />
        <path d="M16 4.8a3.3 3.3 0 0 1 0 6.4M17.6 14.6c2 .7 3.3 2.3 3.9 4.9" />
      </svg>
    )
  }

```

Troque:

```jsx
function SettingsMenu({ onOpenStatus, onOpenUsers }) {
```

por:

```jsx
function SettingsMenu({ onOpenStatus }) {
```

Remova o bloco do card (de `{onOpenUsers && (` até o `)}` que o fecha):

```jsx
        {onOpenUsers && (
          <button className="settings-option-card" type="button" onClick={onOpenUsers}>
            <span className="settings-option-card__icon settings-option-card__icon--users"><Icon name="users" /></span>
            <span className="settings-option-card__copy">
              <strong>Gestão de Usuários</strong>
              <small>Consulte quem acessa o Chat-bot O&amp;M e abra o console do Keycloak para liberar ou bloquear contas.</small>
            </span>
            <span className="settings-option-card__arrow" aria-hidden="true">›</span>
          </button>
        )}
```

Troque:

```jsx
export default function SettingsModal({ open, onClose, onOpenUsers }) {
```

por:

```jsx
export default function SettingsModal({ open, onClose }) {
```

Troque:

```jsx
  return <SettingsDialog onClose={onClose} onOpenUsers={onOpenUsers} />
```

por:

```jsx
  return <SettingsDialog onClose={onClose} />
```

Troque:

```jsx
function SettingsDialog({ onClose, onOpenUsers }) {
```

por:

```jsx
function SettingsDialog({ onClose }) {
```

Troque:

```jsx
          <SettingsMenu onOpenStatus={openStatus} onOpenUsers={onOpenUsers} />
```

por:

```jsx
          <SettingsMenu onOpenStatus={openStatus} />
```

- [ ] **Step 7: Tirar o estilo morto do ícone**

Em `frontend/src/features/settings/settings.css`, remova o bloco:

```css
.settings-option-card__icon--users {
  color: #7a5a12;
  background: #fff7da;
}

```

- [ ] **Step 8: Rodar testes, lint e build**

Run: `docker exec chatbot-frontend sh -c "npm test 2>&1 | grep -E '^ℹ (pass|fail)'; npx oxlint --format unix 2>&1 | grep -v '^$' | head -10; npm run build 2>&1 | grep -E 'built in|rror'"`
Expected: `ℹ fail 0`, nenhum aviso do lint, `✓ built`.

- [ ] **Step 9: Commit**

```bash
git add frontend
git commit -m "feat(frontend): remove a tela de Gestão de Usuários

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: Configuração, documentação e verificação no navegador

**Files:**
- Modify: `docker-compose.yml`, `.env.example`, `SEGURANCA_E_AUTENTICACAO.md`

- [ ] **Step 1: Tirar a variável de ambiente**

Em `docker-compose.yml`, remova a linha:

```yaml
      KEYCLOAK_CONSOLE_URL: ${KEYCLOAK_CONSOLE_URL:-http://localhost:8081/admin/gentil-dev/console/}
```

Em `.env.example`, remova as duas linhas:

```
# Link "Gerenciar no Keycloak", exibido só a quem tem users.view.
KEYCLOAK_CONSOLE_URL=http://localhost:8081/admin/gentil-dev/console/
```

- [ ] **Step 2: Atualizar `SEGURANCA_E_AUTENTICACAO.md`**

Troque:

```markdown
- Console do realm (gestores de acesso): `http://localhost:8081/admin/gentil-dev/console/`.
```

por:

```markdown
- Gestão de usuários (cadastro, liberação, bloqueio, sessões): Painel de acesso do `keycloak-central`, não neste app.
```

Troque:

```markdown
Tudo vem do `.env` do app: `OIDC_ISSUER_URL`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `OIDC_REDIRECT_URI`, `OIDC_POST_LOGOUT_REDIRECT_URI` e `KEYCLOAK_CONSOLE_URL`. Trocar de Keycloak é trocar esses valores.
```

por:

```markdown
Tudo vem do `.env` do app: `OIDC_ISSUER_URL`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `OIDC_REDIRECT_URI` e `OIDC_POST_LOGOUT_REDIRECT_URI`. Trocar de Keycloak é trocar esses valores.
```

Troque:

```markdown
- **Gestão de Usuários (Configurações):** consulta somente leitura, com a permissão `users.view`. Mostra quem já entrou, o perfil do último acesso e se há sessão ativa, e tem o botão "Gerenciar no Keycloak".
- **Bloqueio imediato:** no console, desligar **Enabled** e encerrar as sessões (**Sign out**). Só desligar derruba o acesso em até 5 min.
```

por:

```markdown
- **Gestão de usuários:** fora deste app. Cadastro, liberação, perfil, bloqueio e sessões são feitos no Painel de acesso do `keycloak-central` — o Chat-bot só usa login e os papéis do token.
- **Bloqueio imediato:** no Painel, desligar a conta e encerrar as sessões. Só desligar derruba o acesso em até 5 min.
```

Troque:

```markdown
Roteiro e checklist obrigatório: `../keycloak-central/docs/MIGRACAO_TI.md`. No app, basta atualizar o `.env`:
`OIDC_ISSUER_URL`, `OIDC_CLIENT_SECRET` (novo), `OIDC_REDIRECT_URI`, `OIDC_POST_LOGOUT_REDIRECT_URI`, `KEYCLOAK_CONSOLE_URL`, `SESSION_ENCRYPTION_KEY` (nova) e `SESSION_COOKIE_SECURE=true`.
```

por:

```markdown
Roteiro e checklist obrigatório: `../keycloak-central/docs/MIGRACAO_TI.md`. No app, basta atualizar o `.env`:
`OIDC_ISSUER_URL`, `OIDC_CLIENT_SECRET` (novo), `OIDC_REDIRECT_URI`, `OIDC_POST_LOGOUT_REDIRECT_URI`, `SESSION_ENCRYPTION_KEY` (nova) e `SESSION_COOKIE_SECURE=true`.
```

Na tabela de variáveis, remova a linha:

```markdown
| `KEYCLOAK_CONSOLE_URL` | Link do console para quem tem `users.view` |
```

- [ ] **Step 3: Subir o backend novo**

Run:
```bash
docker compose up -d --build backend
curl -s -o /dev/null -w "backend: %{http_code}\n" http://localhost:8040/health/live
```
Expected: `backend: 200`.

- [ ] **Step 4: Verificar no navegador**

Entre como `admin.om` (perfil Administrador, que antes tinha `users.view`) e confira:
- O menu do usuário (canto superior direito) não tem mais "Gestão de Usuários".
- Configurações não tem mais o card "Gestão de Usuários".
- `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8040/users` com o cookie de sessão responde `404` (ou tente abrir `/users` fora do fluxo de navegação — não há mais link para chegar lá).
- O restante do app (assistente, indicadores, ativos, auditoria) continua funcionando normalmente.

- [ ] **Step 5: Verificação final e commit**

```bash
(cd backend && ../.venv/Scripts/python.exe -m pytest -q | tail -1)
docker exec chatbot-frontend sh -c "npm test 2>&1 | grep -E '^ℹ (pass|fail)'; npx oxlint 2>&1 | grep Found; npm run build 2>&1 | grep 'built in'"
git add docker-compose.yml .env.example SEGURANCA_E_AUTENTICACAO.md
git commit -m "docs: gestão de usuários fica só no keycloak-central

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

Expected: backend sem falhas, `ℹ fail 0` no frontend, lint com `0 warnings`, build ok.

Depois deste commit, siga com `superpowers:finishing-a-development-branch`.
