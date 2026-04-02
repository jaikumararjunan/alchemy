import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'
import { ShieldCheck, ShieldAlert, RefreshCw, Trash2, Plus, Eye, EyeOff, CheckCircle, XCircle, Clock, AlertCircle } from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'

const api = axios.create({ baseURL: '/api' })
const getStatus    = () => api.get('/tokens/status').then(r => r.data)
const registerToken = (data) => api.post('/tokens/register', data).then(r => r.data)
const deregister   = (ex) => api.delete(`/tokens/${ex}`).then(r => r.data)
const validateToken = (ex) => api.post(`/tokens/${ex}/validate`).then(r => r.data)
const refreshToken = (ex) => api.post(`/tokens/${ex}/refresh`).then(r => r.data)
const getHistory   = () => api.get('/tokens/history').then(r => r.data)

const STATUS_META = {
  active:     { color: 'text-emerald-400', bg: 'bg-emerald-500/10 border-emerald-500/30', Icon: CheckCircle,  label: 'Active'     },
  expiring:   { color: 'text-amber-400',   bg: 'bg-amber-500/10 border-amber-500/30',     Icon: Clock,        label: 'Expiring'   },
  expired:    { color: 'text-red-400',     bg: 'bg-red-500/10 border-red-500/30',         Icon: XCircle,      label: 'Expired'    },
  invalid:    { color: 'text-red-400',     bg: 'bg-red-500/10 border-red-500/30',         Icon: XCircle,      label: 'Invalid'    },
  missing:    { color: 'text-gray-500',    bg: 'bg-gray-800/50 border-gray-700',          Icon: AlertCircle,  label: 'Not Set'    },
  refreshing: { color: 'text-blue-400',    bg: 'bg-blue-500/10 border-blue-500/30',       Icon: RefreshCw,    label: 'Refreshing' },
}

const EXCHANGE_META = {
  kite:    { label: 'Zerodha Kite',    color: '#4F86C6', flag: '🇮🇳', market: 'NSE/BSE India', logo: '🔷' },
  delta:   { label: 'Delta Exchange',  color: '#1D4ED8', flag: '🌐', market: 'Crypto Derivatives', logo: '♦️' },
  binance: { label: 'Binance',         color: '#F59E0B', flag: '🌐', market: 'Spot + Futures', logo: '🔶' },
  ib:      { label: 'Interactive Brokers', color: '#C62828', flag: '🇺🇸', market: 'US Equities', logo: '📊' },
}

