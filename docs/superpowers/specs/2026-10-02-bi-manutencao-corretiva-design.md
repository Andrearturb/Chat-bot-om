# BI Manutenção no chatbot-om: Chamados Corretivos — design

Data: 2026-10-02 · Status: aguardando revisão

## Objetivo

Trazer o painel de **manutenção corretiva** do aplicativo `bi-manutencao` para dentro do card **Chamados Corretivos** da Central de Indicadores do chatbot-om, alimentado pela base de chamados que o chatbot-om já sincroniza da Tape — sem upload de planilha.

Este é o **ciclo 1 de 3**. Preventiva e Financeiro vêm depois, cada um com spec e plano próprios.

## Contexto

O `bi-manutencao` é um aplicativo separado (Next.js + FastAPI) com três áreas: corretiva, preventiva e financeiro. O backend dele é fino — as rotas devolvem linhas de uma tabela de cache (`dashboard_cache`) e **toda a lógica de KPI vive no frontend** (~2.150 linhas de TypeScript). Portar significa reescrever essa camada em React, não plugar um endpoint.

A Central de Indicadores do chatbot-om já tem quatro cards mapeados: `performance` (construído, é o antigo `bi-resultados`) e `corrective`, `preventive`, `financial`, hoje caindo num `IndicatorPlaceholder`.

A corretiva é o ponto de partida porque os dados **já existem vivos** no chatbot-om: a tabela `services` é alimentada pelo sync da Tape (app 57531), e o `FIELDS_REFERENCE` já pede todos os campos que faltam — eles só não são persistidos.

## Decisões

| Tema | Decisão |
|---|---|
| Recorte | Três ciclos independentes. Este cobre **só a corretiva** |
| Autonomia dos painéis | Cada card da central é um aplicativo autônomo. O painel de corretiva é portado **inteiro**, inclusive o que duplica o de Desempenho. A redundância é intencional |
| Fonte de dados | A base de chamados que já existe (`services`, sync da Tape). Sem upload, sem tabela de cache, sem endpoint novo |
| Camada de dados | A `IndicatorsPage` já carrega os registros uma vez e compartilha entre painéis. Corretiva reusa esses registros: uma requisição, um "Última atualização" |
| Permissão | `indicators.view`, a que já existe. **Nenhuma** role nova no keycloak-central |
| Regra de SLA | Conta só chamados concluídos. Entre eles, atrasado é quem tem a marca do campo 620293; o resto é no prazo |
| Status | Guardar o status **cru** da Tape num campo novo, **mantendo** o status canônico como está. Na lógica de agregação, `Chamado Concluído` e `Solicitação Finalizada` contam como concluído |
| Persistência | Fase de desenvolvimento: recriar a tabela é aceitável, não há migração a preservar |

## Três descobertas que o desenho precisa respeitar

**1. O indicador de SLA do BI Manutenção está vazio na prática.** A regra do `ChamadoTransformer` procura "atras" na coluna que ele chama de `coluna_d_raw`, mas o alias desse campo aponta para `["progresso do sla", "progresso sla"]` — ele lê a coluna errada. A coluna "Progresso do SLA" é uma barra de progresso cujo texto **satura em 100%** e nunca diz "atrasado". Resultado: todos os 3.779 concluídos da fotografia sairiam como "no prazo".

A marca real de atraso está na **coluna D** da planilha, cujo cabeçalho é literalmente `"  "` (dois espaços), e cujo único valor é `Atrasado`, em 1.026 registros. Na Tape é o campo **620293**, que no `FIELDS_REFERENCE` do chatbot-om está presente mas **sem label** (comentário vazio) — consistente com a coluna sem nome.

**2. Na API da Tape, o campo 620293 não é texto: é HTML.** A planilha achata para `Atrasado`, mas a API devolve o badge:

```html
<div><div style="background-color:#ff0000;color: #fff;...">Atrasado</div></div>
```

Comparar por igualdade (`== "Atrasado"`) marcaria **zero** chamados como atrasados e o SLA voltaria a dar 100% no prazo — a mesma falha silenciosa do BI, por outro caminho. A derivação procura "atrasado" **dentro** do HTML, normalizado sem acento e sem caixa.

