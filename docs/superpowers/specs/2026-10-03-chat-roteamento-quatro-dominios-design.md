# Roteamento do Chat para Quatro Domínios — Design

**Data:** 2026-10-03
**Escopo:** fluxo de chat do n8n (`gLbok2Xvy09ciYIf`) e os endpoints de consulta do backend
**Relacionados:** [consulta de ativos no chat](../../integracao-ativos-chat.md), [custos](2026-10-03-bi-manutencao-custos-design.md), [corretiva](2026-10-02-bi-manutencao-corretiva-design.md)

## Objetivo

O chat responde hoje sobre **chamados corretivos** e **ativos**. Os painéis de
**preventiva** e **custos** existem e o chat não os conhece. Este ciclo conserta
a espinha de roteamento e estado, e sobre ela entrega os dois domínios novos.

A arquitetura que já funciona é preservada e é a razão do desenho: o modelo
traduz linguagem comum num JSON de pontos-chave, e o backend monta SQL
determinístico. Nenhum SQL vem do modelo. A velocidade vem da saída curta do
modelo, não de prompt pequeno.

## Fora de escopo

| Item | Por quê |
|---|---|
| Refatorar o prompt de 85 KB dos chamados | Sustenta a capacidade analítica da corretiva (comparações, drill-down, seleção contextual, análise de driver — ver os sete documentos em `n8n/`). Medimos que ele custa dinheiro, não velocidade. Mexer nele arrisca a única parte que responde bem hoje, para ganhar em preventiva e custos uma capacidade que ninguém pediu. |
| Generalizar `structured_query.py` (1.164 linhas) | Está amarrado ao modelo `Service`. `asset_query.py` provou em 131 linhas que um serviço por domínio é suficiente. |
| Comparações e drill-down em preventiva e custos | Entram enxutos. Se a falta incomodar no uso real, fatorar o núcleo comum é um ciclo próprio — ver *Quando fatorar*. |
| Mover roteamento para o backend | Tiraria inteligência do n8n e exigiria cliente de LLM no backend, que hoje não existe. |

## Estado atual

### O contrato backend ↔ n8n

O backend (`POST /assistant/chat`) chama o webhook do n8n com:

```
{ action, sessionId, chatInput, history (6 últimas, 1000 ch cada),
  assetAccessToken, assetQueryState, hadAssetContext }
```

e recebe `{ output, asset_query_state }`, persistindo o estado em
`assistant_conversations.asset_query_state`.

### O fluxo

```
Chat → Roteamento da Consulta (code) → Tem Acesso aos Ativos? (if, testa route=='asset_denied')
   ├─ sim → Responder Sem Acesso a Ativos
   └─ não → Consulta de Ativos? (if, testa route=='asset')
        ├─ sim → Interpretar Ativos (LLM) → Mesclar → Consultar Ativos → Montar Resposta
        └─ não → Buscar Estado (dataTable) → Interpretar (LLM) → Mesclar
                 → Salvar Estado (dataTable) → Query Estruturada → Montar Resposta
```

### Os sete problemas, medidos

**1. Roteamento é regex com padrão para chamados.** `let route = selected || 'service'`.
Não existe rota "não sei": toda pergunta não reconhecida consulta a corretiva em
silêncio.

**2. `service` é testado antes de `asset`.** A ordem do código decide a
ambiguidade, não o sentido da frase.

**3. Dois mecanismos de estado.** Chamados usa o `dataTable` `chat_query_state`
(29 colunas tipadas, chave `session_id`, `upsert`). Ativos faz round-trip pelo
banco do backend e **não tem nó de salvar**.

**4. O backend compensa erro de roteamento.** O comentário em
`backend/app/api/routes/assistant.py:152` declara que preserva o estado de ativos
"para que a conversa não perca o contexto só porque uma pergunta de
acompanhamento foi roteada errado".

