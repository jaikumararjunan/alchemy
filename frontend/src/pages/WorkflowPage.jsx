import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'
import { GitBranch, Play, CheckCircle, XCircle, Clock, AlertTriangle, ArrowRight, RefreshCw, Zap } from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'

const api = axios.create({ baseURL: '/api' })
const executeBuy    = (req) => api.post('/workflows/buy',  req).then(r => r.data)
const executeSell   = (req) => api.post('/workflows/sell', req).then(r => r.data)
const getHistory    = () => api.get('/workflows/history?limit=20').then(r => r.data)
const getStates     = () => api.get('/workflows/states').then(r => r.data)
const routePreview  = (p)  => api.get('/workflows/route-preview', { params: p }).then(r => r.data)

const STATUS_STYLE = {
  pending:          'bg-gray-700 text-gray-300',
  signal_validated: 'bg-blue-800/50 text-blue-300',
  risk_checked:     'bg-purple-800/50 text-purple-300',
  token_verified:   'bg-indigo-800/50 text-indigo-300',
  routed:           'bg-sky-800/50 text-sky-300',
  placed:           'bg-amber-800/50 text-amber-300',
  monitoring:       'bg-amber-700/50 text-amber-200',
  filled:           'bg-emerald-800/50 text-emerald-300',
  partially_filled: 'bg-teal-800/50 text-teal-300',
  rejected:         'bg-red-900/50 text-red-400',
  cancelled:        'bg-gray-800 text-gray-400',
  settled:          'bg-emerald-900/50 text-emerald-400',
  error:            'bg-red-900/50 text-red-400',
}

// Visual pipeline showing all workflow steps in order
const PIPELINE_STEPS = [
  { key: 'pending',          label: 'Pending',          icon: Clock },
  { key: 'signal_validated', label: 'Validated',         icon: CheckCircle },
  { key: 'risk_checked',     label: 'Risk OK',           icon: CheckCircle },
  { key: 'token_verified',   label: 'Token OK',          icon: CheckCircle },
  { key: 'routed',           label: 'Routed',            icon: GitBranch },
  { key: 'placed',           label: 'Placed',            icon: Play },
  { key: 'monitoring',       label: 'Monitoring',        icon: RefreshCw },
  { key: 'filled',           label: 'Filled',            icon: CheckCircle },
  { key: 'settled',          label: 'Settled',           icon: CheckCircle },
]

function OrderPipeline({ workflow }) {
  const currentIdx = PIPELINE_STEPS.findIndex(s => s.key === workflow.status)
  const isError    = ['rejected','cancelled','error'].includes(workflow.status)

  return (
    <div className="flex items-center gap-0 overflow-x-auto py-2">
      {PIPELINE_STEPS.map((step, i) => {
        const Icon = step.icon
        const done    = i < currentIdx
        const active  = i === currentIdx
        const future  = i > currentIdx
        return (
          <div key={step.key} className="flex items-center flex-shrink-0">
            <div className={clsx('flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium transition-all',
              done   ? 'bg-emerald-900/40 text-emerald-400' :
              active && isError ? 'bg-red-900/50 text-red-400' :
              active ? 'bg-blue-700/50 text-blue-300 ring-1 ring-blue-500' :
                       'bg-white/[0.02] text-gray-600')}>
              <Icon size={10} className={active && step.key === 'monitoring' ? 'animate-spin' : ''} />
              {step.label}
            </div>
            {i < PIPELINE_STEPS.length - 1 && (
              <ArrowRight size={10} className={clsx('mx-0.5 flex-shrink-0',
                done ? 'text-emerald-600' : 'text-gray-700')} />
            )}
          </div>
        )
      })}
      {isError && (
        <div className="flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium bg-red-900/50 text-red-400 ml-1">
          <XCircle size={10} /> {workflow.status}
        </div>
      )}
    </div>
  )
}

