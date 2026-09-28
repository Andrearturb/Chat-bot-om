# Revisao da Central de Ativos

Data da revisao: 28/09/2026

## Melhorias aplicadas

- Correcao da geracao dos codigos de ativos para nao reutilizar sequencias apos exclusoes.
- Correcao da sincronizacao de lojas para preservar o mesmo registro quando uma loja passa a receber SAP depois de ter sido identificada por BPCS.
- Consolidacao segura de duplicidades preexistentes, preservando os relacionamentos com equipamentos e documentos.
- Eliminacao do padrao N+1 na listagem de lojas por meio de contagens agregadas.
- Criacao de endpoint de filtros de praca independente do resultado da pesquisa.
- Remocao de sincronizacoes e recargas desnecessarias durante a digitacao da busca.
- Capacidade em BTU obrigatoria no cadastro de climatizacao.
- Ajuste visual do card de climatizacao para destacar tipo, BTU e localizacao.
- Edicao de ativos agora permite limpar campos opcionais.
- Edicao de documentos agora permite limpar metadados opcionais.
- Substituicao real do arquivo de um documento existente via multipart/form-data.
- Troca de arquivo com seguranca: o arquivo antigo so e removido depois da persistencia do novo registro.
- Validacao de documento do tipo "Outro" exigindo nome personalizado.
- Refatoracao da Central de Ativos em componentes menores para facilitar manutencao e evolucao.
- Inclusao de testes adicionais da Central de Ativos.

## Validacoes executadas neste ambiente

- Compilacao dos modulos Python do backend: OK.
- Suite completa do backend: 182 testes aprovados.
- Testes especificos de utilitarios do frontend da Central de Ativos: 3 testes aprovados.
- Foram validados, durante a revisao, os fluxos de API da Central de Ativos para criacao/edicao/exclusao de equipamentos e upload/substituicao/leitura/exclusao de documentos.

## Limitacoes do ambiente de validacao

O ZIP recebido nao continha as dependencias executaveis do frontend em `node_modules/.bin`, e este ambiente nao dispoe de instalacao externa das dependencias. Por isso, `npm run build` nao pode ser concluido aqui (`vite: not found`).

O ambiente tambem nao possui Docker disponivel, entao nao foi possivel executar `docker compose up/down` nesta revisao. A configuracao existente de persistencia dos documentos por volume Docker foi mantida.

Antes da publicacao em producao, recomenda-se executar na maquina de desenvolvimento:

```bash
cd frontend
npm install
npm run build

# na raiz do projeto
docker compose up -d --build
```

Depois, validar visualmente a Central de Ativos e reiniciar os containers para confirmar a persistencia dos anexos.

## Seguranca do pacote entregue

O pacote compartilhavel gerado nesta revisao nao inclui o arquivo `.env`, nem `.git`, `.venv`, caches, `node_modules` ou build antigo do frontend. Use o seu `.env` local existente ou crie um a partir de `.env.example`.
