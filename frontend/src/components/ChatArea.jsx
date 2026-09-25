import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { assistantImage } from '../assets/assistantImage'

function formatSeconds(value) {
  if (!Number.isFinite(value)) return null
  return new Intl.NumberFormat('pt-BR', {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format(Math.max(0, value))
}

function buildTimestamp() {
  const now = new Date()
  const pad = (value) => String(value).padStart(2, '0')

  return [
    now.getFullYear(),
    pad(now.getMonth() + 1),
    pad(now.getDate()),
    '-',
    pad(now.getHours()),
    pad(now.getMinutes()),
  ].join('')
}

function downloadBlob(blob, fileName) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = fileName
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

function excelColumnName(columnNumber) {
  let value = columnNumber
  let name = ''

  while (value > 0) {
    const remainder = (value - 1) % 26
    name = String.fromCharCode(65 + remainder) + name
    value = Math.floor((value - 1) / 26)
  }

  return name
}

function tableRows(table) {
  return Array.from(table.rows)
    .map((row) => Array.from(row.cells).map((cell) => cell.innerText.trim()))
    .filter((row) => row.some((cell) => cell !== ''))
}

function CopyIcon({ copied = false }) {
  if (copied) {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="m5 12 4 4L19 6" />
      </svg>
    )
  }

  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <rect x="9" y="9" width="10" height="10" rx="2" />
      <path d="M15 9V7a2 2 0 0 0-2-2H7a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2" />
    </svg>
  )
}

function DownloadIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 4v11" />
      <path d="m7.5 10.5 4.5 4.5 4.5-4.5" />
      <path d="M5 19h14" />
    </svg>
  )
}

function ExcelIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M6 3h9l3 3v15H6z" />
      <path d="M15 3v4h4" />
      <path d="m9 11 4 6" />
      <path d="m13 11-4 6" />
    </svg>
  )
}

async function copyText(text) {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text)
      return
    } catch {
      // Usa o fallback abaixo quando a API moderna não estiver disponível no contexto atual.
    }
  }

  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.setAttribute('readonly', '')
  textarea.style.position = 'fixed'
  textarea.style.opacity = '0'
  document.body.appendChild(textarea)
  textarea.select()
  document.execCommand('copy')
  textarea.remove()
}

function Message({ message, suggestions = [] }) {
  const isAssistant = message.role === 'assistant'
  const showActions = isAssistant && !message.isGreeting
  const showDownloads = showActions && !message.isError
  const [copied, setCopied] = useState(false)
  const [hasTable, setHasTable] = useState(false)
  const [exportingExcel, setExportingExcel] = useState(false)
  const contentRef = useRef(null)
  const copyResetRef = useRef(null)
  const responseTime = formatSeconds(message.responseTime)

  useEffect(() => () => clearTimeout(copyResetRef.current), [])

  useEffect(() => {
    setHasTable(Boolean(contentRef.current?.querySelector('table')))
  }, [message.content])

  function getVisibleText() {
    return contentRef.current?.innerText?.trim() || message.content || ''
  }

  async function handleCopy() {
    try {
      await copyText(getVisibleText())
      setCopied(true)
      clearTimeout(copyResetRef.current)
      copyResetRef.current = setTimeout(() => setCopied(false), 1600)
    } catch (error) {
      console.error('Não foi possível copiar a resposta:', error)
    }
  }

  function handleDownloadTxt() {
    const text = getVisibleText()
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
    downloadBlob(blob, `gentileza_resposta_${buildTimestamp()}.txt`)
  }

  async function handleExportExcel() {
    const tables = Array.from(contentRef.current?.querySelectorAll('table') || [])
    if (tables.length === 0 || exportingExcel) return

    setExportingExcel(true)

    try {
      const excelModule = await import('exceljs')
      const ExcelJS = excelModule.default || excelModule
      const workbook = new ExcelJS.Workbook()
      workbook.creator = 'Gentileza - Gentil Negócios'
      workbook.created = new Date()

      tables.forEach((table, index) => {
        const rows = tableRows(table)
        if (rows.length === 0) return

        const sheetName = tables.length === 1 ? 'Dados' : `Tabela ${index + 1}`
        const worksheet = workbook.addWorksheet(sheetName)
        worksheet.addRows(rows)

        const columnCount = Math.max(...rows.map((row) => row.length))
        const headerRow = worksheet.getRow(1)

        headerRow.height = 24
        headerRow.eachCell((cell) => {
          cell.font = { bold: true, color: { argb: 'FFFFFFFF' } }
          cell.fill = {
            type: 'pattern',
            pattern: 'solid',
            fgColor: { argb: 'FF111A3E' },
          }
          cell.alignment = { vertical: 'middle', wrapText: true }
        })

        worksheet.eachRow((row, rowNumber) => {
          row.eachCell((cell) => {
            cell.alignment = {
              ...cell.alignment,
              vertical: 'top',
              wrapText: true,
            }

            if (rowNumber > 1) {
              cell.border = {
                bottom: { style: 'hair', color: { argb: 'FFE7EAF0' } },
              }
            }
          })
        })

        for (let columnIndex = 1; columnIndex <= columnCount; columnIndex += 1) {
          const values = rows.map((row) => String(row[columnIndex - 1] || ''))
          const longest = Math.max(10, ...values.map((value) => value.length + 2))
          worksheet.getColumn(columnIndex).width = Math.min(longest, 45)
        }

        if (columnCount > 0) {
          worksheet.autoFilter = `A1:${excelColumnName(columnCount)}1`
        }

        worksheet.views = [{ state: 'frozen', ySplit: 1 }]
      })

      if (workbook.worksheets.length === 0) return

      const buffer = await workbook.xlsx.writeBuffer()
      const blob = new Blob([buffer], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      })

      downloadBlob(blob, `gentileza_dados_${buildTimestamp()}.xlsx`)
    } catch (error) {
      console.error('Não foi possível gerar o arquivo Excel:', error)
    } finally {
      setExportingExcel(false)
    }
  }

  return (
    <article className={`message message--${message.role}`}>
      {isAssistant && <img className="message__avatar" src={assistantImage} alt="" />}
      <div className="message__body">
        <div className="message__content">
          {isAssistant ? (
            <div className="message__markdown" ref={contentRef}>
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content || ''}</ReactMarkdown>
            </div>
          ) : message.content}
          {isAssistant && suggestions.length > 0 && (
            <div className="message__suggestions" aria-label="Sugestões relacionadas">
              {suggestions.map((suggestion) => (
                <button key={suggestion} type="button">{suggestion}</button>
              ))}
            </div>
          )}
        </div>

        {showActions && (
          <div className="message__actions">
            {responseTime && (
              <span className={`message__response-time ${message.isError ? 'message__response-time--error' : ''}`}>
                {message.isError ? `Falhou em ${responseTime}s` : `Respondido em ${responseTime}s`}
              </span>
            )}

            <button
              className={`message__action-button ${copied ? 'message__action-button--success' : ''}`}
              type="button"
              onClick={handleCopy}
              aria-label={copied ? 'Resposta copiada' : 'Copiar resposta'}
              title={copied ? 'Copiado' : 'Copiar'}
            >
              <CopyIcon copied={copied} />
              <span>{copied ? 'Copiado' : 'Copiar'}</span>
            </button>

            {showDownloads && (
              <button
                className="message__action-button"
                type="button"
                onClick={handleDownloadTxt}
                aria-label="Baixar resposta em TXT"
                title="Baixar TXT"
              >
                <DownloadIcon />
                <span>TXT</span>
              </button>
            )}

            {showDownloads && hasTable && (
              <button
                className="message__action-button message__action-button--excel"
                type="button"
                onClick={handleExportExcel}
                disabled={exportingExcel}
                aria-label="Exportar tabela para Excel"
                title="Exportar Excel (.xlsx)"
              >
                <ExcelIcon />
                <span>{exportingExcel ? 'Gerando...' : 'Excel'}</span>
              </button>
            )}
          </div>
        )}
      </div>
    </article>
  )
}

