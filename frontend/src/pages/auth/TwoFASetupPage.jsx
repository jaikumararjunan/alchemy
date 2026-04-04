import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Shield, Smartphone, CheckCircle, Copy, RefreshCw, AlertCircle } from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'

export default function TwoFASetupPage() {
  const { apiClient } = useAuth()
  const api = apiClient()
  const navigate = useNavigate()
  const [step, setStep] = useState(1)   // 1=intro, 2=scan, 3=confirm, 4=done
  const [code, setCode] = useState('')
  const [secret, setSecret] = useState('')
  const [qr, setQr] = useState('')

  const initMut = useMutation({
    mutationFn: () => api.post('/auth/otp/2fa/setup/init').then(r => r.data),
    onSuccess: d => { setSecret(d.secret); setQr(d.qr_code); setStep(2) },
    onError:   e => toast.error(e.response?.data?.detail || 'Setup failed'),
  })

  const confirmMut = useMutation({
    mutationFn: () => api.post('/auth/otp/2fa/setup/confirm', { totp_code: code }).then(r => r.data),
    onSuccess: () => setStep(4),
    onError:   e => toast.error(e.response?.data?.detail || 'Invalid code'),
  })

  const { data: status } = useQuery({
    queryKey: ['2fa-status'],
    queryFn:  () => api.get('/auth/otp/2fa/status').then(r => r.data).catch(() => ({ enabled: false })),
  })

  const copySecret = () => { navigator.clipboard.writeText(secret); toast.success('Secret copied') }

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="text-4xl mb-3">🔮</div>
          <h1 className="text-2xl font-bold text-white">Two-Factor Authentication</h1>
          <p className="text-gray-400 text-sm mt-1">Add an extra layer of security</p>
        </div>

        {/* Progress */}
        <div className="flex items-center justify-center gap-2 mb-8">
          {[1,2,3,4].map(s => (
            <div key={s} className={clsx('flex items-center gap-2', s < 4 && 'flex-1')}>
              <div className={clsx('w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold transition-all',
                step > s  ? 'bg-emerald-600 text-white' :
                step === s ? 'bg-blue-600 text-white ring-4 ring-blue-600/30' :
                             'bg-gray-800 text-gray-500')}>
                {step > s ? <CheckCircle size={14}/> : s}
              </div>
              {s < 4 && <div className={clsx('flex-1 h-0.5 rounded', step > s ? 'bg-emerald-600' : 'bg-gray-800')}/>}
            </div>
          ))}
        </div>

        <div className="card space-y-5">
          {/* Step 1: Intro */}
          {step === 1 && (
            <>
              {status?.enabled && (
                <div className="flex items-center gap-2 p-3 bg-emerald-900/20 border border-emerald-500/30 rounded-xl">
                  <CheckCircle size={16} className="text-emerald-400"/>
                  <span className="text-sm text-emerald-300">2FA is already enabled on your account</span>
                </div>
              )}
              <div className="space-y-3">
                {[
                  { icon:'📱', t:'Get Authenticator App', d:'Download Google Authenticator or Authy on your phone' },
                  { icon:'📷', t:'Scan QR Code',          d:'Open the app and scan the QR code we provide' },
                  { icon:'🔢', t:'Enter Verification Code', d:'Type the 6-digit code from the app to confirm' },
                ].map(({icon,t,d}) => (
                  <div key={t} className="flex items-start gap-3 p-3 bg-gray-800/50 rounded-xl">
                    <span className="text-xl flex-shrink-0">{icon}</span>
                    <div>
                      <p className="text-sm font-medium text-white">{t}</p>
                      <p className="text-xs text-gray-400 mt-0.5">{d}</p>
                    </div>
                  </div>
                ))}
              </div>
              <button onClick={() => initMut.mutate()} disabled={initMut.isPending}
                className="btn-primary w-full flex items-center justify-center gap-2">
                {initMut.isPending ? <RefreshCw size={14} className="animate-spin"/> : <Shield size={14}/>}
                {status?.enabled ? 'Regenerate 2FA' : 'Set Up 2FA'}
              </button>
              <button onClick={() => navigate('/dashboard')} className="btn-ghost w-full text-center">
                {status?.enabled ? 'Back to Dashboard' : 'Skip for now'}
              </button>
            </>
          )}

          {/* Step 2: Scan QR */}
          {step === 2 && (
            <>
              <h2 className="text-sm font-semibold text-white">Scan with Authenticator App</h2>
              {qr && (
                <div className="bg-white p-4 rounded-xl mx-auto w-fit">
                  <img src={`data:image/png;base64,${qr}`} alt="QR Code" className="w-48 h-48"/>
                </div>
              )}
              <div className="p-3 bg-gray-800/60 rounded-xl">
                <p className="text-xs text-gray-500 mb-1">Can't scan? Enter this secret manually:</p>
                <div className="flex items-center gap-2">
                  <code className="flex-1 text-xs text-blue-400 font-mono bg-gray-900 px-2 py-1 rounded break-all">{secret}</code>
                  <button onClick={copySecret} className="flex-shrink-0 p-1.5 rounded-lg bg-gray-700 hover:bg-gray-600 text-gray-300">
                    <Copy size={12}/>
                  </button>
                </div>
              </div>
              <button onClick={() => setStep(3)} className="btn-primary w-full">
                I've Scanned the QR Code →
              </button>
            </>
          )}

          {/* Step 3: Verify */}
          {step === 3 && (
            <>
              <h2 className="text-sm font-semibold text-white">Enter the 6-digit code from your app</h2>
              <input
                type="text" inputMode="numeric" pattern="[0-9]*"
                maxLength={6} value={code}
                onChange={e => setCode(e.target.value.replace(/\D/g,'').slice(0,6))}
                placeholder="000000"
                className="input-field w-full text-center text-3xl font-mono tracking-[0.5em] py-4"
                autoFocus
              />
              <button onClick={() => confirmMut.mutate()}
                disabled={code.length !== 6 || confirmMut.isPending}
                className="btn-primary w-full flex items-center justify-center gap-2">
                {confirmMut.isPending ? <RefreshCw size={14} className="animate-spin"/> : <CheckCircle size={14}/>}
                Verify & Enable
              </button>
              <button onClick={() => setStep(2)} className="btn-ghost w-full text-center">← Back</button>
            </>
          )}

          {/* Step 4: Done */}
          {step === 4 && (
            <div className="text-center space-y-4 py-4">
              <div className="text-6xl">✅</div>
              <h2 className="text-xl font-bold text-white">2FA Enabled!</h2>
              <p className="text-gray-400 text-sm">Your account is now protected with two-factor authentication.</p>
              <div className="p-3 bg-amber-900/20 border border-amber-500/30 rounded-xl text-left">
                <p className="text-xs text-amber-300 font-medium">⚠️ Save your backup secret:</p>
                <code className="text-xs text-amber-400 font-mono mt-1 block break-all">{secret}</code>
              </div>
              <button onClick={() => navigate('/dashboard')} className="btn-primary w-full">
                Go to Dashboard
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
