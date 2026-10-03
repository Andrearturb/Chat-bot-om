# Painel de Custos de Manutenção — Design

**Data:** 2026-10-03
**Ciclo:** 3 de 3 do merge do `bi-manutencao` na Central de Indicadores
**Antecessores:** [corretiva](2026-10-02-bi-manutencao-corretiva-design.md), preventiva (`docs/integracao-bi-preventiva.md`), dCentros (`docs/integracao-dcentros.md`)

## Objetivo

Trazer o painel de custos do `bi-manutencao` para a Central de Indicadores do
chatbot-om, alimentado pela extração de partidas individuais do SAP (FBL3N),
atribuindo cada lançamento à loja pelo **centro de custo** via `tape_centers`
(dCentros).

A entrega é a conta razão **41140014** (manutenção corretiva), estruturada para
receber **41140026** (preventiva) sem alteração de código, e preparada para que
um fluxo de dados automático substitua o upload manual depois.

## Fora de escopo

| Item | Por quê |
|---|---|
| Faturamento e o indicador `gastos ÷ faturamento` | A fonte não existe — nem planilha nem API. A seção *Encaixe do faturamento* fixa onde entra, sem construir. |
| Conciliação com o valor aprovado na Tape | Decisão do solicitante: não é a conta que interessa. Também é tecnicamente impossível hoje — ver *Conciliação*. |
| Os três cards de orçamento do painel antigo | `% Custos x Orçado` e `% Desvio` estão fixos em `N/D` no bi-manutenção por não existir base orçamentária. Card que nunca informa ensina a ignorar KPI. |
| Tela de upload | Escolha do solicitante: só endpoint. O fluxo automático herda a mesma porta. |

## A fonte de dados

Extração FBL3N do SAP em XLSX, uma linha por partida individual. A amostra de
referência (`EXPORT_20261002_160635.XLSX`) tem 1.260 linhas, 24 colunas, toda
ela conta razão 41140014, lançamentos de jan a set/2026.

Colunas consumidas:

| Coluna da planilha | Uso |
|---|---|
| Conta do Razão | Tipo de manutenção: `41140014` corretiva, `41140026` preventiva |
| **Centro custo** (col. K) | **Atribuição da loja** — quem arca com o custo |
| Divisão (col. B) | Loja onde a nota foi lançada. Rastro do lançamento, **não** atribuição |
| Data do documento | Competência exibida no painel |
| Data de lançamento | Chave de substituição na reimportação |
| Montante em moeda interna | Valor. Estornos já vêm negativos |
| Chave de lançamento | `81` débito, `91` estorno |
| Tipo de documento | `RE` (1.187 linhas) / `WE` (73) |
| Nº documento | Identidade do lançamento no drill-down |
| Nome 1 | Fornecedor |
| Texto | Descrição; começa com o número do documento de origem |

As 12 colunas restantes ficam fora: Símb.prtds, Stat.partidas, Doc.compensação,
datas de compensação, pagamento e vencimento vêm todas vazias; Empresa é
constante `4000`; as contrapartidas contábeis e "Criado por" não têm consumidor.
Coluna sem consumidor é peso morto.

### Divisão não é a loja

A regra escrita no `bi-manutencao` está errada. De
`backend/app/services/custos_import_service.py:66`:

```python
# Regra de negocio: em custos, a coluna "Divisão" representa o SAP da loja.
```

O app antigo não tem coluna de centro de custo. Em 7 lançamentos (R$ 14.477,35)
ele atribuiu a loja errada. A divisão diz onde a nota foi lançada; o centro de
custo diz quem paga.

### Conciliação com a Tape é impossível hoje

Nem `services` nem `preventive_services` têm número de nota fiscal ou de
documento. O número no campo Texto (`20261755757`) é documento do SAP e não tem
par do lado da Tape. Qualquer comparação custo × chamado só poderia ser
agregada, nunca linha a linha. Registrado para que ninguém tente.

## Modelo de dados

Tabela nova, `maintenance_costs`, uma linha por partida do SAP.

