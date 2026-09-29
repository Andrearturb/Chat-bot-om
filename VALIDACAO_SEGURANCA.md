# Validação de Segurança — Chat-bot O&M

## Resultados dos testes automatizados

### Backend — testes unitários (SQLite in-memory)

**Arquivo:** `backend/tests/test_auth_security.py`

| Teste | Resultado |
|---|---|
| seed_idempotente | ✅ PASSOU |
| token armazenado como hash (não texto puro) | ✅ PASSOU |
| get_session válida | ✅ PASSOU |
| get_session token inválido → None | ✅ PASSOU |
| sessão expirada (idle) → None | ✅ PASSOU |
| sessão expirada (absoluta) → None | ✅ PASSOU |
| logout revoga sessão | ✅ PASSOU |
| usuário pending bloqueado | ✅ PASSOU |
| usuário disabled bloqueado | ✅ PASSOU |
| usuário ativo → OK | ✅ PASSOU |
| usuário expirado bloqueado | ✅ PASSOU |
| perfil ANALISTA — permissões corretas | ✅ PASSOU |
| perfil GERENTE — permissões corretas | ✅ PASSOU |
| perfil DIRETOR — permissões corretas | ✅ PASSOU |
| perfil CONVIDADO — permissões corretas | ✅ PASSOU |
| perfil ADMINISTRADOR — permissões corretas | ✅ PASSOU |
| override allow (assets.import para analista) | ✅ PASSOU |
| override deny (assets.edit bloqueado) | ✅ PASSOU |
| deny prevalece sobre allow de perfil | ✅ PASSOU |
| limite diário permitido | ✅ PASSOU |
| limite diário atingido → blocked | ✅ PASSOU |
| limite por minuto atingido → blocked | ✅ PASSOU |
| erros não contam para o limite | ✅ PASSOU |
| override individual de limite IA | ✅ PASSOU |
| conversa isolada por usuário | ✅ PASSOU |
| dono acessa própria conversa | ✅ PASSOU |
| record_audit registra corretamente | ✅ PASSOU |
| record_security_event registra corretamente | ✅ PASSOU |
| novo usuário criado com status=pending | ✅ PASSOU |
| bootstrap admin na primeira autenticação | ✅ PASSOU |
| bootstrap admin ocorre apenas uma vez | ✅ PASSOU |
| identidade existente retorna mesmo usuário | ✅ PASSOU |

**Total: 32/32**

---

### Backend — testes de API (TestClient + SQLite in-memory)

**Arquivo:** `backend/tests/test_api_security.py`

| Teste | Resultado |
|---|---|
| /health/live é público → 200 | ✅ PASSOU |
| /health sem sessão → 401 | ✅ PASSOU |
| /auth/me sem sessão → 401 | ✅ PASSOU |
| /auth/me com sessão → 200 com csrf_token | ✅ PASSOU |
| POST sem X-CSRF-Token → 403 | ✅ PASSOU |
| POST com CSRF errado → 403 | ✅ PASSOU |
| GET não exige CSRF | ✅ PASSOU |
| POST com CSRF correto → 200 | ✅ PASSOU |
| /services sem sessão → 401 | ✅ PASSOU |
| /services com sessão ANALISTA → 200 | ✅ PASSOU |
| /assets/stores sem sessão → 401 | ✅ PASSOU |
| /assets/stores com sessão → 200 | ✅ PASSOU |
| /chatbot/structured-query sem chave → 401 | ✅ PASSOU |
| /chatbot/structured-query chave errada → 401 | ✅ PASSOU |
| /chatbot/structured-query chave correta → não 401 | ✅ PASSOU |
| DELETE /assets/.../climatization sem delete perm → 403/404 | ✅ PASSOU |
| /audit/logs ANALISTA → 403 | ✅ PASSOU |
| /users ANALISTA → 403 | ✅ PASSOU |
| /assistant/chat sem sessão → 401 | ✅ PASSOU |
| /assistant/conversations sem sessão → 401 | ✅ PASSOU |
| /assistant/conversations/{inexistente} → 404 | ✅ PASSOU |

**Total: 21/21**

---

### Backend — testes de regressão (suite original)

**Arquivos:** todos os testes exceto test_api_security.py

| Suite | Resultado |
|---|---|
| test_assets.py | ✅ PASSOU |
| test_chatbot_query.py | ✅ PASSOU |
| test_importer_sync.py | ✅ PASSOU |
| test_in_attendance_date.py | ✅ PASSOU (adaptado) |
| test_normalizar_status.py | ✅ PASSOU |
| test_novos_campos.py | ✅ PASSOU |
| test_qa_trace.py | ✅ PASSOU |
| test_structured_query.py | ✅ PASSOU |

**Total: 214/214**

---

### Resumo total

| Categoria | Testes | Resultado |
|---|---|---|
| Autenticação/Segurança (unitário) | 32 | ✅ 32/32 |
| Segurança via API (TestClient) | 21 | ✅ 21/21 |
| Regressão (suite original) | 214 | ✅ 214/214 |
| **TOTAL** | **267** | **✅ 267/267** |

---

## Checklist de conclusão

