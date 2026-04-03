import { useState, useRef, useEffect } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
import { Eye, EyeOff, ShieldCheck, AlertTriangle, Loader2, Lock } from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'

// Password strength meter
function StrengthMeter({ score }) {
  const levels = [
    { max: 25,  label: 'Weak',   color: 'bg-red-500' },
    { max: 50,  label: 'Fair',   color: 'bg-amber-500' },
    { max: 75,  label: 'Good',   color: 'bg-yellow-400' },
    { max: 100, label: 'Strong', color: 'bg-emerald-500' },
  ]
  const level = levels.find(l => score <= l.max) || levels[3]
  if (!score) return null
  return (
    <div className="mt-1.5">
      <div className="flex gap-1">
        {[25,50,75,100].map(t => (
          <div key={t} className={clsx('h-1 flex-1 rounded-full transition-colors',
            score >= t ? level.color : 'bg-gray-700')} />
        ))}
      </div>
      <span className={clsx('text-xs mt-0.5', level.color.replace('bg-','text-'))}>{level.label}</span>
    </div>
  )
}

// TOTP input — auto-focus, paste support, digit-only
function TOTPInput({ onComplete, loading }) {
  const [digits, setDigits] = useState(['','','','','',''])
  const refs = useRef([])

  const handleChange = (i, val) => {
    if (!/^\d*$/.test(val)) return
    const next = [...digits]
    next[i] = val.slice(-1)
    setDigits(next)
    if (val && i < 5) refs.current[i+1]?.focus()
    if (next.every(d => d !== '')) onComplete(next.join(''))
  }

  const handleKeyDown = (i, e) => {
    if (e.key === 'Backspace' && !digits[i] && i > 0) refs.current[i-1]?.focus()
  }

  const handlePaste = (e) => {
    const pasted = e.clipboardData.getData('text').replace(/\D/g,'').slice(0,6)
    if (pasted.length === 6) {
      setDigits(pasted.split(''))
      onComplete(pasted)
    }
  }

  return (
    <div className="flex gap-2 justify-center" onPaste={handlePaste}>
      {digits.map((d, i) => (
        <input key={i} ref={el => refs.current[i] = el}
          type="text" inputMode="numeric" maxLength={1} value={d}
          onChange={e => handleChange(i, e.target.value)}
          onKeyDown={e => handleKeyDown(i, e)}
          disabled={loading}
          className="w-11 h-12 text-center text-xl font-bold bg-gray-800 border border-gray-600 rounded-lg text-white focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none transition-colors disabled:opacity-50"
        />
      ))}
    </div>
  )
}