**3. O status canônico apaga uma distinção que o painel usa.** O `importer.py` normaliza `Chamado Concluído` **e** `Solicitação Finalizada` para `Concluído`. O painel do BI mostra os dois como cards separados (600 e 3.779). Sem o status cru, o card "Solicitação Finalizada" ficaria permanentemente em zero.

Manter o normalizador custa ~100 kB num `services` de 5.360 kB (+2%) e zero tempo de sync — a normalização é busca em dicionário na memória, invisível ao lado da paginação da API. Tirá-lo exigiria refatorar o `structured_query.py` (o fluxo de chamados do chatbot) e o painel de Desempenho inteiro, com os testes dos dois. Por isso guardamos os dois campos.

## Caminho dos dados

O mesmo caminho de 6 passos que o `in_attendance_date` já percorreu, documentado em `docs/integracao-bi.md`:

```text
Tape API (app 57531)
  → FIELDS_REFERENCE          já pede 620293, 613329 e 580453
  → FIELD_ALIASES             novo: sla_late, approved_value, raw_status
  → TapeTransformer
  → importer                  entram na comparação de diferenças
  → Service.sla_late / .approved_value / .raw_status
  → schema de GET /services
  → dataAdapter.js            slaLate / approvedValue / rawStatus
  → features/indicators/corrective/
```

### Campos novos em `Service`

| Campo | Tipo | Origem | Derivação |
|---|---|---|---|
| `sla_late` | texto nulável | campo 620293 (label `"  "`) | `"Atrasado"` quando o HTML contém "atrasado" normalizado; `null` quando vazio |
| `approved_value` | Numeric(14,2) nulável | campo 613329 ("Valor Aprovado") | número; valor ilegível vira `null` |
| `raw_status` | texto nulável | campo 580453 ("Status") | texto da Tape preservado, sem normalização |

`sla_late` guarda texto, não booleano: hoje a coluna carrega só `Atrasado` ou vazio, e texto sobrevive a um terceiro valor sem migração — além de ser mais fiel à origem.

Os três participam da comparação de diferenças do importer, portanto são atualizados em sincronizações posteriores.

## O painel

### Filtros

Status, Loja (`store_name`), Praça (`praca`), Categoria (`category`), Mês e Ano — os dois últimos derivados de `created_on`. Aplicados no cliente, sobre os registros já carregados, como no painel de Desempenho.

### KPIs grandes

**Definição de "concluído"**, usada pelo SLA, pelo custo médio e pelo card de Concluídos: o chamado cujo `status` canônico é `Concluído`. Como o importer normaliza `Chamado Concluído` e `Solicitação Finalizada` para esse mesmo valor, o conjunto é o mesmo que o BI obtém somando os dois status crus — são os 3.779 da fotografia. O `raw_status` serve apenas para **separar os cards** de status, nunca para definir o conjunto de concluídos.

Quatro cartões, cada um clicável abrindo um modal com a lista dos chamados por trás do número.

| KPI | Fórmula | Alvo na fotografia |
|---|---|---|
| Total de Chamados | `count(filtrados)` | 4.899 |
| Total de O.S | `count` onde `signature_status` normalizado ∈ {pendente, concluido} | 2.285 |
| Custo Médio Serviço | `round(soma(approved_value dos concluídos) / count(concluídos))` | R$ 199 |
| SLA % | `round(noPrazo / (noPrazo + atrasado) × 100)`, só entre concluídos | 82% |

Normalização de `signature_status`: contém "conclu" ou "complet" → `concluido`; contém "pend" ou "aguard" → `pendente`.

**Duas regras deliberadas, preservadas do BI:**

- No custo médio, **concluído sem valor aprovado entra no denominador como zero**. Na fotografia, 2.672 dos 3.779 concluídos têm valor, somando R$ 751.895,03, mas a divisão é por 3.779 — daí os R$ 199.
- No SLA, chamado **não** concluído não entra em nenhum dos dois lados, mesmo marcado como atrasado. São 348 marcações fora da conta (266 em Não Aprovado, 58 Em Atendimento, 11 Em Aberto, 13 Pendente de Aprovação).

### Mini-KPIs de status

Cinco contadores clicáveis. Os quatro primeiros leem o `raw_status`; o último usa a definição de concluído acima.

