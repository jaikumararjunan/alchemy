/**
 * AuthContext — secure authentication state management.
 *
 * Security design:
 *   - Access token stored in memory (React state) ONLY — never localStorage/sessionStorage
 *   - Refresh token stored in httpOnly Secure SameSite=Strict cookie by server
 *   - Token refresh via /auth/refresh endpoint (cookie sent automatically)
 *   - Auto-refresh 2 minutes before access token expiry
 *   - On tab close/refresh: user must re-authenticate OR have valid refresh cookie
 */
import { createContext, useContext, useState, useEffect, useRef, useCallback } from 'react'
import axios from 'axios'

const AuthContext = createContext(null)

// Base API client — no auth header (uses httpOnly cookie for refresh)
const authApi = axios.create({ baseURL: '/api', withCredentials: true })

// Decode JWT payload without verification (client-side display only)
function decodeJWT(token) {
  try {
    const payload = token.split('.')[1]
    return JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/')))
  } catch {
    return null
  }
}

export function AuthProvider({ children }) {
  const [accessToken, setAccessToken]   = useState(null)
  const [user, setUser]                 = useState(null)
  const [loading, setLoading]           = useState(true)
  const [requires2FA, setRequires2FA]   = useState(false)
  const [pendingUserId, setPendingUserId] = useState(null)
  const refreshTimerRef = useRef(null)

  // ── Token management ────────────────────────────────────────────────────────

  const storeToken = useCallback((token) => {
    setAccessToken(token)
    const payload = decodeJWT(token)
    if (payload) {
      setUser({
        id:       payload.sub,
        email:    payload.email,
        role:     payload.role,
        exp:      payload.exp,
      })
      // Schedule refresh 2 minutes before expiry
      const msUntilExpiry = (payload.exp * 1000) - Date.now() - 120_000
      if (msUntilExpiry > 0) {
        clearTimeout(refreshTimerRef.current)
        refreshTimerRef.current = setTimeout(silentRefresh, msUntilExpiry)
      }
    }
  }, [])

  const clearAuth = useCallback(() => {
    setAccessToken(null)
    setUser(null)
    clearTimeout(refreshTimerRef.current)
  }, [])

  // ── Silent refresh (runs automatically before expiry) ──────────────────────

  const silentRefresh = useCallback(async () => {
    try {
      const { data } = await authApi.post('/auth/refresh')
      storeToken(data.access_token)
    } catch {
      // Refresh failed — session expired, require re-login
      clearAuth()
    }
  }, [storeToken, clearAuth])

  // Attempt silent refresh on app mount (user might have valid cookie from prev session)
  useEffect(() => {
    silentRefresh().finally(() => setLoading(false))
    return () => clearTimeout(refreshTimerRef.current)
  }, [])

  // ── Auth actions ────────────────────────────────────────────────────────────

  const login = async (email, password, totpCode = null) => {
    const { data } = await authApi.post('/auth/login', {
      email, password, totp_code: totpCode
    })
    if (data.requires_2fa) {
      setRequires2FA(true)
      setPendingUserId(data.user_id)
      return { requires2FA: true }
    }
    storeToken(data.access_token)
    setRequires2FA(false)
    return { success: true, user: data.user }
  }

  const signup = async (email, username, fullName, password) => {
    const { data } = await authApi.post('/auth/signup', {
      email, username, full_name: fullName, password
    })
    return data
  }

  const logout = async () => {
    try {
      await authApi.post('/auth/logout', {}, {
        headers: { Authorization: `Bearer ${accessToken}` }
      })
    } catch { /* ignore */ }
    clearAuth()
  }

  const logoutAll = async () => {
    try {
      await authApi.post('/auth/logout-all', {}, {
        headers: { Authorization: `Bearer ${accessToken}` }
      })
    } catch { /* ignore */ }
    clearAuth()
  }

  // ── API client with auto-injected access token ────────────────────────────

  const apiClient = useCallback(() => {
    const client = axios.create({ baseURL: '/api', withCredentials: true })
    client.interceptors.request.use(config => {
      if (accessToken) {
        config.headers.Authorization = `Bearer ${accessToken}`
      }
      return config
    })
    client.interceptors.response.use(
      r => r,
      async err => {
        if (err.response?.status === 401 && !err.config._retry) {
          err.config._retry = true
          try {
            await silentRefresh()
            // Retry original request with new token
            err.config.headers.Authorization = `Bearer ${accessToken}`
            return client(err.config)
          } catch {
            clearAuth()
          }
        }
        return Promise.reject(err)
      }
    )
    return client
  }, [accessToken, silentRefresh, clearAuth])

  const value = {
    user, accessToken, loading, requires2FA, pendingUserId,
    login, signup, logout, logoutAll, apiClient,
    isAuthenticated: !!accessToken,
    isAdmin: user?.role === 'admin' || user?.role === 'super_admin',
    isSuperAdmin: user?.role === 'super_admin',
    clearAuth,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export const useAuth = () => {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
