# Painel de Chamados Preventivos

O painel Preventivos da Central de Indicadores lê o app Tape **57532** com a
mesma variável `TAPE_API_TOKEN` usada pela corretiva (app **57531**). Há um
único `TapeSyncScheduler`; a cada ciclo ele sincroniza os dois apps, com
sessões e tratamento de erro separados. O endpoint manual existente
`POST /imports/tape?app_id=57532` também aciona a preventiva. O padrão sem
`app_id` continua sendo a corretiva, para preservar as integrações atuais.

Os dados ficam na tabela `preventive_services`, separada de `services`. O
mesmo número de ticket pode existir nos dois apps sem colisão. A sincronização
atualiza por diferenças e não apaga registros que a Tape deixe de retornar.
`GET /preventive-services` exige `indicators.view` e devolve somente os campos
usados pelo painel.

| Uso no painel | Campo Tape | ID |
|---|---|---:|
| Ticket | Ticket | 677154 |
| Status | Status | 676273 |
| Loja | Loja_custom / Local de Atendimento | 681363 / 580460 |
| Praça | Praça | 580462 |
| Categoria e subcategoria | Serviço (Categoria) / Subcategoria | 580461 / 676274 |
| Analista e fornecedor | Analista Responsável / Fornecedor | 676275 / 676276 |
| Valor do serviço | Valor Total | 680415 |
| O.S e PDF | Status de Assinatura / Status da ordem de serviço / PDF_VIEW | 681369 / 681370 / 681371 |
| Periodicidade | Periocidade | 693107 |
| SLA | Progresso SLA / Data Prevista / Data de Encerramento | 676271 / 676272 / 676284 |

Descrição, solução, visita, motivo de reprovação e data de criação também são
guardados para o detalhe do chamado. Os demais campos da lista da Tape não são
persistidos.

## Regras do painel

- **Concluídos:** status cru `Serviço Finalizado` (ou `Serviço Concluído`) é
  apresentado como `Concluído` nos cálculos, preservando o status cru no card.
- **Total de O.S:** assinatura pendente ou concluída. O link PDF só aparece
  quando a assinatura está concluída e há URL HTTP(S) válida.
- **Custo médio:** soma de `Valor Total` dos concluídos dividida por todos os
  concluídos; valor ausente entra como zero no denominador.
- **Filtros:** status, loja, praça, categoria, mês, ano e periodicidade. Os
  rankings de loja, categoria/subcategoria e periodicidade respeitam o recorte.
- **SLA:** só entra no cálculo quando a Tape indicar explicitamente `Atrasado`
  ou `No prazo`. A barra HTML de progresso sozinha não permite classificar.
  Quando não há nenhum concluído classificado, o card mostra **Sem dados**.

Na leitura de 2026-10-02, o app 57532 retornou 2.509 registros. Todos tinham
`Progresso SLA`, mas nenhum continha marca de atraso; `Data Prevista` e `Data
de Encerramento` estavam vazias. Exibir 100% a partir dessa barra repetiria a
falha de interpretação identificada no BI original da corretiva.

Na primeira sincronização local, os 2.509 registros foram inseridos sem rejeições.
A base corretiva permaneceu com 4.898 registros. O agendador continua sendo
um só para os dois apps.