| Card | Campo | Regra | Alvo |
|---|---|---|---|
| Em aberto | `raw_status` | `Em Aberto` | 55 |
| Em atendimento | `raw_status` | `Em Atendimento` | 108 |
| Não aprovado | `raw_status` | `Não Aprovado` | 941 |
| Solicitação Finalizada | `raw_status` | `Solicitação Finalizada` ou `Serviço Finalizado` | 600 |
| Concluídos (destaque) | `status` | `Concluído` | 3.779 |

"Concluídos" **inclui** os 600 de Solicitação Finalizada — é assim no BI e é o mesmo conjunto que alimenta SLA e custo médio.

Os cards **não somam** o Total de Chamados, por duas razões: Concluídos engloba Solicitação Finalizada, e `Pendente de Aprovação` (16 na fotografia) não tem card — o BI também não mostra esse status. Não é defeito; é o comportamento do painel de origem.

### Gráficos e rankings

- **Chamados por analistas**
- **Concluídos x totais por mês**, agrupado por `created_on`
- **Ranking por Loja** — top 8, quantidade e percentual
- **Ranking por Categoria** — top 8, quantidade e percentual

## Estados de tela

O painel reusa os estados que o de Desempenho já tem: carregando, base vazia, backend indisponível, erro de HTTP/payload, tentar novamente, atualização manual, e falha de atualização preservando a última base carregada. `upload_data` aparece como "Última atualização".

A `IndicatorsPage` já guarda a posição de rolagem por indicador; o painel de corretiva ganha a **sua própria chave de estado persistido**, para que os filtros dele não se misturem com os do Desempenho.

## Tratamento de erro nos dados

- `approved_value` ilegível → tratado como ausente; entra no denominador como zero, nunca quebra
- HTML do `sla_late` sem "atrasado" → conta como no prazo
- chamado sem status → aparece no Total de Chamados, mas em nenhum card de status e fora do SLA
- base sem nenhum concluído → SLA % e Custo Médio devolvem zero, em vez de dividir por zero
- loja ou categoria ausente no ranking → agrupadas como "Sem loja" / "Sem categoria"

## Testes

### Backend (pytest)

Para cada um dos três campos novos, a cobertura de 6 passos usada no `in_attendance_date`:

1. captura do campo no payload da Tape
2. conversão do valor
3. valor nulo ou ausente
4. persistência
5. atualização em sincronização posterior (comparação de diferenças)
6. exposição em `GET /services`

Para o `sla_late`, a entrada do teste é o **HTML real do badge**, não o texto achatado da planilha. Um teste que usa o texto achatado passa e deixa a produção falhar.

### Frontend (`npm run test:indicators`)

Arquivo próprio do módulo de corretiva:

- SLA: só entre concluídos (678 atrasados / 3.101 no prazo → 82%), excluindo as 348 marcações em não concluídos
- Custo médio: concluído sem valor entra no denominador como zero → R$ 199
- Total de O.S: `signature_status` ∈ {pendente, concluido} → 2.285
- Cards de status a partir do `raw_status`, com Solicitação Finalizada em 600 separado de Concluídos em 3.779
- Filtros: loja, praça, categoria, mês e ano sobre `created_on`
- Base vazia: KPIs em zero, sem quebrar

### Validação contra a fotografia

A planilha `Manutenções Corretivas - All data (29).xlsx` (4.899 linhas) é a fotografia de referência, como no merge anterior. Os números ao vivo divergem um pouco: a base tem 4.894 linhas porque a regra de praça do importer descarta registros sem praça ou com praça "Escritório". A diferença é **documentada, não corrigida** — é regra deliberada do importer.

## Fora de escopo

- **Preventiva e Financeiro** — ciclos 2 e 3, cada um com spec próprio
- **Mudar a regra de SLA** para usar `prazo` vs `diasUteisPassados`. A fotografia tem 2.130 registros com dias úteis passados acima do prazo, contra 678 marcados como atrasados — os dois números discordam. Fica registrado como assunto para depois; este ciclo usa a marca do campo 620293
- **Remover o normalizador de status** do importer
- **Novas permissões** ou roles no keycloak-central
- **Desligar o `bi-manutencao`** ou mexer nele
- Campos da Tape que o painel não usa (`Recorrente`, `Mau uso?`, `Valor do Saving`, `Código do Ar Condicionado`, valor informado pelo prestador)
