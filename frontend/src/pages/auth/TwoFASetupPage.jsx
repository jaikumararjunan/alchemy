import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useAuth } from '@/context/AuthContext'
import { ShieldCheck, Copy, CheckCircle, Download, RefreshCw, AlertTriangle } from 'lucide-react'
import toast from 'react-hot-toast'
import clsx from 'clsx'

export default function TwoFASetupPage() {
  const { apiClient } = useAuth()
  const [step,     setStep]    = useState('intro')   // intro | qr | verify | done
  const [code,     setCode]    = useState('')
  const [qrData,   setQrData]  = useState(null)
  const [copied,   setCopied]  = useState(false)

  const api = apiClient()

  const setupMut = useMutation({
    mutationFn: () => api.post('/auth/2fa/setup').then(r => r.data),
    onSuccess:  (data) => { setQrData(data); setStep('qr') },
    onError:    () => toast.error('Failed to initialize 2FA'),
  })

  const verifyMut = useMutation({
    mutationFn: (code) => api.post('/auth/2fa/verify', { code }).then(r => r.data),
    onSuccess:  () => setStep('done'),
    onError:    (e) => toast.error(e.response?.data?.detail || 'Invalid code'),
  })

  const copySecret = () => {
    navigator.clipboard.writeText(qrData.secret)
    setCopied(true); setTimeout(() => setCopied(false), 2000)
    toast.success('Secret copied')
  }

  const downloadBackupCodes = () => {
    const text = `Alchemy 2FA Backup Codes\nGenerated: ${new Date().toISOString()}\n\n${qrData.backup_codes.join('\n')}\n\nKeep these codes safe. Each can only be used once.`
    const a = document.createElement('a')
    a.href = URL.createObjectURL(new Blob([text], { type: 'text/plain' }))
    a.download = 'alchemy-backup-codes.txt'
    a.click()
  }

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center p-4">
      <div className="w-full max-w-lg">
        <div className="text-center mb-8">
          <ShieldCheck size={40} className="text-emerald-400 mx-auto mb-3" />
          <h1 className="text-2xl font-bold text-white">Two-Factor Authentication</h1>
          <p className="text-gray-400 text-sm mt-1">Add an extra layer of security to your account</p>
        </div>

        <div className="bg-gray-900 rounded-2xl border border-gray-800 p-8">
          {step === 'intro' && (
            <div className="space-y-6">
              <div className="space-y-3">
                {[
                  ['📱', 'Download an authenticator app', 'Google Authenticator, Authy, or 1Password'],
                  ['📷', 'Scan the QR code', 'Use the app to scan a QR code we\'ll generate'],
                  ['🔢', 'Enter the 6-digit code', 'Verify setup by entering the generated code'],
                  ['💾', 'Save backup codes', 'Store emergency backup codes somewhere safe'],
                ].map(([icon, title, sub]) => (
                  <div key={title} className="flex gap-3 items-start p-3 bg-gray-800/50 rounded-lg">
                    <span className="text-xl">{icon}</span>
                    <div>
                      <div className="text-sm font-medium text-white">{title}</div>
                      <div className="text-xs text-gray-400">{sub}</div>
                    </div>
                  </div>
                ))}
              </div>

              <button onClick={() => setupMut.mutate()} disabled={setupMut.isPending}
                className="btn-primary w-full py-2.5 flex items-center justify-center gap-2">
                {setupMut.isPending && <RefreshCw size={14} className="animate-spin" />}
                Begin 2FA Setup
              </button>
            </div>
          )}

          {step === 'qr' && qrData && (
            <div className="space-y-6">
              <div className="text-center">
                <p className="text-sm text-gray-300 mb-4">
                  Scan this QR code with your authenticator app:
                </p>
                <div className="bg-white p-3 rounded-xl inline-block shadow-lg">
                  <img src={qrData.qr_code} alt="2FA QR Code" className="w-48 h-48" />
                </div>
              </div>

              <div>
                <p className="text-xs text-gray-400 mb-1">Or enter this secret manually:</p>
                <div className="flex items-center gap-2 bg-gray-800 rounded-lg px-3 py-2">
                  <code className="flex-1 text-xs font-mono text-blue-300 break-all">{qrData.secret}</code>
                  <button onClick={copySecret} className="text-gray-400 hover:text-white flex-shrink-0">
                    {copied ? <CheckCircle size={14} className="text-emerald-400" /> : <Copy size={14} />}
                  </button>
                </div>
              </div>

              <div>
                <div className="flex items-center justify-between mb-2">
                  <p className="text-xs text-amber-400 font-medium">⚠️ Backup Codes (save these now!)</p>
                  <button onClick={downloadBackupCodes}
                    className="text-xs text-blue-400 flex items-center gap-1">
                    <Download size={11} /> Download
                  </button>
                </div>
                <div className="grid grid-cols-2 gap-1.5 bg-gray-800 rounded-lg p-3">
                  {qrData.backup_codes?.map((code, i) => (
                    <code key={i} className="text-xs font-mono text-gray-300 py-0.5">{code}</code>
                  ))}
                </div>
                <p className="text-xs text-gray-500 mt-1">Each code can only be used once. Store them offline.</p>
              </div>

              <button onClick={() => setStep('verify')} className="btn-primary w-full py-2.5">
                I've saved my backup codes → Continue
              </button>
            </div>
          )}

          {step === 'verify' && (
            <div className="space-y-6">
              <div className="text-center">
                <p className="text-gray-300 mb-2">Enter the current 6-digit code from your authenticator app to confirm setup:</p>
              </div>

              <div>
                <input type="text" inputMode="numeric" value={code}
                  onChange={e => setCode(e.target.value.replace(/\D/g,'').slice(0,6))}
                  className="input-field text-center text-xl tracking-[0.5em] font-mono"
                  placeholder="000000" maxLength={6} autoFocus />
              </div>

              <button onClick={() => verifyMut.mutate(code)}
                disabled={code.length !== 6 || verifyMut.isPending}
                className="btn-primary w-full py-2.5 flex items-center justify-center gap-2">
                {verifyMut.isPending && <RefreshCw size={14} className="animate-spin" />}
                Verify & Enable 2FA
              </button>

              <button onClick={() => setStep('qr')} className="w-full text-sm text-gray-500 hover:text-gray-300">
                ← Back to QR code
              </button>
            </div>
          )}

          {step === 'done' && (
            <div className="text-center space-y-4">
              <CheckCircle size={56} className="text-emerald-400 mx-auto" />
              <h3 className="text-xl font-bold text-white">2FA Enabled!</h3>
              <p className="text-gray-400">Your account is now protected with two-factor authentication.</p>
              <div className="bg-emerald-900/20 border border-emerald-500/30 rounded-lg px-4 py-3 text-sm text-emerald-400">
                Future logins will require your authenticator code.
              </div>
              <a href="/settings" className="btn-primary inline-block">Go to Settings</a>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
