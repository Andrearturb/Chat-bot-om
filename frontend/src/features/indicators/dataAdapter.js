const FALLBACK_TEXT = 'Não informado'

function normalizeText(value) {
  return String(value ?? '').trim()
}

export function normalizeApiDate(value) {
  if (value === null || value === undefined || value === '') return null
  const text = normalizeText(value)
  if (!text) return null
  const parsed = new Date(text)
  return Number.isNaN(parsed.getTime()) ? null : text
}

export function classifyStatus(value) {
  const status = normalizeText(value)

  switch (status) {
    case 'Concluído':
      return 'concluded'
    case 'Não Aprovado':
      return 'rejected'
    case 'Em Aberto':
      return 'backlog'
    case 'Em atendimento':
    case 'Pendente de aprovação':
      return 'in_progress'
    default:
      return 'other'
  }
}

export function statusDisplayLabel(value) {
  const status = normalizeText(value)
  if (!status) return FALLBACK_TEXT
  if (status === 'Em Aberto') return 'Backlog'
  if (status === 'Em atendimento' || status === 'Pendente de aprovação') return 'Em Atendimento'
  return status
}

export function adaptService(service = {}) {
  const canonicalStatus = normalizeText(service.status)
  const approvedValue = Number(service.approved_value)

  return {
    ticketId: normalizeText(service.ticket),
    status: statusDisplayLabel(canonicalStatus),
    statusGroup: classifyStatus(canonicalStatus),
    recurring: '',
    region: normalizeText(service.praca) || FALLBACK_TEXT,
    location: normalizeText(service.store_name) || FALLBACK_TEXT,
    category: normalizeText(service.category) || FALLBACK_TEXT,
    subcategory: normalizeText(service.subcategory) || FALLBACK_TEXT,
    provider: normalizeText(service.supplier) || 'Sem fornecedor',
    analyst: normalizeText(service.analyst_responsible) || FALLBACK_TEXT,
    requester: normalizeText(service.requester) || FALLBACK_TEXT,
    requestDate: normalizeApiDate(service.created_on),
    conclusionDate: normalizeApiDate(service.completion_date),
    createdOn: normalizeApiDate(service.created_on),
    inAttendanceDate: normalizeApiDate(service.in_attendance_date),
    visitDate: normalizeApiDate(service.visit_date),
    slaProgress: '',
    canonicalStatus: canonicalStatus || FALLBACK_TEXT,
    rawStatus: normalizeText(service.raw_status) || FALLBACK_TEXT,
    slaLate: normalizeText(service.sla_late).toLowerCase() === 'atrasado',
    approvedValue:
      service.approved_value === null || service.approved_value === undefined || Number.isNaN(approvedValue)
        ? null
        : approvedValue,
    signatureStatus: normalizeText(service.signature_status),
  }
}

export function adaptServicesPayload(payload) {
  if (!payload || !Array.isArray(payload.dados)) {
    throw new TypeError('Resposta de /services inválida: campo dados ausente ou não é uma lista.')
  }

  return {
    records: payload.dados.map(adaptService),
    uploadData: normalizeApiDate(payload.upload_data),
    pracas: Array.isArray(payload.pracas) ? payload.pracas : [],
  }
}
