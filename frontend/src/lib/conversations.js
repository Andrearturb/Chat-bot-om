/** Conversas do assistente: converte o formato da API para o do painel "Conversas". */

export function toConversationItem(item) {
  const count = Number(item.message_count)
  return {
    id: item.id,
    title: item.title || 'Nova conversa',
    createdAt: item.created_at || item.updated_at || '',
    updatedAt: item.updated_at || item.created_at || '',
    messageCount: Number.isFinite(count) && count > 0 ? Math.floor(count) : 0,
  }
}

export function messageCountLabel(count) {
  if (count <= 0) return 'sem mensagens'
  return count === 1 ? '1 mensagem' : `${count} mensagens`
}
