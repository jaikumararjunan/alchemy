import { useState } from 'react'
import { useAuth } from '@/context/AuthContext'
import { useMutation } from '@tanstack/react-query'
import { Shield, Bell, Moon, Globe, Key, RefreshCw, CheckCircle, AlertCircle } from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'

export default function SettingsPage() {
  const { user, apiClient } = useAuth()
  const api = apiClient()
  const [pwForm, setPwForm] = useState({ current: '', newPw: '', confirm: '' })
  const [show, setShow] = useState({})

  const changePwMut = useMutation({
    mutationFn: (data) => api.post('/auth/password/change', data).then(r => r.data),
    onSuccess: () => { toast.success('Password changed'); setPwForm({ current:'',newPw:'',confirm:'' }) },
    onError: (e) => toast.error(e.response?.data?.detail || 'Failed to change password'),
  })

  const handleChangePw = () => {
    if (pwForm.newPw !== pwForm.confirm) { toast.error('Passwords do not match'); return }
    if (pwForm.newPw.length < 12) { toast.error('Password must be at least 12 characters'); return }
    changePwMut.mutate({ current_password: pwForm.current, new_password: pwForm.newPw })
  }

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-xl font-bold text-white">Settings</h1>
        <p className="text-sm text-gray-400">Account and security settings</p>
      </div>

      {/* Profile */}
      <div className="card">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-12 h-12 rounded-full bg-blue-600 flex items-center justify-center text-xl font-bold text-white">
            {user?.email?.[0]?.toUpperCase()}
          </div>
          <div>
            <div className="text-white font-semibold">{user?.email}</div>
            <div className="text-xs text-gray-400 capitalize">{user?.role?.replace('_',' ')}</div>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3 text-xs">
          <div className="p-3 bg-gray-900/60 rounded-xl">
            <div className="text-gray-500 mb-1">User ID</div>
            <div className="text-gray-300 font-mono text-[10px] break-all">{user?.id || '—'}</div>
          </div>
          <div className="p-3 bg-gray-900/60 rounded-xl">
            <div className="text-gray-500 mb-1">Session</div>
            <div className="flex items-center gap-1 text-emerald-400"><CheckCircle size={10}/> Active</div>
          </div>
        </div>
      </div>

      {/* Change password */}
      <div className="card">
        <div className="flex items-center gap-2 mb-4">
          <Key size={16} className="text-blue-400"/>
          <h2 className="text-sm font-semibold text-white">Change Password</h2>
        </div>
        <div className="space-y-3">
          {[
            { key: 'current', label: 'Current Password' },
            { key: 'newPw',   label: 'New Password (min 12 chars)' },
            { key: 'confirm', label: 'Confirm New Password' },
          ].map(({ key, label }) => (
            <div key={key}>
              <label className="text-xs text-gray-400 block mb-1">{label}</label>
              <div className="relative">
                <input
                  type={show[key] ? 'text' : 'password'}
                  value={pwForm[key]}
                  onChange={e => setPwForm(f => ({...f, [key]: e.target.value}))}
                  className="input-field w-full text-sm pr-10"
                  autoComplete="off"
                />
                <button type="button"
                  onClick={() => setShow(s => ({...s, [key]: !s[key]}))}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300 text-xs">
                  {show[key] ? 'Hide' : 'Show'}
                </button>
              </div>
            </div>
          ))}
          <button onClick={handleChangePw} disabled={changePwMut.isPending || !pwForm.current || !pwForm.newPw}
            className="btn-primary flex items-center gap-2 text-sm">
            {changePwMut.isPending ? <RefreshCw size={14} className="animate-spin"/> : <Shield size={14}/>}
            Change Password
          </button>
        </div>
      </div>

      {/* Security info */}
      <div className="card bg-emerald-900/10 border-emerald-500/20">
        <div className="flex items-center gap-2 mb-3">
          <Shield size={16} className="text-emerald-400"/>
          <h2 className="text-sm font-semibold text-white">Security Status</h2>
        </div>
        <div className="space-y-2 text-xs">
          {[
            { label: 'JWT Authentication', ok: true },
            { label: 'AES-256 Credential Vault', ok: true },
            { label: 'bcrypt Password Hashing (cost=12)', ok: true },
            { label: 'Rate Limiting', ok: true },
            { label: '2FA / TOTP', ok: false, note: 'Optional — enable via API' },
          ].map(({ label, ok, note }) => (
            <div key={label} className="flex items-center gap-2">
              {ok
                ? <CheckCircle size={12} className="text-emerald-400 flex-shrink-0"/>
                : <AlertCircle size={12} className="text-amber-400 flex-shrink-0"/>}
              <span className={ok ? 'text-gray-300' : 'text-amber-300'}>{label}</span>
              {note && <span className="text-gray-600">— {note}</span>}
            </div>
          ))}
        </div>
      </div>

      {/* Version info */}
      <div className="card">
        <h2 className="text-sm font-semibold text-white mb-3">About</h2>
        <div className="space-y-1 text-xs text-gray-500">
          <div className="flex justify-between"><span>Platform</span><span className="text-white">Alchemy AI Trading v0.6</span></div>
          <div className="flex justify-between"><span>Backend</span><span className="text-white">FastAPI + SQLite</span></div>
          <div className="flex justify-between"><span>Live Data</span><span className="text-emerald-400">Binance WebSocket (public)</span></div>
          <div className="flex justify-between"><span>AI</span><span className="text-white">LangGraph + Anthropic</span></div>
          <div className="flex justify-between"><span>Vector DB</span><span className="text-white">ChromaDB (EI memory)</span></div>
        </div>
      </div>
    </div>
  )
}
