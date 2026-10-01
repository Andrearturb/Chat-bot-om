# Chat-bot O&M

Assistente de Obras & Manutenções da Gentil Negócios: conversa em linguagem natural sobre os chamados, Central de Indicadores e Central de Ativos das lojas.

## Arquitetura

| Serviço | Pasta | Endereço (DEV) | Papel |
|---|---|---|---|
| frontend | `frontend/` | http://localhost:5173 | React + Vite; o navegador só fala com o backend (mesma origem, proxy do Vite) |
| backend | `backend/` | http://localhost:8040 | FastAPI (BFF): sessões, permissões, chamados, indicadores, ativos, auditoria |
| db | — | rede interna | PostgreSQL do app |
| n8n | `n8n/` | http://localhost:5678 | Workflow do assistente (agente de IA); chamado só pelo backend |
| qa | `qa/` | — | Testes de ponta a ponta do assistente (ver `qa/README.md`) |

O login e os perfis vêm do Keycloak do repositório irmão **keycloak-central** (`../keycloak-central`): o app é um cliente OIDC, sem credencial administrativa. Perfis, permissões, liberação e bloqueio de contas são feitos no Keycloak (painel de acesso em http://localhost:8090). Detalhes em `SEGURANCA_E_AUTENTICACAO.md`.

## Como rodar (DEV)

1. Suba o keycloak-central (ver `../keycloak-central/docs/OPERACAO.md`).
2. Copie `.env.example` para `.env` e preencha os valores (o `OIDC_CLIENT_SECRET` é o `CHATBOT_CLIENT_SECRET` do keycloak-central).
3. `docker compose up -d --build`
4. Abra http://localhost:5173 e entre com um usuário DEV (as senhas ficam no `.env` do keycloak-central).

## Testes

- Backend: `cd backend && ../.venv/Scripts/python.exe -m pytest -q`
- Frontend: `docker exec chatbot-frontend npm test` (ou `npx oxlint` para o lint)
- Fluxo completo de login no navegador: `../keycloak-central/scripts/e2e_flow.py`

## Documentação

- `SEGURANCA_E_AUTENTICACAO.md` — login OIDC, sessões, permissões e cabeçalhos de segurança.
- `docs/integracao-bi.md` — regras da Central de Indicadores (BI de Resultados).
- `n8n/README.md` e `n8n/*.md` — workflow do assistente e suas regras de interpretação.
- `qa/README.md` — testes do assistente contra o n8n e o banco.
- `docs/historico/` — registros de revisões anteriores.
- `docs/superpowers/` — especificações e planos de implementação.
