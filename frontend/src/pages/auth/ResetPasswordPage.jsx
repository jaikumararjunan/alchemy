import { useState, useEffect } from 'react'
import { Link, useSearchParams, useNavigate } from 'react-router-dom'
import { Eye, EyeOff, CheckCircle, XCircle, Loader2 } from 'lucide-react'
import clsx from 'clsx'
import axios from 'axios'
import toast from 'react-hot-toast'

function Req({ met, label }) {
  return (
    <div className={clsx('flex items-center gap-1.5 text-xs', met ? 'text-emerald-400' : 'text-gray-500')}>
      {met ? <CheckCircle size={11}/> : <XCircle size={11}/>} {label}
    </div>
  )
}

export default function ResetPasswordPage() {
  const [params]    = useSearchParams()
  const navigate    = useNavigate()
  const token       = params.get('token') || ''
  const [pwd,  setPwd]  = useState('')
  const [conf, setConf] = useState('')
  const [show, setShow] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const reqs = [
    { met: pwd.length >= 12,          label: 'At least 12 characters' },
    { met: /[A-Z]/.test(pwd),         label: 'One uppercase letter' },
    { met: /[a-z]/.test(pwd),         label: 'One lowercase letter' },
    { met: /\d/.test(pwd),            label: 'One number' },
    { met: /[!@#$%^&*]/.test(pwd),   label: 'One special character' },
    { met: pwd === conf && conf.length > 0, label: 'Passwords match' },
  ]
  const canSubmit = reqs.every(r => r.met) && token

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!canSubmit) return
    setLoading(true); setError('')
    try {
      await axios.post('/api/auth/password/reset', { token, new_password: pwd })
      toast.success('Password reset! Please sign in with your new password.')
      navigate('/auth/login')
    } catch (err) {
      const detail = err.response?.data?.detail
      setError(typeof detail?.message === 'string' ? detail.message
              : typeof detail === 'string' ? detail
              : 'Reset failed. The link may have expired — request a new one.')
    } finally {
      setLoading(false)
    }
  }

  if (!token) return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center p-4 text-center">
      <div>
        <div className="text-5xl mb-4">⚠️</div>
        <h2 className="text-xl font-bold text-white mb-2">Invalid Reset Link</h2>
        <p className="text-gray-400 text-sm mb-4">This password reset link is invalid or has expired.</p>
        <Link to="/auth/forgot-password" className="btn-primary px-6 py-2 rounded-xl text-sm">
          Request New Link
        </Link>
      </div>
    </div>
  )

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="text-5xl mb-3">🔮</div>
          <h1 className="text-2xl font-bold text-white">Set New Password</h1>
          <p className="text-gray-400 text-sm mt-1">Choose a strong password for your account</p>
        </div>

        <div className="bg-gray-900 rounded-2xl border border-gray-800 p-8 shadow-2xl space-y-5">
          {error && (
            <div className="bg-red-900/30 border border-red-500/40 rounded-lg px-3 py-2.5 text-sm text-red-400">
              {error}
              {' '}<Link to="/auth/forgot-password" className="underline">Request new link</Link>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="text-xs text-gray-400 mb-1 block">New Password</label>
              <div className="relative">
                <input type={show ? 'text' : 'password'} value={pwd}
                  onChange={e => setPwd(e.target.value)}
                  className="input-field w-full pr-10" placeholder="Min 12 characters"
                  autoComplete="new-password" autoFocus />
                <button type="button" onClick={() => setShow(s=>!s)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500">
                  {show ? <EyeOff size={14}/> : <Eye size={14}/>}
                </button>
              </div>
              {pwd && (
                <div className="grid grid-cols-2 gap-1 mt-2">
                  {reqs.slice(0,4).map((r,i) => <Req key={i} {...r}/>)}
                </div>
              )}
            </div>

            <div>
              <label className="text-xs text-gray-400 mb-1 block">Confirm Password</label>
              <input type="password" value={conf} onChange={e => setConf(e.target.value)}
                className={clsx('input-field w-full', conf && (pwd===conf ? 'border-emerald-500':'border-red-500'))}
                placeholder="Repeat password" autoComplete="new-password"/>
            </div>

            <button type="submit" disabled={!canSubmit || loading}
              className="btn-primary w-full py-2.5 flex items-center justify-center gap-2">
              {loading && <Loader2 size={16} className="animate-spin"/>}
              {loading ? 'Resetting…' : 'Reset Password'}
            </button>
          </form>

          <div className="text-center">
            <Link to="/auth/login" className="text-sm text-gray-500 hover:text-gray-300">
              Back to Sign In
            </Link>
          </div>
        </div>
      </div>
    </div>
  )
}
