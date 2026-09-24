# Seleção contextual + filtros múltiplos

Esta versão adiciona duas capacidades ao fluxo determinístico da Gentileza:

1. **Seleção contextual**: reutiliza grupos produzidos por uma comparação anterior, como "essas lojas" ou "essas categorias", sem pedir ao LLM para inventar/copiar os nomes.
2. **Filtros múltiplos**: permite OR dentro de uma dimensão, combinado com AND entre dimensões diferentes.

## Migração da Data Table

Na Data Table `chat_query_state`, adicione duas colunas do tipo **String / Text**:

- `multi_filters`
- `selection_context`

Não remova nem altere as colunas existentes.

O workflow serializa os dois campos como JSON em texto.

## Como funciona a seleção contextual

Exemplo de conversa:

1. `Compare julho e agosto de 2026 e diga quais lojas mais contribuíram para a redução.`
2. `Mostre somente os chamados dessas lojas.`

No segundo passo, o Interpretador retorna apenas uma referência:

```json
{
  "source": "previous_comparison",
  "mode": "top_drivers",
  "dimension": "store_name",
  "limit": 3
}
```

O Merge acrescenta automaticamente um snapshot da comparação e do estado anteriores. O backend então recalcula deterministicamente os grupos reais, aplica-os como filtro múltiplo e mantém o escopo dos dois cenários comparados.

Modos suportados:

- `top_drivers`: grupos que mais contribuíram na direção da variação.
- `offsets`: grupos que compensaram parcialmente a variação.
- `breakdown`: grupos mostrados no breakdown simples anterior.
- `comparison_items`: os dois valores comparados anteriormente.

## Filtros múltiplos

Exemplo:

`Mostre os chamados das lojas ER Itapipoca e Paracuru.`

Estado estruturado:

```json
{
  "multi_filters": {
    "store_name": ["ER Itapipoca", "Paracuru"]
  }
}
```

A semântica é:

- OR dentro da mesma dimensão;
- AND entre dimensões.

Exemplo:

```json
{
  "multi_filters": {
    "store_name": ["ER Itapipoca", "Paracuru"],
    "category": ["Elétrica", "Hidráulica"]
  }
}
```

Significa:

`(loja = ER Itapipoca OU Paracuru) E (categoria = Elétrica OU Hidráulica)`.

Dimensões suportadas:

- `praca`
- `store_name`
- `location_term`
- `analyst_responsible`
- `supplier`
- `requester`
- `category`
- `subcategory`

Status explícitos continuam usando `statuses`.

## Teste recomendado no n8n

Use uma sessão nova:

1. `Compare a quantidade de chamados abertos em julho e agosto de 2026 e diga quais lojas mais contribuíram para a redução.`
2. `Mostre somente os chamados dessas lojas.`
3. `E só os em atendimento?`

O segundo passo deve virar `query_shape = list` com `selection_context` por `store_name`. O terceiro deve preservar a seleção e adicionar o status atual.

Depois teste filtro múltiplo explícito:

`Mostre os chamados das lojas ER Itapipoca e Paracuru.`

## Backend

O endpoint `POST /chatbot/structured-query` aceita agora:

- `state.multi_filters`
- `selection_context`

Quando `selection_context` é usado, a resposta inclui `resolved_selection`, com os valores efetivamente selecionados. O `Montar Resposta Final` usa esse retorno para informar ao usuário quais grupos foram considerados.

## Validação

Nesta versão:

- 43 testes de `test_structured_query.py` passaram;
- 127 testes dos módulos relacionados passaram;
- a suíte completa local não foi executada porque dois módulos dependem de `sqlglot`, ausente neste ambiente de validação.


## Correção de referência curta

O Merge possui fallback determinístico para referências como `dessas lojas` e `dessas categorias`. Se o LLM não preencher `selection_context`, o próprio Merge reconhece a dimensão citada e reconstrói a seleção a partir da comparação anterior. Isso evita que uma listagem contextual caia para todos os registros.
