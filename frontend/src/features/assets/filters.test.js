import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  EMPTY_FILTERS, exportParams, exportSummary, filtersParams, isFiltered, matchesStore, normalize,
  pruneStoreIds, samePraca, storesCountLabel, storesForPracas, withPracas,
} from './filters.js'

const options = [
  { id: 1, name: 'Natal Shopping', praca: 'Natal', bpcs: '111', sap: 'A1' },
  { id: 2, name: 'Midway', praca: 'Natal', bpcs: '112', sap: 'A2' },
  { id: 3, name: 'Mossoró Centro', praca: 'Mossoró', bpcs: '113', sap: 'A3' },
  { id: 4, name: 'Loja Sem Praça', praca: null, bpcs: '115', sap: 'A5' },
]

test('praças se comparam sem diferenciar caixa, acento ou espaços', () => {
  assert.ok(samePraca(' natal ', 'Natal'))
  assert.ok(samePraca('Mossoro', 'Mossoró'))
  assert.ok(!samePraca('Natal', 'Fortaleza'))
  assert.equal(normalize(null), '')
})

test('sem praça marcada o seletor de lojas oferece todas', () => {
  assert.equal(storesForPracas(options, []).length, 4)
})

test('com praças marcadas o seletor oferece só as lojas delas (a loja sem praça fica de fora)', () => {
  assert.deepEqual(storesForPracas(options, ['Natal', 'Mossoró']).map(o => o.id), [1, 2, 3])
  assert.deepEqual(storesForPracas(options, ['Natal']).map(o => o.id), [1, 2])
})

test('lojas marcadas que ficam fora das praças restantes saem do filtro', () => {
  assert.deepEqual(pruneStoreIds(options, ['Natal'], [1, 3]), [1])
  assert.deepEqual(pruneStoreIds(options, [], [1, 3, 4]), [1, 3, 4])
  const depois = withPracas({ pracas: ['Natal', 'Mossoró'], storeIds: [2, 3] }, options, ['Natal'])
  assert.deepEqual(depois, { pracas: ['Natal'], storeIds: [2] })
})

test('busca por nome, BPCS, SAP ou praça ignora acento e caixa', () => {
  assert.ok(matchesStore(options[2], 'mossoro'))
  assert.ok(matchesStore(options[0], '111'))
  assert.ok(matchesStore(options[1], 'a2'))
  assert.ok(matchesStore(options[0], 'NATAL'))
  assert.ok(!matchesStore(options[0], 'fortaleza'))
  assert.ok(matchesStore(options[0], '   '))
})

test('filtros viram parâmetros repetidos', () => {
  const params = filtersParams({ pracas: ['Natal', 'Mossoró'], storeIds: [2, 3] })
  assert.deepEqual(params.getAll('praca'), ['Natal', 'Mossoró'])
  assert.deepEqual(params.getAll('store_id'), ['2', '3'])
  assert.equal(filtersParams(EMPTY_FILTERS).toString(), '')
})

test('escopo "tudo" não manda filtros; "filtro ativo" manda', () => {
  const filters = { pracas: ['Natal'], storeIds: [1] }
  const tudo = exportParams(filters, ['water'], 'all')
  assert.equal(tudo.getAll('praca').length, 0)
  assert.deepEqual(tudo.getAll('asset_type'), ['water'])
  const filtrado = exportParams(filters, ['climatization', 'water'], 'filtered')
  assert.deepEqual(filtrado.getAll('praca'), ['Natal'])
  assert.deepEqual(filtrado.getAll('store_id'), ['1'])
  assert.deepEqual(filtrado.getAll('asset_type'), ['climatization', 'water'])
})

test('isFiltered e contagem de lojas', () => {
  assert.equal(isFiltered(EMPTY_FILTERS), false)
  assert.equal(isFiltered({ pracas: ['Natal'], storeIds: [] }), true)
  assert.equal(storesCountLabel(132, 132), '132 lojas')
  assert.equal(storesCountLabel(1, 1), '1 loja')
  assert.equal(storesCountLabel(12, 132), '12 de 132 lojas')
})

test('resumo da exportação só cita os tipos escolhidos', () => {
  const previa = { stores: 12, climatization: 40, fire_safety: 9, water: 3 }
  assert.equal(exportSummary(previa, ['climatization', 'fire_safety', 'water']), '12 lojas · 40 climatização · 9 incêndio · 3 água')
  assert.equal(exportSummary(previa, ['water']), '12 lojas · 3 água')
  assert.equal(exportSummary({ stores: 1, climatization: 0, fire_safety: 0, water: 0 }, ['water']), '1 loja · 0 água')
})