function TokenCard({ exchange, info }) {
  const qc = useQueryClient()
  const meta   = STATUS_META[info.status] || STATUS_META.missing
  const exMeta = EXCHANGE_META[exchange] || {}
  const { Icon } = meta

  const validateMut = useMutation({ mutationFn: () => validateToken(exchange),
    onSuccess: () => { toast.success(`Validating ${exchange}…`); setTimeout(() => qc.invalidateQueries(['tokens']), 2000) } })
  const refreshMut  = useMutation({ mutationFn: () => refreshToken(exchange),
    onSuccess: (d) => { toast(d.ok ? `✅ ${exchange} refreshed` : `⚠️ ${exchange} needs manual refresh`); qc.invalidateQueries(['tokens']) } })
  const deleteMut   = useMutation({ mutationFn: () => deregister(exchange),
    onSuccess: () => { toast.success(`${exchange} token removed`); qc.invalidateQueries(['tokens']) } })

  return (
    <div className={clsx('rounded-xl border p-4 space-y-3 transition-all', meta.bg)}>
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <span className="text-2xl">{exMeta.logo}</span>
          <div>
            <div className="font-semibold text-white text-sm">{exMeta.label || exchange}</div>
            <div className="text-xs text-gray-500">{exMeta.market} {exMeta.flag}</div>
          </div>
        </div>
        <div className={clsx('flex items-center gap-1.5 text-xs font-medium', meta.color)}>
          <Icon size={13} className={info.status === 'refreshing' ? 'animate-spin' : ''} />
          {meta.label}
        </div>
      </div>

      {info.api_key && (
        <div className="text-xs font-mono text-gray-400 bg-gray-900/60 rounded px-2 py-1">
          API Key: {info.api_key}
        </div>
      )}

      <div className="grid grid-cols-2 gap-2 text-xs">
        {info.use_count !== undefined && (
          <div><span className="text-gray-500">Uses: </span><span className="text-white">{info.use_count}</span></div>
        )}
        {info.expires_at && (
          <div><span className="text-gray-500">Expires: </span>
            <span className={info.status === 'expiring' ? 'text-amber-400' : 'text-gray-300'}>
              {info.seconds_to_expiry ? `${Math.round(info.seconds_to_expiry / 3600)}h` : 'N/A'}
            </span>
          </div>
        )}
        {info.paper_mode !== undefined && (
          <div><span className="text-gray-500">Mode: </span>
            <span className={info.paper_mode ? 'text-amber-400' : 'text-emerald-400'}>
              {info.paper_mode ? 'Paper' : 'Live'}
            </span>
          </div>
        )}
        {info.last_error && (
          <div className="col-span-2 text-red-400 truncate">Error: {info.last_error}</div>
        )}
      </div>

      <div className="flex gap-1.5 pt-1">
        <button onClick={() => validateMut.mutate()} disabled={validateMut.isPending}
          className="flex-1 py-1.5 text-xs bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg transition-colors flex items-center justify-center gap-1">
          <ShieldCheck size={11} /> Validate
        </button>
        <button onClick={() => refreshMut.mutate()} disabled={refreshMut.isPending}
          className="flex-1 py-1.5 text-xs bg-blue-800/50 hover:bg-blue-700/50 text-blue-300 rounded-lg transition-colors flex items-center justify-center gap-1">
          <RefreshCw size={11} className={refreshMut.isPending ? 'animate-spin' : ''} /> Refresh
        </button>
        {info.status !== 'missing' && (
          <button onClick={() => deleteMut.mutate()}
            className="px-2 py-1.5 text-xs bg-red-900/30 hover:bg-red-800/50 text-red-400 rounded-lg transition-colors">
            <Trash2 size={11} />
          </button>
        )}
      </div>
    </div>
  )
}