| Item | Status |
|---|---|
| Keycloak DEV no docker-compose | ✅ |
| Realm gentil-dev com 5 usuários dev | ✅ |
| Fluxo OIDC Authorization Code + PKCE | ✅ |
| Router /auth registrado no FastAPI | ✅ |
| Sessão server-side (token opaco + hash) | ✅ |
| Cookie HttpOnly, SameSite=Lax | ✅ |
| Tokens NÃO no localStorage | ✅ |
| CSRF obrigatório em mutações | ✅ |
| Idle timeout + absolute timeout | ✅ |
| Bootstrap admin (uma vez só) | ✅ |
| 5 perfis com permissões granulares | ✅ |
| Overrides individuais (allow/deny) | ✅ |
| deny prevalece sobre allow de perfil | ✅ |
| /services protegido (indicators.view) | ✅ |
| /assets/* protegido por permissões | ✅ |
| /documents/* protegido por permissões | ✅ |
| /chatbot/structured-query → X-Internal-API-Key | ✅ |
| /health/live público; /health → settings.view | ✅ |
| Gateway /assistant/chat (sem n8n direto) | ✅ |
| Quota IA (diário + por minuto) | ✅ |
| HTTP 429 ao atingir limite | ✅ |
| Conversas no PostgreSQL | ✅ |
| Isolamento de conversas por usuário | ✅ |
| 404 ao acessar conversa alheia | ✅ |
| VITE_N8N_WEBHOOK_URL removido do frontend | ✅ |
| AuthProvider em memória | ✅ |
| apiClient centralizado (credentials:include) | ✅ |
| LoginScreen identidade Gentil | ✅ |
| AccessPending / AccessDenied | ✅ |
| PermissionGate para botões | ✅ |
| Sidebar com itens por permissão | ✅ |
| Header com nome do usuário | ✅ |
| UserMenu com logout | ✅ |
| Gestão de Acessos (users.manage) | ✅ |
| Tela Auditoria (audit.view) | ✅ |
| Security headers no middleware | ✅ |
| CORS via FRONTEND_ORIGINS | ✅ |
| AuditLog em operações críticas | ✅ |
| SecurityEvent em violações | ✅ |
| guest expiry (access_expires_at) | ✅ |
| .env.example atualizado | ✅ |
| docker-compose com keycloak + keycloak-db | ✅ |
| keycloak_postgres_data volume | ✅ |
| Volumes existentes preservados | ✅ |

---

## Como testar os 5 perfis

### 1. Admin (admin.om@local)
```
Acessa: http://localhost:5173
Clica: "Entrar com conta corporativa"
Credenciais: admin.om@local / valor definido em DEV_ADMIN_PASSWORD
Verifica:
  - Header mostra "Bom dia, Admin!"
  - Menu usuário: Gestão de acessos + Auditoria + Configurações
  - Sidebar: todos os itens
  - Ativos: Adicionar/Editar/Excluir disponíveis
```

### 2. Analista (analista.om@local)
```
Após login, acesse Gestão de Acessos (como admin) e:
  - Ative a conta
  - Defina perfil ANALISTA
Login como analista:
  - Sidebar: Assistente, Conversas, Indicadores, Ativos, Configurações
  - Ativos: Adicionar ✓, Editar ✓, Excluir ✗
  - Menu: sem Gestão de Acessos, sem Auditoria
```

### 3. Gerente (gerente.om@local)
```
  - Ative com perfil GERENTE
  - Ativos: Adicionar ✓, Editar ✓, Excluir ✓
  - Auditoria: visível no menu
  - Gestão de Acessos: não visível
```

### 4. Diretor (diretor.om@local)
```
  - Ative com perfil DIRETOR
  - Assistente: disponível
  - Indicadores: disponível
  - Ativos: somente visualização
  - Sem Adicionar/Editar/Excluir
```

### 5. Convidado (convidado.om@local)
```
  - Ative com perfil CONVIDADO
  - Defina access_expires_at para data futura
  - Assistente limitado (20 msg/dia)
  - Indicadores: disponível
  - Ativos: somente visualização
  - Sem documentos, sem configurações
  Para testar expiração:
    - Defina access_expires_at para 1 minuto atrás
    - Próxima chamada retorna 403
```

---

## Comandos de teste

```bash
# Ativar ambiente virtual
.venv\Scripts\activate

# Rodar todos os testes
cd backend
python -m pytest tests/ -q

# Apenas segurança
python -m pytest tests/test_auth_security.py tests/test_api_security.py -v

# Build do frontend
cd frontend
npm run build
# Verificar que nenhum secret está no bundle:
npm run build && Select-String -Path "dist\assets\*.js" -Pattern "OIDC_CLIENT_SECRET|INTERNAL_API_KEY|SESSION_SECRET|n8n.io/webhook"
```

## Subir Docker
```bash
# Copiar .env.example para .env e preencher os valores obrigatórios
# Subir sem apagar volumes:
docker compose down
docker compose up -d --build
# Verificar serviços:
docker compose ps
# Acessar Keycloak: http://localhost:8081
# Acessar frontend: http://localhost:5173
# Acessar backend: http://localhost:8040/docs
```
