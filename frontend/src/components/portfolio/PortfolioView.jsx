import { useQuery, useMutation } from '@tanstack/react-query'
import { useAuth } from '@/context/AuthContext'
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid } from 'recharts'
import { RefreshCw, AlertCircle, TrendingUp, TrendingDown, Wifi, WifiOff, Lock } from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'

const EXCHANGE_COLORS = { delta: '#F7931A', binance: '#F3BA2F', angel: '#E53935', kite: '#387ED1' }

function Empty({ message, sub }) {
  return (
    <div className="text-center py-10">
      <AlertCircle size={28} className="mx-auto mb-2 text-gray-600"/>
      <p className="text-sm text-gray-400">{message}</p>
      {sub && <p className="text-xs text-gray-600 mt-1">{sub}</p>}
    </div>
  )
}

function LiveBadge({ live }) {
  return (
    <span className={clsx('inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full',
      live ? 'bg-emerald-900/30 text-emerald-400' : 'bg-blue-900/30 text-blue-400')}>
      {live ? <Wifi size={9}/> : <Lock size={9}/>}
      {live ? 'Live' : 'Paper (read-only)'}
    </span>
  )
}

function ExchangePositions({ exchange, api, isLive }) {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['positions', exchange],
    queryFn: () => api.get(`/crypto/${exchange}/positions`).then(r => r.data),
    retry: false,
    staleTime: 15000,
    refetchInterval: 30000,
  })

  const closeMut = useMutation({
    mutationFn: (symbol) => api.post(`/crypto/${exchange}/close/${symbol}`).then(r => r.data),
    onSuccess: () => { toast.success('Position closed'); refetch() },
    onError: (e) => toast.error(e.response?.data?.detail || 'Close failed'),
  })

  if (isLoading) return (
    <div className="space-y-2 animate-pulse">
      {[1,2].map(i => <div key={i} className="h-8 bg-gray-800 rounded"/>)}
    </div>
  )

  if (error) return (
    <div className="flex items-center gap-2 p-3 bg-gray-900/50 rounded-lg text-xs text-gray-500">
      <WifiOff size={12}/> Cannot load {exchange} positions — check API credentials
    </div>
  )

  const positions = Array.isArray(data) ? data :
    data?.result || data?.positions || data?.data || []

  const active = positions.filter(p => {
    const qty = parseFloat(p.size || p.quantity || p.positionAmt || 0)
    return Math.abs(qty) > 0
  })

  if (active.length === 0) return (
    <p className="text-xs text-gray-500 py-2 italic">No open positions on {exchange}</p>
  )

  return (
    <div className="space-y-1">
      {active.map((p, i) => {
        const sym   = p.symbol || p.product?.symbol || p.product_id || '—'
        const qty   = parseFloat(p.size || p.quantity || p.positionAmt || 0)
        const side  = qty > 0 ? 'LONG' : 'SHORT'
        const entry = parseFloat(p.entry_price || p.entryPrice || 0)
        const mark  = parseFloat(p.mark_price  || p.markPrice  || p.ltp || 0)
        const pnl   = parseFloat(p.realized_pnl || p.unrealizedProfit || p.unrealized_pnl || 0)
        const pnlUp = pnl >= 0

        return (
          <div key={i} className="flex items-center justify-between py-2 border-b border-gray-800/50 last:border-0">
            <div className="flex items-center gap-3">
              <span className={clsx('text-xs font-bold px-2 py-0.5 rounded',
                side === 'LONG' ? 'bg-emerald-900/40 text-emerald-400' : 'bg-red-900/40 text-red-400')}>
                {side}
              </span>
              <div>
                <div className="text-sm font-medium text-white">{sym}</div>
                <div className="text-xs text-gray-500">
                  Qty: {Math.abs(qty).toFixed(4)} · Entry: {entry ? entry.toLocaleString() : '—'}
                </div>
              </div>
            </div>
            <div className="text-right flex items-center gap-3">
              <div>
                <div className="text-sm text-gray-300">{mark ? mark.toLocaleString() : '—'}</div>
                <div className={clsx('text-xs font-semibold', pnlUp ? 'text-emerald-400' : 'text-red-400')}>
                  {pnlUp ? '+' : ''}{pnl.toFixed(2)} USDT
                </div>
              </div>
              {isLive && (
                <button onClick={() => closeMut.mutate(sym)}
                  disabled={closeMut.isPending}
                  className="text-xs text-red-400 hover:text-red-300 px-2 py-1 rounded bg-red-900/20 hover:bg-red-900/40 transition-colors">
                  {closeMut.isPending ? <RefreshCw size={10} className="animate-spin"/> : 'Close'}
                </button>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function ExchangeBalance({ exchange, api }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['balance', exchange],
    queryFn: () => api.get(`/crypto/${exchange}/balance`).then(r => r.data),
    retry: false,
    staleTime: 30000,
    refetchInterval: 60000,
  })

  if (isLoading) return <div className="animate-pulse h-4 bg-gray-800 rounded w-20"/>
  if (error)     return <span className="text-xs text-gray-600">—</span>

  // Normalize balance response from different exchanges
  const totalUsdt = (
    parseFloat(data?.balance || data?.total?.USDT || data?.totalWalletBalance ||
               data?.availableBalanceUsdt || data?.equity || 0)
  )

  return (
    <span className="text-sm font-bold text-white">
      {totalUsdt > 0 ? `$${totalUsdt.toLocaleString(undefined, {maximumFractionDigits: 2})}` : 'No balance'}
    </span>
  )
}

function TradeHistory({ api }) {
  const { data, isLoading } = useQuery({
    queryKey: ['trade-history'],
    queryFn: () => api.get('/intelligence/analytics/trades').then(r => r.data).catch(() => ({ trades: [] })),
    staleTime: 60000,
  })

  const trades = data?.trades || []

  if (isLoading) return (
    <div className="animate-pulse space-y-2">
      {[1,2,3].map(i => <div key={i} className="h-8 bg-gray-800 rounded"/>)}
    </div>
  )

  if (trades.length === 0) return (
    <Empty message="No trade history yet" sub="Executed trades will appear here"/>
  )

  const dailyPnl = Object.entries(
    trades.reduce((acc, t) => {
      const day = (t.closed_at || t.created_at || '').slice(0,10)
      if (day) acc[day] = (acc[day] || 0) + (t.pnl || 0)
      return acc
    }, {})
  ).slice(-20).map(([d, pnl]) => ({ d: d.slice(5), pnl }))

  return (
    <div className="space-y-4">
      {dailyPnl.length > 0 && (
        <div>
          <h3 className="text-xs text-gray-500 mb-2">Daily P&L (last 20 days)</h3>
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={dailyPnl}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b"/>
              <XAxis dataKey="d" tick={{fill:'#64748b',fontSize:9}}/>
              <YAxis tick={{fill:'#64748b',fontSize:9}} tickFormatter={v=>`$${v.toFixed(0)}`}/>
              <Tooltip formatter={v=>`$${parseFloat(v).toFixed(2)}`}
                contentStyle={{background:'#1e293b',border:'1px solid #334155',borderRadius:'8px',color:'#f1f5f9'}}/>
              <Bar dataKey="pnl" radius={[2,2,0,0]}>
                {dailyPnl.map((e,i) => (
                  <Cell key={i} fill={e.pnl >= 0 ? '#10B981' : '#EF4444'}/>
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      <table className="w-full min-w-[500px] text-xs">
        <thead><tr className="text-gray-500 border-b border-gray-800">
          {['Symbol','Exchange','Side','Strategy','P&L','Status','Closed'].map(h => (
            <th key={h} className="pb-2 text-left font-medium pr-3">{h}</th>
          ))}
        </tr></thead>
        <tbody>
          {trades.slice(0, 30).map((t, i) => (
            <tr key={i} className="border-b border-gray-800/30 hover:bg-gray-800/20">
              <td className="py-2 pr-3 font-medium text-white">{t.symbol}</td>
              <td className="py-2 pr-3 text-gray-500 capitalize">{t.exchange || '—'}</td>
              <td className="py-2 pr-3">
                <span className={clsx('px-1.5 py-0.5 rounded text-xs font-bold',
                  t.direction === 'long' ? 'bg-emerald-900/40 text-emerald-400' : 'bg-red-900/40 text-red-400')}>
                  {t.direction?.toUpperCase() || '—'}
                </span>
              </td>
              <td className="py-2 pr-3 text-gray-400 capitalize">{t.strategy || '—'}</td>
              <td className={clsx('py-2 pr-3 font-semibold',
                (t.pnl || 0) >= 0 ? 'text-emerald-400' : 'text-red-400')}>
                {t.pnl != null ? `${t.pnl >= 0 ? '+' : ''}$${parseFloat(t.pnl).toFixed(2)}` : '—'}
              </td>
              <td className="py-2 pr-3">
                <span className={clsx('px-1.5 py-0.5 rounded-full text-xs',
                  t.status === 'closed' ? 'bg-gray-800 text-gray-400' : 'bg-blue-900/30 text-blue-400')}>
                  {t.status || 'open'}
                </span>
              </td>
              <td className="py-2 text-gray-600">{t.closed_at ? t.closed_at.slice(0,10) : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function PortfolioPage() {
  const { apiClient } = useAuth()
  const api = apiClient()

  const { data: tokenData, isLoading: tokLoading } = useQuery({
    queryKey: ['token-status'],
    queryFn: () => api.get('/tokens/status').then(r => r.data).catch(() => ({ tokens: {} })),
    refetchInterval: 60000,
  })

  const tokens = tokenData?.tokens || {}
  const connected = Object.entries(tokens)
  const cryptoExchanges = connected.filter(([ex]) => ['delta','binance'].includes(ex))

  // Allocation from actual tokens + positions (dynamic)
  const allocationColors = ['#F7931A','#F3BA2F','#E53935','#387ED1','#10B981','#6B7280']
  const allocationData = cryptoExchanges.map(([ex], i) => ({
    name: ex.charAt(0).toUpperCase() + ex.slice(1),
    value: Math.round(100 / Math.max(cryptoExchanges.length, 1)),
    color: allocationColors[i],
  }))

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-white">Portfolio</h1>
        <p className="text-sm text-gray-400">Real positions and balances from connected exchanges</p>
      </div>

      {/* Exchange balances */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {tokLoading ? (
          [1,2].map(i => <div key={i} className="card animate-pulse h-16"/>)
        ) : connected.length === 0 ? (
          <div className="col-span-4 card border-dashed border-amber-500/30 bg-amber-900/10">
            <div className="flex items-center gap-2 text-amber-400">
              <AlertCircle size={16}/>
              <span className="text-sm">No exchanges connected. Go to Tokens to connect.</span>
            </div>
          </div>
        ) : (
          connected.map(([ex, t]) => (
            <div key={ex} className="card">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-medium text-gray-400 capitalize">{ex}</span>
                <LiveBadge live={!t.paper_trading}/>
              </div>
              <div className="flex items-center gap-1">
                <span className="text-xs text-gray-500">Balance:</span>
                {['delta','binance'].includes(ex) ? (
                  <ExchangeBalance exchange={ex} api={api}/>
                ) : (
                  <span className="text-xs text-gray-500">See broker app</span>
                )}
              </div>
            </div>
          ))
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Allocation pie */}
        <div className="card">
          <h2 className="section-title">Connected Exchanges</h2>
          {allocationData.length === 0 ? (
            <Empty message="Connect exchanges to see allocation"/>
          ) : (
            <>
              <ResponsiveContainer width="100%" height={180}>
                <PieChart>
                  <Pie data={allocationData} cx="50%" cy="50%" innerRadius={50} outerRadius={75} dataKey="value">
                    {allocationData.map((e,i) => <Cell key={i} fill={e.color}/>)}
                  </Pie>
                  <Tooltip formatter={v=>`${v}%`}
                    contentStyle={{background:'#1e293b',border:'1px solid #334155',borderRadius:'8px',color:'#f1f5f9'}}/>
                </PieChart>
              </ResponsiveContainer>
              <div className="space-y-1 mt-2">
                {allocationData.map(a => (
                  <div key={a.name} className="flex items-center gap-2 text-xs">
                    <span className="w-2 h-2 rounded-full" style={{background: a.color}}/>
                    <span className="text-gray-400">{a.name}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>

        {/* Trade history chart */}
        <div className="lg:col-span-2 card">
          <h2 className="section-title mb-3">Trade History & P&L</h2>
          <TradeHistory api={api}/>
        </div>
      </div>

      {/* Live positions per exchange */}
      {cryptoExchanges.length > 0 && (
        <div className="card">
          <h2 className="section-title mb-4">Open Positions (from exchange)</h2>
          <div className="space-y-6">
            {cryptoExchanges.map(([ex, t]) => (
              <div key={ex}>
                <div className="flex items-center gap-2 mb-3">
                  <span className="text-sm font-medium text-white capitalize">{ex}</span>
                  <LiveBadge live={!t.paper_trading}/>
                  {t.paper_trading && (
                    <span className="text-xs text-gray-500">· Paper mode: positions not tracked</span>
                  )}
                </div>
                {t.paper_trading ? (
                  <p className="text-xs text-gray-600 italic">
                    Switch to live mode to track real positions. Paper mode does not place real orders.
                  </p>
                ) : (
                  <ExchangePositions exchange={ex} api={api} isLive={!t.paper_trading}/>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default PortfolioPage
