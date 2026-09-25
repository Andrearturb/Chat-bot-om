# Gentileza - Exportacao TXT e Excel

Arquivos alterados nesta etapa:

- `frontend/src/components/ChatArea.jsx`
- `frontend/src/App.css`
- `frontend/package.json`

## Comportamento

- Toda resposta normal da Gentileza mostra `Copiar` e `TXT`.
- O botao `Excel` aparece somente quando a resposta renderizada contem uma tabela Markdown.
- O Excel gerado e um arquivo `.xlsx` real.
- Se houver mais de uma tabela na resposta, cada tabela vira uma aba no mesmo arquivo.
- A planilha usa cabecalho em azul-marinho, texto branco, autofiltro, primeira linha congelada e larguras de coluna ajustadas.
- Respostas de erro nao mostram botoes de download.

## Dependencia nova

Foi adicionada ao `frontend/package.json`:

```json
"exceljs": "^4.4.0"
```

Como o projeto usa um volume Docker persistente para `node_modules`, depois de substituir os arquivos execute na raiz do projeto:

```powershell
docker compose exec frontend npm install
```

Isso instala a dependencia no volume atual e atualiza o `package-lock.json` do frontend no seu projeto.

Depois reinicie o frontend:

```powershell
docker compose restart frontend
```

Se o container frontend nao estiver em execucao, use:

```powershell
docker compose up -d --build frontend
```

## Teste sugerido

1. Pergunte algo que gere resposta comum: deve aparecer `Copiar | TXT`.
2. Peca explicitamente uma tabela: deve aparecer `Copiar | TXT | Excel`.
3. Clique em Excel e confirme a geracao de um arquivo `.xlsx`.