function WorkflowCard({ wf }) {
  const [open, setOpen] = useState(false)
  const isBuy = wf.side === 'buy'
  return (
    <div className="card-sm space-y-2 cursor-pointer" onClick={() => setOpen(o => !o)}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={isBuy ? 'badge-buy' : 'badge-sell'}>{wf.side?.toUpperCase()}</span>
          <span className="text-sm font-semibold text-white">{wf.symbol}</span>
          <span className="text-xs text-gray-500">{wf.exchange} → {wf.routed_to || '—'}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className={clsx('text-xs px-2 py-0.5 rounded-full', STATUS_STYLE[wf.status] || 'bg-gray-700 text-gray-300')}>
            {wf.status?.replace(/_/g, ' ')}
          </span>
          <span className="text-xs text-gray-600">{wf.duration_ms}ms</span>
        </div>
      </div>
      <OrderPipeline workflow={wf} />
      {open && (
        <div className="mt-2 space-y-1 border-t border-gray-700 pt-2">
          {wf.fill_price && <div className="text-xs text-gray-300">Fill: <span className="text-white font-medium">${wf.fill_price.toLocaleString()}</span> × {wf.fill_quantity}</div>}
          {wf.pnl !== null && wf.pnl !== undefined && <div className={clsx('text-xs font-semibold', wf.pnl >= 0 ? 'text-emerald-400' : 'text-red-400')}>P&L: {wf.pnl >= 0 ? '+' : ''}${wf.pnl?.toFixed(2)}</div>}
          {wf.errors?.length > 0 && <div className="text-xs text-red-400">{wf.errors.join(' | ')}</div>}
          <div className="text-xs text-gray-600 font-mono">{wf.workflow_id}</div>
        </div>
      )}
    </div>
  )
}

