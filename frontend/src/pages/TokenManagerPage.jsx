import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/context/AuthContext'
import {
  Key, Eye, EyeOff, CheckCircle, XCircle, RefreshCw,
  Trash2, Plus, AlertTriangle, ExternalLink, Shield,
  Wifi, WifiOff, ChevronDown, ChevronUp, Info
} from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'

const EXCHANGES = {
  delta: {
    name: 'Delta Exchange', logo: 'Delta', color: '#F7931A',
    bg: 'bg-orange-900/20 border-orange-500/30',
    description: 'Crypto derivatives — BTC, ETH futures and options',
    paper_mode: true, docs: 'https://docs.delta.exchange',
    fields: [
      { key: 'api_key',    label: 'API Key',    secret: false, placeholder: 'Your Delta API Key' },
      { key: 'api_secret', label: 'API Secret', secret: true,  placeholder: 'Your Delta API Secret' },
    ],
    setup_steps: [
      'Login at delta.exchange → Account → API Keys',
      'Click "Create New API Key"',
      'Enable permissions: Read + Trade',
      'Copy the API Key and API Secret here',
    ],
  },
  binance: {
    name: 'Binance', logo: 'BNB', color: '#F3BA2F',
    bg: 'bg-yellow-900/20 border-yellow-500/30',
    description: 'Crypto spot and futures — USDT perpetuals',
    paper_mode: true, docs: 'https://binance-docs.github.io/apidocs',
    fields: [
      { key: 'api_key',    label: 'API Key',    secret: false, placeholder: 'Binance API Key' },
      { key: 'api_secret', label: 'API Secret', secret: true,  placeholder: 'Binance Secret Key' },
    ],
    setup_steps: [
      'Login at binance.com → Profile → API Management',
      'Click "Create API" and give it a name',
      'Enable: Reading + Futures trading',
      'Optionally whitelist your IP address',
      'Copy API Key and Secret Key here',
    ],
  },
  angel: {
    name: 'Angel Broking', logo: 'Angel', color: '#E53935',
    bg: 'bg-red-900/20 border-red-500/30',
    description: 'NSE / BSE equity, F&O, commodity — SmartAPI',
    paper_mode: true, docs: 'https://smartapi.angelbroking.com/docs',
    fields: [
      { key: 'api_key',     label: 'SmartAPI Key', secret: false, placeholder: 'Your SmartAPI application key' },
      { key: 'client_id',   label: 'Client ID',    secret: false, placeholder: 'Angel One Client ID (e.g. A123456)' },
      { key: 'password',    label: 'Trading PIN',  secret: true,  placeholder: '4-digit trading PIN' },
      { key: 'totp_secret', label: 'TOTP Secret',  secret: true,
        placeholder: 'Base32 TOTP secret (from authenticator app setup)',
        help: 'Required for Angel SmartAPI authentication' },
    ],
    setup_steps: [
      'Login at smartapi.angelbroking.com and create an App',
      'Copy your SmartAPI Key from the app dashboard',
      'Client ID = your Angel One login ID (A123456)',
      'Trading PIN = your 4-digit Angel One trading PIN',
      'For TOTP: in Angel One app go to Profile → TOTP → Enable → copy the secret key shown',
    ],
  },
  kite: {
    name: 'Zerodha Kite', logo: 'Kite', color: '#387ED1',
    bg: 'bg-blue-900/20 border-blue-500/30',
    description: 'NSE / BSE equity, F&O — Kite Connect API',
    paper_mode: false, docs: 'https://kite.trade/docs/connect/v3',
    fields: [
      { key: 'api_key',    label: 'API Key',    secret: false, placeholder: 'Kite Connect API Key' },
      { key: 'api_secret', label: 'API Secret', secret: true,  placeholder: 'Kite Connect API Secret' },
    ],
    setup_steps: [
      'Go to developers.kite.trade and create an app',
      'Set Redirect URL: http://localhost:8000/tokens/kite/callback',
      'Note: Kite requires daily login via browser to refresh the access token',
      'Copy API Key and API Secret here',
    ],
  },
}

