# Filtros de Praça/Loja e exportação de ativos — design

Data: 2026-10-01 · Status: aguardando revisão

## Objetivo

Na Central de Ativos: (1) filtrar as lojas por **Praças** e **Lojas**, ambos de múltipla escolha; (2) **exportar para planilha** (.xlsx) os equipamentos de Climatização, Incêndio e Água, de todas as lojas ou só do filtro ativo. A planilha define o layout padrão que a importação (fase seguinte) vai reaproveitar.

A Central é a fonte dos dados. Esta fase **não** importa nada.

## Decisões

| Tema | Decisão |
|---|---|
| Onde ficam os filtros | Na tela de ativos, para consulta. A exportação só os aproveita |
| Filtros | Só Praças e Lojas (a busca livre sai da tela e passa a existir dentro do seletor de Lojas) |
| Combinação | Dentro de cada filtro os valores se somam (Natal **ou** Mossoró). Entre os dois, **estreita**: o seletor de Lojas só oferece lojas das praças marcadas, e o resultado é exatamente o que foi marcado |
| Exportação | Botão **Exportar** abre uma janela: Lojas ("todas" ou "somente o filtro ativo") e Ativos ("todos" ou qualquer combinação dos 3 tipos) |
| Arquivo | Um .xlsx com **uma aba por tipo** marcado, gerado no servidor (openpyxl, já usado no projeto). Sem IA |
| Permissão | Quem tem `assets.view` exporta. Cada exportação vai para a auditoria |

## Filtros da tela

- Dois seletores com caixas de marcar: **Praças** e **Lojas**. Etiquetas dos valores marcados ("Natal ×"), contador "12 de 132 lojas" e botão "Limpar filtros".
- **Lojas** mostra só as lojas das praças marcadas (todas, se nenhuma praça estiver marcada), com busca por nome, BPCS ou SAP dentro do seletor. Desmarcar uma praça remove as lojas escolhidas que ficarem fora das praças restantes.
- Sem digitação em campo livre, não há espera nem busca a cada tecla: cada mudança consulta o servidor uma vez.
- Celular: o seletor abre como painel de largura total.

## Janela "Exportar ativos"

- **Lojas:** (•) Todas as lojas (N) · ( ) Somente o filtro ativo (M lojas). A segunda opção só fica ativa quando há filtro.
- **Ativos:** caixa "Todos" mais Climatização, Incêndio e Água. Pelo menos um tipo é obrigatório.
- **Resumo ao vivo** (consulta de prévia, cancelando a anterior): "12 lojas · 40 climatização · 9 incêndio · 3 água". "Baixar planilha" fica desativado sem lojas ou sem tipo.
- Erros aparecem na própria janela; o download usa `fetch` e `blob`, para mostrar mensagens em vez de abrir uma página de erro.

## Planilha

Arquivo `ativos-AAAA-MM-DD.xlsx` (data de Fortaleza). Abas: **Climatização**, **Incêndio**, **Água**. Linhas por loja (nome) e depois código. Cabeçalho na linha 1, fixo, com filtro automático, fundo azul-marinho e texto branco.

| Aba | Colunas (nesta ordem) |
|---|---|
| Todas | Loja · BPCS · SAP · Praça · Código · Tipo · Local |
| Climatização | + Capacidade (BTU) · Marca · Modelo · Nº de série · Ano de fabricação · Ano de instalação · Tensão · Gás refrigerante · Status · Observações |
| Incêndio | + Agente extintor · Capacidade · Ano de fabricação · Vencimento · Teste hidrostático · Status · Observações |
| Água | + Marca · Modelo · Nº de série · Ano de fabricação · Ano de instalação · Tensão · Última troca de filtro · Próxima troca de filtro · Status · Observações |

- Datas são datas de verdade do Excel (`DD/MM/AAAA`); anos e BTU são números; campo vazio é célula vazia.
- Aba de um tipo marcado sem equipamentos no filtro sai só com o cabeçalho.
- **Proteção contra fórmulas:** todo texto é gravado como texto; valor que comece com `=`, `+`, `-` ou `@` nunca vira fórmula ao abrir no Excel.

## API

Filtro único no servidor, usado pela lista da tela e pela exportação.

- `GET /assets/stores` aceita `praca` e `store_id` repetidos (mais o `q` atual, mantido por compatibilidade). Regra: praça ∈ marcadas **e** id ∈ marcados **e** `q`.
- `GET /assets/stores/options` (novo, leve): `[{id, name, praca, bpcs, sap}]`, para o seletor de Lojas.
- `GET /assets/export/preview?praca=&store_id=&asset_type=` → `{"stores": n, "climatization": n, "fire_safety": n, "water": n}`.
- `GET /assets/export?...` → .xlsx com `Content-Disposition: attachment`. `asset_type` ∈ `climatization | fire_safety | water` (repetido; ausente = todos; valor inválido = 422). Sem lojas ou sem tipos → 400 em português.
- Todos exigem `assets.view`. A exportação grava `ASSET_EXPORT` na auditoria (`new_values`: filtros, nº de lojas, nº de equipamentos, tipos) e a tela de Auditoria passa a mostrar "Exportou ativos".

## Código

- Backend: `app/services/assets_export.py` (filtro compartilhado, contagens, montagem do .xlsx) e `app/api/routes/assets_export.py` (rotas). `list_stores` passa a usar o filtro compartilhado.
- Frontend (`features/assets/`): `components/MultiSelect.jsx`, `components/AssetFilters.jsx`, `components/ExportDialog.jsx`, `filters.js` (regras puras, com teste), mudanças em `AssetsPage.jsx` e `api.js`.

## Testes

- Backend: abas e colunas de cada tipo; ordem das linhas; datas como datas; filtros somados e estreitos (praça × loja); tipos escolhidos; seleção vazia e tipo inválido; proteção contra fórmula; auditoria registrada; permissão (401/403); contagem da prévia igual às linhas do arquivo; `list_stores` com vários valores.
- Frontend (`node --test`): montagem da consulta, estreitamento de lojas ao mudar praças, texto das contagens.
- Navegador: filtrar, exportar "tudo" e "filtro ativo", abrir o arquivo gerado e conferir abas e linhas.

## Fora do escopo

Importação (próxima fase, usando este layout), documentos (PDFs), CSV, outros filtros (status, tipo de ativo na loja, documentos), filtros salvos e escolha de equipamentos individuais.

## Economia de tokens

Nada de IA em uso: geração determinística no servidor. Um único filtro compartilhado, endpoints pequenos e um seletor reaproveitado para Praças e Lojas.
