#!/usr/bin/env sh
# ─────────────────────────────────────────────────────────────────────────────
# bootstrap-dev.sh — Sincroniza o Keycloak DEV com as variáveis do .env.
#
# Idempotente: pode ser executado N vezes sem efeitos colaterais.
# Compatível com Keycloak 26.2.5.
#
# CAUSA RAIZ CORRIGIDA:
#   O campo lastName não aceita o caractere '&' no Keycloak 26.
#   "lastName=O&M" causava: error-person-name-invalid-character → exit 1
#   Correção: usar lastName="OM" em todos os usuários DEV.
# ─────────────────────────────────────────────────────────────────────────────
set -eu

KC_URL="${KEYCLOAK_INTERNAL_URL:-http://keycloak:8080}"
REALM="${KEYCLOAK_REALM:-gentil-dev}"
KCADM="/opt/keycloak/bin/kcadm.sh"

log()  { echo "[bootstrap] $*"; }
err()  { echo "[bootstrap][ERROR] $*" >&2; }
ok()   { echo "[bootstrap] OK — $*"; }

# ─── 1. Aguardar Keycloak estar pronto ───────────────────────────────────────
log "Aguardando Keycloak em $KC_URL ..."
attempt=0
until "$KCADM" config credentials \
        --server "$KC_URL" \
        --realm master \
        --user "$KEYCLOAK_ADMIN" \
        --password "$KEYCLOAK_ADMIN_PASSWORD" \
        > /dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 60 ]; then
    err "Keycloak não ficou disponível após 120s."
    exit 1
  fi
  sleep 2
done
ok "Autenticado no master realm."

# ─── 2. Aguardar realm existir ────────────────────────────────────────────────
log "Verificando realm '$REALM'..."
attempt=0
until "$KCADM" get "realms/$REALM" > /dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 30 ]; then
    err "Realm '$REALM' não encontrado após 30s."
    exit 1
  fi
  sleep 1
done
ok "Realm '$REALM' encontrado."

# ─── 3. Sincronizar usuários DEV ──────────────────────────────────────────────
# NOTA: lastName NÃO pode conter '&' no Keycloak 26 — usa "OM" como sufixo.
# O display name completo fica como: firstName + " OM" (ex: "Admin OM").
ensure_user() {
  USERNAME="$1"
  EMAIL="$2"
  PASSWORD="$3"
  FIRSTNAME="$4"
  # lastName fixo sem caracteres especiais
  LASTNAME="OM"

  log "Sincronizando usuário '$USERNAME' ($EMAIL)..."

  # Busca por username
  USER_ID=$("$KCADM" get users -r "$REALM" \
    -q "username=$USERNAME" \
    --fields id \
    --format csv \
    --noquotes 2>/dev/null || true)

  if [ -z "$USER_ID" ]; then
    log "  → usuário não existe, criando..."
    USER_ID=$("$KCADM" create users -r "$REALM" -i \
      -s "username=$USERNAME" \
      -s "email=$EMAIL" \
      -s "enabled=true" \
      -s "emailVerified=true" \
      -s "firstName=$FIRSTNAME" \
      -s "lastName=$LASTNAME" 2>&1)

    # Valida que obteve um UUID (não uma mensagem de erro)
    case "$USER_ID" in
      *error*|*Error*|*invalid*)
        err "Falha ao criar usuário '$USERNAME': $USER_ID"
        exit 1
        ;;
    esac
    USER_ID=$(printf '%s' "$USER_ID" | tr -d '"[:space:]')
    log "  → criado com ID: $USER_ID"
  else
    log "  → usuário encontrado (ID: $USER_ID), atualizando..."
    UPDATE_RESULT=$("$KCADM" update "users/$USER_ID" -r "$REALM" \
      -s "email=$EMAIL" \
      -s "enabled=true" \
      -s "emailVerified=true" \
      -s "firstName=$FIRSTNAME" \
      -s "lastName=$LASTNAME" 2>&1) || {
        err "Falha ao atualizar usuário '$USERNAME': $UPDATE_RESULT"
        exit 1
      }
  fi

  # Define/atualiza senha
  log "  → definindo senha..."
  PWD_RESULT=$("$KCADM" set-password -r "$REALM" \
    --userid "$USER_ID" \
    --new-password "$PASSWORD" \
    --temporary=false 2>&1) || {
      err "Falha ao definir senha para '$USERNAME': $PWD_RESULT"
      exit 1
    }
  ok "Usuário '$USERNAME' sincronizado."
}

