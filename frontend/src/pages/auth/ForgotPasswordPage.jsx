import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ShieldCheck, ArrowLeft, CheckCircle, Loader2 } from 'lucide-react'
import axios from 'axios'

export default function ForgotPasswordPage() {
  const [email,   setEmail]   = useState('')
  const [status,  setStatus]  = useState('idle') // idle | loading | sent | error
  const [error,   setError]   = useState('')

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!email) return
    setStatus('loading'); setError('')
    try {
      await axios.post('/api/auth/password/reset-request', { email })
      setStatus('sent')
    } catch (err) {
      const detail = err.response?.data?.detail
      const msg = typeof detail?.message === 'string' ? detail.message
                : typeof detail === 'string' ? detail
                : 'Failed to send reset email. Try again.'
      setError(msg); setStatus('error')
    }
  }

  if (status === 'sent') return (
    <div className="min-h-screen flex items-center justify-center p-4" style={{background:'var(--surface-0)'}}>
      <div className="w-full max-w-md text-center space-y-4">
        <CheckCircle size={52} className="text-emerald-400 mx-auto"/>
        <h2 className="text-xl font-bold text-white">Check Your Email</h2>
        <p className="text-gray-400 text-sm">
          If an account exists for <span className="text-white font-medium">{email}</span>,
          you'll receive a password reset link within a few minutes.
        </p>
        <p className="text-gray-600 text-xs">
          Didn't receive it? Check your spam folder or try again.
        </p>
        <Link to="/auth/login"
          className="inline-flex items-center gap-2 text-blue-400 hover:text-blue-300 text-sm mt-4">
          <ArrowLeft size={14}/> Back to Sign In
        </Link>
      </div>
    </div>
  )

  return (
    <div className="min-h-screen flex items-center justify-center p-4" style={{background:'var(--surface-0)'}}>
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center mx-auto mb-4 shadow-lg shadow-blue-500/20"><span className="text-white text-2xl font-display font-black">A</span></div>
          <h1 className="text-2xl font-bold text-white">Reset Password</h1>
          <p className="text-gray-400 text-sm mt-1">Enter your email to receive a reset link</p>
        </div>

        <div className="rounded-2xl p-8 shadow-2xl space-y-5" style={{background:'var(--surface-2)', border:'1px solid var(--border)'}}>
          {error && (
            <div className="bg-red-900/30 border border-red-500/40 rounded-lg px-3 py-2.5 text-sm text-red-400">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Email Address</label>
              <input type="email" value={email} onChange={e => setEmail(e.target.value)}
                className="input-field w-full" placeholder="you@example.com"
                autoComplete="email" required autoFocus />
            </div>

            <button type="submit" disabled={!email || status === 'loading'}
              className="btn-primary w-full py-2.5 flex items-center justify-center gap-2">
              {status === 'loading' && <Loader2 size={16} className="animate-spin"/>}
              {status === 'loading' ? 'Sending…' : 'Send Reset Link'}
            </button>
          </form>

          <div className="text-center">
            <Link to="/auth/login"
              className="inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-300 transition-colors">
              <ArrowLeft size={13}/> Back to Sign In
            </Link>
          </div>
        </div>

        <div className="flex items-center justify-center gap-2 mt-4 text-xs text-gray-600">
          <ShieldCheck size={12}/>
          <span>Reset link expires in 1 hour · 256-bit encrypted</span>
        </div>
      </div>
    </div>
  )
}
