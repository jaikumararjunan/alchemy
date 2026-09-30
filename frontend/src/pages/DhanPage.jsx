import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/context/AuthContext'
import { ShieldAlert, RefreshCw } from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'

const errMsg = e => e?.response?.data?.detail || e?.message || 'Request failed'

export default function DhanPage() {
  const { apiClient } = useAuth()
  const api = apiClient()
  const qc = useQueryClient()
  const [symbols, setSymbols] = useState('RELIANCE,TCS,INFY,HDFCBANK')
  const [form, setForm] = useState({ symbol: 'RELIANCE', side: 'BUY', qty: 1, type: 'MARKET', product: 'INTRADAY', price: 0 })
  const [confirmLive, setConfirmLive] = useState(false)

  const { data: st, error: stErr } = useQuery({
    queryKey: ['dhan-status'], retry: false, refetchInterval: 30000,
    queryFn: () => api.get('/dhan/status').then(r => r.data),
  })
  const live = st?.mode === 'LIVE'

  const { data: quotes, refetch: refetchQuotes, isFetching } = useQuery({
    queryKey: ['dhan-quotes', symbols], enabled: !!st, refetchInterval: 5000,
    queryFn: () => api.get('/dhan/quote', { params: { symbols } }).then(r => r.data?.data || {}),
  })
  const { data: positions } = useQuery({
    queryKey: ['dhan-pos'], enabled: !!st, refetchInterval: 10000,
    queryFn: () => api.get('/dhan/positions').then(r => r.data),
  })
  const { data: orders } = useQuery({
    queryKey: ['dhan-orders'], enabled: !!st, refetchInterval: 10000,
    queryFn: () => api.get('/dhan/orders').then(r => r.data),
  })

  const orderMut = useMutation({
    mutationFn: () => api.post('/dhan/orders', {
      symbol: form.symbol, transaction_type: form.side, quantity: Number(form.qty),
      order_type: form.type, product_type: form.product, price: Number(form.price),
      confirm_live: confirmLive,
    }).then(r => r.data),
    onSuccess: d => {
      toast.success(`${live ? 'LIVE' : 'Paper'} order ${d.orderId || ''}`)
      setConfirmLive(false)
      qc.invalidateQueries(['dhan-orders']); qc.invalidateQueries(['dhan-pos'])
    },
    onError: e => toast.error(errMsg(e)),
  })
  const killMut = useMutation({
    mutationFn: active => api.post('/dhan/kill-switch', null, { params: { active } }).then(r => r.data),
    onSuccess: () => { toast('Kill switch updated'); qc.invalidateQueries(['dhan-status']) },
    onError: e => toast.error(errMsg(e)),
  })
  const cancelMut = useMutation({
    mutationFn: id => api.delete(`/dhan/orders/${id}`).then(r => r.data),
    onSuccess: () => qc.invalidateQueries(['dhan-orders']),
    onError: e => toast.error(errMsg(e)),
  })

  if (stErr) return (
    <div className="p-6 text-gray-300">
      <h1 className="text-xl font-bold mb-2">Dhan</h1>
      <p>{errMsg(stErr)}</p>
      <p className="text-sm text-gray-500 mt-2">Add your Client ID and Access Token on the Tokens page.</p>
    </div>
  )

  const set = k => e => setForm(f => ({ ...f, [k]: e.target.value }))
  const rows = Object.values(quotes || {}).flatMap(seg => Object.entries(seg))
  const input = 'bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm w-full'

  return (
    <div className="p-4 md:p-6 space-y-6 text-gray-200">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h1 className="text-xl font-bold">Dhan — Indian Markets</h1>
        <div className="flex items-center gap-2">
          <span className={clsx('px-2 py-1 rounded text-xs font-bold', live ? 'bg-red-600' : 'bg-emerald-700')}>
            {live ? 'LIVE — REAL MONEY' : 'PAPER'}
          </span>
          <button onClick={() => killMut.mutate(!st?.kill_switch)}
            className={clsx('px-3 py-1.5 rounded text-sm flex items-center gap-1', st?.kill_switch ? 'bg-yellow-600' : 'bg-red-700')}>
            <ShieldAlert size={14} /> {st?.kill_switch ? 'Resume trading' : 'Kill switch'}
          </button>
        </div>
      </div>

      <section className="bg-gray-900 rounded-lg p-4 space-y-3">
        <div className="flex gap-2">
          <input className={input} value={symbols} onChange={e => setSymbols(e.target.value.toUpperCase())} />
          <button onClick={() => refetchQuotes()} className="px-3 rounded bg-gray-800">
            <RefreshCw size={14} className={isFetching ? 'animate-spin' : ''} />
          </button>
        </div>
        <table className="w-full text-sm">
          <thead className="text-gray-500 text-left"><tr><th>Security ID</th><th className="text-right">LTP (₹)</th></tr></thead>
          <tbody>{rows.map(([id, q]) => (
            <tr key={id} className="border-t border-gray-800"><td>{id}</td><td className="text-right">{q.last_price}</td></tr>
          ))}</tbody>
        </table>
        <p className="text-xs text-gray-500">
          Available funds: ₹{st?.funds?.availabelBalance ?? st?.funds?.availableBalance ?? '—'} · per-order cap ₹{st?.max_order_value?.toLocaleString('en-IN')}
        </p>
      </section>

      <section className="bg-gray-900 rounded-lg p-4">
        <h2 className="font-semibold mb-3">Place order</h2>
        <div className="grid grid-cols-2 md:grid-cols-6 gap-2">
          <input className={input} placeholder="Symbol" value={form.symbol}
            onChange={e => setForm(f => ({ ...f, symbol: e.target.value.toUpperCase() }))} />
          <select className={input} value={form.side} onChange={set('side')}><option>BUY</option><option>SELL</option></select>
          <input className={input} type="number" min="1" value={form.qty} onChange={set('qty')} />
          <select className={input} value={form.type} onChange={set('type')}><option>MARKET</option><option>LIMIT</option></select>
          <select className={input} value={form.product} onChange={set('product')}><option>INTRADAY</option><option>CNC</option></select>
          <input className={input} type="number" placeholder="Limit price" disabled={form.type === 'MARKET'}
            value={form.price} onChange={set('price')} />
        </div>
        {live && (
          <label className="flex items-center gap-2 mt-3 text-sm text-red-400">
            <input type="checkbox" checked={confirmLive} onChange={e => setConfirmLive(e.target.checked)} />
            I understand this places a REAL order with real money
          </label>
        )}
        <button disabled={orderMut.isPending || (live && !confirmLive) || st?.kill_switch}
          onClick={() => orderMut.mutate()}
          className={clsx('mt-3 px-4 py-2 rounded font-semibold disabled:opacity-40', form.side === 'BUY' ? 'bg-emerald-600' : 'bg-red-600')}>
          {form.side} {form.qty} {form.symbol}
        </button>
      </section>

      <section className="grid md:grid-cols-2 gap-4">
        <div className="bg-gray-900 rounded-lg p-4">
          <h2 className="font-semibold mb-2">Positions</h2>
          <pre className="text-xs overflow-auto max-h-60">{JSON.stringify(positions ?? [], null, 1)}</pre>
        </div>
        <div className="bg-gray-900 rounded-lg p-4">
          <h2 className="font-semibold mb-2">Orders</h2>
          {(orders || []).slice(0, 15).map(o => (
            <div key={o.orderId} className="flex justify-between text-xs border-t border-gray-800 py-1">
              <span>{o.transactionType} {o.quantity} {o.tradingSymbol || o.securityId} · {o.orderStatus}</span>
              {['PENDING', 'TRANSIT'].includes(o.orderStatus) &&
                <button className="text-red-400" onClick={() => cancelMut.mutate(o.orderId)}>cancel</button>}
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