function StatusBadge({ status }) {
  const map = {
    active:         { icon: <Wifi size={11}/>,    label: 'Live',       cls: 'text-emerald-400 bg-emerald-900/30 border-emerald-500/30' },
    paper:          { icon: <Shield size={11}/>,  label: 'Paper',      cls: 'text-blue-400 bg-blue-900/30 border-blue-500/30' },
    expired:        { icon: <WifiOff size={11}/>, label: 'Expired',    cls: 'text-amber-400 bg-amber-900/30 border-amber-500/30' },
    error:          { icon: <XCircle size={11}/>, label: 'Error',      cls: 'text-red-400 bg-red-900/30 border-red-500/30' },
    not_configured: { icon: <WifiOff size={11}/>, label: 'Not Set',    cls: 'text-gray-500 bg-gray-800 border-gray-700' },
  }
  const s = map[status] || map.not_configured
  return (
    <span className={clsx('flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border', s.cls)}>
      {s.icon} {s.label}
    </span>
  )
}

function ExchangeCard({ id, config, status }) {
  const { apiClient } = useAuth()
  const qc = useQueryClient()
  const api = apiClient()

  const [open,        setOpen]        = useState(false)
  const [showSteps,   setShowSteps]   = useState(false)
  const [form,        setForm]        = useState({})
  const [showSecrets, setShowSecrets] = useState({})
  const [paperMode,   setPaperMode]   = useState(true)

  const conn = status?.status || 'not_configured'

  const registerMut = useMutation({
    mutationFn: (payload) => api.post('/tokens/register', payload).then(r => r.data),
    onSuccess: () => {
      toast.success(`${config.name} connected successfully!`)
      qc.invalidateQueries(['token-status'])
      setOpen(false); setForm({})
    },
    onError: (e) => toast.error(e.response?.data?.detail || `Failed to connect ${config.name}`),
  })

  const validateMut = useMutation({
    mutationFn: () => api.post(`/tokens/${id}/validate`).then(r => r.data),
    onSuccess: (d) => {
      if (d.valid) toast.success(`${config.name}: Connection verified!`)
      else toast.error(`${config.name}: ${d.error || 'Validation failed'}`)
      qc.invalidateQueries(['token-status'])
    },
    onError: () => toast.error(`${config.name}: Validation request failed`),
  })

  const deleteMut = useMutation({
    mutationFn: () => api.delete(`/tokens/${id}`).then(r => r.data),
    onSuccess: () => { toast.success(`${config.name} disconnected`); qc.invalidateQueries(['token-status']) },
  })

  const handleConnect = () => {
    const missing = config.fields.filter(f => !form[f.key]?.trim())
    if (missing.length) { toast.error(`Required: ${missing.map(f=>f.label).join(', ')}`); return }
    registerMut.mutate({ exchange: id, paper_trading: paperMode, testnet: paperMode, ...form })
  }

  return (
    <div className={clsx('rounded-2xl border', config.bg)}>
      <div className="p-5">
        {/* Header row */}
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="px-2.5 py-1 rounded-lg text-xs font-bold"
                 style={{ background: config.color + '22', color: config.color }}>
              {config.logo}
            </div>
            <div>
              <h3 className="text-sm font-semibold text-white">{config.name}</h3>
              <p className="text-xs text-gray-500">{config.description}</p>
            </div>
          </div>
          <StatusBadge status={conn} />
        </div>

        {/* Buttons */}
        <div className="flex gap-2">
          {conn === 'not_configured' ? (
            <button onClick={() => setOpen(o=>!o)}
              className="flex-1 py-2 rounded-xl text-xs font-medium bg-white/10 hover:bg-white/15 text-white transition-colors flex items-center justify-center gap-1.5">
              <Plus size={12}/> Connect
            </button>
          ) : (
            <>
              <button onClick={() => validateMut.mutate()} disabled={validateMut.isPending}
                className="flex-1 py-2 rounded-xl text-xs font-medium bg-emerald-900/30 hover:bg-emerald-900/50 text-emerald-400 transition-colors flex items-center justify-center gap-1.5">
                {validateMut.isPending ? <RefreshCw size={11} className="animate-spin"/> : <CheckCircle size={11}/>}
                Test
              </button>
              <button onClick={() => setOpen(o=>!o)}
                className="px-3 py-2 rounded-xl text-xs bg-white/10 hover:bg-white/15 text-gray-300 transition-colors">
                Edit
              </button>
              <button onClick={() => confirm(`Disconnect ${config.name}?`) && deleteMut.mutate()}
                className="px-3 py-2 rounded-xl text-xs bg-red-900/20 hover:bg-red-900/40 text-red-400 transition-colors">
                <Trash2 size={11}/>
              </button>
            </>
          )}
          <a href={config.docs} target="_blank" rel="noopener noreferrer"
            className="px-3 py-2 rounded-xl text-xs bg-white/5 hover:bg-white/10 text-gray-600 transition-colors">
            <ExternalLink size={11}/>
          </a>
        </div>
      </div>

      {/* Expand: form */}
      {open && (
        <div className="border-t border-white/10 p-5 space-y-4">

          {/* Setup steps */}
          <div>
            <button onClick={() => setShowSteps(s=>!s)}
              className="flex items-center gap-1.5 text-xs text-blue-400 hover:text-blue-300">
              <Info size={11}/>
              {showSteps ? 'Hide' : 'Show'} setup guide
              {showSteps ? <ChevronUp size={11}/> : <ChevronDown size={11}/>}
            </button>
            {showSteps && (
              <div className="mt-2 bg-gray-900/60 rounded-xl p-3">
                <p className="text-xs font-medium text-gray-300 mb-2">Setup steps:</p>
                <ol className="space-y-1.5 list-decimal list-inside">
                  {config.setup_steps.map((s,i) => (
                    <li key={i} className="text-xs text-gray-400">{s}</li>
                  ))}
                </ol>
              </div>
            )}
          </div>

          {/* Paper/Live toggle */}
          {config.paper_mode && (
            <div className="flex items-center justify-between p-3 rounded-xl bg-black/20">
              <div>
                <p className="text-xs font-medium text-white flex items-center gap-1.5">
                  <Shield size={11} className="text-blue-400"/> Paper / Testnet Mode
                </p>
                <p className="text-xs text-gray-500 mt-0.5">No real money — safe for testing</p>
              </div>
              <button onClick={() => setPaperMode(p=>!p)}
                className={clsx('w-10 h-5 rounded-full relative transition-colors flex-shrink-0',
                  paperMode ? 'bg-blue-600' : 'bg-gray-700')}>
                <span className={clsx('absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full transition-transform',
                  paperMode ? 'translate-x-5' : '')}/>
              </button>
            </div>
          )}

          {!paperMode && (
            <div className="flex gap-2 p-3 bg-amber-900/20 border border-amber-500/30 rounded-xl">
              <AlertTriangle size={13} className="text-amber-400 flex-shrink-0 mt-0.5"/>
              <p className="text-xs text-amber-300">
                <strong>Live mode enabled.</strong> Real orders will be placed with real money. Proceed with caution.
              </p>
            </div>
          )}

          {/* Credential fields */}
          {config.fields.map(field => (
            <div key={field.key}>
              <label className="block text-xs text-gray-400 mb-1">
                {field.label} <span className="text-red-400">*</span>
                {field.help && <span className="ml-2 text-gray-600 normal-case">{field.help}</span>}
              </label>
              <div className="relative">
                <input
                  type={field.secret && !showSecrets[field.key] ? 'password' : 'text'}
                  value={form[field.key] || ''}
                  onChange={e => setForm(f => ({...f, [field.key]: e.target.value}))}
                  placeholder={field.placeholder}
                  autoComplete="off" spellCheck={false}
                  className="w-full bg-gray-900 border border-gray-700 rounded-xl px-3 py-2.5 text-xs text-white placeholder-gray-600 focus:border-blue-500 focus:outline-none font-mono pr-8"
                />
                {field.secret && (
                  <button type="button"
                    onClick={() => setShowSecrets(s=>({...s,[field.key]:!s[field.key]}))}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300">
                    {showSecrets[field.key] ? <EyeOff size={12}/> : <Eye size={12}/>}
                  </button>
                )}
              </div>
            </div>
          ))}

          {/* Security note */}
          <div className="flex gap-2 p-3 bg-gray-900/50 rounded-xl">
            <Shield size={12} className="text-emerald-500 flex-shrink-0 mt-0.5"/>
            <p className="text-xs text-gray-500">
              Keys are encrypted with AES-256 and stored in your local vault. Never sent externally.
            </p>
          </div>

          {/* Submit */}
          <div className="flex gap-2 pt-1">
            <button onClick={() => { setOpen(false); setForm({}) }}
              className="flex-1 py-2.5 rounded-xl text-xs text-gray-400 bg-gray-800 hover:bg-gray-700 transition-colors">
              Cancel
            </button>
            <button onClick={handleConnect} disabled={registerMut.isPending}
              className="flex-1 py-2.5 rounded-xl text-xs font-semibold text-white transition-all flex items-center justify-center gap-2 hover:opacity-90"
              style={{ background: config.color }}>
              {registerMut.isPending ? <RefreshCw size={12} className="animate-spin"/> : <Key size={12}/>}
              {registerMut.isPending ? 'Connecting...' : `Connect ${config.name}`}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export default function TokenManagerPage() {
  const { apiClient } = useAuth()
  const api = apiClient()

  const { data, isLoading } = useQuery({
    queryKey: ['token-status'],
    queryFn: () => api.get('/tokens/status').then(r => r.data).catch(() => ({ tokens: {} })),
    refetchInterval: 30000,
  })

  const tokens = data?.tokens || {}
  const connected  = Object.values(tokens).filter(t => t?.status === 'active').length
  const configured = Object.keys(tokens).length

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white flex items-center gap-2">
            <Key size={20} className="text-blue-400"/> Exchange Connections
          </h1>
          <p className="text-sm text-gray-400 mt-1">
            Connect Binance, Delta Exchange, Angel Broking or Zerodha Kite
          </p>
        </div>
        <div className="flex gap-4 text-center">
          <div className="card px-4 py-2">
            <div className="text-lg font-bold text-emerald-400">{connected}</div>
            <div className="text-xs text-gray-500">Live</div>
          </div>
          <div className="card px-4 py-2">
            <div className="text-lg font-bold text-white">{configured}</div>
            <div className="text-xs text-gray-500">Set up</div>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-3 p-4 bg-emerald-900/10 border border-emerald-500/20 rounded-2xl">
        <Shield size={18} className="text-emerald-400 flex-shrink-0"/>
        <p className="text-sm text-gray-300">
          <strong className="text-emerald-400">All credentials encrypted.</strong>{' '}
          API keys are stored in your local AES-256 vault and never leave your machine.
          Start with paper/testnet mode to trade safely.
        </p>
      </div>

      {isLoading ? (
        <div className="text-center py-16 text-gray-500 animate-pulse">Loading exchange status...</div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {Object.entries(EXCHANGES).map(([id, config]) => (
            <ExchangeCard key={id} id={id} config={config} status={tokens[id]} />
          ))}
        </div>
      )}

      <div className="card border-dashed border-gray-700/50">
        <h3 className="text-sm font-semibold text-gray-300 mb-3">Which exchange should I use?</h3>
        <div className="grid grid-cols-2 gap-4 text-xs text-gray-500">
          <div>
            <p className="text-orange-400 font-medium mb-1">Crypto trading</p>
            <p>Delta Exchange testnet or Binance testnet — free paper trading with real market data. Enable testnet mode in the connection form.</p>
          </div>
          <div>
            <p className="text-red-400 font-medium mb-1">Indian equities</p>
            <p>Angel Broking SmartAPI (has paper mode) or Zerodha Kite (live account needed). Angel API is free; Kite costs 2000/month.</p>
          </div>
        </div>
      </div>
    </div>
  )
}