function OrderForm({ onResult }) {
  const EXCHANGES = ['auto','delta','binance','kite','ib']
  const SYMBOLS   = ['BTCUSD','ETHUSD','SOLUSD','BTCUSDT','ETHUSDT','RELIANCE','TCS','AAPL']
  const [form, setForm] = useState({ symbol:'BTCUSD', exchange:'auto', side:'buy', quantity:'1', order_type:'market', leverage:'1', limit_price:'' })
  const [preview, setPreview] = useState(null)

  const buyMut  = useMutation({ mutationFn: executeBuy,  onSuccess: (d) => { onResult?.(d); toast.success(`BUY workflow: ${d.status}`)  } })
  const sellMut = useMutation({ mutationFn: executeSell, onSuccess: (d) => { onResult?.(d); toast.success(`SELL workflow: ${d.status}`) } })
  const isPending = buyMut.isPending || sellMut.isPending

  const previewMut = useMutation({ mutationFn: () => routePreview({ symbol: form.symbol, exchange: form.exchange, side: form.side, quantity: form.quantity }),
    onSuccess: setPreview })

  const submit = () => {
    if (!form.quantity || isNaN(Number(form.quantity))) return toast.error('Enter valid quantity')
    const payload = { ...form, quantity: Number(form.quantity), leverage: Number(form.leverage),
                      limit_price: form.limit_price ? Number(form.limit_price) : null }
    form.side === 'buy' ? buyMut.mutate(payload) : sellMut.mutate(payload)
  }

  return (
    <div className="card space-y-4">
      <h3 className="text-sm font-semibold text-white flex items-center gap-2">
        <Zap size={14} className="text-blue-400" /> Execute Order Workflow
      </h3>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs text-gray-400 mb-1 block">Symbol</label>
          <select value={form.symbol} onChange={e => setForm(f => ({...f, symbol: e.target.value}))} className="input-field">
            {SYMBOLS.map(s => <option key={s}>{s}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs text-gray-400 mb-1 block">Exchange</label>
          <select value={form.exchange} onChange={e => setForm(f => ({...f, exchange: e.target.value}))} className="input-field">
            {EXCHANGES.map(e => <option key={e} value={e}>{e === 'auto' ? '🤖 Auto (Smart Router)' : e}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs text-gray-400 mb-1 block">Side</label>
          <div className="flex gap-1">
            {['buy','sell'].map(s => (
              <button key={s} type="button" onClick={() => setForm(f => ({...f, side: s}))}
                className={clsx('flex-1 py-2 text-xs font-semibold rounded-lg transition-colors',
                  form.side === s ? (s==='buy' ? 'bg-emerald-600 text-white' : 'bg-red-600 text-white') : 'bg-gray-800 text-gray-400 hover:bg-gray-700')}>
                {s === 'buy' ? '▲ BUY' : '▼ SELL'}
              </button>
            ))}
          </div>
        </div>
        <div>
          <label className="text-xs text-gray-400 mb-1 block">Order Type</label>
          <select value={form.order_type} onChange={e => setForm(f => ({...f, order_type: e.target.value}))} className="input-field">
            <option value="market">Market</option>
            <option value="limit">Limit</option>
            <option value="stop_market">Stop Market</option>
          </select>
        </div>
        <div>
          <label className="text-xs text-gray-400 mb-1 block">Quantity</label>
          <input value={form.quantity} onChange={e => setForm(f => ({...f, quantity: e.target.value}))} className="input-field" placeholder="1" />
        </div>
        <div>
          <label className="text-xs text-gray-400 mb-1 block">Leverage</label>
          <select value={form.leverage} onChange={e => setForm(f => ({...f, leverage: e.target.value}))} className="input-field">
            {['1','2','3','5','10','20','50'].map(l => <option key={l}>{l}x</option>)}
          </select>
        </div>
        {form.order_type === 'limit' && (
          <div className="col-span-2">
            <label className="text-xs text-gray-400 mb-1 block">Limit Price</label>
            <input value={form.limit_price} onChange={e => setForm(f => ({...f, limit_price: e.target.value}))} className="input-field" placeholder="68000" />
          </div>
        )}
      </div>

      {preview && (
        <div className="text-xs bg-blue-900/20 border border-blue-500/30 rounded-lg px-3 py-2 space-y-1">
          <div className="text-blue-400 font-medium">🤖 Smart Router Preview</div>
          <div className="text-gray-300">Route to: <span className="text-white font-semibold">{preview.exchange}</span></div>
          <div className="text-gray-400">{preview.reason}</div>
          <div className="text-gray-500">Est. fee: ${preview.fee_estimate?.toFixed(4)} · Score: {preview.score?.toFixed(3)}</div>
        </div>
      )}

      <div className="flex gap-2">
        <button onClick={() => previewMut.mutate()} disabled={previewMut.isPending} className="btn-ghost text-xs flex-shrink-0">
          <GitBranch size={12} className="inline mr-1" /> Preview Route
        </button>
        <button onClick={submit} disabled={isPending} className={clsx('flex-1 py-2 rounded-lg text-sm font-semibold transition-colors',
          form.side === 'buy' ? 'bg-emerald-600 hover:bg-emerald-500 text-white disabled:opacity-50'
                              : 'bg-red-600 hover:bg-red-500 text-white disabled:opacity-50')}>
          {isPending ? <RefreshCw size={14} className="animate-spin inline mr-1" /> : <Play size={14} className="inline mr-1" />}
          {isPending ? 'Processing…' : `Execute ${form.side.toUpperCase()} Workflow`}
        </button>
      </div>
    </div>
  )
}

export default function WorkflowPage() {
  const qc = useQueryClient()
  const { data: history = [], isLoading } = useQuery({ queryKey:['wf-history'], queryFn: getHistory, refetchInterval: 5000 })
  const { data: states  } = useQuery({ queryKey:['wf-states'],  queryFn: getStates })

  const filled    = history.filter(w => w.status === 'settled' || w.status === 'filled').length
  const cancelled = history.filter(w => ['cancelled','rejected','error'].includes(w.status)).length
  const active    = history.filter(w => !['settled','filled','cancelled','rejected','error'].includes(w.status)).length

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-display font-bold text-white tracking-tight flex items-center gap-2">
          <GitBranch size={20} className="text-blue-400" /> Order Workflow Engine
        </h1>
        <p className="text-sm text-gray-400">LangGraph state machine · 9 stages · Smart Order Router · Token-gated execution</p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {[['Total Workflows', history.length, 'text-white'],
          ['Active',          active,          'text-blue-400'],
          ['Completed',       filled,          'text-emerald-400'],
          ['Cancelled/Error', cancelled,       'text-red-400']].map(([l,v,c]) => (
          <div key={l} className="card-sm text-center">
            <div className="text-xs text-gray-500">{l}</div>
            <div className={clsx('text-2xl font-bold mt-1', c)}>{v}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Order Form */}
        <div className="lg:col-span-1">
          <OrderForm onResult={() => qc.invalidateQueries(['wf-history'])} />

          {/* State machine reference */}
          {states && (
            <div className="card mt-4">
              <h3 className="text-xs font-semibold text-gray-300 mb-3 flex items-center gap-1">
                <GitBranch size={11} /> State Machine
              </h3>
              <div className="space-y-1">
                {states.states?.map(s => (
                  <div key={s} className="flex items-center justify-between">
                    <span className={clsx('text-xs px-1.5 py-0.5 rounded', STATUS_STYLE[s] || 'bg-gray-800 text-gray-400')}>
                      {s.replace(/_/g, ' ')}
                    </span>
                    {states.terminal_states?.includes(s) && (
                      <span className="text-xs text-gray-600">terminal</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Workflow history */}
        <div className="lg:col-span-2">
          <div className="card">
            <h2 className="section-title">Workflow History</h2>
            {isLoading
              ? <div className="text-gray-500 text-center py-8 animate-pulse">Loading…</div>
              : history.length === 0
                ? <div className="text-gray-500 text-sm text-center py-10">No workflows yet — execute an order above</div>
                : <div className="space-y-2 max-h-[600px] overflow-y-auto pr-1">
                    {history.map((wf, i) => <WorkflowCard key={wf.workflow_id || i} wf={wf} />)}
                  </div>
            }
          </div>
        </div>
      </div>
    </div>
  )
}