```
id                      PK
upload_id               FK → uploads.id
conta_razao             text         NOT NULL, índice
document_date           date         NOT NULL   -- competência exibida
posting_date            date         NOT NULL   -- chave de substituição
document_number         text
posting_key             text                    -- 81 | 91
document_type           text                    -- RE | WE
amount                  Numeric(14,2) NOT NULL
division                text                    -- rastro do lançamento
cost_center             text         NOT NULL, índice
tape_center_record_id   BigInteger   FK → tape_centers.record_id, NULL, índice
attribution_source      text         NULL        -- cost_center | sap_fallback
supplier_name           text
description             text
synced_at               timestamptz
```

Índice composto `(conta_razao, posting_date)` — é por ele que a reimportação
apaga.

`store_name` e `praca` são **propriedades calculadas** a partir do centro
vinculado, como `AssetStore` já faz (`backend/app/models/asset_store.py`). Não
existem como coluna: o dCentros é a fonte única de identidade de loja, e
duplicar o nome aqui o faria divergir.

Não existe coluna `competencia` denormalizada. O mês vem de `document_date` no
cálculo do frontend, igual aos outros dois painéis. Campo derivado armazenado é
campo que deriva errado algum dia.

## Atribuição de loja — congelada na importação

A atribuição é resolvida **no momento da importação** e gravada em
`tape_center_record_id`, como `services` e `preventive_services` fazem. Não é
resolvida na leitura.

**Por quê congelar:** a regra consulta o status da loja no dCentros. Se Nevaldo
Rocha fechar no ano que vem, uma regra avaliada na leitura reatribuiria
R$ 55 mil de custo histórico, e o painel do ano passado mudaria sozinho. O
passado precisa parar de se mexer.

### A regra, em camadas e nesta ordem

Seja `cc` o centro de custo da linha. "Única" significa: exatamente uma loja
com `status <> 'Fechada'`; se nenhuma estiver aberta e houver só uma loja, é
ela.

1. **`cc` existe em `tape_centers.cost_center`** → se a loja é única, vincula
   com `attribution_source = 'cost_center'`. Se não é única, **não atribui**.
2. **`cc` não existe em `tape_centers.cost_center`** → compara os **últimos 4
   caracteres** de `cc` contra `tape_centers.sap_number`. Se a loja é única,
   vincula com `attribution_source = 'sap_fallback'`.
3. Nada resolve → `tape_center_record_id` nulo. A linha vive no balde
   "Não atribuído".

### Por que a ordem é obrigatória

O número SAP é **reutilizado entre praças**. Para o SAP `4027` o dCentros tem:

| cost_center | loja | status | praça |
|---|---|---|---|
| `402164027` | Container Assaí | Aberta | Mossoró |
| `402114027` | BR 101 Container | Fechada | Natal |
| `402114027` | Via Direta | Fechada | Natal |

A planilha traz `402114027`, que é Natal. Uma regra que olhasse o sufixo
primeiro mandaria R$ 1.631,35 para **Container Assaí, em Mossoró** — praça
errada, sem erro aparente. O prefixo de 5 dígitos carrega a praça e não pode ser
descartado.

### `sap_number` é alfanumérico

Existem 38 lojas na série A, com `sap_number` como `A103`, `A116`, `A121`
(João Câmara, Hub Forquilha, Itapajé). Código que trate esse campo como inteiro
quebra. Por isso a camada 2 compara os últimos 4 **caracteres**, não dígitos.

### O que a regra produz na amostra

| via | linhas | valor | % |
|---|---|---|---|
| centro de custo inteiro | 1.247 | R$ 639.261,05 | 99,52% |
| fallback pelo SAP | 4 | R$ 1.227,63 | 0,19% |
| não atribuído | 9 | R$ 1.849,85 | 0,28% |

O fallback resolve `402114099`, que o SAP lançou com prefixo `40211` (Natal)
quando a loja — Mateus Ubatuba, `402124099` — é de São Luís. Confirmado pelo
solicitante.

Os 9 não atribuídos são dois casos distintos, ambos deliberados:

- `402114027`, 3 linhas, R$ 1.631,35 — BR 101 Container e Via Direta, as duas
  fechadas, no mesmo centro de custo. Nenhum campo da planilha distingue.
- `401100103`, `401100116`, `401100121`, 6 linhas, R$ 218,50 — lançamentos
  errados no SAP. As lojas reais são da série A (`40218A103` João Câmara,
  `40212A116` Hub Forquilha, `40213A121` Itapajé), em **três praças
  diferentes**, e o prefixo gravado (`40110`) não é de nenhuma delas.

