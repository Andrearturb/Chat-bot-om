import assert from 'node:assert/strict'
import { test } from 'node:test'

import { messageCountLabel, toConversationItem } from './conversations.js'

test('converte o item da API para o formato do painel de Conversas', () => {
  const item = toConversationItem({
    id: 'c1', title: 'Chamados em aberto', created_at: '2026-10-01T10:00:00Z',
    updated_at: '2026-10-01T10:31:00Z', message_count: 4,
  })
  assert.deepEqual(item, {
    id: 'c1', title: 'Chamados em aberto', createdAt: '2026-10-01T10:00:00Z',
    updatedAt: '2026-10-01T10:31:00Z', messageCount: 4,
  })
})

test('campos ausentes não quebram a tela', () => {
  const item = toConversationItem({ id: 'c2', updated_at: '2026-10-01T10:31:00Z' })
  assert.equal(item.title, 'Nova conversa')
  assert.equal(item.messageCount, 0)
  assert.equal(item.createdAt, '2026-10-01T10:31:00Z')
})

test('contagem inválida vira zero', () => {
  assert.equal(toConversationItem({ id: 'c3', message_count: 'muitas' }).messageCount, 0)
  assert.equal(toConversationItem({ id: 'c3', message_count: -2 }).messageCount, 0)
})

test('texto da contagem no singular e no plural', () => {
  assert.equal(messageCountLabel(0), 'sem mensagens')
  assert.equal(messageCountLabel(1), '1 mensagem')
  assert.equal(messageCountLabel(7), '7 mensagens')
})
