import { useState, useEffect } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
import { Eye, EyeOff, CheckCircle, XCircle, Loader2, ShieldCheck } from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'
import axios from 'axios'

const checkStrength = async (pwd) => {
  if (pwd.length < 3) return { score: 0, errors: [] }
  try {
    // POST so the password never appears in server access logs or browser history
    const { data } = await axios.post(`/api/auth/password/strength`, { password: pwd })
    return data
  } catch { return { score: 0, errors: [] } }
}

function Requirement({ met, label }) {
  return (
    <div className={clsx('flex items-center gap-1.5 text-xs', met ? 'text-emerald-400' : 'text-gray-500')}>
      {met ? <CheckCircle size={11} /> : <XCircle size={11} />}
      {label}
    </div>
  )
}

export default function SignupPage() {
  const { signup }   = useAuth()
  const navigate     = useNavigate()
  const [form, setForm] = useState({ email:'', username:'', fullName:'', password:'', confirm:'' })
  const [showPwd,   setShowPwd]   = useState(false)
  const [strength,  setStrength]  = useState({ score: 0, errors: [] })
  const [loading,   setLoading]   = useState(false)
  const [error,     setError]     = useState('')
  const [success,   setSuccess]   = useState(false)

  const f = (k) => (e) => {
    let v = e.target.value
    if (k === 'username') v = v.replace(/[^a-zA-Z0-9_]/g, '').slice(0, 32)
    setForm(p => ({...p, [k]: v}))
  }

  useEffect(() => {
    const t = setTimeout(async () => {
      if (form.password.length >= 4) {
        setStrength(await checkStrength(form.password))
      }
    }, 300)
    return () => clearTimeout(t)
  }, [form.password])

  const usernameValid = form.username.length >= 3 && /^[a-zA-Z0-9_]{3,32}$/.test(form.username)

  const reqs = [
    { met: form.password.length >= 12, label: 'At least 12 characters' },
    { met: /[A-Z]/.test(form.password), label: 'One uppercase letter' },
    { met: /[a-z]/.test(form.password), label: 'One lowercase letter' },
    { met: /\d/.test(form.password),    label: 'One number' },
    { met: /[!@#$%^&*]/.test(form.password), label: 'One special character' },
    { met: form.password === form.confirm && form.confirm.length > 0, label: 'Passwords match' },
  ]

  const canSubmit = reqs.every(r => r.met) && form.email && usernameValid && form.fullName

  const [otpMode, setOtpMode]     = useState(false)
  const [otpEmail, setOtpEmail]   = useState('')
  const [otpCode, setOtpCode]     = useState('')
  const [otpLoading, setOtpLoading] = useState(false)
  const [searchParams] = useSearchParams()

  // Auto-enter OTP mode if redirected from login with ?verify=email
  useEffect(() => {
    const verifyEmail = searchParams.get('verify')
    if (verifyEmail) {
      setOtpMode(true)
      setOtpEmail(decodeURIComponent(verifyEmail))
    }
  }, [searchParams])

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!canSubmit) return
    setError(''); setLoading(true)
    try {
      const result = await signup(form.email, form.username, form.fullName, form.password)

      // If server says OTP verification needed (production mode)
      if (result.requires_otp) {
        setOtpMode(true)
        setOtpEmail(result.email || form.email)
        toast.success('Verification code sent to your email!')
        return
      }

      // Dev mode: auto-login succeeded
      if (result.access_token) {
        toast.success('Welcome to Alchemy! Your account is ready.')
        navigate('/dashboard')
        return
      }

      // Fallback: account created but needs verification
      setOtpMode(true)
      setOtpEmail(form.email)
    } catch (err) {
      const detail = err.response?.data?.detail
      const errMsg =
        typeof detail === 'string'    ? detail :
        typeof detail?.message === 'string' ? detail.message :
        err.response?.status === 422  ? 'Please check your details and try again.' :
        err.response?.status === 429  ? 'Too many attempts. Please wait a moment.' :
        'Something went wrong. Please try again.'
      setError(errMsg)
    } finally {
      setLoading(false)
    }
  }

  const handleVerifyOtp = async (e) => {
    e.preventDefault()
    if (otpCode.length < 6) return
    setOtpLoading(true); setError('')
    try {
      await axios.post('/api/auth/otp/verify', {
        email: otpEmail,
        otp: otpCode,
        purpose: 'verification',
      })
      toast.success('Email verified! Please sign in.')
      navigate('/auth/login')
    } catch (err) {
      const msg = err.response?.data?.detail || 'Invalid or expired OTP. Try again.'
      setError(typeof msg === 'string' ? msg : 'Invalid OTP')
    } finally {
      setOtpLoading(false)
    }
  }

  const handleResendOtp = async () => {
    try {
      const { data } = await axios.post('/api/auth/otp/resend', { email: otpEmail, purpose: 'verification' })
      if (data.auto_activated) {
        toast.success('Account activated! Please sign in.')
        navigate('/auth/login')
        return
      }
      toast.success('New OTP sent!')
    } catch {
      toast.error('Failed to resend. Try again in a moment.')
    }
  }

  if (success) return (
    <div className="min-h-screen flex items-center justify-center p-4" style={{background:'var(--surface-0)'}}>
      <div className="text-center max-w-sm">
        <CheckCircle size={48} className="text-emerald-400 mx-auto mb-4" />
        <h2 className="text-xl font-bold text-white mb-2">Account Created!</h2>
        <p className="text-gray-400 mb-6">Check your email to verify your account, then sign in.</p>
        <Link to="/auth/login" className="btn-primary">Go to Login</Link>
      </div>
    </div>
  )

  // ── OTP Verification Screen ──
  if (otpMode) return (
    <div className="min-h-screen flex items-center justify-center p-4" style={{background:'var(--surface-0)'}}>
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="text-5xl mb-3">📧</div>
          <h1 className="text-2xl font-display font-bold text-white tracking-tight">Verify Your Email</h1>
          <p className="text-gray-400 text-sm mt-1">
            We sent a 6-digit code to <span className="text-blue-400">{otpEmail}</span>
          </p>
        </div>

        <div className="rounded-2xl p-8 shadow-2xl" style={{background:'var(--surface-2)', border:'1px solid var(--border)'}}>
          {error && (
            <div className="bg-red-900/30 border border-red-500/40 rounded-lg px-3 py-2.5 mb-4 text-sm text-red-400">
              {error}
            </div>
          )}

          <form onSubmit={handleVerifyOtp} className="space-y-5">
            <div>
              <label className="text-xs text-gray-400 mb-2 block">Verification Code</label>
              <input
                type="text"
                inputMode="numeric"
                pattern="[0-9]*"
                maxLength={6}
                value={otpCode}
                onChange={e => setOtpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                className="input-field text-center text-2xl tracking-[0.5em] font-mono"
                placeholder="000000"
                autoFocus
                required
              />
              <p className="text-xs text-gray-500 mt-2 text-center">
                Code expires in 10 minutes
              </p>
            </div>

            <button type="submit" disabled={otpCode.length < 6 || otpLoading}
              className="btn-primary w-full py-2.5 flex items-center justify-center gap-2">
              {otpLoading && <Loader2 size={16} className="animate-spin" />}
              {otpLoading ? 'Verifying…' : 'Verify Email'}
            </button>
          </form>

          <div className="flex items-center justify-between mt-6 pt-4 border-t border-gray-800">
            <button onClick={handleResendOtp}
              className="text-sm text-blue-400 hover:text-blue-300">
              Resend Code
            </button>
            <Link to="/auth/login" className="text-sm text-gray-500 hover:text-gray-400">
              Back to Login
            </Link>
          </div>
        </div>
      </div>
    </div>
  )

  const scoreColor = strength.score > 75 ? 'bg-emerald-500' : strength.score > 50 ? 'bg-yellow-400' : strength.score > 25 ? 'bg-amber-500' : 'bg-red-500'

  return (
    <div className="min-h-screen flex items-center justify-center p-4" style={{background:'var(--surface-0)'}}>
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center mx-auto mb-4 shadow-lg shadow-blue-500/20"><span className="text-white text-2xl font-display font-black">A</span></div>
          <h1 className="text-2xl font-display font-bold text-white tracking-tight">Create Account</h1>
          <p className="text-gray-400 text-sm mt-1">Join Alchemy Trading Platform</p>
        </div>

        <div className="rounded-2xl p-8 shadow-2xl" style={{background:'var(--surface-2)', border:'1px solid var(--border)'}}>
          {error && (
            <div className="bg-red-900/30 border border-red-500/40 rounded-lg px-3 py-2.5 mb-4 text-sm text-red-400">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4" autoComplete="on">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="text-[11px] font-semibold text-gray-500 uppercase tracking-wider mb-1.5 block">Email</label>
                <input type="email" value={form.email} onChange={f('email')}
                  className="input-field" placeholder="you@example.com"
                  autoComplete="email" required />
              </div>
              <div>
                <label className="text-[11px] font-semibold text-gray-500 uppercase tracking-wider mb-1.5 block">Username</label>
                <input type="text" value={form.username} onChange={f('username')}
                  className="input-field" placeholder="trader123"
                  autoComplete="username" required />
                {form.username && !usernameValid && (
                  <p className="text-xs text-red-400 mt-1">3–32 chars, letters/numbers/underscore only</p>
                )}
                {form.username && usernameValid && (
                  <p className="text-xs text-emerald-500 mt-1">✓ @{form.username}</p>
                )}
              </div>
            </div>

            <div>
              <label className="text-[11px] font-semibold text-gray-500 uppercase tracking-wider mb-1.5 block">Full Name</label>
              <input type="text" value={form.fullName} onChange={f('fullName')}
                className="input-field" placeholder="Jai Kumar"
                autoComplete="name" required />
            </div>

            <div>
              <label className="text-[11px] font-semibold text-gray-500 uppercase tracking-wider mb-1.5 block">Password</label>
              <div className="relative">
                <input type={showPwd ? 'text' : 'password'} value={form.password}
                  onChange={f('password')} className="input-field pr-10"
                  placeholder="Min 12 characters" autoComplete="new-password" required />
                <button type="button" onClick={() => setShowPwd(s=>!s)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500">
                  {showPwd ? <EyeOff size={14}/> : <Eye size={14}/>}
                </button>
              </div>
              {form.password && (
                <div className="mt-2 space-y-1">
                  <div className="flex gap-1">
                    {[25,50,75,100].map(t => (
                      <div key={t} className={clsx('h-1 flex-1 rounded-full transition-colors',
                        strength.score >= t ? scoreColor : 'bg-gray-700')} />
                    ))}
                  </div>
                  <div className="grid grid-cols-2 gap-1 mt-2">
                    {reqs.slice(0,4).map((r,i) => <Requirement key={i} {...r} />)}
                  </div>
                </div>
              )}
            </div>

            <div>
              <label className="text-[11px] font-semibold text-gray-500 uppercase tracking-wider mb-1.5 block">Confirm Password</label>
              <input type="password" value={form.confirm} onChange={f('confirm')}
                className={clsx('input-field', form.confirm && (form.password === form.confirm ? 'border-emerald-500' : 'border-red-500'))}
                placeholder="Repeat password" autoComplete="new-password" required />
            </div>

            <div className="text-xs text-gray-500 bg-gray-800/50 rounded-lg px-3 py-2">
              By creating an account you agree to our Terms of Service and Privacy Policy.
              Your data is encrypted and never sold.
            </div>

            <button type="submit" disabled={!canSubmit || loading}
              className="btn-primary w-full py-2.5 flex items-center justify-center gap-2">
              {loading && <Loader2 size={16} className="animate-spin" />}
              {loading ? 'Creating account…' : 'Create Account'}
            </button>
          </form>

          <p className="text-center text-sm text-gray-500 mt-6">
            Already have an account?{' '}
            <Link to="/auth/login" className="text-blue-400 hover:text-blue-300">Sign in</Link>
          </p>
        </div>

        <div className="flex items-center justify-center gap-2 mt-4 text-xs text-gray-600">
          <ShieldCheck size={12} />
          <span>bcrypt hashing · AES-256 vault · TOTP 2FA available</span>
        </div>
      </div>
    </div>
  )
}
