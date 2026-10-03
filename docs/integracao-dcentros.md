# Relação dos chamados com o dCentros

O app Tape **30902** contém as lojas do dCentros. O campo `Local de Atendimento`
dos chamados corretivos (app 57531, field 580441) e preventivos (app 57532,
field 580460) contém uma referência com `app_id: 30902` e o `record_id` da loja.
Esse é o identificador usado para ligar os dados; o número visível da loja
vem do campo `Unique ID` (field 290650) do registro do dCentros.

O mesmo `TapeSyncScheduler` sincroniza, nessa ordem, dCentros, corretivas e
preventivas com a mesma `TAPE_API_TOKEN`. A sincronização manual existente
também aceita `POST /imports/tape?app_id=30902`. Os registros do dCentros ficam
em `tape_centers`, com `record_id` como chave primária. Os chamados guardam
`tape_center_record_id`, indexado em ambas as tabelas. O vínculo pode ser
consultado por `LEFT JOIN`; não há chave estrangeira obrigatória para que um
chamado continue importável mesmo quando um registro de loja estiver ausente
na resposta atual da Tape. Nenhuma sincronização apaga registros não retornados.

Campos guardados da loja: número (`Unique ID`), nome, nome abreviado, BCPS, SAP,
centro de custo, praça, status, marca, tipo, empresa, UF, CNPJ, endereço e URL
do registro. E-mail e outros campos não usados nessa relação não são copiados.
Os endpoints `/services` e `/preventive-services` expõem
`tape_center_record_id` e `center_unique_number`.

```sql
SELECT p.ticket, c.unique_number, c.name, c.bcps_number, c.cost_center
FROM preventive_services p
LEFT JOIN tape_centers c ON c.record_id = p.tape_center_record_id;
```

Na validação local de 2026-10-03, as **224 lojas** foram importadas sem rejeição.
Os 224 `record_id`, números `Unique ID` e BCPS eram distintos nessa leitura.
Todos os **2.509** chamados preventivos e **4.893** corretivos que traziam
referência do dCentros encontraram sua loja na tabela. Dez registros corretivos
locais ficaram sem referência: oito sem loja na origem e dois tickets de teste.
Exemplos confirmados: preventiva 2727 → Natal Shopping (`record_id` 32220251,
`Unique ID` 40); preventiva 2728 → Mateus Cohama (`record_id` 32220203,
`Unique ID` 36).
