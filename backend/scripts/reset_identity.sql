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
