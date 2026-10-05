import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  costFilterOptions, costKpis, costPredicates, costRank, defaultCostFilters, filterCosts,
  postingParts, sortCostDetails,
} from './costsData.js'
import { migrateFilterValues } from '../utils/filterState.js'

const rows = [
  { id: 1, contaRazao: '41140014', postingDate: '2026-01-04', documentDate: '2025-12-29', amount: 100, storeName: 'Loja A', tapeCenterRecordId: 1, supplierName: 'X', praca: 'Natal' },
  { id: 2, contaRazao: '41140014', postingDate: '2026-01-09', documentDate: null, amount: -20, storeName: 'Loja A', tapeCenterRecordId: 1, supplierName: 'X', praca: 'Natal' },
  { id: 3, contaRazao: '41140026', postingDate: '2026-02-01', documentDate: null, amount: 50, storeName: 'Loja B', tapeCenterRecordId: 2, supplierName: 'Y', praca: 'Recife' },
  { id: 4, contaRazao: '41140014', postingDate: '2026-02-03', documentDate: null, amount: 5, storeName: null, tapeCenterRecordId: null, supplierName: null, praca: null },
]

test('KPIs e drill-down compartilham predicados; estorno soma líquido', () => {
  const kpis = costKpis(rows)
  assert.equal(kpis.corretiva, 85)
  assert.equal(kpis.preventiva, 50)
  assert.equal(kpis.total, 135)
  assert.equal(kpis.naoAtribuido, 5)
  assert.equal(kpis.naoAtribuidoCount, rows.filter(costPredicates.naoAtribuido).length)
  assert.equal(kpis.corretiva, costKpis(rows.filter(costPredicates.corretiva)).total)
})

test('mês e ano vêm do lançamento, inclusive documento de exercício anterior', () => {
  assert.deepEqual(postingParts(rows[0].postingDate), { ano: '2026', mes: '01' })
  const result = filterCosts(rows, {
    ...defaultCostFilters, fornecedor: ['X'], loja: ['Loja A'], praca: ['Natal'], mes: ['01'], ano: ['2026'],
  })
  assert.deepEqual(result.map((row) => row.id), [1, 2])
  assert.deepEqual(costFilterOptions(rows).ano, ['2026'])
})

test('filtro com múltiplos valores é OU dentro do mesmo campo', () => {
  // O pedido: a mesma lógica da corretiva — duas ou mais praças ao mesmo tempo.
  const result = filterCosts(rows, { ...defaultCostFilters, praca: ['Natal', 'Recife'] })
  assert.deepEqual(result.map((row) => row.id), [1, 2, 3])
})

test('filtro vazio (array sem itens) não restringe nada', () => {
  assert.equal(filterCosts(rows, defaultCostFilters).length, 4)
  assert.equal(filterCosts(rows, { ...defaultCostFilters, praca: [] }).length, 4)
})

test('tipo aceita corretiva e preventiva juntas', () => {
  const result = filterCosts(rows, { ...defaultCostFilters, tipo: ['41140014', '41140026'] })
  assert.deepEqual(result.map((row) => row.id), [1, 2, 3, 4])
})

test('mês e ano aceitam vários valores', () => {
  const result = filterCosts(rows, { ...defaultCostFilters, mes: ['01', '02'] })
  assert.deepEqual(result.map((row) => row.id), [1, 2, 3, 4])
})

test('ranking ordena por valor líquido, limita em 20 e detalhe desce pela data', () => {
  assert.deepEqual(costRank(rows, 'storeName').map((item) => [item.label, item.amount]), [
    ['Loja A', 80], ['Loja B', 50], ['Não atribuído', 5],
  ])
  const many = Array.from({ length: 25 }, (_, id) => ({ storeName: `L${id}`, amount: id }))
  assert.equal(costRank(many, 'storeName').length, 20)
  assert.deepEqual(sortCostDetails(rows).map((row) => row.id), [4, 3, 2, 1])
})

test('migração: filtro salvo no formato antigo (valor único) entra como array', () => {
  const antigo = { tipo: '41140014', praca: 'todos', loja: '' }
  const migrado = migrateFilterValues(antigo, defaultCostFilters)

  assert.deepEqual(migrado.tipo, ['41140014'])
  assert.deepEqual(migrado.praca, [])
  assert.deepEqual(migrado.loja, [])
})
