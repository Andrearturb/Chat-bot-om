# Custos de Manutenção na Central de Indicadores

O painel usa as partidas individuais da extração SAP FBL3N. A competência é o mês da **data de lançamento**. A data do documento aparece apenas no detalhe. O valor é líquido: estornos já negativos reduzem o total.

## Fonte e atribuição

- Conta razão `41140014`: corretiva. Conta `41140026`: preventiva, aceita pelo mesmo importador.
- O campo **Centro custo** identifica quem arca com o custo. **Divisão** fica como rastro contábil e não atribui loja.
- A importação procura primeiro o centro completo em `tape_centers.cost_center`. Só se ele não existir usa os últimos quatro caracteres contra `tape_centers.sap_number`.
- Entre lojas com o mesmo código, vincula a única não fechada. Se nenhuma estiver aberta, aceita a única loja existente. Ambiguidade permanece em “Não atribuído”. A referência é gravada na importação e não muda quando o cadastro da loja mudar.
- `store_name` e `praca` são lidos do dCentros; não há cópia desses campos em `maintenance_costs`.

## Importação

`POST /imports/costs` recebe `multipart/form-data` com campo `file` contendo `.xlsx`. Exige cookie de sessão com `sync.tape` e cabeçalho `x-api-key`, como `/imports/tape`. O nome original fica em `uploads.source_file_name`; `uploads.source_type = maintenance_costs` isola a atualização do painel dos demais syncs. A operação registra `IMPORT_COSTS` na auditoria.

Cada par **conta razão + mês de lançamento** presente no arquivo é substituído inteiro em uma transação. Reenviar a mesma extração mantém o resultado. Linhas sem conta, centro, data de lançamento ou valor legível são rejeitadas e contadas, mesmo se todas forem inválidas. Uma importação sem linha válida preserva os custos e a data da última atualização efetiva. Valor zero e data do documento vazia são aceitos. Um mês ausente da extração permanece no banco.

`GET /maintenance-costs` exige `indicators.view` e devolve `{dados, upload_data}`. O proxy do Vite encaminha essa rota ao backend. O frontend filtra por tipo, fornecedor, loja, praça, mês e ano, e abre as partidas de cada card ou ranking.

Para a primeira carga local, o operador pode copiar a extração para o container e executar `python -m scripts.import_cost_file /tmp/arquivo.xlsx`. O script usa a mesma regra de importação e registra auditoria com `origin=local_cli`.

## Validação da amostra de 02/10/2026

O comando `qa/verify_cost_sample.py` leu o dCentros atual em modo de consulta e importou a planilha `EXPORT_20261002_160635.XLSX` em um SQLite temporário. Nenhum custo foi escrito no banco operacional nessa validação.

| Atribuição | Linhas | Valor líquido |
|---|---:|---:|
| Centro de custo completo | 1.247 | R$ 639.261,05 |
| Fallback por SAP | 4 | R$ 1.227,63 |
| Não atribuído | 9 | R$ 1.849,85 |
| **Total** | **1.260** | **R$ 642.338,53** |

As 7 notas de dez/2025 foram lançadas em jan/2026 e aparecem na competência jan/2026.

## Ativação local

Em 03/10/2026, a migração `0007` foi aplicada ao banco local e a amostra foi carregada pelo script administrativo. O banco passou a ter 1.260 lançamentos e uma entrada de auditoria `IMPORT_COSTS`. Uma consulta ao endpoint retornou as 1.260 linhas; o proxy respondeu `401 application/json` sem sessão, confirmando que encaminha a rota protegida ao backend.
