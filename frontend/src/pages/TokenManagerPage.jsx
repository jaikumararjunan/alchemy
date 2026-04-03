import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/context/AuthContext'
import {
  Key, Eye, EyeOff, CheckCircle, XCircle, RefreshCw,
  Trash2, Plus, AlertTriangle, ExternalLink, Shield,
  Wifi, WifiOff, ChevronDown, ChevronUp, Info, Edit3,
} from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'

const EXCHANGES = {
  delta: {
    name:'Delta Exchange', logo:'Delta', color:'#F7931A',
    bg:'bg-orange-900/20 border-orange-500/30',
    description:'Crypto derivatives — BTC, ETH futures and options',
    paper_mode: true, docs:'https://docs.delta.exchange',
    fields:[
      {key:'api_key',    label:'API Key',    secret:false, placeholder:'Your Delta API Key'},
      {key:'api_secret', label:'API Secret', secret:true,  placeholder:'Your Delta API Secret'},
    ],
    setup_steps:[
      'Login at delta.exchange → Account → API Keys',
      'Click "Create New API Key"',
      'Enable permissions: Read + Trade',
      'Copy the API Key and API Secret here',
    ],
  },
  binance: {
    name:'Binance', logo:'BNB', color:'#F3BA2F',
    bg:'bg-yellow-900/20 border-yellow-500/30',
    description:'Crypto spot and futures — USDT perpetuals',
    paper_mode: true, docs:'https://binance-docs.github.io/apidocs',
    fields:[
      {key:'api_key',    label:'API Key',    secret:false, placeholder:'Binance API Key'},
      {key:'api_secret', label:'API Secret', secret:true,  placeholder:'Binance Secret Key'},
    ],
    setup_steps:[
      'Login at binance.com → Profile → API Management',
      'Click "Create API" and give it a name',
      'Enable: Enable Reading + Enable Futures',
      'Restrict to your IP for security',
      'Copy API Key and Secret Key here',
    ],
  },
  angel: {
    name:'Angel Broking', logo:'Angel', color:'#E53935',
    bg:'bg-red-900/20 border-red-500/30',
    description:'NSE / BSE equity, F&O, commodity — SmartAPI',
    paper_mode: true, docs:'https://smartapi.angelbroking.com/docs',
    fields:[
      {key:'api_key',     label:'SmartAPI Key', secret:false, placeholder:'Your SmartAPI application key'},
      {key:'client_id',   label:'Client ID',    secret:false, placeholder:'Angel One Client ID (e.g. A123456)'},
      {key:'password',    label:'Trading PIN',  secret:true,  placeholder:'4-digit trading PIN'},
      {key:'totp_secret', label:'TOTP Secret',  secret:true,  placeholder:'Base32 TOTP secret',
       help:'Get from Angel app → Profile → Enable TOTP'},
    ],
    setup_steps:[
      'Login at smartapi.angelbroking.com and create an App',
      'Copy your SmartAPI Key from the app dashboard',
      'Client ID = your Angel One login ID (A123456)',
      'Trading PIN = your 4-digit Angel One PIN',
      'TOTP Secret: in Angel One app → Profile → TOTP → Enable → copy secret key',
    ],
  },
  kite: {
    name:'Zerodha Kite', logo:'Kite', color:'#387ED1',
    bg:'bg-blue-900/20 border-blue-500/30',
    description:'NSE / BSE equity, F&O — Kite Connect API',
    paper_mode: false, docs:'https://kite.trade/docs/connect/v3',
    fields:[
      {key:'api_key',    label:'API Key',    secret:false, placeholder:'Kite Connect API Key'},
      {key:'api_secret', label:'API Secret', secret:true,  placeholder:'Kite Connect API Secret'},
    ],
    setup_steps:[
      'Go to developers.kite.trade and create an app',
      'Set Redirect URL: http://localhost:8000/tokens/kite/callback',
      'Copy API Key and API Secret here',
      'Note: requires daily browser login for access token',
    ],
  },
}

