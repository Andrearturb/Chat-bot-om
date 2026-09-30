# Tema de login `gentil-om` (Keycloak 26.2.x)

Tema da página de login do Chat-bot O&M. Herda o tema `base` do Keycloak e
reproduz a identidade visual do aplicativo (mesma composição da página `/login`
do frontend em `frontend/src/features/auth/`).

- `login/template.ftl` — layout em duas áreas (Gentileza + card de autenticação).
- `login/login.ftl`, `login-update-password.ftl`, `login-reset-password.ftl`,
  `logout-confirm.ftl` — páginas personalizadas; as demais usam o tema `base`
  com as classes definidas em `theme.properties`.
- `login/messages/` — textos em pt-BR (o `messages_en` repete os mesmos textos
  para o caso de o realm estar sem internacionalização).
- `login/resources/` — CSS, imagens da Gentileza e a fonte Manrope.

Montagem e ativação são automáticas no DEV (`docker-compose.yml` +
`keycloak/bootstrap-dev.sh`). Em `start-dev` o cache de tema fica desligado:
alterações em `.ftl`/`.css` aparecem ao recarregar a página.

Fonte Manrope © The Manrope Project Authors, distribuída sob a
SIL Open Font License 1.1 (https://openfontlicense.org).
