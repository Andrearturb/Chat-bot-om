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
    # Não força enabled=true: um bloqueio feito pela Gestão de Usuários
    # continua valendo depois de "docker compose down/up".
    log "  → usuário encontrado (ID: $USER_ID), atualizando..."
    UPDATE_RESULT=$("$KCADM" update "users/$USER_ID" -r "$REALM" \
      -s "email=$EMAIL" \
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

FRONTEND_URL="${FRONTEND_BASE_URL:-http://localhost:5173}"
# Retorno do logout: /login (com ?auth_error=... quando o acesso é negado).
POST_LOGOUT_URIS="$FRONTEND_URL/login##$FRONTEND_URL/*##$FRONTEND_URL##http://127.0.0.1:5173/*##http://127.0.0.1:5173"

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
    -s "baseUrl=$FRONTEND_URL/login" \
    -s 'redirectUris=["http://localhost:5173/auth/callback","http://localhost:8040/auth/callback","http://127.0.0.1:5173/auth/callback"]' \
    -s 'webOrigins=["http://localhost:5173","http://localhost:8040","http://127.0.0.1:5173"]' \
    -s "attributes={\"pkce.code.challenge.method\":\"S256\",\"post.logout.redirect.uris\":\"$POST_LOGOUT_URIS\"}" \
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
    -s "baseUrl=$FRONTEND_URL/login" \
    -s 'redirectUris=["http://localhost:5173/auth/callback","http://localhost:8040/auth/callback","http://127.0.0.1:5173/auth/callback"]' \
    -s 'webOrigins=["http://localhost:5173","http://localhost:8040","http://127.0.0.1:5173"]' \
    -s "attributes={\"pkce.code.challenge.method\":\"S256\",\"post.logout.redirect.uris\":\"$POST_LOGOUT_URIS\"}" \
    2>&1) || {
      err "Falha ao atualizar client '$OIDC_CLIENT_ID': $UPDATE_RESULT"
      exit 1
    }
fi
ok "Client '$OIDC_CLIENT_ID' sincronizado."

# ─── 5. Client de serviço para a Keycloak Admin API ───────────────────────────
# Usado SOMENTE pelo backend (server-side) na Gestão de Usuários e no
# pré-provisionamento DEV. Sem login interativo; papéis mínimos de
# realm-management (gerir usuários + ler a configuração de SMTP do realm).
ADMIN_CLIENT_ID="${KEYCLOAK_ADMIN_CLIENT_ID:-chat-bot-om-admin}"
if [ -z "${KEYCLOAK_ADMIN_CLIENT_SECRET:-}" ]; then
  err "KEYCLOAK_ADMIN_CLIENT_SECRET não definido."
  exit 1
fi
log "Sincronizando client de serviço '$ADMIN_CLIENT_ID'..."

ADMIN_UUID=$("$KCADM" get clients -r "$REALM" \
  -q "clientId=$ADMIN_CLIENT_ID" \
  --fields id \
  --format csv \
  --noquotes 2>/dev/null || true)

if [ -z "$ADMIN_UUID" ]; then
  log "  → client não existe, criando..."
  ADMIN_UUID=$("$KCADM" create clients -r "$REALM" -i \
    -s "clientId=$ADMIN_CLIENT_ID" \
    -s "name=Chat-bot OM - Admin API" \
    -s "description=Gestão de usuários do Chat-bot O&M (somente backend)" \
    -s "enabled=true" \
    -s "protocol=openid-connect" \
    -s "publicClient=false" \
    -s "standardFlowEnabled=false" \
    -s "implicitFlowEnabled=false" \
    -s "directAccessGrantsEnabled=false" \
    -s "serviceAccountsEnabled=true" \
    -s "secret=$KEYCLOAK_ADMIN_CLIENT_SECRET" \
    2>&1)
  case "$ADMIN_UUID" in
    *error*|*Error*)
      err "Falha ao criar client '$ADMIN_CLIENT_ID': $ADMIN_UUID"
      exit 1
      ;;
  esac
  ADMIN_UUID=$(printf '%s' "$ADMIN_UUID" | tr -d '"[:space:]')
  log "  → criado com UUID: $ADMIN_UUID"
