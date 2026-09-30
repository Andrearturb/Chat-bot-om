/**
 * Gestão de Usuários — consulta ao BFF (somente leitura).
 * Cadastro, liberação e bloqueio são feitos no console do Keycloak.
 */

import { api } from '../../lib/apiClient.js'

export const fetchUsers = (signal) => api.get('/users', { signal })
