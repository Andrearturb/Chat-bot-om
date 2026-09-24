# Percentual contextual no detalhamento de comparações

Esta evolução separa duas métricas que antes apareciam misturadas no detalhamento por categoria, loja, fornecedor, analista e demais dimensões.

## 1. Variação percentual do próprio grupo

Fórmula:

`(valor_final - valor_inicial) / valor_inicial * 100`

Exemplo:

- Julho: 52
- Agosto: 36
- Diferença: -16
- Variação do próprio grupo: `-16 / 52 = -30,77%`

A resposta passa a apresentar isso como:

> queda de 30,77% dentro da própria categoria

## 2. Contribuição para a variação líquida do recorte

Fórmula:

`diferença_do_grupo / diferença_líquida_do_recorte * 100`

Exemplo geral:

- Total geral: 323 -> 293
- Redução líquida: 30
- Climatização: redução de 16
- Contribuição: `16 / 30 = 53,33%`

A resposta passa a apresentar:

> contribuição para a redução líquida deste recorte: 53,33%

No drill-down, o recorte muda automaticamente. Se a categoria Climatização caiu 16 chamados e a ER Areinha caiu 4 dentro dessa categoria, a contribuição da loja para esse recorte é:

`4 / 16 = 25,00%`

## Movimentos em sentido contrário

Quando um grupo varia no sentido oposto ao resultado líquido, o sistema não o chama de contribuição positiva. Ele informa:

> movimento em sentido contrário equivalente a X% da variação líquida deste recorte

## Escopo da alteração

A mudança é somente de apresentação determinística no node `Montar Resposta Final` do workflow `gentileza.json`.

Não exige:

- nova coluna na Data Table;
- alteração de schema do PostgreSQL;
- alteração do endpoint `/chatbot/structured-query`;
- rebuild do backend ou frontend.

## Ajustes finais de apresentação

1. A frase de contribuição passa a usar o artigo correto conforme o movimento líquido:

- `contribuição para a redução líquida...`
- `contribuição para o aumento líquido...`

2. Quando a soma das contribuições exibidas no mesmo sentido ultrapassa 100% da variação líquida, a resposta inclui automaticamente uma observação explicando a compensação por movimentos no sentido contrário.

Exemplo:

> **Observação:** as reduções dos grupos acima somam mais de 100% da redução líquida porque aumentos em outros grupos compensaram parcialmente a queda.

A observação só aparece quando essa condição realmente ocorrer.
