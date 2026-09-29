export const AUTH_ERROR_MESSAGES = {
  invalid_state: {
    title: 'Sessão de autenticação expirada',
    message: 'A tentativa de acesso perdeu a validade. Inicie o login novamente.',
  },
  token_exchange: {
    title: 'Não foi possível concluir a autenticação',
    message: 'O provedor confirmou o acesso, mas houve uma falha ao concluir a sessão. Tente novamente.',
  },
  no_user: {
    title: 'Conta não reconhecida',
    message: 'A identidade foi autenticada, mas não foi possível vinculá-la ao Chat-bot O&M.',
  },
  pending: {
    title: 'Acesso aguardando liberação',
    message: 'Sua identidade foi autenticada com sucesso, mas seu acesso ao Chat-bot O&M ainda não está ativo.',
  },
  disabled: {
    title: 'Acesso indisponível',
    message: 'Sua conta está desativada ou o período de acesso expirou.',
  },
}

export function getAuthError(code) {
  if (!code) return null
  return AUTH_ERROR_MESSAGES[code] || {
    title: 'Não foi possível concluir o acesso',
    message: 'Ocorreu um problema durante a autenticação. Tente novamente.',
  }
}
