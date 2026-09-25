# Integração do BI de Resultados no Gentileza

## Arquitetura implementada

O `Chat-bot-OM` continua sendo o aplicativo central. Não foi criado iframe, segundo frontend, segunda porta ou novo container para o antigo `bi-resultados`.

```text
PostgreSQL
  ↓
FastAPI / GET /services
  ↓
frontend/src/features/indicators/api.js
  ↓
dataAdapter.js
  ↓
IndicatorsPage.jsx
  ├── filtros
  ├── KPIs
  ├── volume por praça
  ├── categorias/subcategorias
  ├── resumo executivo
  ├── produtividade de fornecedores
  └── produtividade de analistas
```

A navegação usa estado local no `App.jsx` (`assistant` / `indicators`). O estado e o histórico das conversas permanecem no componente principal e não são apagados ao alternar entre Assistente e Indicadores. `Nova conversa` retorna para o Assistente.

## Fonte de dados

O dashboard não usa upload de Excel. Ele consulta automaticamente:

```text
GET ${VITE_BACKEND_URL}/services
```

A rota já existente foi reaproveitada. Nenhum endpoint duplicado de BI foi criado.

A planilha `Manutenções Corretivas - All data.xlsx` foi usada somente como fotografia de validação.

## Novo campo de backend

Foi incorporado `in_attendance_date` seguindo o fluxo:

```text
Tape field 672479
→ TapeTransformer
→ importer
→ Service.in_attendance_date
→ schema da API
→ GET /services
→ dataAdapter
→ inAttendanceDate
```

Esse campo participa da comparação de diferenças do importer, portanto também é atualizado em sincronizações posteriores.

## Regras preservadas do BI

- `created_on` alimenta `createdOn` e `requestDate`.
- `Em Aberto` é apresentado como `Backlog` e pertence a `statusGroup = backlog`.
- `Em atendimento` e `Pendente de aprovação` são apresentados operacionalmente como `Em Atendimento` e pertencem a `statusGroup = in_progress`.
- `Concluído` pertence a `statusGroup = concluded`.
- `Não Aprovado` pertence a `statusGroup = rejected`.
- produtividade de fornecedores: `(inAttendanceDate ?? createdOn) → conclusionDate`.
- produtividade de analistas: `createdOn → conclusionDate`.
- o nome de fornecedor usado na produtividade continua removendo documento numérico inicial quando existir.
- filtros, KPIs, resumo executivo, praça, categorias/subcategorias e blocos de produtividade foram preservados.

O frontend não tenta renormalizar a regra de negócio da Tape. Ele recebe os status canônicos do backend e faz somente o mapeamento necessário para apresentação/agrupamento.

## Estados da tela

A tela de Indicadores possui estados para:

- carregamento;
- base vazia;
- backend indisponível;
- erro HTTP/payload;
- tentativa novamente;
- atualização manual dos dados;
- falha de atualização mantendo a última base já carregada.

`upload_data` é exibido como `Última atualização`.

## CSS

Os estilos do antigo BI foram incorporados de forma escopada. As regras usam `.indicators-page` / `.workspace--indicators`; regras globais do antigo aplicativo não foram copiadas para o CSS global do chatbot.

## Dependências

Adicionado ao frontend central:

```text
recharts ^2.15.4
```

A dependência `xlsx` do antigo BI não foi adicionada. `exceljs`, já utilizado pelo Gentileza para exportações, foi preservado.

## Validação da planilha de referência

Planilha analisada: 4.825 chamados.

### Datas

- `Created on` e `Data da Requisição`: 4.825/4.825 valores equivalentes na fotografia analisada.
- `data_inicio_atendimento`: 2.795 registros preenchidos.

Isso confirma o uso de `created_on` para `createdOn` e `requestDate`, sem criar coluna redundante no banco.

### Diferença deliberada da regra do importer

Aplicando as regras atuais do backend à fotografia da planilha, 4.818 dos 4.825 registros seriam persistidos.

Os 7 registros excluídos são consequência da regra preexistente de praça:

- 3 registros com praça ausente;
- 4 registros cuja praça original é `Escritório`.

A regra atual também transforma os 130 registros de praça `Brasil` em `Escritório`.

Tickets filtrados nessa fotografia: `4153`, `2275`, `2082`, `2081`, `1965`, `1861`, `181`.

Essa diferença não foi “corrigida” para forçar igualdade com a planilha, porque é uma regra deliberada do importer existente.

### Status / KPIs da fotografia

BI antigo sobre os 4.825 registros da planilha:

- Concluídos: 3.695
- Em andamento: 141
- Backlog: 54
- Rejeitados: 935

API simulada após as regras atuais do importer (4.818 registros):

- Concluídos: 3.694
- Em andamento: 141
- Backlog: 53
- Rejeitados: 930

A diferença é explicada integralmente pelos 7 registros filtrados por praça. Os status restantes são normalizados pelo backend, por exemplo `Chamado Concluído` e `Solicitação Finalizada` → `Concluído`.

Os principais fornecedores da fotografia permaneceram na mesma ordem após a aplicação das regras do backend. Na produtividade de analistas, André Brito passa de 1.713 para 1.712 conclusões nessa fotografia porque o ticket `181`, concluído e atribuído a ele, é um dos registros filtrados pela regra de praça.

## Testes executados

### Backend

```text
pytest backend/tests
169 passed
```

Cobertura adicionada para:

- captura do field 672479;
- conversão de `in_attendance_date`;
- valor nulo;
- persistência;
- atualização em sincronização posterior;
- exposição em `GET /services`.

Também foi executado `compileall` sobre `backend/app` e `backend/tests` sem erro.

### Frontend — regras de Indicadores

```text
npm run test:indicators
9 passed
```

Os testes cobrem:

- adapter da API;
- status/statusGroup;
- datas;
- valores nulos;
- fornecedor/analista ausentes;
- filtros;
- KPIs;
- produtividade de fornecedor com `inAttendanceDate` e fallback;
- produtividade de analista.

### Integração planilha → API → adapter

Foi montada uma API FastAPI de aprovação em SQLite com a fotografia da planilha após as regras reais do importer:

```text
GET /services → HTTP 200
registros retornados: 4.818
in_attendance_date preenchido: 2.795
praças retornadas: 11
adapter do frontend: 4.818 registros
```

### Bundle do frontend

O código completo do frontend foi empacotado com `esbuild` sem erro, incluindo os componentes React, Recharts, CSS e a nova tela de Indicadores.

O comando exato `npm run build` também foi tentado neste ambiente. Ele não chegou à compilação do código porque o `node_modules` disponível no arquivo anexado contém binding opcional do Rollup para outra plataforma e este ambiente não possui acesso ao npm para baixar `@rollup/rollup-linux-x64-gnu`. Isso é uma limitação do ambiente de execução, não um erro de source. O Dockerfile final continua executando `npm install`, portanto o build/execução local instalará o binding correto para o container.

### Docker / endpoints reais

Este ambiente de execução não possui o binário Docker, portanto não foi possível iniciar o `docker-compose.yml` aqui. A validação real local deve ser feita com os comandos abaixo após substituir o projeto.

## Como aplicar localmente

### 1. Recriar somente a tabela `services`

O model ganhou a coluna `in_attendance_date`. Como este é ambiente de desenvolvimento e não há migrations, recrie somente a tabela `services`. Isso preserva o volume e as credenciais/workflows do n8n.

Com o banco já em execução:

```powershell
docker compose stop backend
docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "DROP TABLE IF EXISTS services CASCADE;"'
docker compose up -d --build backend frontend
```

Não é necessário executar `docker compose down -v`; isso removeria também o volume `n8n_data`.

### 2. Sincronizar novamente a Tape

Sem expor API key no terminal:

```powershell
docker compose exec backend python -c "from app.tasks.tape_scheduler import executar_sincronizacao_tape; executar_sincronizacao_tape()"
```

### 3. Validar backend

```powershell
Invoke-RestMethod http://localhost:8040/health | ConvertTo-Json -Depth 5
```

E:

```powershell
$services = Invoke-RestMethod http://localhost:8040/services
$services.dados.Count
```

### 4. Validar frontend

Abra:

```text
http://localhost:5173
```

Teste:

1. Assistente abre normalmente;
2. clique `Indicadores`;
3. painel carrega automaticamente, sem selecionar Excel;
4. filtros e KPIs respondem;
5. gráficos de praça e categoria/subcategoria aparecem;
6. resumo executivo aparece;
7. produtividade de fornecedores e analistas aparece;
8. volte a `Assistente` e confirme que a conversa continua;
9. volte a `Indicadores` e use `Atualizar dados`;
10. clique `Nova conversa` a partir dos Indicadores e confirme retorno ao Assistente.

## Migrations

Nenhum Alembic ou mecanismo temporário de `ALTER TABLE` automático foi criado. A alteração foi feita diretamente no model SQLAlchemy, apropriada para a fase atual de desenvolvimento.
