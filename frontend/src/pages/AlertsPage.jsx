import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/context/AuthContext'
import { Bell, Plus, Trash2, RefreshCw, CheckCircle2, XCircle, PauseCircle } from 'lucide-react'
import clsx from 'clsx'

function fmt(n, digits = 2) {
  if (n == null || isNaN(n)) return '—'
  return Number(n).toLocaleString('en-IN', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

const STATUS_STYLE = {
  active:    'text-emerald-400 bg-emerald-400/10 border-emerald-400/30',
  triggered: 'text-blue-400 bg-blue-400/10 border-blue-400/30',
  disabled:  'text-gray-500 bg-gray-700/30 border-gray-600/30',
}

const STATUS_ICON = {
  active:    <CheckCircle2 size={12} />,
  triggered: <Bell size={12} />,
  disabled:  <PauseCircle size={12} />,
}

function CreateAlertModal({ onClose, onCreate }) {
  const [symbol, setSymbol] = useState('')
  const [exchange, setExchange] = useState('binance')
  const [condition, setCondition] = useState('above')
  const [targetPrice, setTargetPrice] = useState('')
  const [notes, setNotes] = useState('')
  const [error, setError] = useState('')

  function handleSubmit(e) {
    e.preventDefault()
    const sym = symbol.trim().toUpperCase()
    if (!sym) { setError('Symbol is required'); return }
    if (!targetPrice || parseFloat(targetPrice) <= 0) { setError('Target price must be > 0'); return }
    onCreate({ symbol: sym, exchange, condition, target_price: parseFloat(targetPrice), notes: notes || null })
    onClose()
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl p-6 w-full max-w-md shadow-2xl">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-white font-bold text-lg">New Price Alert</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white"><XCircle size={18} /></button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4 animate-fade-in">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Symbol *</label>
              <input
                value={symbol}
                onChange={e => setSymbol(e.target.value.toUpperCase())}
                placeholder="BTCUSDT"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Exchange</label>
              <select
                value={exchange}
                onChange={e => setExchange(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
              >
                <option value="binance">Binance</option>
                <option value="delta">Delta</option>
                <option value="nse">NSE</option>
                <option value="bse">BSE</option>
              </select>
            </div>
          </div>
          <div>
            <label className="text-xs text-gray-400 mb-1 block">Condition *</label>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setCondition('above')}
                className={clsx(
                  'py-2 rounded-lg text-sm font-medium border transition',
                  condition === 'above'
                    ? 'bg-emerald-600/20 border-emerald-500/50 text-emerald-400'
                    : 'border-gray-700 text-gray-400 hover:bg-gray-800'
                )}
              >
                📈 Price Above
              </button>
              <button
                type="button"
                onClick={() => setCondition('below')}
                className={clsx(
                  'py-2 rounded-lg text-sm font-medium border transition',
                  condition === 'below'
                    ? 'bg-red-600/20 border-red-500/50 text-red-400'
                    : 'border-gray-700 text-gray-400 hover:bg-gray-800'
                )}
              >
                📉 Price Below
              </button>
            </div>
          </div>
          <div>
            <label className="text-xs text-gray-400 mb-1 block">Target Price *</label>
            <input
              type="number"
              value={targetPrice}
              onChange={e => setTargetPrice(e.target.value)}
              placeholder="0.00"
              min="0"
              step="any"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
            />
          </div>
          <div>
            <label className="text-xs text-gray-400 mb-1 block">Notes (optional)</label>
            <input
              value={notes}
              onChange={e => setNotes(e.target.value)}
              placeholder="Reason for this alert..."
              maxLength={500}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
            />
          </div>
          {error && <p className="text-red-400 text-xs">{error}</p>}
          <div className="flex gap-2 pt-2">
            <button type="button" onClick={onClose} className="flex-1 py-2 rounded-lg border border-gray-700 text-gray-400 text-sm hover:bg-gray-800 transition">Cancel</button>
            <button type="submit" className="flex-1 py-2 rounded-lg bg-blue-600 text-white text-sm font-semibold hover:bg-blue-500 transition">Create Alert</button>
          </div>
        </form>
      </div>
    </div>
  )
}

function AlertRow({ alert, onDelete, onToggle }) {
  const isTriggered = alert.status === 'triggered'
  const isDisabled = alert.status === 'disabled'

  return (
    <div className={clsx(
      'border rounded-xl p-4 transition',
      isTriggered
        ? 'bg-blue-900/20 border-blue-700/40'
        : isDisabled
          ? 'bg-gray-800/30 border-gray-700/30 opacity-60'
          : 'bg-gray-800/60 border-gray-700/50'
    )}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span className="font-bold text-white text-sm">{alert.symbol}</span>
            <span className={clsx(
              'flex items-center gap-1 text-[10px] border rounded px-1.5 py-0.5',
              STATUS_STYLE[alert.status] || STATUS_STYLE.active
            )}>
              {STATUS_ICON[alert.status]}
              {alert.status}
            </span>
            <span className="text-[10px] text-gray-500 bg-gray-700/60 rounded px-1.5 py-0.5 uppercase">{alert.exchange}</span>
          </div>
          <p className="text-sm text-gray-300">
            {alert.condition === 'above' ? '📈 When price rises above' : '📉 When price falls below'}
            {' '}
            <span className="font-mono font-semibold text-white">${fmt(alert.target_price)}</span>
          </p>
          {alert.notes && <p className="text-xs text-gray-400 mt-1">{alert.notes}</p>}
          {alert.triggered_at && (
            <p className="text-xs text-blue-400 mt-1">
              ✓ Triggered {new Date(alert.triggered_at).toLocaleString('en-IN')}
            </p>
          )}
          <p className="text-[10px] text-gray-600 mt-1">
            Created {new Date(alert.created_at).toLocaleDateString('en-IN')}
          </p>
        </div>
        <div className="flex items-center gap-1 flex-shrink-0">
          {!isTriggered && (
            <button
              onClick={() => onToggle(alert.id, isDisabled ? 'active' : 'disabled')}
              className={clsx(
                'p-1.5 rounded-lg transition',
                isDisabled
                  ? 'text-gray-500 hover:text-emerald-400 hover:bg-gray-700/50'
                  : 'text-gray-500 hover:text-amber-400 hover:bg-gray-700/50'
              )}
              title={isDisabled ? 'Enable alert' : 'Disable alert'}
            >
              <PauseCircle size={14} />
            </button>
          )}
          <button
            onClick={() => onDelete(alert.id)}
            className="p-1.5 rounded-lg text-gray-500 hover:text-red-400 hover:bg-gray-700/50 transition"
          >
            <Trash2 size={14} />
          </button>
        </div>
      </div>
    </div>
  )
}

export default function AlertsPage() {
  const { apiClient } = useAuth()
  const api = apiClient()
  const qc = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [statusFilter, setStatusFilter] = useState('')

  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ['alerts', statusFilter],
    queryFn: () => api.get('/api/alerts', {
      params: statusFilter ? { status_filter: statusFilter } : {}
    }).then(r => r.data),
    refetchInterval: 30000,
  })

  const createMut = useMutation({
    mutationFn: (body) => api.post('/api/alerts', body),
    onSuccess: () => qc.invalidateQueries(['alerts']),
  })

  const deleteMut = useMutation({
    mutationFn: (id) => api.delete(`/api/alerts/${id}`),
    onSuccess: () => qc.invalidateQueries(['alerts']),
  })

  const toggleMut = useMutation({
    mutationFn: ({ id, status }) => api.patch(`/api/alerts/${id}`, { status }),
    onSuccess: () => qc.invalidateQueries(['alerts']),
  })

  const alerts = data?.alerts || []
  const activeCount = alerts.filter(a => a.status === 'active').length
  const triggeredCount = alerts.filter(a => a.status === 'triggered').length

  return (
    <div className="space-y-6 max-w-2xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-display font-bold text-white tracking-tight flex items-center gap-2">
            <Bell size={20} className="text-blue-400" />
            Price Alerts
          </h1>
          <p className="text-sm text-gray-400">Get notified when prices hit your targets</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="p-2 rounded-lg text-gray-400 hover:text-white hover:bg-gray-800 transition"
          >
            <RefreshCw size={16} className={clsx(isFetching && 'animate-spin')} />
          </button>
          <button
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold rounded-xl transition"
          >
            <Plus size={16} />
            New Alert
          </button>
        </div>
      </div>

      {/* Summary stats */}
      {alerts.length > 0 && (
        <div className="grid grid-cols-3 gap-3">
          <div className="bg-gray-800/60 border border-gray-700/50 rounded-xl p-3 text-center">
            <p className="text-2xl font-display font-bold text-white tracking-tight">{alerts.length}</p>
            <p className="text-xs text-gray-400">Total</p>
          </div>
          <div className="bg-emerald-900/20 border border-emerald-700/30 rounded-xl p-3 text-center">
            <p className="text-2xl font-bold text-emerald-400">{activeCount}</p>
            <p className="text-xs text-gray-400">Active</p>
          </div>
          <div className="bg-blue-900/20 border border-blue-700/30 rounded-xl p-3 text-center">
            <p className="text-2xl font-bold text-blue-400">{triggeredCount}</p>
            <p className="text-xs text-gray-400">Triggered</p>
          </div>
        </div>
      )}

      {/* Filter tabs */}
      {alerts.length > 0 && (
        <div className="flex gap-2">
          {['', 'active', 'triggered', 'disabled'].map(f => (
            <button
              key={f}
              onClick={() => setStatusFilter(f)}
              className={clsx(
                'px-3 py-1.5 rounded-lg text-xs font-medium border transition',
                statusFilter === f
                  ? 'bg-blue-600/20 border-blue-500/50 text-blue-400'
                  : 'border-gray-700 text-gray-400 hover:bg-gray-800'
              )}
            >
              {f || 'All'}
            </button>
          ))}
        </div>
      )}

      {/* List */}
      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-24 bg-gray-800/40 rounded-xl animate-pulse" />
          ))}
        </div>
      ) : alerts.length === 0 ? (
        <div className="text-center py-16 text-gray-500">
          <Bell size={40} className="mx-auto mb-3 opacity-30" />
          <p className="text-sm">
            {statusFilter ? `No ${statusFilter} alerts` : 'No price alerts yet'}
          </p>
          {!statusFilter && (
            <button
              onClick={() => setShowCreate(true)}
              className="mt-4 text-blue-400 text-sm hover:underline"
            >
              Create your first alert →
            </button>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          {alerts.map(alert => (
            <AlertRow
              key={alert.id}
              alert={alert}
              onDelete={id => deleteMut.mutate(id)}
              onToggle={(id, status) => toggleMut.mutate({ id, status })}
            />
          ))}
          <p className="text-xs text-gray-600 text-center pt-2">
            {alerts.length} alert{alerts.length !== 1 ? 's' : ''} · auto-refreshes every 30s
          </p>
        </div>
      )}

      {showCreate && (
        <CreateAlertModal
          onClose={() => setShowCreate(false)}
          onCreate={(body) => createMut.mutate(body)}
        />
      )}
    </div>
  )
}
