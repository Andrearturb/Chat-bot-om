# Correção do retorno OIDC / bootstrap DEV

Esta revisão corrige o cenário em que o Keycloak autentica corretamente, mas o aplicativo volta para a tela de acesso com `auth_error`.

## O que foi corrigido

- Um usuário já vinculado por `issuer + subject` agora volta a passar pela regra de bootstrap enquanto `bootstrap_admin_granted=false`.
- Em `development`, `DEV_ADMIN_EMAIL` é a referência efetiva para o bootstrap do primeiro administrador.
- O email/nome do usuário local é sincronizado quando a mesma identidade OIDC muda esses atributos.
- Os emails DEV do realm agora usam `DEV_ADMIN_EMAIL`, `DEV_ANALYST_EMAIL`, etc.
- O Keycloak DEV passou a ter um bootstrap idempotente que sincroniza email, senha e client secret mesmo quando o realm já existe no volume `keycloak_postgres_data`.
- A URL `?auth_error=...` deixa de apenas piscar: o frontend captura o erro e mostra uma mensagem clara.

## Como testar

1. Mantenha seu `.env` real fora do ZIP.
2. Defina `DEV_ADMIN_EMAIL` com o email que deseja usar no usuário `admin.om`.
3. Defina `DEV_ADMIN_PASSWORD` com a senha DEV desejada.
4. Rode:

```bash
docker compose down
docker compose up -d --build
```

Não use `-v`.

5. Aguarde `keycloak-bootstrap` concluir:

```bash
docker compose ps -a
docker compose logs keycloak-bootstrap
```

O serviço deve terminar com código 0 e registrar que o Keycloak DEV foi sincronizado.

6. Acesse `http://localhost:5173`, clique em entrar e use o email configurado em `DEV_ADMIN_EMAIL` e a senha `DEV_ADMIN_PASSWORD`.

## Se o usuário já estava `pending`

Não é necessário apagar o PostgreSQL principal. No próximo callback com o mesmo `issuer+subject`, se o email autenticado for o `DEV_ADMIN_EMAIL`, o usuário existente será promovido para `ADMINISTRADOR` e ativado, desde que `bootstrap_admin_granted` ainda seja `false`.