function ThinkingMessage({ startedAt }) {
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    if (!Number.isFinite(startedAt)) {
      setElapsed(0)
      return undefined
    }

    const updateElapsed = () => {
      setElapsed(Math.max(0, (performance.now() - startedAt) / 1000))
    }

    updateElapsed()
    const interval = setInterval(updateElapsed, 100)
    return () => clearInterval(interval)
  }, [startedAt])

  return (
    <article className="message message--assistant message--thinking" aria-label="Gentileza está processando a resposta">
      <img className="message__avatar" src={assistantImage} alt="" />
      <div className="message__body">
        <div className="message__content message__thinking">
          <span className="thinking-dots" aria-hidden="true"><i /><i /><i /></span>
          <span>Pensando... {formatSeconds(elapsed)}s</span>
        </div>
      </div>
    </article>
  )
}

export default function ChatArea({
  messages,
  active,
  suggestions = [],
  loading = false,
  thinkingStartedAt = null,
  serviceStatus = 'ready',
}) {
  const messagesRef = useRef(null)

  const statusConfig = {
    checking: {
      label: 'Verificando...',
      className: 'checking',
      title: 'Verificando a disponibilidade da API, banco de dados e n8n.',
    },
    online: {
      label: 'Online',
      className: 'online',
      title: 'API, banco de dados e n8n disponíveis na última verificação.',
    },
    error: {
      label: 'Erro no serviço',
      className: 'error',
      title: 'O sistema respondeu, mas algum componente não está pronto ou uma solicitação falhou.',
    },
    offline: {
      label: 'Sem conexão',
      className: 'offline',
      title: 'O navegador não conseguiu alcançar o serviço.',
    },
  }

  const currentStatus = statusConfig[serviceStatus] || statusConfig.checking

  useEffect(() => {
    if (!active || !messagesRef.current) return

    const container = messagesRef.current
    container.scrollTo({
      top: container.scrollHeight,
      behavior: 'smooth',
    })
  }, [active, messages, loading])

  return (
    <section className={`chat-area ${active ? 'chat-area--active' : ''}`} aria-live="polite">
      <div className="chat-header">
        <img src={assistantImage} alt="" />
        <div>
          <strong>Gentileza</strong>
          <span className={`service-status service-status--${currentStatus.className}`} title={currentStatus.title}>
            <i />
            Assistente de Obras &amp; Manutenções · {currentStatus.label}
          </span>
        </div>
      </div>
      <div className="messages" ref={messagesRef}>
        {messages.map((message) => (
          <Message key={message.id} message={message} suggestions={message.role === 'assistant' ? suggestions : []} />
        ))}
        {loading && <ThinkingMessage startedAt={thinkingStartedAt} />}
      </div>
    </section>
  )
}
