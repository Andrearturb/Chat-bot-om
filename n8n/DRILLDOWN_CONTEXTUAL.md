# Drill-down contextual por dimensão

Esta evolução aprofunda uma comparação existente sem criar um novo `query_shape`.

## Exemplo principal

1. `Compare a quantidade de chamados abertos em julho e agosto de 2026 e explique a redução por categoria.`
2. `Dentro de Climatização e Qualidade do Ar, quais lojas mais contribuíram para a redução?`
3. `E dentro de Controle de Acesso e Segurança?`
4. `E por fornecedor?`

O estado preserva os dois cenários comparados. O valor após `dentro de` vira filtro comum e a dimensão pedida vira `comparison.breakdown_by`.

Exemplo estrutural:

- `changes.category = "Climatização e Qualidade do Ar"`
- `comparison.breakdown_by = "store_name"`
- `comparison.breakdown_order = "decrease"`
- `comparison.breakdown_limit = 5`
- `comparison.analysis_mode = null`

## Referência contextual

Também é possível aprofundar um grupo sem repetir o nome:

`Dentro da primeira categoria, quais lojas mais contribuíram para a redução?`

Nesse caso o Interpretador usa `selection_context` com `mode = "top_drivers"`, `dimension = "category"` e `limit = 1`. O backend resolve o nome real deterministicamente antes de executar o novo breakdown.

## Data Table

Não há novas colunas. Continua usando as colunas já existentes:

- `comparison`
- `multi_filters`
- `selection_context`

## Observação

O drill-down descreve onde a variação está concentrada. Ele não infere causalidade operacional.
