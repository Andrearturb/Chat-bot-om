import test from 'node:test'
import assert from 'node:assert/strict'
import { buildAssetPayload, buildDocumentFormData } from './formUtils.js'

test('asset payload keeps required values and clears optional fields', () => {
  const fields = [
    ['equipment_type', 'Tipo', 'text', true],
    ['capacity_btu', 'BTUs', 'number', true],
    ['location', 'Localização', 'text', true],
    ['brand', 'Marca', 'text', false],
    ['manufacture_year', 'Ano', 'number', false],
  ]
  const payload = buildAssetPayload(fields, {
    equipment_type: ' Cassete ',
    capacity_btu: '36000',
    location: ' Salão ',
    brand: '',
    manufacture_year: '',
    notes: ' ',
  })

  assert.deepEqual(payload, {
    equipment_type: 'Cassete',
    capacity_btu: 36000,
    location: 'Salão',
    brand: null,
    manufacture_year: null,
    notes: null,
  })
})

test('document edit sends empty metadata so existing values can be cleared', () => {
  const data = buildDocumentFormData({
    document_type: 'AVCB',
    custom_document_type: '',
    document_number: '',
    issue_date: '',
    expiration_date: '',
    issuer: '',
    notes: '',
    file: null,
  }, { isEdit: true })

  assert.equal(data.get('document_type'), 'AVCB')
  assert.equal(data.get('document_number'), '')
  assert.equal(data.get('issuer'), '')
  assert.equal(data.get('expiration_date'), '')
})

test('document create omits empty optional metadata', () => {
  const data = buildDocumentFormData({
    document_type: 'AVCB',
    custom_document_type: '',
    document_number: '',
    issue_date: '',
    expiration_date: '',
    issuer: '',
    notes: '',
    file: null,
  })

  assert.equal(data.get('document_type'), 'AVCB')
  assert.equal(data.has('document_number'), false)
  assert.equal(data.has('issuer'), false)
})
