export const AUTH_ERROR_MESSAGES = {
  invalid_state: {
    title: 'Sessão de autenticação expirada',
    message: 'A tentativa de acesso perdeu a validade. Inicie o login novamente.',
  },
  token_exchange: {
    title: 'Não foi possível concluir a autenticação',
    message: 'O provedor confirmou o acesso, mas houve uma falha ao concluir a sessão. Tente novamente.',
  },
  not_released: {
    title: 'Sua conta ainda não foi liberada',
    message: 'Seu cadastro está confirmado, mas um gestor de acesso ainda precisa liberar o seu perfil no Chat-bot O&M.',
  },
  provider_unavailable: {
    title: 'Login indisponível no momento',
    message: 'Não foi possível contatar o serviço de autenticação. Tente novamente em alguns minutos.',
  },
  provider_error: {
    title: 'Login não concluído',
    message: 'A autenticação foi cancelada ou não pôde ser concluída. Tente novamente.',
  },
  session_not_started: {
    title: 'Não foi possível iniciar a sessão',
    message: 'O login foi feito, mas a sessão não foi confirmada neste navegador. Tente entrar novamente.',
  },
  unavailable: {
    title: 'Serviço indisponível no momento',
    message: 'Não foi possível conectar ao Chat-bot O&M. Verifique sua conexão e tente novamente.',
  },
}

export function getAuthError(code) {
  if (!code) return null
  return AUTH_ERROR_MESSAGES[code] || {
    title: 'Não foi possível concluir o acesso',
    message: 'Ocorreu um problema durante a autenticação. Tente novamente.',
  }
}
