#!/usr/bin/env sh
# Substitui placeholders no realm-export.json antes de importar no Keycloak.
set -e
REALM_FILE="/opt/keycloak/data/import/realm-export.json"
PROCESSED="/tmp/realm-processed.json"

sed \
  -e "s|\${OIDC_CLIENT_SECRET}|${OIDC_CLIENT_SECRET}|g" \
  -e "s|\${DEV_ADMIN_PASSWORD}|${DEV_ADMIN_PASSWORD}|g" \
  -e "s|\${DEV_ANALYST_PASSWORD}|${DEV_ANALYST_PASSWORD}|g" \
  -e "s|\${DEV_MANAGER_PASSWORD}|${DEV_MANAGER_PASSWORD}|g" \
  -e "s|\${DEV_DIRECTOR_PASSWORD}|${DEV_DIRECTOR_PASSWORD}|g" \
  -e "s|\${DEV_GUEST_PASSWORD}|${DEV_GUEST_PASSWORD}|g" \
  "$REALM_FILE" > "$PROCESSED"

exec /opt/keycloak/bin/kc.sh "$@" --import-realm