**5. ~~Nó de modelo duplicado.~~ RETIRADO — diagnóstico errado.** Eu afirmei que
`Google Gemini Chat Model` e `Google Gemini Chat Model1` disputavam o mesmo input
`ai_languageModel[0]` de `Interpretar Estado da Consulta`. **Não é verdade.** O
`Model1` está no índice **0** (modelo principal, `gemini-3.5-flash-lite`) e o
`Model` no índice **1** (fallback), porque o nó tem `needsFallback = True`. O erro
veio do meu script de mapeamento, que imprimia o índice do *ramo* — 0 para os
dois — em vez do campo `index` da conexão.

Remover o nó do índice 0 derruba a cadeia de chamados com
`NodeOperationError: A Model sub-node must be connected and enabled`, e foi
exatamente o que aconteceu na primeira implantação. Nenhum dos dois nós sai, e
`n8n/router/verificar_fluxo.py` passou a exigir as três ligações de modelo nos
índices certos.

Isso também explica parte da velocidade que o solicitante observa no ramo de
chamados: ele roda num modelo leve, com reserva configurada.

**6. Workflow morto homônimo.** `upI5TZs9209GtPQU`, 4 nós, inativo desde
2026-09-17, também chamado "My workflow" — igual ao vivo. Export por nome é
cara ou coroa.

**7. `/chatbot/assets-query` nunca foi commitado.** Existe só como diff na árvore
de trabalho. Um clone do repositório tem workflow ativo chamando endpoint
ausente.

### Por que regex não escala para quatro domínios

Teste dos regex reais contra perguntas dos domínios novos — **6 de 6 erram**:

| pergunta | rota atual | correta |
|---|---|---|
| "Quantos chamados preventivos foram concluídos?" | corretiva | preventiva |
| "Liste as preventivas atrasadas da praça Natal" | corretiva (padrão) | preventiva |
| "Qual a periodicidade das preventivas de climatização?" | **ativos** | preventiva |
| "Quanto gastamos com manutenção corretiva em agosto?" | corretiva (padrão) | custos |
| "Qual loja teve o maior custo de manutenção?" | corretiva (padrão) | custos |
| "Quanto foi o custo por fornecedor?" | corretiva (padrão) | custos |

Corretiva e preventiva são **as duas** "chamados". Não é vocabulário faltando: a
lista achatada não tem como expressar "chamado, mas preventivo".

### Custo por turno, medido

| ramo | prompt | schema de saída | ~tokens de entrada |
|---|---|---|---|
| Chamados | 85.660 ch | 14.172 ch | ~25.000 |
| Ativos | 3.248 ch | 3.824 ch | ~1.770 |

O ramo de ativos é 14× mais barato. Nenhum dos dois usa `history`; o histórico
que o `dataTable` evita vale ~1.500 tokens, 6% de uma chamada de chamados.
Clonar o ramo de chamados para dois domínios novos seria quadruplicar o custo e
manter quatro cópias do mesmo corpus.

O `dataTable` **não** é frágil ao deploy: vive no SQLite do n8n
(`/home/node/.n8n/database.sqlite`), separado do JSON do workflow. Reimportar o
workflow não apaga a tabela.

## Desenho

### 1. Roteador em dois eixos

Em vez de uma lista achatada, dois eixos independentes:

- **entidade:** `custo` · `ativo` · `chamado`
- **qualificador:** `preventivo` · `corretivo`

Marcadores de entidade:

| entidade | termos |
|---|---|
| `custo` | custo, custos, gasto, gastos, gastamos, gastou, gastar, despesa, despesas |
| `ativo` | ativo, ativos, equipamento, equipamentos, inventário, climatização, climatizador, ar condicionado, máquina de ar, split, extintor, incêndio, purificador, gelágua, bebedouro, filtro de água, btu |
| `chamado` | chamado, chamados, ticket, tickets, ordem de serviço, ordens de serviço, solicitação, solicitações, atendimento, atendimentos |

Marcadores de qualificador: `preventiva`, `preventivas`, `preventivo`,
`preventivos` · `corretiva`, `corretivas`, `corretivo`, `corretivos`.

Todos comparados sobre texto normalizado (sem acento, minúsculo), com limite de
palavra.

### 2. Precedência — na ordem, a primeira que casa decide

