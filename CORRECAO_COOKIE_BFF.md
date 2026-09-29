# Correção do cookie de sessão no BFF

## Causa encontrada

O fluxo OIDC de login/callback passava por `http://localhost:5173` e pelo proxy do Vite, porém chamadas normais do frontend (como `/auth/me`) podiam usar `VITE_BACKEND_URL=http://localhost:8040` e contornar o proxy.

Isso misturava duas origens no navegador:

- login/callback: `localhost:5173`;
- API normal: `localhost:8040`.

Em uma arquitetura BFF com cookie HttpOnly, o browser deve conversar sempre com a mesma origem. O proxy/reverse proxy é quem conhece o endereço interno do FastAPI.

## Arquitetura corrigida

```text
Browser -> http://localhost:5173/auth/login
        -> Vite proxy -> backend:8000
        -> Keycloak

Keycloak -> http://localhost:5173/auth/callback
         -> Vite proxy -> backend:8000
         -> Set-Cookie: om_session=...; HttpOnly; Path=/; SameSite=Lax

Browser -> http://localhost:5173/auth/me
        -> Cookie: om_session=...
        -> Vite proxy -> backend:8000
```

## Alterações

- O container frontend não recebe mais `VITE_BACKEND_URL`.
- O cliente HTTP do browser usa somente caminhos relativos.
- Health check, Settings e downloads de documentos também usam caminhos relativos.
- O callback OIDC usa `RedirectResponse` e define o cookie na mesma resposta 302 devolvida ao browser.
- O callback padrão OIDC foi alinhado para `http://localhost:5173/auth/callback`.
- O client DEV do Keycloak aceita somente callbacks/origins browser-facing em `localhost:5173` / `127.0.0.1:5173`.
- `.env.example` documenta `VITE_BACKEND_URL` vazio/depreciado no modo BFF.

## Validação esperada no navegador

No DevTools > Network:

1. `/auth/login` deve ser `http://localhost:5173/auth/login`.
2. `/auth/callback?...` deve ser `http://localhost:5173/auth/callback?...`.
3. A resposta do callback deve conter `Set-Cookie: om_session=...`.
4. `/auth/me` deve ser `http://localhost:5173/auth/me` (não `:8040`).
5. `/auth/me` deve retornar `200` após o login.

No backend, login, callback e `/auth/me` devem chegar pelo mesmo caminho de proxy do frontend no cenário Docker/Vite.

## Produção

Manter a mesma premissa: frontend e BFF publicados sob a mesma origem por um reverse proxy. O browser deve usar URLs relativas para as APIs da aplicação.
