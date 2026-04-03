/**
 * AuthContext - secure auth state management.
 * Access token stored in memory. Refresh token in httpOnly cookie.
 */
import { createContext, useContext, useState, useEffect, useRef, useCallback } from 'react'
import axios from 'axios'

const AuthContext = createContext(null)

const authApi = axios.create({ baseURL: '/api', withCredentials: true, timeout: 10000 })

function decodeJWT(token) {
  try {
    return JSON.parse(atob(token.split('.')[1].replace(/-/g,'+').replace(/_/g,'/')))
  } catch { return null }
}

export function AuthProvider({ children }) {
  const [accessToken, setAccessToken] = useState(null)
  const [user,        setUser]        = useState(null)
  const [loading,     setLoading]     = useState(true)
  const tokenRef      = useRef(null)   // always current without stale closure
  const refreshTimer  = useRef(null)

  // ── Store token + schedule silent refresh ─────────────────────────────────
  const storeToken = useCallback((token) => {
    tokenRef.current = token
    setAccessToken(token)
    const p = decodeJWT(token)
    if (p) {
      setUser({ id: p.sub, email: p.email, role: p.role, exp: p.exp })
      const ms = (p.exp * 1000) - Date.now() - 90_000   // refresh 90s before expiry
      clearTimeout(refreshTimer.current)
      if (ms > 0) refreshTimer.current = setTimeout(doRefresh, ms)
    }
  }, [])

  const clearAuth = useCallback(() => {
    tokenRef.current = null
    setAccessToken(null)
    setUser(null)
    clearTimeout(refreshTimer.current)
  }, [])

  // ── Silent refresh ────────────────────────────────────────────────────────
  async function doRefresh() {
    try {
      const { data } = await authApi.post('/auth/refresh')
      if (data?.access_token) storeToken(data.access_token)
      else clearAuth()
    } catch {
      clearAuth()   // refresh failed → back to login
    }
  }

  // ── Init: try silent refresh on mount ────────────────────────────────────
  useEffect(() => {
    doRefresh().finally(() => setLoading(false))
    return () => clearTimeout(refreshTimer.current)
  }, [])

  // ── Login / Signup / Logout ───────────────────────────────────────────────
  const login = async (email, password) => {
    const { data } = await authApi.post('/auth/login', { email, password })
    storeToken(data.access_token)
    return { success: true, user: data.user }
  }

  const signup = async (email, username, fullName, password) => {
    const { data } = await authApi.post('/auth/signup', { email, username, full_name: fullName, password })
    return data
  }

  const logout = async () => {
    try { await authApi.post('/auth/logout', {}, { headers: { Authorization: `Bearer ${tokenRef.current}` } }) }
    catch { /* ignore */ }
    clearAuth()
  }

  // ── apiClient factory — uses ref so token is always current ──────────────
  const apiClient = useCallback(() => {
    const client = axios.create({ baseURL: '/api', withCredentials: true, timeout: 20000 })

    client.interceptors.request.use(cfg => {
      const tok = tokenRef.current
      if (tok) cfg.headers.Authorization = `Bearer ${tok}`
      return cfg
    })

    client.interceptors.response.use(
      r => r,
      async err => {
        if (err.response?.status === 401 && !err.config._retry) {
          err.config._retry = true
          try {
            await doRefresh()
            const tok = tokenRef.current
            if (tok) {
              err.config.headers.Authorization = `Bearer ${tok}`
              return client(err.config)
            }
          } catch { /* ignore */ }
        }
        return Promise.reject(err)
      }
    )
    return client
  }, [])  // stable — uses tokenRef, not accessToken state

  return (
    <AuthContext.Provider value={{
      user, accessToken, loading,
      login, signup, logout, apiClient, clearAuth,
      isAuthenticated:  !!accessToken,
      isAdmin:          user?.role === 'admin' || user?.role === 'super_admin',
      isSuperAdmin:     user?.role === 'super_admin',
    }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
