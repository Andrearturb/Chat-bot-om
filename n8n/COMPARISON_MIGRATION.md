# Comparações determinísticas — ajuste da Data Table

O workflow `n8n/workflows/gentileza.json` passou a persistir o objeto de comparação para manter continuidade entre mensagens.

Antes de publicar/importar a nova versão no n8n, adicione **uma coluna** na Data Table `chat_query_state`:

- Nome: `comparison`
- Tipo: `String` / `Text`

O valor é salvo como JSON em texto pelo node `Salvar Estado da Conversa`.

Depois disso, publique o workflow e teste, por exemplo:

> Compare a quantidade de chamados abertos em julho e agosto de 2026 e informe a variação percentual.

A comparação suporta dois itens por vez nas dimensões: período, praça, loja, localidade, analista, fornecedor, requisitante, categoria, subcategoria e status.
