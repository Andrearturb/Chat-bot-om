/**
 * Gestão de Usuários — chamadas ao BFF.
 * O navegador fala somente com o backend; a Keycloak Admin API é server-side.
 */

import { api } from '../../lib/apiClient.js'

export const fetchUsers = (signal) => api.get('/users', { signal })
export const fetchProfiles = (signal) => api.get('/users/profiles', { signal })
export const fetchCapabilities = (signal) => api.get('/users/capabilities', { signal })

export const createUser = (payload) => api.post('/users', payload)
export const updateUser = (id, payload) => api.patch(`/users/${id}`, payload)
export const activateUser = (id) => api.post(`/users/${id}/activate`, {})
export const deactivateUser = (id) => api.post(`/users/${id}/deactivate`, {})

// A senha temporária segue apenas para o backend → Keycloak e nunca volta na resposta.
export const resetUserPassword = (id, temporaryPassword) =>
  api.post(`/users/${id}/reset-password`, { temporary_password: temporaryPassword })

export const sendPasswordEmail = (id) => api.post(`/users/${id}/password-email`, {})