**O código não adivinha nenhum dos dois.** Mapear `0103 → A103` seria palpite
sobre erro de lançamento, e palpite errado espalha dinheiro por três praças —
o mesmo erro silencioso do caso 4027. Ficam visíveis no balde para serem
corrigidos na origem. O painel denuncia o erro em vez de maquiá-lo.

### Ambiguidade não é defeito do dCentros

O dCentros registra unidades mais finas que o SAP contabiliza: loja e quiosque
no mesmo endereço, loja e escritório no mesmo site. O SAP lança no site. Dos 15
centros de custo que apontam para mais de uma loja, 11 se resolvem porque
exatamente uma está aberta — observação do solicitante que reduziu a
ambiguidade de R$ 91.397,24 para R$ 1.631,35.

## Importação

`POST /imports/costs`, multipart, atrás de `Depends(verificar_api_key)` e
`Depends(require_permission("sync.tape"))` — a mesma porta de `/imports/tape`.
Nenhuma permissão nova: o catálogo de `backend/app/services/permissions.py`
espelha papéis do Keycloak, e criar permissão exigiria alterar o realm.

Grava um registro em `uploads` (`source_file_name` = nome do arquivo) e uma
entrada de auditoria, como a sincronização da Tape. Responde com o schema
`UploadResponse` já existente.

Dependências: `pandas`, `openpyxl` e `python-multipart` já estão em
`backend/requirements.txt`. Nada novo.

### Reimportação

O serviço coleta os pares **(conta razão, mês da data de lançamento)** presentes
no arquivo, apaga `maintenance_costs` desses pares e insere o lote.

**Por que a chave é o mês de lançamento e não a competência exibida:** a
extração do SAP é fatiada por data de lançamento, mas o painel agrupa por data
do documento, e as duas dimensões não coincidem — há documentos de dez/2025
lançados em jan/2026. Se a chave fosse a competência, subir a extração do
exercício 2025 apagaria o balde dez/2025 e reinseriria só as linhas dela,
perdendo os documentos de dezembro lançados em janeiro que vieram no outro
arquivo. A chave tem que ser a dimensão pela qual o arquivo é produzido.

Consequências, todas desejadas:

- Subir o mesmo arquivo duas vezes dá o mesmo resultado.
- Subir a extração da preventiva 41140026 não toca na corretiva.
- Um lançamento estornado no SAP desaparece do painel.
- Dois arquivos de exercícios diferentes nunca colidem.

### Linhas rejeitadas

Rejeitada é a linha sem conta razão, sem centro de custo, sem data de
lançamento, sem data do documento ou com valor ilegível. Contadas em
`rejected_count` e devolvidas na resposta.

**Valor zero é valor, não ausência** — entra. Lição do `converter_decimal` da
corretiva, onde 338 registros com valor zero teriam virado nulos.

### Limitação conhecida

Um mês de lançamento que deixe de existir inteiramente na extração não é
apagado, porque o par não aparece no arquivo. É a escolha conservadora: não
apagar o que o arquivo não menciona.

## Leitura

`GET /maintenance-costs` sob `require_permission("indicators.view")`,
devolvendo as linhas e `upload_data`, como `/services` e
`/preventive-services`.

`upload_data` deve considerar **apenas** uploads de custos. A corretiva já teve
esse bug: um sync da preventiva mais recente fazia o painel de corretivos
mostrar "atualizado agora", escondendo uma falha de sync da própria corretiva
(ver `test_services_ignora_sync_mais_novo_da_preventiva_no_ultima_atualizacao`).

O endpoint devolve linhas, não agregados — simetria com os outros dois painéis,
drill-down de graça, e a regra de negócio fica no JS testado em vez de em SQL.
1.260 linhas não é tráfego.

O proxy do Vite tem allowlist: `/maintenance-costs` precisa entrar em
`proxyRoutes` em `frontend/vite.config.js`, senão o fallback de SPA devolve HTML
e a tela quebra com 404. Já aconteceu com `/preventive-services`.

## Painel

`frontend/src/features/indicators/costs/`, com `costsData.js` concentrando o
cálculo, no padrão de `correctiveData.js` e `preventiveData.js`. Registrado em
`IndicatorsHome.jsx` como o terceiro painel da Central.

**Filtros:** tipo de manutenção (pela conta razão), fornecedor, loja, praça,
mês, ano. Mês e ano saem da data do documento.