1. **Entidade `custo` presente → domínio `custos`.** O qualificador, se houver,
   vira **filtro** de conta razão (`corretivo` → 41140014, `preventivo` →
   41140026), nunca troca de domínio. É o que faz "custo de manutenção
   corretiva" ser uma pergunta de custo, não de chamado.
2. **Entidade `chamado` presente → domínio `chamados`**, com subtipo pelo
   qualificador: `preventivo` → preventiva; caso contrário corretiva.
3. **Qualificador presente sem entidade de chamado → domínio `chamados`**, mesmo
   subtipo.
4. **Entidade `ativo` presente → domínio `ativos`.**
5. **Nenhum marcador, mas existe `lastDomain` no estado → domínio `lastDomain`.**
6. **Senão → `desconhecido`.**

**`chamado` vem antes de `ativo` deliberadamente.** "Quantos chamados de ar
condicionado?" tem marcador de ativo (`ar condicionado`) e de chamado, e é
pergunta de chamado filtrada por categoria. A ordem inversa a mandaria para o
inventário.

A regra 3 vir antes da 4 é o que corrige o terceiro erro da tabela:
"periodicidade das **preventivas** de climatização" tem marcador de ativo
(`climatizacao`) e qualificador (`preventivas`), e o qualificador indica chamado
preventivo da categoria climatização, não inventário.

Verificação da ordem contra os casos conhecidos:

| pergunta | regra que decide | domínio |
|---|---|---|
| "quanto gastamos com ar condicionado" | 1 (custo vence ativo) | custos |
| "custo de manutenção corretiva" | 1, qualificador vira filtro | custos + 41140014 |
| "quantos chamados de ar condicionado" | 2 (chamado vence ativo) | chamados_corretiva |
| "quantos chamados preventivos" | 2 + qualificador | chamados_preventiva |
| "liste as preventivas atrasadas" | 3 (qualificador sozinho) | chamados_preventiva |
| "periodicidade das preventivas de climatização" | 3 antes de 4 | chamados_preventiva |
| "quantos extintores na loja 4006" | 4 | ativos |
| "e na praça Natal?" | 5 | o anterior |
| "qual a capital da França?" | 6 | desconhecido |

A regra 5 generaliza o `hadAssetContext` atual para `lastDomain`, fazendo
continuidade de acompanhamento valer para os quatro domínios — hoje só ativos
tem isso.

Entidade `custo` vencer primeiro resolve também o cruzamento com ativos:
"quanto gastamos com ar condicionado" tem marcador de custo e de ativo, e é
pergunta de custo. É deliberado — o chat não cruza gasto do SAP com inventário,
e o spec de custos registra que cruzar custo com chamado é impossível hoje por
falta de número de nota do lado da Tape.

### 3. Rota `desconhecido`

Quando a regra 6 decide, o chat responde que não identificou o assunto e oferece
exemplos de cada domínio, **sem** consultar nada. Hoje essas perguntas consultam
a corretiva em silêncio e devolvem resposta sem sentido. É o conserto do problema 1.

### 4. Estado unificado no `dataTable`

A tabela `chat_query_state` continua sendo a única fonte de estado conversacional
e ganha:

| coluna | tipo | uso |
|---|---|---|
| `domain` | string | `chamados_corretiva` · `chamados_preventiva` · `ativos` · `custos` |
| `conta_razao` | string | filtro de custos |
| `periodicity` | string | filtro de preventiva |
| `asset_type` | string | filtro de ativos |
| `location` | string | filtro de ativos |

As 29 colunas existentes permanecem; a maioria já é genérica (`praca`,
`store_name`, `status`, `year`, `month`, `start_date`, `end_date`, `limit`,
`group_by`, `sort_by`, `sort_order`) e serve aos quatro domínios.

Consequências:

**`Buscar Estado da Conversa` passa a ser o primeiro nó, antes do roteador.**
Hoje o roteador é o primeiro nó e por isso não tem como ler o estado — é
exatamente por isso que ele depende de `hadAssetContext` vindo do backend.
Lendo a tabela antes de rotear, a regra 5 de precedência obtém `lastDomain`
diretamente de `domain`, e o backend deixa de participar do contexto de consulta.

