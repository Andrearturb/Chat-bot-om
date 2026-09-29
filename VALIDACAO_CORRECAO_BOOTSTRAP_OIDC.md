# Validação — correção do retorno OIDC / bootstrap DEV

## Problema tratado

Após autenticar no Keycloak, o browser retornava à tela de acesso com `?auth_error=...`. Havia três causas de UX/configuração relevantes:

1. uma identidade OIDC já vinculada retornava cedo demais e não reavaliava o bootstrap de administrador;
2. os emails dos usuários DEV do realm estavam fixos em `*.om@local`, enquanto o `.env` permitia configurar `DEV_*_EMAIL`;
3. o frontend removia `auth_error` da URL sem informar o motivo ao usuário.

## Correções aplicadas

- Bootstrap reavaliado para identidades existentes enquanto `bootstrap_admin_granted=false`.
- Em ambiente `development`, `DEV_ADMIN_EMAIL` é a referência efetiva do bootstrap.
- Sincronização segura de email/nome para a mesma identidade `issuer + subject`.
- Realm DEV usa placeholders `DEV_*_EMAIL`.
- Serviço `keycloak-bootstrap` sincroniza usuários, senhas e client secret mesmo quando o realm já existe no volume.
- Uso de `KC_BOOTSTRAP_ADMIN_USERNAME` e `KC_BOOTSTRAP_ADMIN_PASSWORD` no Keycloak 26.
- `auth_error` agora é convertido em estado/mensagem de UI em vez de apenas piscar na URL.
- Callback de erro usa redirects `no-store`.

## Testes executados neste ambiente

### Backend — autenticação

`pytest -q tests/test_auth_security.py`

Resultado: **34/34 aprovados**.

Inclui novos cenários:

- usuário `pending` já vinculado é promovido após correção do email de bootstrap;
- alteração de email no mesmo `issuer + subject` não cria usuário duplicado.

### Frontend

`npm test`

Resultado: **16/16 aprovados**.

Inclui mensagens de `auth_error` e os testes existentes de BFF, Indicadores e Ativos.

### Build frontend

Build Vite executado diretamente com o binário instalado:

`node node_modules/vite/bin/vite.js build`

Resultado: **PASSOU — 897 módulos transformados**.

Há somente o aviso já conhecido de chunks maiores que 500 kB.

### Lint

Oxlint: **0 erros**. Permanecem warnings preexistentes do projeto; a correção retirou o warning novo que havia sido introduzido pelo tratamento inicial de `auth_error`.

### Estrutura

- `docker-compose.yml`: YAML válido.
- `keycloak/realm-export.json`: JSON válido.
- `keycloak/bootstrap-dev.sh`: sintaxe POSIX shell válida.
- módulos Python modificados: compilação válida.

## Limitação desta validação

Este ambiente não possui Docker, portanto o fluxo real `docker compose up` + Keycloak + browser não pôde ser executado aqui. A validação final no computador do usuário deve conferir o serviço one-shot `keycloak-bootstrap` e o login real.

## Validação local recomendada

```bash
docker compose down
docker compose up -d --build
docker compose ps -a
docker compose logs keycloak-bootstrap
docker compose logs backend --tail=150
```

O `keycloak-bootstrap` deve terminar com código 0 e registrar:

`Keycloak DEV sincronizado com as variáveis DEV_* do ambiente.`

Depois acessar `http://localhost:5173` e autenticar com o email definido em `DEV_ADMIN_EMAIL` e a senha definida em `DEV_ADMIN_PASSWORD`.

Não usar `docker compose down -v`.
