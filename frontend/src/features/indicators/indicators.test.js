import test from 'node:test'
import assert from 'node:assert/strict'

import {
  adaptService,
  adaptServicesPayload,
  classifyStatus,
  statusDisplayLabel,
} from './dataAdapter.js'
import {
  applyFilters,
  buildAnalystProductivity,
  buildMetrics,
  buildSupplierProductivity,
  defaultFilters,
} from './utils/dashboardData.js'

function service(overrides = {}) {
  return {
    ticket: '1001',
    status: 'Concluído',
    store_name: 'ER Centro',
    praca: 'Natal',
    category: 'Instalações Elétricas',
    subcategory: 'Iluminação',
    supplier: '12.345.678/0001-90 - FORNECEDOR TESTE LTDA',
    analyst_responsible: 'Analista Teste',
    requester: 'Solicitante Teste',
    created_on: '2026-09-01T08:00:00',
    completion_date: '2026-09-05T08:00:00',
    visit_date: '2026-09-03T08:00:00',
    in_attendance_date: '2026-09-02T08:00:00',
    ...overrides,
  }
}

test('adapter mapeia o contrato do GET /services para o dashboard', () => {
  const record = adaptService(service())

  assert.equal(record.ticketId, '1001')
  assert.equal(record.canonicalStatus, 'Concluído')
  assert.equal(record.statusGroup, 'concluded')
  assert.equal(record.region, 'Natal')
  assert.equal(record.location, 'ER Centro')
  assert.equal(record.provider, '12.345.678/0001-90 - FORNECEDOR TESTE LTDA')
  assert.equal(record.analyst, 'Analista Teste')
  assert.equal(record.requestDate, '2026-09-01T08:00:00')
  assert.equal(record.createdOn, '2026-09-01T08:00:00')
  assert.equal(record.conclusionDate, '2026-09-05T08:00:00')
  assert.equal(record.inAttendanceDate, '2026-09-02T08:00:00')
  assert.equal(record.visitDate, '2026-09-03T08:00:00')
})

test('status do backend mantém grupos e apresentação esperados pelo BI', () => {
  assert.equal(classifyStatus('Em Aberto'), 'backlog')
  assert.equal(statusDisplayLabel('Em Aberto'), 'Backlog')

  assert.equal(classifyStatus('Em atendimento'), 'in_progress')
  assert.equal(statusDisplayLabel('Em atendimento'), 'Em Atendimento')

  assert.equal(classifyStatus('Pendente de aprovação'), 'in_progress')
  assert.equal(statusDisplayLabel('Pendente de aprovação'), 'Em Atendimento')

  assert.equal(classifyStatus('Concluído'), 'concluded')
  assert.equal(classifyStatus('Não Aprovado'), 'rejected')
})

test('adapter trata datas e campos nulos sem quebrar o dashboard', () => {
  const record = adaptService(service({
    supplier: null,
    analyst_responsible: null,
    requester: null,
    category: null,
    subcategory: null,
    in_attendance_date: null,
    visit_date: 'data-invalida',
  }))

  assert.equal(record.provider, 'Sem fornecedor')
  assert.equal(record.analyst, 'Não informado')
  assert.equal(record.requester, 'Não informado')
  assert.equal(record.category, 'Não informado')
  assert.equal(record.subcategory, 'Não informado')
  assert.equal(record.inAttendanceDate, null)
  assert.equal(record.visitDate, null)
})

test('payload exige dados e preserva upload_data/pracas', () => {
  const result = adaptServicesPayload({
    dados: [service()],
    upload_data: '2026-09-25T12:00:00-03:00',
    pracas: ['Natal'],
  })

  assert.equal(result.records.length, 1)
  assert.equal(result.uploadData, '2026-09-25T12:00:00-03:00')
  assert.deepEqual(result.pracas, ['Natal'])
  assert.throws(() => adaptServicesPayload({ dados: null }), /campo dados/)
})

