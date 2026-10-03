import { useEffect } from 'react'
import { isConcluded } from '../correctiveData'

const NUMERO = new Intl.NumberFormat('pt-BR')
const MOEDA = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' })
const LIMITE = 200

function dataBr(value) {
  if (!value) return '—'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? '—' : parsed.toLocaleDateString('pt-BR')
}

export default function CorrectiveDetailModal({ detail, onClose }) {
  useEffect(() => {
    if (!detail) return undefined
    function onKeyDown(event) {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [detail, onClose])

  if (!detail) return null

  const { titulo, registros } = detail
  const visiveis = registros.slice(0, LIMITE)

  return (
    <div className="corrective-modal" role="dialog" aria-modal="true" aria-label={titulo}>
      <div className="corrective-modal__backdrop" onClick={onClose} />
      <div className="corrective-modal__content">
        <header>
          <div>
            <h3>{titulo}</h3>
            <p>{NUMERO.format(registros.length)} chamado(s)</p>
          </div>
          <button type="button" onClick={onClose} aria-label="Fechar">×</button>
        </header>

        {registros.length === 0 ? (
          <p className="corrective-empty">Nenhum chamado neste recorte.</p>
        ) : (
          <div className="corrective-modal__scroll">
            <table>
              <thead>
                <tr>
                  <th>Ticket</th><th>Status</th><th>Loja</th><th>Praça</th>
                  <th>Categoria</th><th>Criado em</th><th>SLA</th>
                  <th style={{ textAlign: 'right' }}>Valor</th>
                </tr>
              </thead>
              <tbody>
                {visiveis.map((record) => (
                  <tr key={record.ticketId}>
                    <td>{record.ticketId}</td>
                    <td>{record.rawStatus}</td>
                    <td>{record.location}</td>
                    <td>{record.region}</td>
                    <td>{record.category}</td>
                    <td>{dataBr(record.createdOn)}</td>
                    <td>{!isConcluded(record) ? '—' : record.slaLate ? 'Atrasado' : 'No prazo'}</td>
                    <td style={{ textAlign: 'right' }}>
                      {typeof record.approvedValue === 'number' ? MOEDA.format(record.approvedValue) : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {registros.length > LIMITE && (
          <footer>
            Mostrando os primeiros {NUMERO.format(LIMITE)} de {NUMERO.format(registros.length)}. Use os filtros para estreitar.
          </footer>
        )}
      </div>
    </div>
  )
}
