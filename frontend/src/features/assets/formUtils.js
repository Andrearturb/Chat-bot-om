export function buildAssetPayload(fields, form) {
  const payload = {}
  fields.forEach(([key, , type, required]) => {
    const raw = form[key]
    if (type === 'number') {
      payload[key] = raw === '' || raw === null || raw === undefined ? null : Number(raw)
      return
    }
    if (type === 'date') {
      payload[key] = raw || null
      return
    }
    if (typeof raw === 'string') {
      const cleaned = raw.trim()
      payload[key] = cleaned || (required ? '' : null)
      return
    }
    payload[key] = raw ?? null
  })
  payload.notes = typeof form.notes === 'string' && form.notes.trim() ? form.notes.trim() : null
  return payload
}

export function buildDocumentFormData(form, { isEdit = false } = {}) {
  const data = new FormData()
  const metadataKeys = [
    'document_type',
    'custom_document_type',
    'document_number',
    'issue_date',
    'expiration_date',
    'issuer',
    'notes',
  ]

  metadataKeys.forEach((key) => {
    const value = form[key] ?? ''
    // Em edições, os campos vazios precisam ser enviados para que o backend
    // consiga limpar valores previamente cadastrados.
    if (isEdit || value !== '') data.append(key, value)
  })
  if (form.file) data.append('file', form.file)
  return data
}