else
  log "  → client encontrado (UUID: $ADMIN_UUID), atualizando..."
  UPDATE_RESULT=$("$KCADM" update "clients/$ADMIN_UUID" -r "$REALM" \
    -s "enabled=true" \
    -s "publicClient=false" \
    -s "standardFlowEnabled=false" \
    -s "implicitFlowEnabled=false" \
    -s "directAccessGrantsEnabled=false" \
    -s "serviceAccountsEnabled=true" \
    -s "secret=$KEYCLOAK_ADMIN_CLIENT_SECRET" \
    2>&1) || {
      err "Falha ao atualizar client '$ADMIN_CLIENT_ID': $UPDATE_RESULT"
      exit 1
    }
fi

ROLES_RESULT=$("$KCADM" add-roles -r "$REALM" \
  --uusername "service-account-$ADMIN_CLIENT_ID" \
  --cclientid realm-management \
  --rolename manage-users \
  --rolename view-users \
  --rolename query-users \
  --rolename view-realm 2>&1) || {
    err "Falha ao atribuir papéis ao client '$ADMIN_CLIENT_ID': $ROLES_RESULT"
    exit 1
  }
ok "Client de serviço '$ADMIN_CLIENT_ID' sincronizado (manage-users, view-users, query-users, view-realm)."

# ─── 6. Identidade visual, idioma e recuperação de senha do realm ─────────────
LOGIN_THEME="${KEYCLOAK_LOGIN_THEME:-gentil-om}"
log "Aplicando tema de login '$LOGIN_THEME' e idioma pt-BR..."
THEME_RESULT=$("$KCADM" update "realms/$REALM" \
  -s "loginTheme=$LOGIN_THEME" \
  -s "displayName=Chat-bot O&M" \
  -s "internationalizationEnabled=true" \
  -s 'supportedLocales=["pt-BR"]' \
  -s "defaultLocale=pt-BR" \
  -s "registrationAllowed=false" 2>&1) || {
    err "Falha ao aplicar o tema de login: $THEME_RESULT"
    exit 1
  }

if [ -n "${KEYCLOAK_SMTP_HOST:-}" ]; then
  log "Configurando SMTP do realm ($KEYCLOAK_SMTP_HOST)..."
  SMTP_AUTH=false
  if [ -n "${KEYCLOAK_SMTP_USER:-}" ]; then SMTP_AUTH=true; fi
  SMTP_RESULT=$("$KCADM" update "realms/$REALM" \
    -s "smtpServer.host=$KEYCLOAK_SMTP_HOST" \
    -s "smtpServer.port=${KEYCLOAK_SMTP_PORT:-587}" \
    -s "smtpServer.from=${KEYCLOAK_SMTP_FROM:-}" \
    -s "smtpServer.fromDisplayName=${KEYCLOAK_SMTP_FROM_DISPLAY_NAME:-Chat-bot O&M}" \
    -s "smtpServer.starttls=${KEYCLOAK_SMTP_STARTTLS:-true}" \
    -s "smtpServer.ssl=${KEYCLOAK_SMTP_SSL:-false}" \
    -s "smtpServer.auth=$SMTP_AUTH" \
    -s "smtpServer.user=${KEYCLOAK_SMTP_USER:-}" \
    -s "smtpServer.password=${KEYCLOAK_SMTP_PASSWORD:-}" 2>&1) || {
      err "Falha ao configurar SMTP: $SMTP_RESULT"
      exit 1
    }
fi

# "Esqueci minha senha" só aparece quando o realm consegue enviar e-mails.
SMTP_CONFIGURED_HOST=$("$KCADM" get "realms/$REALM" --fields "smtpServer(host)" --format csv --noquotes 2>/dev/null | tr -d '[:space:]' || true)
if [ -n "$SMTP_CONFIGURED_HOST" ]; then
  RESET_ALLOWED=true
else
  RESET_ALLOWED=false
fi
"$KCADM" update "realms/$REALM" -s "resetPasswordAllowed=$RESET_ALLOWED" > /dev/null 2>&1 || {
  err "Falha ao ajustar resetPasswordAllowed."
  exit 1
}
ok "Tema '$LOGIN_THEME' aplicado. SMTP: ${SMTP_CONFIGURED_HOST:-não configurado} | Esqueci minha senha: $RESET_ALLOWED"

# ─── 7. Concluído ─────────────────────────────────────────────────────────────
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log "Bootstrap DEV concluído com sucesso."
log "  Realm  : $REALM"
log "  Client : $OIDC_CLIENT_ID"
log "  Admin API client : $ADMIN_CLIENT_ID"
log "  Tema de login    : $LOGIN_THEME"
log "  Usuários: admin.om, analista.om, gerente.om, diretor.om, convidado.om"
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