test('KPIs contam os grupos operacionais sem duplicar status', () => {
  const records = [
    adaptService(service({ ticket: '1', status: 'Em Aberto' })),
    adaptService(service({ ticket: '2', status: 'Em atendimento' })),
    adaptService(service({ ticket: '3', status: 'Pendente de aprovação' })),
    adaptService(service({ ticket: '4', status: 'Concluído' })),
    adaptService(service({ ticket: '5', status: 'Não Aprovado' })),
  ]

  const metrics = buildMetrics(records)
  assert.equal(metrics.total, 5)
  assert.equal(metrics.backlog, 1)
  assert.equal(metrics.inProgress, 2)
  assert.equal(metrics.concluded, 1)
  assert.equal(metrics.rejected, 1)
})

test('filtros combinam praça, status e período pela data de requisição', () => {
  const records = [
    adaptService(service({ ticket: '1', status: 'Em Aberto', praca: 'Natal', created_on: '2026-09-10T08:00:00' })),
    adaptService(service({ ticket: '2', status: 'Em Aberto', praca: 'Mossoró', created_on: '2026-09-10T08:00:00' })),
    adaptService(service({ ticket: '3', status: 'Concluído', praca: 'Natal', created_on: '2026-08-10T08:00:00' })),
  ]

  const filtered = applyFilters(records, {
    ...defaultFilters,
    region: 'Natal',
    status: 'Backlog',
    startDate: '2026-09-01',
    endDate: '2026-09-30',
  })

  assert.deepEqual(filtered.map((record) => record.ticketId), ['1'])
})

test('produtividade de fornecedor usa inAttendanceDate antes de createdOn', () => {
  const records = [adaptService(service({
    created_on: '2026-09-01T08:00:00',
    in_attendance_date: '2026-09-03T08:00:00',
    completion_date: '2026-09-05T08:00:00',
  }))]

  const rows = buildSupplierProductivity(records, defaultFilters)
  assert.equal(rows.length, 1)
  assert.equal(rows[0].name, 'FORNECEDOR TESTE LTDA')
  assert.equal(rows[0].concluded, 1)
  assert.equal(rows[0].avgDays, 2)
})

test('produtividade de fornecedor cai para createdOn quando início de atendimento é nulo', () => {
  const records = [adaptService(service({
    in_attendance_date: null,
    created_on: '2026-09-01T08:00:00',
    completion_date: '2026-09-05T08:00:00',
  }))]

  const rows = buildSupplierProductivity(records, defaultFilters)
  assert.equal(rows[0].avgDays, 4)
})

test('produtividade de analista continua usando createdOn e não inAttendanceDate', () => {
  const records = [adaptService(service({
    created_on: '2026-09-01T08:00:00',
    in_attendance_date: '2026-09-04T08:00:00',
    completion_date: '2026-09-05T08:00:00',
  }))]

  const rows = buildAnalystProductivity(records, defaultFilters)
  assert.equal(rows.length, 1)
  assert.equal(rows[0].name, 'Analista Teste')
  assert.equal(rows[0].avgDays, 4)
})

test('adaptService expõe SLA, valor aprovado e status cru da corretiva', () => {
  const record = adaptService(service({
    status: 'Concluído',
    raw_status: 'Chamado Concluído',
    sla_late: 'Atrasado',
    approved_value: 350,
  }))

  assert.equal(record.canonicalStatus, 'Concluído')
  assert.equal(record.rawStatus, 'Chamado Concluído')
  assert.equal(record.slaLate, true)
  assert.equal(record.approvedValue, 350)
})

test('adaptService expõe o status de assinatura para o Total de O.S', () => {
  const record = adaptService(service({ signature_status: 'Concluída' }))

  assert.equal(record.signatureStatus, 'Concluída')
})

test('adaptService trata ausência dos campos da corretiva', () => {
  const record = adaptService(service({ raw_status: null, sla_late: null, approved_value: null }))

  assert.equal(record.rawStatus, 'Não informado')
  assert.equal(record.slaLate, false)
  assert.equal(record.approvedValue, null)
})

test('adaptService preserva valor aprovado zero', () => {
  const record = adaptService(service({ approved_value: 0 }))

  assert.equal(record.approvedValue, 0)
})
