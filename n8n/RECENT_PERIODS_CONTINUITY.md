# Continuidade de períodos recentes

Esta evolução corrige dois comportamentos conversacionais:

1. Após consultas consecutivas de períodos diferentes (ex.: setembro e agosto), uma frase como **"faça um comparativo dos dois meses"** usa os dois períodos realmente mencionados, em vez de assumir automaticamente "mês anterior".
2. Depois de uma comparação, uma nova pergunta simples como **"ainda tem chamados em aberto e em atendimento no mês de agosto?"** sai do modo `comparison` e volta para uma consulta simples (`count` ou `list`).

## Nova coluna da Data Table

Na `chat_query_state`, criar uma coluna String/Text:

- `recent_periods`

O valor é um JSON com no máximo dois períodos recentes. Ele é usado apenas pelo workflow e é removido do payload enviado ao backend estruturado.