Consequências:

- O ramo de ativos **ganha o nó de salvar** que não tem hoje.
- `assistant_conversations.asset_query_state` é removida, junto com o remendo
  compensatório em `assistant.py:152`.
- O payload do webhook perde `assetQueryState` e `hadAssetContext` sem ganhar
  substituto: o estado nunca mais trafega pelo backend. Permanecem `sessionId`,
  `chatInput`, `history` e o comprovante de acesso.

**Troca de domínio limpa o estado específico.** Quando o domínio do turno difere
do `domain` salvo, os campos do domínio anterior são descartados e só os
compartilhados sobrevivem:

| compartilhados — sobrevivem à troca | específicos — descartados na troca |
|---|---|
| `praca`, `store_name`, `start_date`, `end_date`, `year`, `month`, `date_field`, `group_by`, `limit`, `list_limit`, `sort_by`, `sort_order`, `query_shape`, `response_format` | `status`, `statuses`, `analyst_responsible`, `supplier`, `requester`, `category`, `subcategory`, `missing_field`, `location_term`, `comparison`, `multi_filters`, `selection_context`, `recent_periods`, `display_fields`, `conta_razao`, `periodicity`, `asset_type`, `location` |

Assim "e na praça Natal?" continua funcionando ao trocar de assunto, mas um
`conta_razao` não vaza para uma pergunta de ativos nem um `supplier` de chamado
contamina um ranking de custo.

### 5. Um serviço de consulta por domínio

`preventive_query.py` e `cost_query.py` no molde de `asset_query.py`: schema
Pydantic de entrada, três formas (`count`, `list`, `group`/`ranking`), filtros
montados em SQLAlchemy, `LIKE` com escape, nenhum SQL do modelo.

Endpoints `POST /chatbot/preventive-query` e `POST /chatbot/costs-query`, atrás
de `verificar_internal_api_key` mais o comprovante assinado.

**Não copiar o filtro `TapeCenter.status == "Aberta"`** de `asset_query.py` para
custos: gasto histórico de loja fechada é gasto real — há R$ 1.533,11 de São
Gonçalo do Amarante na amostra. Para preventiva, o filtro também não se aplica:
uma preventiva executada antes do fechamento continua sendo histórico válido.

### 6. Autorização por domínio

**Esta seção é um acréscimo ao desenho conversado**, porque custos é dado
financeiro e entrar no chat sem porta seria regressão de segurança.

Hoje `issue_asset_query_token` emite um comprovante HMAC de 180 s com
`{session_id, user_id, exp}`, e a permissão (`assets.view`) é checada antes de
emitir. O comprovante não diz a que o portador tem direito.

O payload passa a carregar `domains`, a lista de domínios que o usuário pode
consultar, derivada das permissões da sessão:

| domínio | permissão exigida |
|---|---|
| `ativos` | `assets.view` |
| `chamados_corretiva` | `indicators.view` |
| `chamados_preventiva` | `indicators.view` |
| `custos` | `indicators.view` |

`verify_asset_query_token` passa a receber o domínio exigido e checar
pertinência. A verificação continua sendo HMAC sobre o corpo inteiro, então
`domains` não é forjável.

O nó `Responder Sem Acesso a Ativos` generaliza para `Responder Sem Acesso`,
nomeando o domínio negado. Como o comprovante vive 180 s, a troca é um corte
limpo: nenhum token em trânsito sobrevive à implantação.

**Chamados corretivos passam a exigir `indicators.view`, o que hoje não
acontece.** É aperto deliberado de permissão, coerente com o painel que mostra o
mesmo dado. Se isso bloquear alguém que deve ter acesso, a correção é o papel no
Keycloak, não afrouxar aqui.

### 7. O roteador vira código testável

O roteador é a parte mais defeituosa do sistema e a única sem teste, porque vive
dentro de um nó do n8n.

