import { apiFetch } from '../../lib/apiClient.js'
import { adaptPreventivePayload, adaptServicesPayload } from './dataAdapter'

export class IndicatorsApiError extends Error {
  constructor(message, { status = null, kind = 'service' } = {}) {
    super(message); this.name = 'IndicatorsApiError'; this.status = status; this.kind = kind
  }
}

export async function fetchIndicatorsData({ signal } = {}) {
  let payload
  try {
    payload = await apiFetch('/services', { signal })
  } catch (error) {
    if (error?.name === 'AbortError') throw error
    throw new IndicatorsApiError(error.message || 'Erro ao consultar /services.',
      { status: error?.status, kind: error?.kind || 'http' })
  }
  try {
    return adaptServicesPayload(payload)
  } catch (error) {
    throw new IndicatorsApiError(error.message || 'Não foi possível interpretar os dados.', { kind: 'payload' })
  }
}

export async function syncIndicatorsData() {
  const result = await apiFetch('/imports/tape/central', { method: 'POST' })
  if (!Array.isArray(result?.sources) || result.sources.length !== 3
      || result.sources.some((source) => !['success', 'empty', 'error'].includes(source.status))) {
    throw new IndicatorsApiError('Não foi possível confirmar o resultado da sincronização.', { kind: 'payload' })
  }
  return result
}

export async function fetchPreventiveIndicatorsData({ signal } = {}) {
  let payload
  try {
    payload = await apiFetch('/preventive-services', { signal })
  } catch (error) {
    if (error?.name === 'AbortError') throw error
    throw new IndicatorsApiError(error.message || 'Erro ao consultar /preventive-services.',
      { status: error?.status, kind: error?.kind || 'http' })
  }
  try {
    return adaptPreventivePayload(payload)
  } catch (error) {
    throw new IndicatorsApiError(error.message || 'Não foi possível interpretar os dados preventivos.', { kind: 'payload' })
  }
}

export async function fetchCostIndicatorsData({ signal } = {}) {
  let payload
  try {
    payload = await apiFetch('/maintenance-costs', { signal })
  } catch (error) {
    if (error?.name === 'AbortError') throw error
    throw new IndicatorsApiError(error.message || 'Erro ao consultar /maintenance-costs.',
      { status: error?.status, kind: error?.kind || 'http' })
  }
  if (!Array.isArray(payload?.dados)) {
    throw new IndicatorsApiError('Resposta de custos inválida.', { kind: 'payload' })
  }
  return {
    uploadData: payload.upload_data,
    records: payload.dados.map((row) => ({
      id: row.id,
      contaRazao: row.conta_razao,
      postingDate: row.posting_date,
      documentDate: row.document_date,
      documentNumber: row.document_number,
      postingKey: row.posting_key,
      documentType: row.document_type,
      amount: Number(row.amount),
      division: row.division,
      costCenter: row.cost_center,
      tapeCenterRecordId: row.tape_center_record_id,
      attributionSource: row.attribution_source,
      storeName: row.store_name,
      praca: row.praca,
      supplierName: row.supplier_name,
      description: row.description,
    })),
  }
}