ensure_user "admin.om"    "$DEV_ADMIN_EMAIL"    "$DEV_ADMIN_PASSWORD"    "Administrador"
ensure_user "analista.om" "$DEV_ANALYST_EMAIL"  "$DEV_ANALYST_PASSWORD"  "Analista"
ensure_user "gerente.om"  "$DEV_MANAGER_EMAIL"  "$DEV_MANAGER_PASSWORD"  "Gerente"
ensure_user "diretor.om"  "$DEV_DIRECTOR_EMAIL" "$DEV_DIRECTOR_PASSWORD" "Diretor"
ensure_user "convidado.om" "$DEV_GUEST_EMAIL"   "$DEV_GUEST_PASSWORD"    "Convidado"

# ─── 4. Sincronizar client OIDC ───────────────────────────────────────────────
log "Sincronizando client '$OIDC_CLIENT_ID'..."

CLIENT_UUID=$("$KCADM" get clients -r "$REALM" \
  -q "clientId=$OIDC_CLIENT_ID" \
  --fields id \
  --format csv \
  --noquotes 2>/dev/null || true)

if [ -z "$CLIENT_UUID" ]; then
  log "  → client não existe, criando..."
  CLIENT_UUID=$("$KCADM" create clients -r "$REALM" -i \
    -s "clientId=$OIDC_CLIENT_ID" \
    -s "name=Chat-bot OM BFF" \
    -s "enabled=true" \
    -s "protocol=openid-connect" \
    -s "publicClient=false" \
    -s "standardFlowEnabled=true" \
    -s "implicitFlowEnabled=false" \
    -s "directAccessGrantsEnabled=false" \
    -s "serviceAccountsEnabled=false" \
    -s "secret=$OIDC_CLIENT_SECRET" \
    -s 'redirectUris=["http://localhost:5173/auth/callback","http://localhost:8040/auth/callback","http://127.0.0.1:5173/auth/callback"]' \
    -s 'webOrigins=["http://localhost:5173","http://localhost:8040","http://127.0.0.1:5173"]' \
    -s 'attributes={"pkce.code.challenge.method":"S256","post.logout.redirect.uris":"http://localhost:5173##http://127.0.0.1:5173"}' \
    2>&1)
  case "$CLIENT_UUID" in
    *error*|*Error*)
      err "Falha ao criar client '$OIDC_CLIENT_ID': $CLIENT_UUID"
      exit 1
      ;;
  esac
  CLIENT_UUID=$(printf '%s' "$CLIENT_UUID" | tr -d '"[:space:]')
  log "  → criado com UUID: $CLIENT_UUID"
else
  log "  → client encontrado (UUID: $CLIENT_UUID), atualizando secret e URIs..."
  UPDATE_RESULT=$("$KCADM" update "clients/$CLIENT_UUID" -r "$REALM" \
    -s "secret=$OIDC_CLIENT_SECRET" \
    -s 'redirectUris=["http://localhost:5173/auth/callback","http://localhost:8040/auth/callback","http://127.0.0.1:5173/auth/callback"]' \
    -s 'webOrigins=["http://localhost:5173","http://localhost:8040","http://127.0.0.1:5173"]' \
    -s 'attributes={"pkce.code.challenge.method":"S256","post.logout.redirect.uris":"http://localhost:5173##http://127.0.0.1:5173"}' \
    2>&1) || {
      err "Falha ao atualizar client '$OIDC_CLIENT_ID': $UPDATE_RESULT"
      exit 1
    }
fi
ok "Client '$OIDC_CLIENT_ID' sincronizado."

# ─── 5. Concluído ─────────────────────────────────────────────────────────────
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log "Bootstrap DEV concluído com sucesso."
log "  Realm  : $REALM"
log "  Client : $OIDC_CLIENT_ID"
log "  Usuários: admin.om, analista.om, gerente.om, diretor.om, convidado.om"
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
