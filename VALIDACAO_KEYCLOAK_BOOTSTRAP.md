# Validação do Keycloak Bootstrap

## Causa raiz do problema

**Arquivo:** `keycloak/bootstrap-dev.sh`

**Comando que falhava:**
```sh
"$KCADM" create users -r "$REALM" \
  -s "username=admin.om" \
  -s "email=admin.om@local" \
  -s "firstName=Admin" \
  -s "lastName=O&M"   # ← AQUI
```

**Resposta do Keycloak:**
```
error-person-name-invalid-character
exit code: 1
```

**Explicação:** O Keycloak 26 não aceita o caractere `&` nos campos de nome pessoal (`firstName`, `lastName`). O script usava `lastName=O&M` para todos os 5 usuários. Como `set -eu` estava ativo, o primeiro `exit 1` matava o script inteiro sem completar o provisionamento.

O mesmo problema existia no `realm-export.json` (usado apenas na primeira inicialização do volume):
```json
"lastName": "O&M"  // ← caractere inválido
```

---

## Correção aplicada

### `keycloak/bootstrap-dev.sh`

- `lastName=O&M` → `LASTNAME="OM"` (variável local sem caracteres especiais)
- Script completamente reescrito com:
  - Logs descritivos em cada etapa (`[bootstrap] ...`)
  - `ensure_user` idempotente: busca por username, cria se não existe, atualiza se existe
  - Sincronização de senha via `set-password` sempre (funciona em criação e atualização)
  - Sincronização do client `chat-bot-om-bff`: atualiza secret e redirect URIs sem recriar
  - Erros reais (401, 403, falha inesperada) geram `exit 1` com mensagem clara
  - Situações esperadas (usuário já existe, realm já existe) tratadas como INFO

### `keycloak/realm-export.json`

- `"lastName": "O&M"` → `"lastName": "OM"` em todos os 5 usuários
- `"displayName"` do realm removeu o `—` (travessão) que poderia causar issues de encoding
- Senhas e emails do realm-export agora são valores de referência (o bootstrap sempre sincroniza)

---

## Como o bootstrap funciona

```
1. Aguarda Keycloak responder (loop com timeout de 120s)
2. Autentica no realm master com KEYCLOAK_ADMIN / KEYCLOAK_ADMIN_PASSWORD
3. Aguarda realm gentil-dev existir (pode ter sido importado via realm-export.json)
4. Para cada usuário DEV (admin.om, analista.om, gerente.om, diretor.om, convidado.om):
   - Busca pelo username
   - Se não existe: cria com os campos do .env
   - Se existe: atualiza email, firstName, lastName, enabled
   - Define/atualiza a senha (set-password funciona em ambos os casos)
5. Para o client chat-bot-om-bff:
   - Busca pelo clientId
   - Se não existe: cria com todas as configurações
   - Se existe: atualiza secret e redirect URIs
6. Termina com exit 0 e log de conclusão
```

---

## Como validar

### Bootstrap com realm existente (cenário atual)
```bash
docker compose down
docker compose up -d --build
```
Esperado: `keycloak-bootstrap` → `Exited (0)`

### Bootstrap segunda execução (idempotência)
```bash
docker compose down
docker compose up -d
```
Esperado: `keycloak-bootstrap` → `Exited (0)` novamente, nada duplicado.

### Ver logs do bootstrap
```bash
docker compose logs keycloak-bootstrap
```

### Trocar email de um usuário DEV
1. Edite `DEV_ADMIN_EMAIL` no `.env`
2. `docker compose up -d` (sem --build)
3. O bootstrap atualiza o email sem criar duplicata

### Trocar senha de um usuário DEV
1. Edite `DEV_ADMIN_PASSWORD` no `.env`
2. `docker compose up -d`
3. O bootstrap chama `set-password` e a nova senha passa a funcionar

### Rodar bootstrap manualmente (para debug)
```bash
docker compose run --rm keycloak-bootstrap
```

---

## Recuperar Keycloak DEV

Se o volume do Keycloak estiver inconsistente (banco corrompido, etc.):

```bash
# 1. Para os containers Keycloak (SEM -v para não apagar outros dados)
docker compose stop keycloak keycloak-bootstrap

# 2. Remove os containers
docker compose rm -f keycloak keycloak-bootstrap

# 3. Remove SOMENTE o volume do banco do Keycloak DEV
docker volume rm chat-bot-om_keycloak_postgres_data

# 4. Sobe novamente — reimporta o realm e executa o bootstrap
docker compose up -d keycloak-db keycloak keycloak-bootstrap
```

**Volumes preservados (dados da aplicação):**
- `chatbot_postgres_data` — banco principal (serviços, ativos, usuários)
- `asset_documents_data` — documentos
- `n8n_data` — workflows do n8n

---

## Resultados dos testes

| Teste | Resultado |
|---|---|
| `docker compose up -d --build` | ✅ `keycloak-bootstrap Exited (0)` |
| Segunda execução (idempotência) | ✅ `keycloak-bootstrap Exited (0)` |
| 5 usuários DEV sincronizados | ✅ |
| Client `chat-bot-om-bff` sincronizado | ✅ |
| Backend tests | ✅ 238/238 |
| Regressão zero | ✅ |

---

## Arquivos alterados

| Arquivo | Alteração |
|---|---|
| `keycloak/bootstrap-dev.sh` | Reescrito — causa raiz corrigida (`lastName=OM`) |
| `keycloak/realm-export.json` | `lastName` corrigido em 5 usuários |