export default function LoginPage() {
  const navigate = useNavigate()
  const { login, requires2FA } = useAuth()
  const [step,       setStep]       = useState('credentials') // credentials | 2fa
  const [email,      setEmail]      = useState('')
  const [password,   setPassword]   = useState('')
  const [showPwd,    setShowPwd]    = useState(false)
  const [loading,    setLoading]    = useState(false)
  const [error,      setError]      = useState('')
  const [attempts,   setAttempts]   = useState(0)
  const emailRef = useRef()

  useEffect(() => { emailRef.current?.focus() }, [])

  const handleCredentials = async (e) => {
    e.preventDefault()
    if (!email || !password) return
    setError(''); setLoading(true)
    try {
      const result = await login(email, password)
      if (result.requires2FA) {
        setStep('2fa')
      } else if (result.success) {
        toast.success(`Welcome back, ${result.user?.username || email}!`)
        navigate('/dashboard')
      }
    } catch (err) {
      const msg = err.response?.data?.detail || 'Login failed'
      setError(msg)
      setAttempts(a => a + 1)
      if (attempts >= 3) {
        toast.error('Multiple failed attempts detected. Your account may be temporarily locked.')
      }
    } finally {
      setLoading(false)
    }
  }

  const handle2FA = async (code) => {
    setError(''); setLoading(true)
    try {
      const result = await login(email, password, code)
      if (result.success) {
        toast.success('Authenticated successfully')
        navigate('/dashboard')
      }
    } catch (err) {
      const msg = err.response?.data?.detail || 'Invalid code'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="text-5xl mb-3">🔮</div>
          <h1 className="text-2xl font-bold text-white">Alchemy</h1>
          <p className="text-gray-400 text-sm mt-1">AI-Powered Trading Platform</p>
        </div>

        <div className="bg-gray-900 rounded-2xl border border-gray-800 p-8 shadow-2xl">
          {step === 'credentials' ? (
            <>
              <div className="flex items-center gap-2 mb-6">
                <Lock size={18} className="text-blue-400" />
                <h2 className="text-lg font-semibold text-white">Sign in</h2>
              </div>

              {error && (
                <div className="flex items-center gap-2 bg-red-900/30 border border-red-500/40 rounded-lg px-3 py-2.5 mb-4 text-sm text-red-400">
                  <AlertTriangle size={14} className="flex-shrink-0" />
                  {error}
                </div>
              )}

              <form onSubmit={handleCredentials} className="space-y-4" autoComplete="on">
                <div>
                  <label className="text-xs text-gray-400 mb-1 block">Email</label>
                  <input ref={emailRef} type="email" value={email}
                    onChange={e => setEmail(e.target.value)}
                    className="input-field" placeholder="you@example.com"
                    autoComplete="email" required
                    onCopy={e => e.preventDefault()} />
                </div>

                <div>
                  <label className="text-xs text-gray-400 mb-1 block">Password</label>
                  <div className="relative">
                    <input type={showPwd ? 'text' : 'password'} value={password}
                      onChange={e => setPassword(e.target.value)}
                      className="input-field pr-10" placeholder="Enter password"
                      autoComplete="current-password" required />
                    <button type="button" onClick={() => setShowPwd(s => !s)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300">
                      {showPwd ? <EyeOff size={14} /> : <Eye size={14} />}
                    </button>
                  </div>
                </div>

                <div className="flex justify-end">
                  <Link to="/auth/forgot-password"
                    className="text-xs text-blue-400 hover:text-blue-300">
                    Forgot password?
                  </Link>
                </div>

                <button type="submit" disabled={loading || !email || !password}
                  className="btn-primary w-full py-2.5 flex items-center justify-center gap-2">
                  {loading ? <Loader2 size={16} className="animate-spin" /> : null}
                  {loading ? 'Signing in…' : 'Sign in'}
                </button>
              </form>

              <p className="text-center text-sm text-gray-500 mt-6">
                No account?{' '}
                <Link to="/auth/signup" className="text-blue-400 hover:text-blue-300">
                  Create one
                </Link>
              </p>
            </>
          ) : (
            <>
              <div className="flex items-center gap-2 mb-2">
                <ShieldCheck size={18} className="text-emerald-400" />
                <h2 className="text-lg font-semibold text-white">Two-Factor Authentication</h2>
              </div>
              <p className="text-sm text-gray-400 mb-6">
                Enter the 6-digit code from your authenticator app.
              </p>

              {error && (
                <div className="flex items-center gap-2 bg-red-900/30 border border-red-500/40 rounded-lg px-3 py-2.5 mb-4 text-sm text-red-400">
                  <AlertTriangle size={14} /> {error}
                </div>
              )}

              <TOTPInput onComplete={handle2FA} loading={loading} />

              {loading && (
                <div className="flex justify-center mt-4">
                  <Loader2 size={20} className="animate-spin text-blue-400" />
                </div>
              )}

              <button onClick={() => { setStep('credentials'); setError('') }}
                className="w-full mt-4 text-sm text-gray-500 hover:text-gray-300 transition-colors">
                ← Back to login
              </button>
            </>
          )}
        </div>

        {/* Security badge */}
        <div className="flex items-center justify-center gap-2 mt-4 text-xs text-gray-600">
          <ShieldCheck size={12} />
          <span>256-bit TLS encryption · TOTP 2FA · Session-based auth</span>
        </div>
      </div>
    </div>
  )
}
