import { useAuth } from './AuthProvider.jsx'

export default function PermissionGate({ permission, fallback = null, children }) {
  const { hasPermission } = useAuth()
  return hasPermission(permission) ? children : fallback
}