function StatusBadge({status}) {
  const map = {
    active:         {icon:<Wifi size={9}/>,    label:'Live',      cls:'text-emerald-400 bg-emerald-900/30 border-emerald-500/30'},
    paper:          {icon:<Shield size={9}/>,  label:'Paper',     cls:'text-blue-400 bg-blue-900/30 border-blue-500/30'},
    expired:        {icon:<WifiOff size={9}/>, label:'Expired',   cls:'text-amber-400 bg-amber-900/30 border-amber-500/30'},
    error:          {icon:<XCircle size={9}/>, label:'Error',     cls:'text-red-400 bg-red-900/30 border-red-500/30'},
    not_configured: {icon:<WifiOff size={9}/>, label:'Not Set',   cls:'text-gray-500 bg-gray-800 border-gray-700'},
  }
  const s = map[status] || map.not_configured
  return (
    <span className={clsx('flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border',s.cls)}>
      {s.icon} {s.label}
    </span>
  )
}

function ExchangeCard({id, config, status}) {
  const {apiClient} = useAuth()
  const api = apiClient()
  const qc  = useQueryClient()

  const [open,        setOpen]        = useState(false)
  const [showSteps,   setShowSteps]   = useState(false)
  const [form,        setForm]        = useState({})
  const [showSecrets, setShowSecrets] = useState({})
  const [paperMode,   setPaperMode]   = useState(true)
  const [testnet,     setTestnet]     = useState(true)
  const conn = status?.status || 'not_configured'

  // Load existing credentials when opening edit form
  const {data: creds, isLoading: credsLoading} = useQuery({
    queryKey: ['creds', id],
    queryFn: () => api.get(`/tokens/credentials/${id}`).then(r => r.data).catch(() => null),
    enabled: open,
    onSuccess: (d) => {
      if (d?.configured) {
        setForm(prev => ({
          api_key:    d.api_key     || prev.api_key    || '',
          client_id:  d.client_id  || prev.client_id  || '',
          api_secret: prev.api_secret || '',  // never pre-fill secret — user must re-enter or leave blank
          password:   prev.password || '',
          totp_secret: prev.totp_secret || '',
        }))
        setPaperMode(d.paper_trading ?? true)
        setTestnet(d.testnet ?? true)
      }
    },
  })

  const registerMut = useMutation({
    mutationFn: (payload) => api.post('/tokens/register', payload).then(r => r.data),
    onSuccess: () => {
      toast.success(`${config.name} saved!`)
      qc.invalidateQueries(['token-status'])
      qc.invalidateQueries(['creds', id])
      setOpen(false)
    },
    onError: (e) => toast.error(e.response?.data?.detail || `Failed: ${e.message}`),
  })

  const validateMut = useMutation({
    mutationFn: () => api.post(`/tokens/${id}/validate`).then(r => r.data),
    onSuccess: (d) => {
      if (d.valid) toast.success(`${config.name}: ${d.message || 'Connected!'}`)
      else toast.error(`${config.name}: ${d.error || 'Failed'}`)
      qc.invalidateQueries(['token-status'])
    },
    onError: () => toast.error('Validation request failed'),
  })

  const deleteMut = useMutation({
    mutationFn: () => api.delete(`/tokens/${id}`).then(r => r.data),
    onSuccess: () => {
      toast.success(`${config.name} disconnected`)
      qc.invalidateQueries(['token-status'])
      qc.invalidateQueries(['creds', id])
      setForm({})
    },
  })

  const handleConnect = () => {
    if (!form.api_key?.trim()) { toast.error('API Key is required'); return }
    registerMut.mutate({
      exchange:      id,
      api_key:       form.api_key,
      api_secret:    form.api_secret  || undefined,
      client_id:     form.client_id   || undefined,
      password:      form.password    || undefined,
      totp_secret:   form.totp_secret || undefined,
      paper_trading: paperMode,
      testnet:       testnet,
    })
  }

  return (
    <div className={clsx('rounded-2xl border transition-all duration-200', config.bg)}>
      {/* Header */}
      <div className="p-5">
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="px-2.5 py-1.5 rounded-xl text-xs font-bold"
                 style={{background: config.color+'22', color: config.color}}>
              {config.logo}
            </div>
            <div>
              <h3 className="text-sm font-semibold text-white">{config.name}</h3>
              <p className="text-xs text-gray-500">{config.description}</p>
            </div>
          </div>
          <StatusBadge status={conn}/>
        </div>

        {/* Show stored key hint if configured */}
        {creds?.configured && !open && (
          <div className="mb-3 px-3 py-2 bg-gray-900/60 rounded-xl flex items-center gap-2">
            <Key size={12} className="text-gray-500 flex-shrink-0"/>
            <div className="text-xs text-gray-400 font-mono">
              <span className="text-gray-500">Key: </span>
              {creds.api_key_masked}
              {creds.api_secret_set && <span className="ml-3 text-gray-500">Secret: ••••••••</span>}
              {creds.has_totp && <span className="ml-3 text-gray-500">TOTP: ✓</span>}
            </div>
          </div>
        )}

        {/* Error hint for common issues */}
        {conn === 'error' && validateMut.data?.error && (
          <div className="mb-2 px-3 py-2 bg-red-900/20 border border-red-500/20 rounded-xl">
            <p className="text-xs text-red-300 leading-relaxed">{validateMut.data.error}</p>
            {id === 'binance' && validateMut.data?.error?.includes('Futures') && (
              <div className="mt-2 space-y-1">
                <p className="text-[10px] text-gray-500 font-medium">How to fix:</p>
                <ol className="text-[10px] text-gray-400 space-y-0.5 pl-3">
                  <li>1. Go to binance.com → Profile → API Management</li>
                  <li>2. Click your API key → Enable "Enable Futures"</li>
                  <li>3. Click Test again</li>
                  <li className="text-blue-400">OR: Click Edit → enable Paper/Testnet mode</li>
                </ol>
              </div>
            )}
          </div>
        )}

        {/* Action buttons */}
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
                className="px-3 py-2 rounded-xl text-xs bg-white/10 hover:bg-white/15 text-gray-300 transition-colors flex items-center gap-1">
                <Edit3 size={10}/> Edit
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

      {/* Expandable form */}
      {open && (
        <div className="border-t border-white/10 p-5 space-y-4">
          {/* Setup guide */}
          <button onClick={() => setShowSteps(s=>!s)}
            className="flex items-center gap-1.5 text-xs text-blue-400 hover:text-blue-300">
            <Info size={11}/> {showSteps ? 'Hide' : 'Show'} setup guide
            {showSteps ? <ChevronUp size={11}/> : <ChevronDown size={11}/>}
          </button>
          {showSteps && (
            <ol className="space-y-1.5 pl-3 border-l border-blue-500/20">
              {config.setup_steps.map((s,i) => (
                <li key={i} className="text-xs text-gray-400 flex gap-2">
                  <span className="text-blue-500/50 flex-shrink-0">{i+1}.</span>{s}
                </li>
              ))}
            </ol>
          )}

          {/* Paper/Live toggle */}
          {config.paper_mode && (
            <div className="flex items-center justify-between p-3 rounded-xl bg-black/20">
              <div>
                <p className="text-xs font-medium text-white flex items-center gap-1.5">
                  <Shield size={11} className="text-blue-400"/> Paper / Testnet Mode
                </p>
                <p className="text-xs text-gray-500">No real money — safe for testing</p>
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
                <strong>Live mode.</strong> Real orders will be placed with real money.
              </p>
            </div>
          )}

          {/* Credential fields */}
          {credsLoading ? (
            <div className="space-y-3">
              {config.fields.map(f => <div key={f.key} className="h-9 bg-gray-800 rounded-xl animate-pulse"/>)}
            </div>
          ) : config.fields.map(field => (
            <div key={field.key}>
              <label className="block text-xs text-gray-400 mb-1">
                {field.label} <span className="text-red-400">*</span>
                {field.help && <span className="ml-2 text-gray-600">{field.help}</span>}
              </label>
              <div className="relative">
                <input
                  type={field.secret && !showSecrets[field.key] ? 'password' : 'text'}
                  value={form[field.key] || ''}
                  onChange={e => setForm(f => ({...f, [field.key]: e.target.value}))}
                  placeholder={
                    field.secret && creds?.configured
                      ? (field.key === 'api_secret' && creds?.api_secret_set ? '(stored — leave blank to keep)' :
                         field.key === 'totp_secret' && creds?.totp_secret_set ? '(stored — leave blank to keep)' :
                         field.placeholder)
                      : field.placeholder
                  }
                  autoComplete="off" spellCheck={false}
                  className="w-full bg-gray-900 border border-gray-700 rounded-xl px-3 py-2.5 text-xs text-white placeholder-gray-600 focus:border-blue-500 focus:outline-none font-mono pr-10"
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

          <div className="flex gap-2 pt-1 items-center">
            <span className="text-xs text-gray-600 flex items-center gap-1">
              <Shield size={10} className="text-emerald-500"/> AES-256 encrypted
            </span>
            <div className="flex gap-2 ml-auto">
              <button onClick={() => { setOpen(false); setForm({}) }}
                className="px-4 py-2 rounded-xl text-xs text-gray-400 bg-gray-800 hover:bg-gray-700 transition-colors">
                Cancel
              </button>
              <button onClick={handleConnect} disabled={registerMut.isPending}
                className="px-5 py-2 rounded-xl text-xs font-semibold text-white transition-all flex items-center gap-2 hover:opacity-90"
                style={{background: config.color}}>
                {registerMut.isPending ? <RefreshCw size={12} className="animate-spin"/> : <Key size={12}/>}
                {creds?.configured ? 'Update' : 'Connect'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default function TokenManagerPage() {
  const {apiClient} = useAuth()
  const api = apiClient()

  const {data, isLoading} = useQuery({
    queryKey: ['token-status'],
    queryFn: () => api.get('/tokens/status').then(r => r.data).catch(() => ({tokens:{}})),
    refetchInterval: 30000,
  })

  const tokens   = data?.tokens || {}
  const connected  = Object.values(tokens).filter(t => t?.status === 'active').length
  const configured = Object.keys(tokens).length

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white flex items-center gap-2">
            <Key size={20} className="text-blue-400"/> Exchange Connections
          </h1>
          <p className="text-sm text-gray-400">Connect Binance, Delta Exchange, Angel Broking or Zerodha Kite</p>
        </div>
        <div className="flex gap-3">
          {[{l:'Live',v:connected,c:'text-emerald-400'},{l:'Set up',v:configured,c:'text-white'}].map(s => (
            <div key={s.l} className="card px-4 py-2 text-center">
              <div className={clsx('text-xl font-bold', s.c)}>{s.v}</div>
              <div className="text-xs text-gray-500">{s.l}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="flex items-center gap-3 p-4 bg-emerald-900/10 border border-emerald-500/20 rounded-2xl">
        <Shield size={18} className="text-emerald-400 flex-shrink-0"/>
        <p className="text-sm text-gray-300">
          <strong className="text-emerald-400">All credentials encrypted.</strong>{' '}
          API keys stored in local AES-256 vault. Existing keys are shown when editing.
          Start with paper mode — no real money.
        </p>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {[1,2,3,4].map(i => <div key={i} className="h-32 rounded-2xl bg-gray-800 animate-pulse"/>)}
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {Object.entries(EXCHANGES).map(([id, config]) => (
            <ExchangeCard key={id} id={id} config={config} status={tokens[id]}/>
          ))}
        </div>
      )}

      <div className="card border-dashed border-gray-700/50">
        <h3 className="text-sm font-semibold text-gray-300 mb-3">Which exchange?</h3>
        <div className="grid grid-cols-2 gap-4 text-xs text-gray-500">
          <div>
            <p className="text-orange-400 font-medium mb-1">Crypto trading</p>
            <p>Delta testnet or Binance testnet — free paper trading with real market data.</p>
          </div>
          <div>
            <p className="text-red-400 font-medium mb-1">Indian equities</p>
            <p>Angel Broking SmartAPI (free, has paper mode) or Zerodha Kite (₹2000/month).</p>
          </div>
        </div>
      </div>
    </div>
  )
}
