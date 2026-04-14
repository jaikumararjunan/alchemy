import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/context/AuthContext'
import { Star, Plus, Trash2, Edit3, Check, X, RefreshCw, TrendingUp, TrendingDown } from 'lucide-react'
import clsx from 'clsx'

function fmt(n, digits = 2) {
  if (n == null || isNaN(n)) return '—'
  return Number(n).toLocaleString('en-IN', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

function PriceTag({ price, change }) {
  if (price == null) return <span className="text-gray-500 text-xs">—</span>
  const pos = change >= 0
  return (
    <span className={clsx('flex items-center gap-1 text-sm font-mono', pos ? 'text-emerald-400' : 'text-red-400')}>
      {pos ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
      {fmt(change, 2)}%
    </span>
  )
}

function AddSymbolModal({ onClose, onAdd }) {
  const [symbol, setSymbol] = useState('')
  const [exchange, setExchange] = useState('binance')
  const [notes, setNotes] = useState('')
  const [targetPrice, setTargetPrice] = useState('')
  const [error, setError] = useState('')

  function handleSubmit(e) {
    e.preventDefault()
    const sym = symbol.trim().toUpperCase()
    if (!sym) { setError('Symbol is required'); return }
    if (!/^[A-Za-z0-9_\-\.]+$/.test(sym)) { setError('Invalid symbol characters'); return }
    onAdd({ symbol: sym, exchange, notes: notes || null, target_price: targetPrice ? parseFloat(targetPrice) : null })
    onClose()
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl p-6 w-full max-w-md shadow-2xl">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-white font-display font-bold text-lg">Add to Watchlist</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white"><X size={18} /></button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4 animate-fade-in">
          <div>
            <label className="text-xs text-gray-400 mb-1 block">Symbol *</label>
            <input
              value={symbol}
              onChange={e => setSymbol(e.target.value.toUpperCase())}
              placeholder="e.g. BTCUSDT"
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
              <option value="delta">Delta Exchange</option>
              <option value="nse">NSE</option>
              <option value="bse">BSE</option>
              <option value="other">Other</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-400 mb-1 block">Target Price (optional)</label>
            <input
              type="number"
              value={targetPrice}
              onChange={e => setTargetPrice(e.target.value)}
              placeholder="Alert when price reaches..."
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
            />
          </div>
          <div>
            <label className="text-xs text-gray-400 mb-1 block">Notes (optional)</label>
            <input
              value={notes}
              onChange={e => setNotes(e.target.value)}
              placeholder="Why are you watching this?"
              maxLength={500}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
            />
          </div>
          {error && <p className="text-red-400 text-xs">{error}</p>}
          <div className="flex gap-2 pt-2">
            <button type="button" onClick={onClose} className="flex-1 py-2 rounded-lg border border-gray-700 text-gray-400 text-sm hover:bg-gray-800 transition">Cancel</button>
            <button type="submit" className="flex-1 py-2 rounded-lg bg-blue-600 text-white text-sm font-semibold hover:bg-blue-500 transition">Add Symbol</button>
          </div>
        </form>
      </div>
    </div>
  )
}

function WatchlistRow({ item, onRemove, onUpdate }) {
  const [editing, setEditing] = useState(false)
  const [notes, setNotes] = useState(item.notes || '')
  const [targetPrice, setTargetPrice] = useState(item.target_price || '')

  function save() {
    onUpdate(item.symbol, {
      notes: notes || null,
      target_price: targetPrice ? parseFloat(targetPrice) : null,
    })
    setEditing(false)
  }

  return (
    <div className="bg-gray-800/60 border border-gray-700/50 rounded-xl p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="font-bold text-white text-sm">{item.symbol}</span>
            <span className="text-[10px] text-gray-500 bg-gray-700/60 rounded px-1.5 py-0.5 uppercase">{item.exchange}</span>
          </div>
          {!editing ? (
            <>
              {item.notes && <p className="text-xs text-gray-400 mt-1">{item.notes}</p>}
              {item.target_price && (
                <p className="text-xs text-amber-400 mt-1">🎯 Target: ${fmt(item.target_price)}</p>
              )}
              <p className="text-[10px] text-gray-600 mt-1">
                Added {new Date(item.added_at).toLocaleDateString('en-IN')}
              </p>
            </>
          ) : (
            <div className="mt-2 space-y-2">
              <input
                value={notes}
                onChange={e => setNotes(e.target.value)}
                placeholder="Notes..."
                className="w-full bg-gray-700 border border-gray-600 rounded px-2 py-1 text-xs text-white focus:outline-none focus:border-blue-500"
              />
              <input
                type="number"
                value={targetPrice}
                onChange={e => setTargetPrice(e.target.value)}
                placeholder="Target price..."
                className="w-full bg-gray-700 border border-gray-600 rounded px-2 py-1 text-xs text-white focus:outline-none focus:border-blue-500"
              />
              <div className="flex gap-2">
                <button onClick={save} className="flex items-center gap-1 text-xs text-emerald-400 hover:text-emerald-300">
                  <Check size={12} /> Save
                </button>
                <button onClick={() => setEditing(false)} className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-300">
                  <X size={12} /> Cancel
                </button>
              </div>
            </div>
          )}
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {!editing && (
            <button
              onClick={() => setEditing(true)}
              className="p-1.5 rounded-lg text-gray-500 hover:text-blue-400 hover:bg-gray-700/50 transition"
            >
              <Edit3 size={14} />
            </button>
          )}
          <button
            onClick={() => onRemove(item.symbol)}
            className="p-1.5 rounded-lg text-gray-500 hover:text-red-400 hover:bg-gray-700/50 transition"
          >
            <Trash2 size={14} />
          </button>
        </div>
      </div>
    </div>
  )
}

export default function WatchlistPage() {
  const { apiClient } = useAuth()
  const api = apiClient()
  const qc = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [search, setSearch] = useState('')

  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ['watchlist'],
    queryFn: () => api.get('/api/watchlist').then(r => r.data),
    refetchInterval: 30000,
  })

  const addMut = useMutation({
    mutationFn: (body) => api.post('/api/watchlist', body),
    onSuccess: () => qc.invalidateQueries(['watchlist']),
  })

  const removeMut = useMutation({
    mutationFn: (symbol) => api.delete(`/api/watchlist/${symbol}`),
    onSuccess: () => qc.invalidateQueries(['watchlist']),
  })

  const updateMut = useMutation({
    mutationFn: ({ symbol, body }) => api.patch(`/api/watchlist/${symbol}`, body),
    onSuccess: () => qc.invalidateQueries(['watchlist']),
  })

  const items = (data?.items || []).filter(i =>
    !search || i.symbol.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className="space-y-6 max-w-2xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-display font-bold text-white tracking-tight flex items-center gap-2">
            <Star size={20} className="text-amber-400" />
            Watchlist
          </h1>
          <p className="text-sm text-gray-400">Track symbols you want to monitor</p>
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
            onClick={() => setShowAdd(true)}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold rounded-xl transition"
          >
            <Plus size={16} />
            Add Symbol
          </button>
        </div>
      </div>

      {/* Search */}
      {(data?.items?.length || 0) > 4 && (
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search symbols..."
          className="w-full bg-gray-800 border border-gray-700 rounded-xl px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
        />
      )}

      {/* List */}
      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-20 bg-gray-800/40 rounded-xl animate-pulse" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="text-center py-16 text-gray-500">
          <Star size={40} className="mx-auto mb-3 opacity-30" />
          <p className="text-sm">
            {search ? 'No symbols match your search' : 'Your watchlist is empty'}
          </p>
          {!search && (
            <button
              onClick={() => setShowAdd(true)}
              className="mt-4 text-blue-400 text-sm hover:underline"
            >
              Add your first symbol →
            </button>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          {items.map(item => (
            <WatchlistRow
              key={item.symbol}
              item={item}
              onRemove={sym => removeMut.mutate(sym)}
              onUpdate={(sym, body) => updateMut.mutate({ symbol: sym, body })}
            />
          ))}
          <p className="text-xs text-gray-600 text-center pt-2">
            {items.length} symbol{items.length !== 1 ? 's' : ''} · auto-refreshes every 30s
          </p>
        </div>
      )}

      {showAdd && (
        <AddSymbolModal
          onClose={() => setShowAdd(false)}
          onAdd={(body) => addMut.mutate(body)}
        />
      )}
    </div>
  )
}
