import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  actionLabel, actionOptions, dayEndUtc, dayStartUtc, describeLog, entityLabel, formatDateTime,
} from './auditLabels.js'

test('ações conhecidas saem em português e as novas viram texto legível', () => {
  assert.equal(actionLabel('LOGIN_SUCCESS'), 'Entrou no sistema')
  assert.equal(actionLabel('ASSET_CREATE'), 'Cadastrou equipamento')
  assert.equal(actionLabel('USER_ROLE_CHANGE'), 'User role change')
  assert.equal(actionLabel(''), '—')
  assert.equal(actionLabel(null), '—')
})

test('entidades técnicas viram nomes de negócio', () => {
  assert.equal(entityLabel('app_user'), 'Usuário')
  assert.equal(entityLabel('climate_asset'), 'Climatização')
  assert.equal(entityLabel('store_document'), 'Documento')
  assert.equal(entityLabel('outra_coisa'), 'outra coisa')
  assert.equal(entityLabel(null), '—')
})

test('detalhe junta loja, código do equipamento e arquivo', () => {
  assert.equal(describeLog({ store_name: 'Acaraú', new_values: { asset_code: 'CLI-0001' } }), 'Acaraú · CLI-0001')
  assert.equal(describeLog({ store_name: 'Amontada', new_values: { filename: 'laudo.pdf' } }), 'Amontada · laudo.pdf')
  assert.equal(describeLog({ old_values: { filename: 'velho.pdf' }, new_values: null }), 'velho.pdf')
  assert.equal(describeLog({}), '—')
})

test('opções do filtro vêm sem repetição e ordenadas pelo rótulo', () => {
  const options = actionOptions(['LOGOUT', 'ASSET_CREATE', 'LOGOUT', 'LOGIN_SUCCESS'])
  assert.deepEqual(options.map(o => o.value), ['ASSET_CREATE', 'LOGIN_SUCCESS', 'LOGOUT'])
  assert.deepEqual(actionOptions(undefined), [])
})

test('o dia local vira início e fim em UTC', () => {
  assert.equal(dayStartUtc('2026-10-01'), new Date(2026, 9, 1, 0, 0, 0, 0).toISOString())
  assert.equal(dayEndUtc('2026-10-01'), new Date(2026, 9, 1, 23, 59, 59, 999).toISOString())
  assert.equal(dayStartUtc(''), '')
  assert.equal(dayEndUtc(''), '')
  assert.ok(new Date(dayEndUtc('2026-10-01')) > new Date(dayStartUtc('2026-10-01')))
})

test('data inválida não quebra a tela', () => {
  assert.equal(formatDateTime('lixo'), '—')
  assert.match(formatDateTime('2026-10-01T03:40:42Z'), /\d{2}\/\d{2}\/\d{4}/)
})

test('exportação de ativos aparece na auditoria com o resumo', () => {
  assert.equal(actionLabel('ASSET_EXPORT'), 'Exportou ativos')
  assert.equal(entityLabel('asset_export'), 'Ativos')
  assert.equal(describeLog({ new_values: { stores: 12, assets: 52 } }), '12 lojas · 52 equipamentos')
  assert.equal(describeLog({ new_values: { stores: 1, assets: 1 } }), '1 loja · 1 equipamento')
})
