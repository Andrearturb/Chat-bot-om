import test from 'node:test'
import assert from 'node:assert/strict'

import {
  applyCorrectiveFilters,
  buildAnalystSeries,
  buildCorrectiveKpis,
  buildFilterOptions,
  buildMonthlySeries,
  buildRank,
  buildSubcategoryRanks,
  buildStatusCounters,
  defaultCorrectiveFilters,
  filterByRank,
  isCompletedOrderService,
  isConcluded,
  isOrderService,
  orderServiceStatusLabel,
} from './correctiveData.js'

function record(overrides = {}) {
  return {
    ticketId: '1001',
    canonicalStatus: 'Concluído',
    rawStatus: 'Chamado Concluído',
    location: 'ER Centro',
    region: 'Natal',
    category: 'Elétrica',
    subcategory: 'Iluminação',
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

test('SLA conta só concluídos e ignora atraso em chamado não concluído', () => {
  const { sla } = buildCorrectiveKpis([
    record({ canonicalStatus: 'Concluído', slaLate: true }),
    record({ canonicalStatus: 'Concluído', slaLate: false }),
    record({ canonicalStatus: 'Concluído', slaLate: false }),
    record({ canonicalStatus: 'Concluído', slaLate: false }),
    // Atrasado, mas não concluído: fora dos dois lados da conta.
    record({ canonicalStatus: 'Não Aprovado', slaLate: true }),
    record({ canonicalStatus: 'Em atendimento', slaLate: true }),
  ])

  assert.equal(sla.atrasado, 1)
  assert.equal(sla.noPrazo, 3)
  assert.equal(sla.totalConsiderado, 4)
  assert.equal(sla.percent, 75)
})

test('custo médio divide pelos concluídos, com os sem valor entrando como zero', () => {
  const { custoMedio } = buildCorrectiveKpis([
    record({ canonicalStatus: 'Concluído', approvedValue: 300 }),
    record({ canonicalStatus: 'Concluído', approvedValue: 100 }),
    record({ canonicalStatus: 'Concluído', approvedValue: null }),
    record({ canonicalStatus: 'Concluído', approvedValue: 0 }),
    // Não concluído não entra em nenhum dos lados.
    record({ canonicalStatus: 'Em aberto', approvedValue: 900 }),
  ])

  // (300 + 100 + 0 + 0) / 4 concluídos = 100
  assert.equal(custoMedio, 100)
})

test('total de O.S conta apenas assinatura pendente ou concluída', () => {
  const registros = [
    record({ signatureStatus: 'concluido' }),
    record({ signatureStatus: 'Concluída' }),
    record({ signatureStatus: 'pendente' }),
    record({ signatureStatus: 'Aguardando assinatura' }),
    record({ signatureStatus: '' }),
    record({ signatureStatus: 'cancelado' }),
  ]
  const { totalOs } = buildCorrectiveKpis(registros)

  assert.equal(totalOs, 4)
  assert.equal(registros.filter(isOrderService).length, totalOs)
})

test('status e PDF da O.S seguem a conclusão da assinatura', () => {
  const concluida = record({ signatureStatus: 'completo', signedPdfUrl: 'https://api.autentique.com.br/pdf' })
  const pendente = record({ signatureStatus: 'pendente', signedPdfUrl: null })
  assert.equal(orderServiceStatusLabel(concluida), 'Concluída')
  assert.equal(orderServiceStatusLabel(pendente), 'Pendente')
  assert.equal(isCompletedOrderService(concluida), true)
  assert.equal(isCompletedOrderService(pendente), false)
})

test('listas dos KPIs de custo e SLA usam o mesmo conjunto de concluídos', () => {
  const registros = [
    record({ canonicalStatus: 'Concluído', approvedValue: null, slaLate: false }),
    record({ canonicalStatus: 'Concluído', approvedValue: 100, slaLate: true }),
    record({ canonicalStatus: 'Não Aprovado', approvedValue: 900, slaLate: true }),
  ]
  const concluidos = registros.filter(isConcluded)
  const kpis = buildCorrectiveKpis(registros)

  assert.equal(concluidos.length, kpis.sla.totalConsiderado)
  assert.equal(kpis.custoMedio, 50)
  assert.equal(kpis.sla.atrasado, 1)
})

test('base sem concluídos devolve zero em vez de dividir por zero', () => {
  const kpis = buildCorrectiveKpis([record({ canonicalStatus: 'Em aberto', approvedValue: 500 })])

  assert.equal(kpis.totalChamados, 1)
  assert.equal(kpis.custoMedio, 0)
  assert.equal(kpis.sla.percent, 0)
  assert.equal(kpis.sla.totalConsiderado, 0)
})

test('base vazia devolve tudo em zero', () => {
  const kpis = buildCorrectiveKpis([])

  assert.equal(kpis.totalChamados, 0)
  assert.equal(kpis.totalOs, 0)
  assert.equal(kpis.custoMedio, 0)
  assert.equal(kpis.sla.percent, 0)
})

test('ranking traz quantidade, percentual e rótulo de ausência', () => {
  const registros = [
    record({ location: 'ER Centro' }),
    record({ location: 'ER Centro' }),
    record({ location: 'ER Praia' }),
    record({ location: '' }),
  ]

  const rank = buildRank(registros, 'location')

  assert.deepEqual(rank[0], { label: 'ER Centro', total: 2, percent: 50 })
  assert.deepEqual(rank[1], { label: 'ER Praia', total: 1, percent: 25 })
  assert.equal(rank[2].label, 'Sem loja')
  assert.equal(rank[2].total, 1)
})

test('ranking respeita o limite', () => {
  const registros = Array.from({ length: 12 }, (_, indice) =>
    record({ category: `Categoria ${indice}` }),
  )

  assert.equal(buildRank(registros, 'category').length, 8)
  assert.equal(buildRank(registros, 'category', 3).length, 3)
})

test('categoria expande subcategorias e a lista usa o mesmo recorte do contador', () => {
  const registros = [
    record({ ticketId: 'A', category: 'Elétrica', subcategory: 'Iluminação' }),
    record({ ticketId: 'B', category: 'Elétrica', subcategory: 'Iluminação' }),
    record({ ticketId: 'C', category: 'Elétrica', subcategory: 'Tomadas' }),
    record({ ticketId: 'D', category: 'Elétrica', subcategory: 'Não informado' }),
    record({ ticketId: 'E', category: 'Hidráulica', subcategory: 'Iluminação' }),
  ]
  const filtrados = applyCorrectiveFilters(registros, { ...defaultCorrectiveFilters, categoria: 'Elétrica' })
  const categorias = buildRank(filtrados, 'category')
  const subcategorias = buildSubcategoryRanks(filtrados).get('Elétrica')

  assert.equal(categorias[0].total, 4)
  assert.deepEqual(subcategorias, [
    { label: 'Iluminação', total: 2 },
    { label: 'Sem subcategoria', total: 1 },
    { label: 'Tomadas', total: 1 },
  ])
  const detalhe = filterByRank(filterByRank(filtrados, 'category', 'Elétrica'), 'subcategory', 'Iluminação')
  assert.deepEqual(detalhe.map((item) => item.ticketId), ['A', 'B'])
  assert.equal(detalhe.length, subcategorias[0].total)
})

test('série de analistas ordena do maior para o menor', () => {
  const series = buildAnalystSeries([
    record({ analyst: 'Ana' }),
    record({ analyst: 'Ana' }),
    record({ analyst: 'Bruno' }),
  ])

  assert.deepEqual(series, [
    { label: 'Ana', total: 2 },
    { label: 'Bruno', total: 1 },
  ])
})

test('série mensal separa concluídos do total e ordena por data', () => {
  const series = buildMonthlySeries([
    record({ createdOn: '2026-10-02T08:00:00', canonicalStatus: 'Concluído' }),
    record({ createdOn: '2026-09-10T08:00:00', canonicalStatus: 'Concluído' }),
    record({ createdOn: '2026-09-11T08:00:00', canonicalStatus: 'Em aberto' }),
    record({ createdOn: null, canonicalStatus: 'Concluído' }),
  ])

  assert.equal(series.length, 2)
  assert.equal(series[0].key, '2026-09')
  assert.equal(series[0].total, 2)
  assert.equal(series[0].concluidos, 1)
  assert.equal(series[1].key, '2026-10')
  assert.equal(series[1].total, 1)
})
