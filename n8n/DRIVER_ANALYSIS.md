# Análise de drivers da variação

Esta versão amplia `query_shape = comparison` para responder perguntas como:

- `Por que houve essa redução?`
- `O que explica essa variação?`
- `O que puxou esse aumento?`
- `Decomponha essa mudança por categoria e loja.`

A Gentileza continua determinística. O recurso não tenta inferir causalidade operacional. Ele decompõe matematicamente a diferença entre os dois cenários e mostra onde a variação está concentrada nos dados.

## Estrutura

Os novos campos ficam dentro do objeto `comparison`:

- `analysis_mode`: `drivers` ou `null`;
- `driver_dimensions`: dimensões usadas na decomposição;
- `driver_limit`: quantidade máxima de drivers e movimentos compensatórios mostrados por dimensão.

Dimensões suportadas:

- `praca`
- `store_name`
- `analyst_responsible`
- `supplier`
- `requester`
- `category`
- `subcategory`
- `status`

Quando o usuário pergunta genericamente `por que caiu?` ou `o que explica a variação?`, o padrão é:

```json
{
  "analysis_mode": "drivers",
  "driver_dimensions": ["category", "store_name"],
  "driver_limit": 3
}
```

## Resultado do backend

O endpoint `/chatbot/structured-query` passa a retornar `driver_analysis` com:

- variação líquida;
- direção geral (`increase`, `decrease` ou `stable`);
- principais drivers por dimensão;
- movimentos em sentido contrário que compensaram parte da variação;
- contribuição de cada grupo para a variação líquida.

A contribuição é calculada como:

`difference_do_grupo / difference_total * 100`

Por isso, movimentos no sentido contrário aparecem com contribuição negativa. Em uma dimensão completa, as contribuições de todos os grupos somam 100% quando a variação líquida é diferente de zero.

## Importante sobre interpretação

Categoria e loja são leituras alternativas da mesma mudança. Os valores de uma dimensão não devem ser somados com os da outra.

A resposta usa linguagem como `a variação está concentrada em` ou `os grupos que puxaram a redução`, evitando afirmar que os dados provam a causa operacional da mudança.

## Data Table

Nenhuma coluna nova é necessária.

Os campos novos são persistidos dentro da coluna existente `comparison` da Data Table `chat_query_state`.

## Atualização

1. Substitua os arquivos do backend.
2. Rode `docker compose up -d --build`.
3. Importe novamente `n8n/workflows/gentileza.json`.
4. Publique o workflow após o teste no chat do n8n.

## Primeiro teste recomendado

Depois de uma comparação ativa entre julho e agosto de 2026, envie:

`Por que houve essa redução?`

O esperado é a Gentileza preservar os dois períodos e retornar a decomposição por categoria e loja.
