/**
 * AuthContext - secure authentication state management.
 * Access token stored in memory only (never localStorage).
 * Refresh token in httpOnly cookie set by server.
 */
import { createContext, useContext, useState, useEffect, useRef, useCallback } from 'react'
import axios from 'axios'

const AuthContext = createContext(null)

// Detect if we're running through Vite dev server (port 3000) or FastAPI directly (port 8000)
const getBaseURL = () => {
  // When served by FastAPI directly, call /api/* (FastAPI has /api/* routes)
  // When served by Vite dev server, also call /api/* (Vite proxy strips it)
  return '/api'
}

const authApi = axios.create({
  baseURL: getBaseURL(),
  withCredentials: true,
  timeout: 10000,
})

function decodeJWT(token) {
  try {
    const payload = token.split('.')[1]
    return JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/')))
  } catch { return null }
}

export function AuthProvider({ children }) {
  const [accessToken, setAccessToken]   = useState(null)
  const [user, setUser]                 = useState(null)
  const [loading, setLoading]           = useState(true)
  const [requires2FA, setRequires2FA]   = useState(false)
  const [pendingUserId, setPendingUserId] = useState(null)
  const refreshTimerRef = useRef(null)

  const storeToken = useCallback((token) => {
    setAccessToken(token)
    const payload = decodeJWT(token)
    if (payload) {
      setUser({ id: payload.sub, email: payload.email, role: payload.role, exp: payload.exp })
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

  const silentRefresh = useCallback(async () => {
    try {
      const { data } = await authApi.post('/auth/refresh')
      storeToken(data.access_token)
    } catch {
      clearAuth()
    }
  }, [storeToken, clearAuth])

  useEffect(() => {
    silentRefresh().finally(() => setLoading(false))
    return () => clearTimeout(refreshTimerRef.current)
  }, [])

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
      email,
      username,
      full_name: fullName,
      password,
    })
    return data
  }

  const logout = async () => {
    try {
      await authApi.post('/auth/logout', {}, {
        headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {}
      })
    } catch { /* ignore */ }
    clearAuth()
  }

  const logoutAll = async () => {
    try {
      await authApi.post('/auth/logout-all', {}, {
        headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {}
      })
    } catch { /* ignore */ }
    clearAuth()
  }

  const apiClient = useCallback(() => {
    const client = axios.create({
      baseURL: getBaseURL(),
      withCredentials: true,
      timeout: 15000,
    })
    client.interceptors.request.use(config => {
      if (accessToken) config.headers.Authorization = `Bearer ${accessToken}`
      return config
    })
    client.interceptors.response.use(
      r => r,
      async err => {
        if (err.response?.status === 401 && !err.config._retry) {
          err.config._retry = true
          try {
            await silentRefresh()
            if (accessToken) err.config.headers.Authorization = `Bearer ${accessToken}`
            return client(err.config)
          } catch { clearAuth() }
        }
        return Promise.reject(err)
      }
    )
    return client
  }, [accessToken, silentRefresh, clearAuth])

  return (
    <AuthContext.Provider value={{
      user, accessToken, loading, requires2FA, pendingUserId,
      login, signup, logout, logoutAll, apiClient, clearAuth,
      isAuthenticated: !!accessToken,
      isAdmin: user?.role === 'admin' || user?.role === 'super_admin',
      isSuperAdmin: user?.role === 'super_admin',
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