function RegisterForm({ onSuccess }) {
  const qc = useQueryClient()
  const [form, setForm] = useState({
    exchange: 'delta', api_key: '', api_secret: '', paper_mode: true,
    access_token: '', testnet: true, market_type: 'futures_usdm'
  })
  const [showSecret, setShowSecret] = useState(false)

  const mut = useMutation({
    mutationFn: () => registerToken(form),
    onSuccess: () => { toast.success(`${form.exchange} token registered!`); qc.invalidateQueries(['tokens']); onSuccess?.() },
    onError: (e) => toast.error(`Registration failed: ${e.message}`)
  })

  return (
    <div className="card space-y-4">
      <h3 className="text-sm font-semibold text-white flex items-center gap-2">
        <Plus size={14} className="text-blue-400" /> Register Exchange Token
      </h3>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs text-gray-400 mb-1 block">Exchange</label>
          <select value={form.exchange} onChange={e => setForm(f => ({...f, exchange: e.target.value}))} className="input-field">
            {Object.entries(EXCHANGE_META).map(([k,v]) => <option key={k} value={k}>{v.label}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs text-gray-400 mb-1 block">Mode</label>
          <div className="flex gap-1">
            {[['Paper', true], ['Live', false]].map(([lbl, val]) => (
              <button key={lbl} type="button" onClick={() => setForm(f => ({...f, paper_mode: val}))}
                className={clsx('flex-1 py-2 text-xs font-medium rounded-lg transition-colors',
                  form.paper_mode === val
                    ? (val ? 'bg-amber-600/30 text-amber-400 border border-amber-500/40' : 'bg-emerald-600/30 text-emerald-400 border border-emerald-500/40')
                    : 'bg-gray-800 text-gray-500')}>
                {lbl}
              </button>
            ))}
          </div>
        </div>
        <div>
          <label className="text-xs text-gray-400 mb-1 block">API Key</label>
          <input value={form.api_key} onChange={e => setForm(f => ({...f, api_key: e.target.value}))}
            className="input-field font-mono text-xs" placeholder="API Key" />
        </div>
        <div>
          <label className="text-xs text-gray-400 mb-1 block">API Secret</label>
          <div className="relative">
            <input type={showSecret ? 'text' : 'password'} value={form.api_secret}
              onChange={e => setForm(f => ({...f, api_secret: e.target.value}))}
              className="input-field font-mono text-xs pr-8" placeholder="API Secret" />
            <button onClick={() => setShowSecret(s => !s)}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300">
              {showSecret ? <EyeOff size={13}/> : <Eye size={13}/>}
            </button>
          </div>
        </div>
        {form.exchange === 'kite' && (
          <div className="col-span-2">
            <label className="text-xs text-gray-400 mb-1 block">Access Token (optional — enter after OAuth login)</label>
            <input value={form.access_token} onChange={e => setForm(f => ({...f, access_token: e.target.value}))}
              className="input-field font-mono text-xs" placeholder="Daily access token" />
          </div>
        )}
      </div>
      {!form.paper_mode && (
        <div className="flex items-center gap-2 text-xs text-amber-400 bg-amber-900/20 border border-amber-500/20 rounded-lg px-3 py-2">
          <ShieldAlert size={12} /> Live mode — real funds will be used. Double-check credentials.
        </div>
      )}
      <button onClick={() => mut.mutate()} disabled={mut.isPending || !form.api_key || !form.api_secret}
        className="btn-primary w-full">
        {mut.isPending ? <RefreshCw size={13} className="animate-spin inline mr-1" /> : <Plus size={13} className="inline mr-1" />}
        Register Token
      </button>
    </div>
  )
}

export default function TokenManagerPage() {
  const [showForm, setShowForm] = useState(false)
  const { data: tokens = {}, isLoading } = useQuery({ queryKey:['tokens'], queryFn: getStatus, refetchInterval: 15000 })
  const { data: history = [] } = useQuery({ queryKey:['token-history'], queryFn: getHistory, refetchInterval: 30000 })

  const allExchanges = ['kite','delta','binance','ib']
  const activeCount  = Object.values(tokens).filter(t => t.status === 'active').length

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white flex items-center gap-2">
            <ShieldCheck size={20} className="text-blue-400" /> Exchange Token Manager
          </h1>
          <p className="text-sm text-gray-400">Manage API credentials for all connected exchanges · AES-256-GCM encrypted vault</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-xs text-gray-400">
            <span className="text-emerald-400 font-semibold">{activeCount}</span> / {allExchanges.length} active
          </div>
          <button onClick={() => setShowForm(f => !f)} className="btn-primary text-xs">
            <Plus size={13} className="inline mr-1" />{showForm ? 'Cancel' : 'Add Token'}
          </button>
        </div>
      </div>

      {showForm && <RegisterForm onSuccess={() => setShowForm(false)} />}

      {/* Token Cards */}
      {isLoading
        ? <div className="text-gray-500 text-center py-12 animate-pulse">Loading token status…</div>
        : <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {allExchanges.map(ex => (
              <TokenCard key={ex} exchange={ex} info={tokens[ex] || { status: 'missing' }} />
            ))}
          </div>
      }

      {/* Refresh History */}
      {history.length > 0 && (
        <div className="card">
          <h2 className="section-title">Refresh History</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead><tr className="text-gray-500 border-b border-gray-800">
                {['Exchange','Result','Triggered By','Time','New Expiry'].map(h =>
                  <th key={h} className="pb-2 text-left font-medium pr-4">{h}</th>)}
              </tr></thead>
              <tbody>
                {history.slice(0,10).map((h, i) => (
                  <tr key={i} className="table-row">
                    <td className="py-2 pr-4 font-medium text-white capitalize">{h.exchange}</td>
                    <td className="py-2 pr-4">
                      {h.success ? <span className="text-emerald-400">✓ Success</span> : <span className="text-red-400">✗ Failed</span>}
                    </td>
                    <td className="py-2 pr-4 text-gray-400 capitalize">{h.triggered_by}</td>
                    <td className="py-2 pr-4 text-gray-400">{new Date(h.timestamp).toLocaleString('en-IN')}</td>
                    <td className="py-2 text-gray-300">{h.new_expiry ? new Date(h.new_expiry).toLocaleString('en-IN') : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