**KPIs:**

| Card | Conteúdo |
|---|---|
| Manutenção corretiva | Soma de 41140014 |
| Manutenção preventiva | Soma de 41140026 |
| Custo das manutenções | Total do filtro ativo |
| Não atribuído | Valor e número de lançamentos sem loja. **Visível só quando > 0** |

**Visualizações:** ranking de fornecedor por valor (top 20) e barras de custo por
loja (top 20), como no painel antigo.

Estornos (chave 91, 10 lançamentos na amostra) já chegam negativos e somam
líquido — R$ 642.338,53 na amostra é o valor líquido e é o número certo.

Os predicados de filtro são **fonte única** para contadores e drill-down, como
`statusPredicates` na corretiva: contador e lista que divergem é bug que ninguém
vê.

## Encaixe do faturamento — documentado, não construído

Quando a fonte existir:

- Tabela `store_revenues`: `tape_center_record_id` + `competencia` (mês) +
  `amount`, usando a mesma `tape_centers` como identidade de loja.
- Importação pela mesma porta, `POST /imports/revenues`.
- Indicador `gastos ÷ faturamento` em `%`, por loja e consolidado, calculado em
  `costsData.js`.

O painel de gastos não muda. É por isso que a estrutura de `maintenance_costs`
não precisa antecipar nada: a ligação é `tape_center_record_id` + mês, que já
existe.

**Por que não construir agora:** o formato é ditado por uma fonte que não
existe. Inventar a tabela hoje provavelmente a faz ser refeita, e o painel antigo
mostra o preço de adiantar estrutura sem fonte — três cards escritos "N/D"
ocupando a tela.

## Testes

Backend, `pytest`, com uma fixture no formato real da extração:

- Transformação de coluna: centro de custo, valor em formato BR, datas.
- Valor zero não vira nulo.
- Estorno negativo soma líquido.
- Atribuição camada 1: centro de custo com uma loja aberta.
- Atribuição camada 1: centro de custo com uma loja só, fechada.
- Atribuição camada 1 **não** atribui quando há duas fechadas (caso `402114027`).
- Atribuição camada 2: centro de custo ausente, sufixo único (caso `402114099`).
- Atribuição camada 2 **não** atropela a camada 1 — o teste do `4027`, que
  garante que Natal não vai para Mossoró.
- `sap_number` alfanumérico (`A103`) não quebra a comparação.
- Não atribuído: nulo e `attribution_source` nulo.
- Reimportação do mesmo arquivo é idempotente.
- Importar 41140026 não apaga 41140014.
- Arquivos de exercícios diferentes não colidem na chave de lançamento.
- Linha rejeitada é contada, não silenciada.
- `upload_data` ignora uploads de outros módulos.

Frontend, `vitest` via `docker exec chatbot-frontend npm test`:

- KPI por conta razão.
- Filtro combinado (loja + mês + fornecedor).
- Card "Não atribuído" aparece só com valor.
- Mês e ano saem da data do documento.
- Ranking ordena por valor e corta em 20.
- Predicados servem contador e drill-down com o mesmo resultado.

## Evidências da amostra

`EXPORT_20261002_160635.XLSX`, 1.260 linhas, conta razão 41140014.

| medida | valor |
|---|---|
| Total líquido | R$ 642.338,53 |
| Chave 81 (débito) | 1.250 linhas |
| Chave 91 (estorno) | 10 linhas, já negativas |
| Tipo RE / WE | 1.187 / 73 — as 73 WE são exatamente as sem Nome 1 |
| Lançamentos | jan a set/2026, sem nulos |
| Documentos | dez/2025 a set/2026 — 7 linhas, R$ 795,60, em dez/2025 |
| Divisão → `sap_number` | 126 de 126 valores distintos casam |
| Centro custo → `cost_center` | 127 de 131 valores distintos casam |
| Divergência Divisão × Centro custo | 7 linhas, R$ 14.477,35 — o centro de custo vence |
| Maior loja | Nevaldo Rocha – Escritório, R$ 55.271,55 em 43 lançamentos |

Não existe chave natural por linha: a melhor combinação testada (Nº documento +
Divisão + Centro custo + Montante + Texto + Data de lançamento + Chave de
lançamento) ainda deixa 33 linhas duplicadas em 1.260. É por isso que a
reimportação substitui por período em vez de fazer diff linha a linha.
