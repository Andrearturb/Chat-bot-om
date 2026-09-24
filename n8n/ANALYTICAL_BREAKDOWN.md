# Detalhamento analítico de comparações

Esta versão amplia `query_shape = comparison` sem criar um novo tipo de consulta.

A estrutura `comparison` agora aceita:

- `breakdown_by`: dimensão usada para explicar onde ocorreu a mudança;
- `breakdown_order`: `absolute_change`, `increase` ou `decrease`;
- `breakdown_limit`: limite opcional de grupos retornados.

Dimensões de detalhamento suportadas:

- `praca`
- `store_name`
- `analyst_responsible`
- `supplier`
- `requester`
- `category`
- `subcategory`
- `status`

## Exemplos

- `Compare julho e agosto e diga quais lojas mais contribuíram para a redução.`
- `Compare Mossoró e Oeste do Ceará por categoria.`
- `Qual categoria teve a maior variação?` (como continuidade de uma comparação ativa)

## Data Table

Nenhuma coluna nova é necessária. Os novos campos ficam dentro do JSON já persistido na coluna `comparison`.

## Atualização do n8n

Importe novamente `n8n/workflows/gentileza.json` após reconstruir o backend.
