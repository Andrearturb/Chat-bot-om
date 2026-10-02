# Painel de Chamados Corretivos

Ciclo 1 do merge do `bi-manutencao` no chatbot-om. Spec:
`docs/superpowers/specs/2026-10-02-bi-manutencao-corretiva-design.md`.

## Arquitetura

O painel não tem endpoint próprio, tabela de cache nem upload de planilha. Ele
consome os registros que a `IndicatorsPage` já carrega de `GET /services`.

```text
Tape API (app 57531)
  → FIELD_ALIASES: sla_late (620293), approved_value (613329)
  → TapeTransformer → importer → Service → GET /services
  → dataAdapter → features/indicators/corrective/
```

## Campos acrescentados

| Campo | Origem | Observação |
|---|---|---|
| `sla_late` | field 620293 | A Tape devolve **badge HTML**, não texto. A derivação procura "atrasado" dentro do HTML |
| `approved_value` | field 613329 | Zero é valor válido, não ausência |
| `raw_status` | field 580453 | Status original; `status` continua normalizado |

O `raw_status` **não** tem alias próprio: o `FIELD_ALIAS_INDEX` mapeia
`field_id → alias` um-para-um, e declarar o campo 580453 duas vezes faria um dos
dois desaparecer. Ele é derivado do mesmo alias `status`, antes da normalização.

## Regras de cálculo

- **Concluído** (SLA, custo médio, card Concluídos): `status == "Concluído"`, que
  engloba `Chamado Concluído` e `Solicitação Finalizada`.
- **SLA %** = no prazo / concluídos. Chamado não concluído fica fora dos dois
  lados, mesmo marcado como atrasado.
- **Custo médio** = soma dos valores dos concluídos ÷ **todos** os concluídos.
  Concluído sem valor entra no denominador como zero.
- **Total de O.S** = assinatura pendente ou concluída.
- Os cards de status **não somam** o Total de Chamados: Concluídos engloba
  Solicitação Finalizada, e `Pendente de Aprovação` não tem card — o painel de
  origem também não mostra esse status.

## O bug de SLA do BI Manutenção

O `ChamadoTransformer` do `bi-manutencao` chama o campo de `coluna_d_raw`
(coluna D, a marca de atraso), mas o alias dele aponta para
`["progresso do sla", "progresso sla"]` — outra coluna, cujo texto satura em 100%
e nunca diz "atrasado". Por isso o SLA do BI classifica **todos** os concluídos
como no prazo. Este painel lê o campo correto.

## Validação

### Contra a fotografia

Planilha `Manutenções Corretivas - All data (29).xlsx`, 4.899 linhas.

| Medida | Fotografia |
|---|---|
| Concluídos | 3.779 |
| Atrasados entre concluídos | 678 |
| SLA % | 82% |
| Concluídos com valor aprovado | 2.672 (soma R$ 751.895,03) |
| Custo médio | R$ 199 |
| Total de O.S | 2.285 |
| Solicitação Finalizada | 600 |

A base tem ~4.894–4.898 registros porque a regra de praça do importer descarta
registros sem praça ou com praça "Escritório". A diferença é deliberada e não
foi corrigida para forçar igualdade com a planilha.

### Contra o banco, após sincronização real da Tape

Sincronização executada em 2026-10-02 contra a API real (app 57531, 4.898
registros):

| Medida | Banco | Fotografia |
|---|---|---|
| Concluídos | 3.778 | 3.779 |
| Atrasados entre concluídos | **678** | 678 |
| Concluídos com valor aprovado | **2.672** | 2.672 |
| Soma dos valores aprovados | **R$ 751.895** | R$ 751.895,03 |
| Status crus distintos | **6** | 6 (`Chamado Concluído`, `Não Aprovado`, `Solicitação Finalizada`, `Em Atendimento`, `Em Aberto`, `Pendente de Aprovação`) |

Atrasados, valores e status crus bateram exatamente com a fotografia — a
derivação do badge HTML e a captura dos campos novos funcionam contra dados
reais, não só contra os testes.

Exemplo real conferido via `GET /services`: ticket `100`, `sla_late=Atrasado`,
`status=Não Aprovado` — confirma que o caso descrito na spec (atraso marcado
em chamado não concluído, fora do cálculo de SLA %) ocorre de fato nos dados.

### Armadilha no deploy

A primeira tentativa de levar o backend para o container usou
`docker cp backend/app chatbot-backend:/app/app`. Como `/app/app` já existia,
o Docker aninhou o conteúdo em `/app/app/app/` em vez de sobrescrever — o
código novo nunca chegou a rodar, e a primeira sincronização de teste
devolveu `sla_late`/`approved_value`/`raw_status` nulos para todos os
registros (zero atrasados, zero com valor). O deploy correto usa
`docker cp backend/app/. chatbot-backend:/app/app` (o `/.` força copiar o
**conteúdo** do diretório, não o diretório como subpasta).

## Fora deste ciclo

Preventiva e Financeiro; trocar a regra de SLA por `prazo` vs
`diasUteisPassados` (a fotografia tem 2.130 registros acima do prazo contra 678
marcados como atrasados — os critérios discordam); remover o normalizador de
status; novas permissões.

## Checagem visual pendente

Este ambiente de execução não tem ferramenta de navegador/Playwright. A
corretude do código foi verificada por: suíte de testes (backend e frontend),
`npm run build` sem erro, e os números acima confirmados direto no banco e via
`GET /services`. A checagem visual do painel (layout, cliques nos cards,
abertura/fechamento do modal, navegação entre Desempenho e Corretivos) listada
no plano como Task 8/9 Step de verificação no navegador **não foi feita** e
fica para validação manual antes do merge.
