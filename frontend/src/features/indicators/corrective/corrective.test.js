import test from 'node:test'
import assert from 'node:assert/strict'

import {
  applyCorrectiveFilters,
  buildFilterOptions,
  buildStatusCounters,
  defaultCorrectiveFilters,
} from './correctiveData.js'

function record(overrides = {}) {
  return {
    ticketId: '1001',
    canonicalStatus: 'Concluído',
    rawStatus: 'Chamado Concluído',
    location: 'ER Centro',
    region: 'Natal',
    category: 'Elétrica',
    createdOn: '2026-09-10T08:00:00',
    slaLate: false,
    approvedValue: 100,
    signatureStatus: 'concluido',
    ...overrides,
  }
}

test('contadores de status leem o status cru, e Concluídos usa o canônico', () => {
  const counters = buildStatusCounters([
    record({ rawStatus: 'Em Aberto', canonicalStatus: 'Em Aberto' }),
    record({ rawStatus: 'Em Atendimento', canonicalStatus: 'Em atendimento' }),
    record({ rawStatus: 'Não Aprovado', canonicalStatus: 'Não Aprovado' }),
    record({ rawStatus: 'Solicitação Finalizada', canonicalStatus: 'Concluído' }),
    record({ rawStatus: 'Chamado Concluído', canonicalStatus: 'Concluído' }),
  ])

  assert.equal(counters.emAberto, 1)
  assert.equal(counters.emAtendimento, 1)
  assert.equal(counters.naoAprovado, 1)
  assert.equal(counters.solicitacaoFinalizada, 1)
  // Concluídos engloba Solicitação Finalizada: 2, não 1.
  assert.equal(counters.concluidos, 2)
})

test('status cru desconhecido entra no total e em nenhum card', () => {
  const registros = [
    record({ rawStatus: 'Status Novo Da Tape', canonicalStatus: 'Status Novo Da Tape' }),
  ]
  const counters = buildStatusCounters(registros)

  assert.equal(registros.length, 1)
  assert.equal(counters.emAberto, 0)
  assert.equal(counters.emAtendimento, 0)
  assert.equal(counters.naoAprovado, 0)
  assert.equal(counters.solicitacaoFinalizada, 0)
  assert.equal(counters.concluidos, 0)
})

test('filtros combinam loja, praça, categoria e status', () => {
  const registros = [
    record({ ticketId: 'A', location: 'ER Centro', region: 'Natal', category: 'Elétrica' }),
    record({ ticketId: 'B', location: 'ER Praia', region: 'Natal', category: 'Elétrica' }),
    record({ ticketId: 'C', location: 'ER Centro', region: 'Mossoró', category: 'Hidráulica' }),
  ]

  const porLoja = applyCorrectiveFilters(registros, { ...defaultCorrectiveFilters, loja: 'ER Centro' })
  assert.deepEqual(porLoja.map((item) => item.ticketId), ['A', 'C'])

  const porLojaEPraca = applyCorrectiveFilters(registros, {
    ...defaultCorrectiveFilters, loja: 'ER Centro', praca: 'Natal',
  })
  assert.deepEqual(porLojaEPraca.map((item) => item.ticketId), ['A'])

  const porCategoria = applyCorrectiveFilters(registros, { ...defaultCorrectiveFilters, categoria: 'Hidráulica' })
  assert.deepEqual(porCategoria.map((item) => item.ticketId), ['C'])
})

test('filtro de mês e ano usa a data de criação', () => {
  const registros = [
    record({ ticketId: 'A', createdOn: '2026-09-10T08:00:00' }),
    record({ ticketId: 'B', createdOn: '2026-10-02T08:00:00' }),
    record({ ticketId: 'C', createdOn: '2025-09-15T08:00:00' }),
  ]

  const setembro = applyCorrectiveFilters(registros, { ...defaultCorrectiveFilters, mes: '09' })
  assert.deepEqual(setembro.map((item) => item.ticketId), ['A', 'C'])

  const setembro2026 = applyCorrectiveFilters(registros, {
    ...defaultCorrectiveFilters, mes: '09', ano: '2026',
  })
  assert.deepEqual(setembro2026.map((item) => item.ticketId), ['A'])
})

test('data de criação nula não quebra o filtro nem gera opção inválida', () => {
  const registros = [
    record({ ticketId: 'A', createdOn: null }),
    record({ ticketId: 'B', createdOn: '2026-09-10T08:00:00' }),
  ]

  const opcoes = buildFilterOptions(registros)
  assert.deepEqual(opcoes.mes, ['09'])
  assert.deepEqual(opcoes.ano, ['2026'])
  assert.ok(!opcoes.mes.includes('NaN'))

  // Sem filtro de data, o registro sem data continua visível.
  assert.equal(applyCorrectiveFilters(registros, defaultCorrectiveFilters).length, 2)
  // Com filtro de data, ele sai.
  assert.deepEqual(
    applyCorrectiveFilters(registros, { ...defaultCorrectiveFilters, mes: '09' })
      .map((item) => item.ticketId),
    ['B'],
  )
})
