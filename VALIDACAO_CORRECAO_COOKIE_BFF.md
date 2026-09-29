# Validação — correção do cookie BFF/OIDC

## Resultado

A correção remove o bypass do proxy Vite e força o navegador a usar sempre a origem `localhost:5173` para as APIs da aplicação em DEV.

## Alterações validadas

- `VITE_BACKEND_URL` não é mais injetado no container frontend.
- Cliente HTTP usa somente caminhos relativos.
- `/auth/me`, `/health/live`, `/health`, assets e documentos passam pela mesma origem.
- Callback OIDC padrão: `http://localhost:5173/auth/callback`.
- Callback FastAPI usa `RedirectResponse` e inclui `Set-Cookie` na resposta 302.
- Client Keycloak DEV não precisa de callback browser-facing em `localhost:8040`.

## Testes executados

### Backend

`pytest -q`

Resultado: **236 passed**.

Foi adicionado teste específico que confirma que `/auth/callback` retorna:

- HTTP 302;
- `Location: http://localhost:5173`;
- `Set-Cookie` com `om_session`;
- `HttpOnly`;
- `Path=/`;
- `SameSite=lax`.

### Frontend

`npm test`

Resultado: **14 passed**.

Inclui dois testes novos do cliente BFF:

- `/auth/me` é requisitado por caminho relativo;
- `credentials: include` é enviado;
- CSRF continua sendo enviado em métodos mutáveis.

### Build Vite

Build concluído com sucesso: **896 modules transformed**.

Somente warning informativo de chunks acima de 500 kB.

### Bundle scan

Nenhuma ocorrência no bundle final de:

- `VITE_BACKEND_URL`;
- `localhost:8040`;
- webhook direto conhecido do n8n.

### Proxy Vite / Set-Cookie

Foi executado um teste isolado com upstream HTTP retornando redirect 302 + `Set-Cookie`, passando pelo `server.proxy` do Vite.

O Vite devolveu ao cliente:

```text
HTTP/1.1 302 Found
location: http://localhost:5173/
set-cookie: om_session=...; HttpOnly; Path=/; SameSite=lax
```

Isso confirma que a configuração do proxy utilizada pelo projeto repassa `Set-Cookie` em respostas de redirect.

### Lint

0 erros.

Existem warnings React/unused preexistentes e não relacionados ao problema do cookie.

## Validação Docker/browser ainda recomendada

Neste ambiente não há daemon Docker disponível. Após substituir o projeto, executar:

```bash
docker compose down
docker compose up -d --build
```

Sem `-v`.

No navegador, confirmar:

1. `/auth/login` em `localhost:5173`;
2. `/auth/callback` em `localhost:5173`;
3. resposta do callback com `Set-Cookie`;
4. cookie `om_session` em Application > Cookies;
5. `/auth/me` em `localhost:5173/auth/me`;
6. `/auth/me` retornando 200 após login.
