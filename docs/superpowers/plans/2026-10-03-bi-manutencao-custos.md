# Painel de Custos de Manutenção — plano de implementação

**Spec:** `docs/superpowers/specs/2026-10-03-bi-manutencao-custos-design.md`

**Objetivo:** importar partidas individuais FBL3N, atribuir cada lançamento pelo centro de custo do dCentros e mostrar o custo líquido na Central de Indicadores.

## Tarefa 1 — Persistência

- [x] Criar `MaintenanceCost`, vinculado a `Upload` e `TapeCenter`, sem nome de loja ou competência duplicados.
- [x] Criar migração Alembic após `0006`, com índices por conta, data de lançamento, centro de custo e loja.
- [x] Registrar o modelo no metadata; verificar migração em banco vazio e em banco migrado.

## Tarefa 2 — Importador FBL3N

- [x] Ler XLSX por nomes de coluna, preservando centro de custo e códigos alfanuméricos como texto.
- [x] Validar conta, centro de custo, data de lançamento e valor; aceitar zero e data do documento vazia.
- [x] Resolver loja na ordem exata do spec, congelando `tape_center_record_id` e a fonte de atribuição.
- [x] Substituir atomica e idempotentemente cada par conta razão/mês de lançamento do arquivo; contar rejeições.
- [x] Testar a amostra e os casos ambíguos e de estorno.

## Tarefa 3 — API e auditoria

- [x] Criar `POST /imports/costs` multipart com API key e `sync.tape`, `UploadResponse` e auditoria.
- [x] Criar `GET /maintenance-costs` com `indicators.view`, linhas, nomes de loja derivados e atualização exclusiva dos uploads de custos.
- [x] Cobrir autenticação e isolamento da data de atualização em testes.

## Tarefa 4 — Cálculo do painel

- [x] Criar `costsData.js` com filtros únicos, KPIs, rankings top 20 e predicados compartilhados com o detalhe.
- [x] Calcular mês/ano da data de lançamento; somar estornos negativos sem alterar o sinal.
- [x] Cobrir filtros combinados, não atribuídos e ranking em testes.

## Tarefa 5 — Interface e validação

- [x] Criar o painel de custos com filtros, cards, rankings e detalhe das partidas.
- [x] Registrar o terceiro painel em `IndicatorsHome` e `IndicatorsPage`; incluir proxy `/maintenance-costs`.
- [x] Executar testes backend, frontend e build; conferir total e atribuição da amostra antes de concluir.
