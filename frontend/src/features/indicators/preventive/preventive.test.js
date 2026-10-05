import test from 'node:test'
import assert from 'node:assert/strict'

import { adaptPreventivePayload, adaptPreventiveService } from '../dataAdapter.js'
import { buildRank } from '../corrective/correctiveData.js'
import {
  applyPreventiveFilters, buildPreventiveFilterOptions, buildPreventiveKpis,
  buildPreventiveStatusCounters, defaultPreventiveFilters,
} from './preventiveData.js'


function service(overrides = {}) {
  return {
    ticket: '2728', status: 'Concluído', raw_status: 'Serviço Finalizado',
    store_name: 'Loja Norte', praca: 'São Luís', category: 'Climatização',
    subcategory: 'Limpeza', periodicity: 'Mensal', approved_value: 2500,
    signature_status: 'completo', signed_pdf_url: 'https://api.autentique.com.br/pdf/1',
    created_on: '2026-09-25T08:00:00', sla_status: null,
    ...overrides,
  }
}


test('adapter da preventiva usa periodicidade, total e PDF do app 57532', () => {
  const record = adaptPreventiveService(service())
  assert.equal(record.canonicalStatus, 'Concluído')
  assert.equal(record.rawStatus, 'Serviço Finalizado')
  assert.equal(record.periodicity, 'Mensal')
  assert.equal(record.approvedValue, 2500)
  assert.equal(record.signedPdfUrl, 'https://api.autentique.com.br/pdf/1')
  assert.equal(record.slaKnown, false)
  assert.equal(adaptPreventivePayload({ dados: [service()], upload_data: null }).records.length, 1)
})


test('status preventivos distinguem Backlog de Serviço Finalizado', () => {
  const records = [
    adaptPreventiveService(service()),
    adaptPreventiveService(service({ ticket: '2', status: 'Backlog', raw_status: 'Backlog' })),
    adaptPreventiveService(service({ ticket: '3', status: 'Em Atendimento', raw_status: 'Em Atendimento' })),
    adaptPreventiveService(service({ ticket: '4', status: 'Não Aprovado', raw_status: 'Não Aprovado' })),
  ]
  const counters = buildPreventiveStatusCounters(records)
  assert.deepEqual(counters, {
    emAberto: 1, emAtendimento: 1, naoAprovado: 1,
    solicitacaoFinalizada: 1, concluidos: 1,
  })
})


test('SLA sem marcador explícito aparece sem dados; custo usa concluídos', () => {
  const records = [
    adaptPreventiveService(service({ approved_value: 300 })),
    adaptPreventiveService(service({ ticket: '2', approved_value: null })),
    adaptPreventiveService(service({ ticket: '3', status: 'Backlog', raw_status: 'Backlog', approved_value: 900 })),
  ]
  const kpis = buildPreventiveKpis(records)
  assert.equal(kpis.totalChamados, 3)
  assert.equal(kpis.custoMedio, 150)
  assert.equal(kpis.sla.percent, null)
  assert.equal(kpis.sla.totalConsiderado, 0)
  assert.equal(kpis.totalOs, 3)
})


test('SLA usa só concluídos com classificação explícita, se houver', () => {
  const records = [
    adaptPreventiveService(service({ sla_status: 'Atrasado' })),
    adaptPreventiveService(service({ ticket: '2', sla_status: 'No prazo' })),
    adaptPreventiveService(service({ ticket: '3', status: 'Backlog', raw_status: 'Backlog', sla_status: 'Atrasado' })),
  ]
  const sla = buildPreventiveKpis(records).sla
  assert.deepEqual(sla, { percent: 50, noPrazo: 1, atrasado: 1, totalConsiderado: 2 })
})


test('periodicidade filtra e ranqueia sem misturar categoria ou loja', () => {
  const records = [
    adaptPreventiveService(service()),
    adaptPreventiveService(service({ ticket: '2', periodicity: 'Anual' })),
    adaptPreventiveService(service({ ticket: '3', periodicity: 'Mensal', category: 'Elétrica' })),
  ]
  const options = buildPreventiveFilterOptions(records)
  assert.deepEqual(options.periodicidade, ['Anual', 'Mensal'])
  const filtered = applyPreventiveFilters(records, {
    ...defaultPreventiveFilters, periodicidade: ['Mensal'], categoria: ['Climatização'],
  })
  assert.deepEqual(filtered.map((item) => item.ticketId), ['2728'])
  assert.deepEqual(buildRank(records, 'periodicity'), [
    { label: 'Mensal', total: 2, percent: 67 },
    { label: 'Anual', total: 1, percent: 33 },
  ])
})

test('periodicidade aceita duas ou mais escolhas de uma vez', () => {
  const records = [
    adaptPreventiveService(service({ periodicity: 'Mensal' })),
    adaptPreventiveService(service({ ticket: '2', periodicity: 'Anual' })),
    adaptPreventiveService(service({ ticket: '3', periodicity: 'Trimestral' })),
  ]
  const filtered = applyPreventiveFilters(records, {
    ...defaultPreventiveFilters, periodicidade: ['Mensal', 'Anual'],
  })
  assert.deepEqual(filtered.map((item) => item.ticketId), ['2728', '2'])
})

test('filtro vazio de periodicidade não restringe nada', () => {
  const records = [adaptPreventiveService(service()), adaptPreventiveService(service({ ticket: '2' }))]
  assert.equal(applyPreventiveFilters(records, defaultPreventiveFilters).length, 2)
})