O roteador canônico passa a ser um módulo JS no repositório
(`n8n/router/route.js`) com testes em `node --test`, registrados no `npm test`
do frontend junto com os demais. O script `n8n/add_asset_query_branch.py`, que
já patcha o workflow programaticamente, injeta esse fonte no `jsCode` do nó.

O fonte no repositório é a verdade; o nó é artefato gerado. Um teste verifica
que o `jsCode` do workflow exportado corresponde ao módulo, para que uma edição
feita na interface do n8n não divirja em silêncio.

### 8. Limpeza

- ~~Remover o nó `Google Gemini Chat Model1`.~~ **RETIRADO** — ver o problema 5
  acima. Os dois nós não são duplicados: `Model1` é o modelo principal no índice
  0 e `Model` é o fallback no índice 1. Remover o do índice 0 derrubou a cadeia
  de chamados em produção. Nenhum dos dois sai.
- Apagar o workflow morto `upI5TZs9209GtPQU`.
- Renomear o workflow vivo de "My workflow" para "Chat O&M — Consultas".
- Commitar `/chatbot/assets-query` e `app/services/asset_query*.py`.

## Ordem de implementação

O ciclo é grande e tem um ponto natural de verificação no meio. A espinha deve
estar no ar e validada **antes** de qualquer domínio novo entrar, porque é ela
que torna os domínios novos possíveis:

**Marco 1 — a espinha, sem domínio novo.** Roteador em módulo testado, estado
unificado no `dataTable` com `Buscar Estado` como primeiro nó, autorização por
domínio, rota `desconhecido`, e a limpeza dos itens 5 a 8. Ao fim, os dois
domínios que já existem — corretiva e ativos — devem responder exatamente como
antes, e as perguntas de preventiva e custos devem cair em `desconhecido` em vez
de responder errado. **Esse é o critério do marco: nada regrediu e o erro ficou
honesto.**

**Marco 2 — os dois domínios novos.** `preventive_query.py`, `cost_query.py`,
seus endpoints, interpretadores enxutos e nós de ramo.

Se o marco 1 não fechar verde, o marco 2 não começa.

## Testes

**Roteador** (`node --test`, o coração do ciclo):

- As 6 perguntas da tabela de erro passam a rotear certo.
- "Quantos chamados estão abertos?" continua corretiva.
- "Quantos extintores na loja 4006?" continua ativos.
- "custo de manutenção corretiva" → custos com `conta_razao` 41140014, não chamados.
- "periodicidade das preventivas de climatização" → preventiva, não ativos.
- Pergunta sem marcador e sem `lastDomain` → `desconhecido`.
- Pergunta sem marcador com `lastDomain` → continua no domínio anterior.
- Acento e caixa não alteram a rota.
- Qualificador sozinho ("liste as preventivas") → preventiva.

**Backend** (`pytest`):

- `cost_query` devolve total, lista, agrupamento e ranking coerentes com o painel.
- `cost_query` **inclui** loja fechada.
- `preventive_query` nas mesmas quatro formas.
- Comprovante sem o domínio exigido recebe 403.
- Comprovante com o domínio exigido passa.
- Comprovante expirado recebe 403.
- Comprovante com `domains` adulterado falha no HMAC.
- `LIKE` com `%` e `_` digitados pelo usuário é tratado como texto.

**Contrato n8n ↔ repositório:**

- O `jsCode` do nó de roteamento no workflow exportado corresponde ao módulo.

## Quando fatorar o núcleo comum

Preventiva e custos nascem sem comparação ("compare agosto com setembro"),
seleção contextual ("essas lojas") e drill-down. Se o uso real mostrar que
falta, o ciclo seguinte separa os 85 KB em regras compartilhadas mais um
suplemento por domínio. A decisão fica para quando houver evidência de uso, não
agora.

## Limitação conhecida

Paráfrase sem nenhum marcador de entidade nem qualificador — "liste os atrasados
da praça Natal" — depende do `lastDomain`. Numa conversa nova, cai em
`desconhecido` e o chat pede esclarecimento. É pior do que adivinhar certo e
melhor do que adivinhar errado em silêncio, que é o comportamento de hoje.
