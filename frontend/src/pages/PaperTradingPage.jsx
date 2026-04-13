import { useState, useEffect, useCallback, useMemo } from 'react'
import { useAuth } from '@/context/AuthContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Wallet, TrendingUp, TrendingDown, BarChart3, Target, Trophy, RefreshCw,
  ArrowUpCircle, ArrowDownCircle, X, Play, RotateCcw, Clock, Zap,
  PieChart, DollarSign, Activity, Percent, AlertTriangle, ChevronDown,
  Shield, Flame, Award, LineChart, WifiOff
} from 'lucide-react'
import clsx from 'clsx'
import { useAlchemyStore } from '@/store'
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts'
import toast from 'react-hot-toast'

export default function PaperTradingPage() {
  const { apiClient } = useAuth()
  const api = useMemo(() => apiClient(), [apiClient])
  const qc = useQueryClient()
  const [activeTab, setActiveTab] = useState('trade')

  // ── Data Fetching ──────────────────────────────────────────────────────
  const { data: portfolio, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['paper-portfolio'],
    queryFn: () => api.get('/paper/portfolio').then(r => r.data),
    refetchInterval: 15000,
    retry: 2,
  })

  const { data: trades } = useQuery({
    queryKey: ['paper-trades'],
    queryFn: () => api.get('/paper/trades?limit=100').then(r => r.data),
    retry: 1,
  })

  const { data: leaderboard } = useQuery({
    queryKey: ['paper-leaderboard'],
    queryFn: () => api.get('/paper/leaderboard').then(r => r.data),
    retry: 1,
  })

  const { data: strategies } = useQuery({
    queryKey: ['backtest-strategies'],
    queryFn: () => api.get('/paper/backtest/strategies').then(r => r.data),
    retry: 1,
  })

  const handleRefresh = useCallback(() => {
    toast.loading('Refreshing...', { id: 'refresh' })
    refetch().then(() => {
      qc.invalidateQueries({ queryKey: ['paper-trades'] })
      qc.invalidateQueries({ queryKey: ['paper-leaderboard'] })
      toast.success('Refreshed!', { id: 'refresh' })
    }).catch(() => {
      toast.error('Refresh failed - check connection', { id: 'refresh' })
    })
  }, [refetch, qc])

  const p = portfolio || {}
  const positions = p.positions || {}

  if (isError) {
    const msg = error?.response?.status === 401
      ? 'Session expired. Please log out and log in again.'
      : error?.message || 'Failed to load portfolio'
    return (
      <div className="flex flex-col items-center justify-center py-20">
        <WifiOff className="w-16 h-16 text-red-400 mb-4" />
        <h2 className="text-xl font-bold text-white mb-2">Connection Error</h2>
        <p className="text-gray-400 text-sm mb-4">{msg}</p>
        <button onClick={() => refetch()}
          className="px-6 py-2.5 rounded-lg bg-blue-600 text-white font-medium flex items-center gap-2 hover:bg-blue-500">
          <RefreshCw className="w-4 h-4" /> Retry
        </button>
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-20">
        <RefreshCw className="w-10 h-10 text-blue-400 animate-spin mb-4" />
        <p className="text-gray-400">Loading paper trading dashboard...</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Wallet className="w-7 h-7 text-blue-400" />
            Paper Trading
          </h1>
          <p className="text-gray-400 text-sm mt-1">
            Practice with $100K virtual capital · Risk-free · Real market data
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={handleRefresh}
            className="px-3 py-2 rounded-lg bg-gray-800 text-gray-300 hover:bg-gray-700 text-sm flex items-center gap-1">
            <RefreshCw className="w-4 h-4" /> Refresh
          </button>
        </div>
      </div>

      {/* Portfolio Summary Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">
        <SummaryCard
          label="Portfolio Value"
          value={`$${(p.portfolio_value || 100000).toLocaleString(undefined, {maximumFractionDigits: 0})}`}
          icon={<Wallet className="w-5 h-5" />}
          color="blue"
          sub={<PnL value={p.total_return_pct || 0} suffix="%" />}
        />
        <SummaryCard
          label="Cash Available"
          value={`$${(p.cash_balance || 100000).toLocaleString(undefined, {maximumFractionDigits: 0})}`}
          icon={<DollarSign className="w-5 h-5" />}
          color="cyan"
        />
        <SummaryCard
          label="Unrealized P&L"
          value={<PnL value={p.unrealized_pnl || 0} prefix="$" size="text-xl" />}
          icon={<TrendingUp className="w-5 h-5" />}
          color={p.unrealized_pnl >= 0 ? "green" : "red"}
          sub={`${Object.keys(positions).length} positions`}
        />
        <SummaryCard
          label="Realized P&L"
          value={<PnL value={p.realized_pnl || 0} prefix="$" size="text-xl" />}
          icon={<Activity className="w-5 h-5" />}
          color={p.realized_pnl >= 0 ? "green" : "red"}
          sub={`${p.total_trades || 0} closed`}
        />
        <SummaryCard
          label="Win Rate"
          value={`${p.win_rate || 0}%`}
          icon={<Target className="w-5 h-5" />}
          color={(p.win_rate || 0) >= 50 ? "green" : "yellow"}
          sub={`${p.winning_trades || 0}W / ${p.losing_trades || 0}L`}
        />
        <SummaryCard
          label="Open Positions"
          value={Object.keys(positions).length}
          icon={<BarChart3 className="w-5 h-5" />}
          color="purple"
          sub={`${(p.total_trades || 0) + Object.keys(positions).length} total`}
        />
      </div>

      {/* Equity Curve Mini Chart */}
      <EquityCurveChart api={api} />

      {/* Tab Navigation */}
      <div className="flex gap-1 bg-gray-900/50 p-1 rounded-xl border border-gray-800">
        {[
          { id: 'trade', label: 'Quick Trade', icon: Zap },
          { id: 'positions', label: 'Positions', icon: TrendingUp, badge: Object.keys(positions).length },
          { id: 'backtest', label: 'Backtest', icon: Play },
          { id: 'history', label: 'Trade History', icon: Clock },
          { id: 'capital', label: 'Capital', icon: PieChart },
          { id: 'leaderboard', label: 'Leaderboard', icon: Trophy },
        ].map(tab => (
          <button key={tab.id} onClick={() => setActiveTab(tab.id)}
            className={clsx(
              'flex-1 flex items-center justify-center gap-2 py-2.5 px-3 rounded-lg text-sm font-medium transition-all',
              activeTab === tab.id
                ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/20'
                : 'text-gray-400 hover:text-white hover:bg-gray-800'
            )}>
            <tab.icon className="w-4 h-4" />
            <span className="hidden sm:inline">{tab.label}</span>
            {tab.badge > 0 && (
              <span className="bg-blue-500/30 text-blue-300 text-xs px-1.5 py-0.5 rounded-full">
                {tab.badge}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === 'trade' && <QuickTradePanel api={api} portfolio={p} />}
      {activeTab === 'positions' && <PositionsPanel api={api} positions={positions} />}
      {activeTab === 'backtest' && <BacktestPanel api={api} strategies={strategies} />}
      {activeTab === 'history' && <TradeHistoryPanel trades={trades} />}
      {activeTab === 'capital' && <CapitalPanel api={api} />}
      {activeTab === 'leaderboard' && <LeaderboardPanel data={leaderboard} />}
    </div>
  )
}

// ── Equity Curve Chart ────────────────────────────────────────────────────────
function EquityCurveChart({ api }) {
  const { data: curve } = useQuery({
    queryKey: ['equity-curve'],
    queryFn: () => api.get('/paper/equity-curve?days=7').then(r => r.data),
    refetchInterval: 60000,
    retry: 1,
  })

  const points = curve?.points || []
  if (points.length < 2) return null

  const chartData = points.map(p => ({
    time: new Date(p.ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    value: p.portfolio_value,
    pnl: p.unrealized_pnl + p.realized_pnl,
  }))

  const first = chartData[0]?.value || 100000
  const last = chartData[chartData.length - 1]?.value || 100000
  const isUp = last >= first

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-4">
      <div className="flex justify-between items-center mb-2">
        <span className="text-gray-400 text-xs font-medium">PORTFOLIO EQUITY CURVE (7D)</span>
        <span className={clsx('text-xs font-bold', isUp ? 'text-emerald-400' : 'text-red-400')}>
          {isUp ? '+' : ''}{((last - first) / first * 100).toFixed(2)}%
        </span>
      </div>
      <ResponsiveContainer width="100%" height={120}>
        <AreaChart data={chartData}>
          <defs>
            <linearGradient id="eqGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={isUp ? '#10b981' : '#ef4444'} stopOpacity={0.3}/>
              <stop offset="95%" stopColor={isUp ? '#10b981' : '#ef4444'} stopOpacity={0}/>
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
          <XAxis dataKey="time" tick={{ fontSize: 10, fill: '#6b7280' }} interval="preserveStartEnd" />
          <YAxis domain={['dataMin - 100', 'dataMax + 100']} tick={{ fontSize: 10, fill: '#6b7280' }} width={60}
            tickFormatter={v => `$${(v/1000).toFixed(1)}k`} />
          <Tooltip contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8 }}
            labelStyle={{ color: '#9ca3af' }}
            formatter={(v) => [`$${v.toLocaleString(undefined, {maximumFractionDigits: 0})}`, 'Portfolio']} />
          <Area type="monotone" dataKey="value" stroke={isUp ? '#10b981' : '#ef4444'}
            fill="url(#eqGrad)" strokeWidth={2} dot={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

// ── Summary Card ─────────────────────────────────────────────────────────────
function SummaryCard({ label, value, icon, color, sub }) {
  const colors = {
    blue: 'border-blue-500/30 bg-blue-500/5', green: 'border-emerald-500/30 bg-emerald-500/5',
    red: 'border-red-500/30 bg-red-500/5', yellow: 'border-yellow-500/30 bg-yellow-500/5',
    purple: 'border-purple-500/30 bg-purple-500/5', cyan: 'border-cyan-500/30 bg-cyan-500/5',
  }
  const iconColors = {
    blue: 'text-blue-400', green: 'text-emerald-400', red: 'text-red-400',
    yellow: 'text-yellow-400', purple: 'text-purple-400', cyan: 'text-cyan-400',
  }
  return (
    <div className={clsx('rounded-xl border p-4', colors[color])}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-gray-400 text-xs font-medium">{label}</span>
        <span className={iconColors[color]}>{icon}</span>
      </div>
      <div className="text-xl font-bold text-white tabular-nums">{value}</div>
      {sub && <div className="text-xs text-gray-400 mt-1">{sub}</div>}
    </div>
  )
}

// ── P&L Display ──────────────────────────────────────────────────────────────
function PnL({ value, prefix = '', suffix = '', size = 'text-sm' }) {
  const isPos = value >= 0
  return (
    <span className={clsx(size, 'font-bold tabular-nums', isPos ? 'text-emerald-400' : 'text-red-400')}>
      {prefix}{isPos ? '+' : ''}{typeof value === 'number' ? value.toFixed(2) : value}{suffix}
    </span>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// QUICK TRADE PANEL
// ══════════════════════════════════════════════════════════════════════════════
function QuickTradePanel({ api, portfolio }) {
  const qc = useQueryClient()
  const [symbol, setSymbol] = useState('BTCUSDT')
  const [side, setSide] = useState('buy')
  const [quantity, setQuantity] = useState('')
  const [price, setPrice] = useState('')
  const [stopLoss, setStopLoss] = useState('')
  const [takeProfit, setTakeProfit] = useState('')

  const fetchPrice = async () => {
    try {
      const resp = await fetch(`https://api.binance.com/api/v3/ticker/price?symbol=${symbol}`)
      const d = await resp.json()
      setPrice(d.price)
    } catch { toast.error('Failed to fetch price') }
  }

  useEffect(() => { fetchPrice() }, [symbol])

  const orderMut = useMutation({
    mutationFn: (data) => api.post('/paper/order', data).then(r => r.data),
    onSuccess: (d) => {
      toast.success(d.message)
      qc.invalidateQueries(['paper-portfolio'])
      qc.invalidateQueries(['paper-trades'])
      setQuantity('')
    },
    onError: (e) => {
      const detail = e.response?.data?.detail
      toast.error(typeof detail?.message === 'string' ? detail.message : detail || 'Order failed')
    },
  })

  const [showConfirm, setShowConfirm] = useState(false)

  const handleOrder = () => {
    if (!quantity || !price) return
    setShowConfirm(true)
  }

  const confirmOrder = () => {
    setShowConfirm(false)
    orderMut.mutate({
      symbol, side, quantity: parseFloat(quantity),
      current_price: parseFloat(price), order_type: 'market',
      stop_loss: stopLoss ? parseFloat(stopLoss) : 0,
      take_profit: takeProfit ? parseFloat(takeProfit) : 0,
    })
  }

  const orderValue = quantity && price ? (parseFloat(quantity) * parseFloat(price)) : 0
  const cash = portfolio?.cash_balance || 100000

  return (
    <>
    {/* Trade Confirmation Modal */}
    {showConfirm && (
      <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={() => setShowConfirm(false)}>
        <div className="bg-gray-900 border border-gray-700 rounded-2xl p-6 max-w-md w-full" onClick={e => e.stopPropagation()}>
          <h3 className="text-white font-bold text-lg mb-4">Confirm Trade</h3>
          <div className="space-y-3 mb-6">
            <div className="flex justify-between text-sm">
              <span className="text-gray-400">Symbol</span>
              <span className="text-white font-medium">{symbol}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-gray-400">Side</span>
              <span className={clsx('font-bold', side === 'buy' ? 'text-emerald-400' : 'text-red-400')}>
                {side === 'buy' ? 'BUY / LONG' : 'SELL / SHORT'}
              </span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-gray-400">Quantity</span>
              <span className="text-white">{parseFloat(quantity || 0).toFixed(6)}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-gray-400">Price</span>
              <span className="text-white">${parseFloat(price || 0).toLocaleString()}</span>
            </div>
            <div className="border-t border-gray-700 pt-2 flex justify-between text-sm">
              <span className="text-gray-400 font-medium">Total Value</span>
              <span className="text-white font-bold">${orderValue.toLocaleString(undefined, {maximumFractionDigits: 2})}</span>
            </div>
            {stopLoss > 0 && (
              <div className="flex justify-between text-sm">
                <span className="text-red-400">Stop Loss</span>
                <span className="text-red-400">${parseFloat(stopLoss).toLocaleString()}</span>
              </div>
            )}
            {takeProfit > 0 && (
              <div className="flex justify-between text-sm">
                <span className="text-emerald-400">Take Profit</span>
                <span className="text-emerald-400">${parseFloat(takeProfit).toLocaleString()}</span>
              </div>
            )}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <button onClick={() => setShowConfirm(false)}
              className="py-3 rounded-xl font-medium text-sm border border-gray-600 text-gray-300 hover:bg-gray-800">
              Cancel
            </button>
            <button onClick={confirmOrder}
              className={clsx('py-3 rounded-xl font-bold text-sm text-white',
                side === 'buy' ? 'bg-emerald-600 hover:bg-emerald-500' : 'bg-red-600 hover:bg-red-500')}>
              Confirm {side === 'buy' ? 'BUY' : 'SELL'}
            </button>
          </div>
        </div>
      </div>
    )}
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      {/* Order Form */}
      <div className="lg:col-span-2 rounded-xl border border-gray-800 bg-gray-900/50 p-5">
        <h3 className="text-white font-semibold mb-4 flex items-center gap-2">
          <Zap className="w-5 h-5 text-yellow-400" /> Place Paper Trade
        </h3>

        {/* Symbol */}
        <label className="text-xs text-gray-400 mb-1 block">Symbol</label>
        <div className="flex gap-2 mb-4 flex-wrap">
          {['BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT','XRPUSDT','DOGEUSDT'].map(s => (
            <button key={s} onClick={() => setSymbol(s)}
              className={clsx('px-3 py-1.5 rounded-lg text-xs font-medium border transition-all',
                symbol === s ? 'bg-blue-600 border-blue-500 text-white' : 'border-gray-700 text-gray-400 hover:border-gray-600')}>
              {s.replace('USDT','')}
            </button>
          ))}
        </div>

        {/* Side */}
        <label className="text-xs text-gray-400 mb-1 block">Side</label>
        <div className="grid grid-cols-2 gap-2 mb-4">
          <button onClick={() => setSide('buy')}
            className={clsx('py-3 rounded-xl font-bold text-sm flex items-center justify-center gap-2 border transition-all',
              side === 'buy' ? 'bg-emerald-600/20 border-emerald-500 text-emerald-400' : 'border-gray-700 text-gray-400')}>
            <ArrowUpCircle className="w-5 h-5" /> BUY / LONG
          </button>
          <button onClick={() => setSide('sell')}
            className={clsx('py-3 rounded-xl font-bold text-sm flex items-center justify-center gap-2 border transition-all',
              side === 'sell' ? 'bg-red-600/20 border-red-500 text-red-400' : 'border-gray-700 text-gray-400')}>
            <ArrowDownCircle className="w-5 h-5" /> SELL / SHORT
          </button>
        </div>

        {/* Price + Quantity */}
        <div className="grid grid-cols-2 gap-3 mb-3">
          <div>
            <label className="text-xs text-gray-400 mb-1 block">Price (USD)</label>
            <div className="flex">
              <input value={price} onChange={e => setPrice(e.target.value)} type="number"
                className="flex-1 bg-gray-800 border border-gray-700 rounded-l-lg px-3 py-2.5 text-white text-sm" />
              <button onClick={fetchPrice}
                className="bg-gray-700 border border-l-0 border-gray-700 rounded-r-lg px-3 text-xs text-blue-400 hover:bg-gray-600">
                Live
              </button>
            </div>
          </div>
          <div>
            <label className="text-xs text-gray-400 mb-1 block">Quantity</label>
            <input value={quantity} onChange={e => setQuantity(e.target.value)} type="number"
              placeholder="0.00" className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2.5 text-white text-sm" />
          </div>
        </div>

        {/* Quick Size */}
        <div className="flex gap-1.5 mb-3">
          {[10,25,50,75,100].map(pct => (
            <button key={pct} onClick={() => {
              const px = parseFloat(price) || 1
              setQuantity(((cash * pct / 100) / px).toFixed(6))
            }}
              className="flex-1 py-1.5 rounded-lg text-xs font-medium bg-gray-800 border border-gray-700 text-gray-400 hover:border-blue-500 hover:text-blue-400">
              {pct}%
            </button>
          ))}
        </div>

        {/* SL / TP */}
        <div className="grid grid-cols-2 gap-3 mb-4">
          <div>
            <label className="text-xs text-red-400 mb-1 block">Stop Loss</label>
            <input value={stopLoss} onChange={e => setStopLoss(e.target.value)} type="number"
              placeholder="Optional" className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-red-400 text-sm" />
          </div>
          <div>
            <label className="text-xs text-emerald-400 mb-1 block">Take Profit</label>
            <input value={takeProfit} onChange={e => setTakeProfit(e.target.value)} type="number"
              placeholder="Optional" className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-emerald-400 text-sm" />
          </div>
        </div>

        {/* Order preview */}
        {orderValue > 0 && (
          <div className="bg-gray-800 rounded-lg px-4 py-2.5 mb-4 flex justify-between text-sm">
            <span className="text-gray-400">Order Value</span>
            <span className="text-white font-semibold">${orderValue.toLocaleString(undefined, {maximumFractionDigits: 2})}</span>
          </div>
        )}

        <button onClick={handleOrder} disabled={orderMut.isPending || !quantity || !price}
          className={clsx('w-full py-3.5 rounded-xl font-bold text-sm flex items-center justify-center gap-2 transition-all',
            side === 'buy'
              ? 'bg-emerald-600 hover:bg-emerald-500 text-white disabled:bg-emerald-600/30'
              : 'bg-red-600 hover:bg-red-500 text-white disabled:bg-red-600/30')}>
          {orderMut.isPending ? <RefreshCw className="w-4 h-4 animate-spin" /> :
            side === 'buy' ? <ArrowUpCircle className="w-5 h-5" /> : <ArrowDownCircle className="w-5 h-5" />}
          {side === 'buy' ? 'BUY' : 'SELL'} {symbol.replace('USDT', '')}
        </button>
      </div>

      {/* Market Info Sidebar */}
      <div className="space-y-3">
        <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-4">
          <h4 className="text-gray-400 text-xs font-medium mb-2">LIVE MARKET</h4>
          <div className="text-2xl font-bold text-white tabular-nums">
            ${parseFloat(price || 0).toLocaleString(undefined, {maximumFractionDigits: 2})}
          </div>
          <div className="text-sm text-gray-400 mt-1">{symbol}</div>
        </div>
        <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-4">
          <h4 className="text-gray-400 text-xs font-medium mb-3">QUICK STATS</h4>
          <div className="space-y-2.5">
            <StatRow label="Cash Available" value={`$${(cash).toLocaleString(undefined, {maximumFractionDigits: 0})}`} />
            <StatRow label="Open Positions" value={Object.keys(portfolio?.positions || {}).length} />
            <StatRow label="Unrealized P&L" value={<PnL value={portfolio?.unrealized_pnl || 0} prefix="$" />} />
            <StatRow label="Total Trades" value={portfolio?.total_trades || 0} />
            <StatRow label="Win Rate" value={`${portfolio?.win_rate || 0}%`} />
          </div>
        </div>
      </div>
    </div>
    </>
  )
}

function StatRow({ label, value }) {
  return (
    <div className="flex justify-between">
      <span className="text-gray-500 text-xs">{label}</span>
      <span className="text-gray-300 text-xs font-medium tabular-nums">{value}</span>
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// POSITIONS PANEL
// ══════════════════════════════════════════════════════════════════════════════
function PositionsPanel({ api, positions }) {
  const qc = useQueryClient()
  const storePrices = useAlchemyStore(s => s.livePrices)
  const [polledPrices, setPolledPrices] = useState({})

  // Merge: prefer WebSocket prices from store, fallback to polled
  const livePrices = useMemo(() => {
    const merged = { ...polledPrices }
    Object.entries(storePrices).forEach(([sym, data]) => {
      if (data?.price) merged[sym] = data.price
    })
    return merged
  }, [storePrices, polledPrices])

  // Polling fallback + push to backend every 10s
  useEffect(() => {
    const symbols = Object.keys(positions)
    if (symbols.length === 0) return

    const fetchAndPush = async () => {
      try {
        const prices = {}
        for (const sym of symbols) {
          // Use store price if fresh, else fetch
          if (storePrices[sym]?.price) {
            prices[sym] = storePrices[sym].price
          } else {
            const resp = await fetch(`https://api.binance.com/api/v3/ticker/price?symbol=${sym}`)
            const d = await resp.json()
            prices[sym] = parseFloat(d.price)
          }
        }
        setPolledPrices(prices)
        // Push to backend for SL/TP checks
        await api.post('/paper/update-prices', { prices }).catch(() => {})
        qc.invalidateQueries({ queryKey: ['paper-portfolio'] })
      } catch {}
    }

    fetchAndPush()
    const interval = setInterval(fetchAndPush, 10000)
    return () => clearInterval(interval)
  }, [JSON.stringify(Object.keys(positions))])

  const closeMut = useMutation({
    mutationFn: async ({ symbol }) => {
      const price = livePrices[symbol] || 0
      if (!price) {
        const resp = await fetch(`https://api.binance.com/api/v3/ticker/price?symbol=${symbol}`)
        const d = await resp.json()
        return api.post('/paper/close', { symbol, current_price: parseFloat(d.price) }).then(r => r.data)
      }
      return api.post('/paper/close', { symbol, current_price: price }).then(r => r.data)
    },
    onSuccess: (d) => {
      toast.success(d.message || 'Position closed')
      qc.invalidateQueries({ queryKey: ['paper-portfolio'] })
      qc.invalidateQueries({ queryKey: ['paper-trades'] })
    },
    onError: () => toast.error('Close failed'),
  })

  const entries = Object.entries(positions)
  if (entries.length === 0) {
    return (
      <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-12 text-center">
        <TrendingUp className="w-12 h-12 text-gray-700 mx-auto mb-3" />
        <p className="text-gray-400 font-medium">No open positions</p>
        <p className="text-gray-600 text-sm mt-1">Place a trade to get started</p>
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-gray-800 overflow-hidden">
      <table className="w-full">
        <thead className="bg-gray-800/50">
          <tr className="text-xs text-gray-400">
            <th className="text-left px-4 py-3">Symbol</th>
            <th className="text-left px-4 py-3">Side</th>
            <th className="text-right px-4 py-3">Qty</th>
            <th className="text-right px-4 py-3">Entry</th>
            <th className="text-right px-4 py-3">Current</th>
            <th className="text-right px-4 py-3">P&L</th>
            <th className="text-right px-4 py-3">Return</th>
            <th className="text-center px-4 py-3">Action</th>
          </tr>
        </thead>
        <tbody>
          {entries.map(([sym, pos]) => (
            <tr key={sym} className="border-t border-gray-800 hover:bg-gray-800/30">
              <td className="px-4 py-3 text-white font-semibold text-sm">{sym.replace('USDT','')}/USDT</td>
              <td className="px-4 py-3">
                <span className={clsx('px-2 py-0.5 rounded text-xs font-medium',
                  pos.side === 'long' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-red-500/20 text-red-400')}>
                  {pos.side?.toUpperCase()}
                </span>
              </td>
              <td className="px-4 py-3 text-right text-gray-300 text-sm tabular-nums">{pos.quantity}</td>
              <td className="px-4 py-3 text-right text-gray-300 text-sm tabular-nums">${pos.avg_entry_price?.toLocaleString()}</td>
              <td className="px-4 py-3 text-right text-gray-300 text-sm tabular-nums">${(livePrices[sym] || pos.current_price)?.toLocaleString()}</td>
              <td className="px-4 py-3 text-right"><PnL value={(() => {
                const lp = livePrices[sym] || pos.current_price || 0
                if (pos.side === 'long') return (lp - pos.avg_entry_price) * pos.quantity
                if (pos.side === 'short') return (pos.avg_entry_price - lp) * pos.quantity
                return pos.unrealized_pnl || 0
              })()} prefix="$" /></td>
              <td className="px-4 py-3 text-right"><PnL value={(() => {
                const lp = livePrices[sym] || pos.current_price || 0
                const cost = pos.avg_entry_price * pos.quantity
                if (!cost) return 0
                if (pos.side === 'long') return ((lp - pos.avg_entry_price) / pos.avg_entry_price) * 100
                if (pos.side === 'short') return ((pos.avg_entry_price - lp) / pos.avg_entry_price) * 100
                return pos.unrealized_pct || 0
              })()} suffix="%" /></td>
              <td className="px-4 py-3 text-center">
                <button onClick={() => closeMut.mutate({ symbol: sym })}
                  disabled={closeMut.isPending}
                  className="px-3 py-1 rounded-lg text-xs font-medium bg-red-500/10 text-red-400 border border-red-500/30 hover:bg-red-500/20">
                  Close
                </button>
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot className="bg-gray-800/70 border-t-2 border-gray-700">
          <tr>
            <td colSpan="4" className="px-4 py-3 text-white font-bold text-sm">
              TOTAL ({entries.length} positions)
            </td>
            <td className="px-4 py-3"></td>
            <td className="px-4 py-3 text-right font-bold">
              <PnL value={entries.reduce((sum, [sym, pos]) => {
                const lp = livePrices[sym] || pos.current_price || 0
                if (pos.side === 'long') return sum + (lp - pos.avg_entry_price) * pos.quantity
                if (pos.side === 'short') return sum + (pos.avg_entry_price - lp) * pos.quantity
                return sum + (pos.unrealized_pnl || 0)
              }, 0)} prefix="$" />
            </td>
            <td className="px-4 py-3 text-right font-bold">
              <PnL value={(() => {
                const pcts = entries.map(([sym, pos]) => {
                  const lp = livePrices[sym] || pos.current_price || 0
                  if (pos.side === 'long') return ((lp - pos.avg_entry_price) / pos.avg_entry_price) * 100
                  if (pos.side === 'short') return ((pos.avg_entry_price - lp) / pos.avg_entry_price) * 100
                  return 0
                })
                return pcts.length ? pcts.reduce((a, b) => a + b, 0) / pcts.length : 0
              })()} suffix="%" />
            </td>
            <td></td>
          </tr>
        </tfoot>
      </table>
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// BACKTEST PANEL
// ══════════════════════════════════════════════════════════════════════════════
function BacktestPanel({ api, strategies }) {
  const [config, setConfig] = useState({
    strategy: 'sma_crossover', symbol: 'BTCUSDT', interval: '1h',
    start_date: '2025-06-01', end_date: '2026-04-01',
    initial_capital: 100000, position_size_pct: 10,
    stop_loss_pct: 2, take_profit_pct: 4,
    fast_period: 9, slow_period: 21, rsi_period: 14,
  })
  const [result, setResult] = useState(null)

  const runMut = useMutation({
    mutationFn: (data) => api.post('/paper/backtest/run', data).then(r => r.data),
    onSuccess: (d) => { setResult(d); toast.success('Backtest completed!') },
    onError: (e) => toast.error(e.response?.data?.detail?.message || 'Backtest failed'),
  })

  const perf = result?.performance || {}

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Config */}
        <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-5 space-y-4">
          <h3 className="text-white font-semibold flex items-center gap-2">
            <Play className="w-5 h-5 text-purple-400" /> Configure Backtest
          </h3>

          <div>
            <label className="text-xs text-gray-400 mb-1 block">Strategy</label>
            <select value={config.strategy} onChange={e => setConfig({...config, strategy: e.target.value})}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm">
              {Object.entries(strategies?.strategies || {}).map(([k, v]) => (
                <option key={k} value={k}>{v.name}</option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Symbol</label>
              <select value={config.symbol} onChange={e => setConfig({...config, symbol: e.target.value})}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm">
                {['BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT','XRPUSDT'].map(s => (
                  <option key={s} value={s}>{s.replace('USDT','')}/USDT</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Interval</label>
              <select value={config.interval} onChange={e => setConfig({...config, interval: e.target.value})}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm">
                {['1h','4h','1d'].map(i => <option key={i} value={i}>{i}</option>)}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Start Date</label>
              <input value={config.start_date} onChange={e => setConfig({...config, start_date: e.target.value})}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm" />
            </div>
            <div>
              <label className="text-xs text-gray-400 mb-1 block">End Date</label>
              <input value={config.end_date} onChange={e => setConfig({...config, end_date: e.target.value})}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm" />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2">
            {[['stop_loss_pct','SL %','text-red-400'],['take_profit_pct','TP %','text-emerald-400'],
              ['fast_period','Fast MA','text-cyan-400'],['slow_period','Slow MA','text-yellow-400']].map(([k,l,c]) => (
              <div key={k}>
                <label className={`text-xs ${c} mb-1 block`}>{l}</label>
                <input value={config[k]} onChange={e => setConfig({...config, [k]: e.target.value})}
                  type="number" className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm" />
              </div>
            ))}
          </div>

          <button onClick={() => runMut.mutate(config)} disabled={runMut.isPending}
            className="w-full py-3 rounded-xl font-bold text-sm bg-purple-600 hover:bg-purple-500 text-white flex items-center justify-center gap-2">
            {runMut.isPending ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Play className="w-5 h-5" />}
            {runMut.isPending ? 'Running...' : 'Run Backtest'}
          </button>
        </div>

        {/* Results */}
        <div className="lg:col-span-2 space-y-3">
          {result ? (
            <>
              <div className={clsx('rounded-xl border p-5',
                perf.total_return_pct >= 0 ? 'border-emerald-500/30 bg-emerald-500/5' : 'border-red-500/30 bg-red-500/5')}>
                <p className="text-gray-400 text-xs mb-1">Total Return</p>
                <PnL value={perf.total_return_pct} suffix="%" size="text-4xl" />
                <div className="mt-1"><PnL value={perf.total_pnl} prefix="$" /></div>
              </div>

              <div className="grid grid-cols-3 gap-2">
                {[
                  ['Trades', perf.total_trades, 'text-blue-400'],
                  ['Win Rate', `${perf.win_rate}%`, perf.win_rate >= 50 ? 'text-emerald-400' : 'text-red-400'],
                  ['Sharpe', perf.sharpe_ratio, perf.sharpe_ratio >= 1 ? 'text-emerald-400' : 'text-yellow-400'],
                  ['Max DD', `${perf.max_drawdown_pct}%`, 'text-red-400'],
                  ['Profit Factor', perf.profit_factor, 'text-cyan-400'],
                  ['Fees', `$${perf.total_fees?.toFixed(0)}`, 'text-gray-400'],
                ].map(([l,v,c]) => (
                  <div key={l} className="rounded-lg border border-gray-800 bg-gray-900/50 p-3 text-center">
                    <div className={`text-lg font-bold ${c} tabular-nums`}>{v}</div>
                    <div className="text-xs text-gray-500 mt-0.5">{l}</div>
                  </div>
                ))}
              </div>

              {/* Trade list */}
              <div className="rounded-xl border border-gray-800 overflow-hidden max-h-64 overflow-y-auto">
                <table className="w-full text-xs">
                  <thead className="bg-gray-800/50 sticky top-0">
                    <tr className="text-gray-400">
                      <th className="text-left px-3 py-2">Entry</th>
                      <th className="text-right px-3 py-2">Price</th>
                      <th className="text-right px-3 py-2">Exit</th>
                      <th className="text-right px-3 py-2">P&L</th>
                      <th className="text-right px-3 py-2">Return</th>
                      <th className="text-right px-3 py-2">Reason</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(result.trades || []).slice(-15).reverse().map((t, i) => (
                      <tr key={i} className="border-t border-gray-800/50">
                        <td className="px-3 py-1.5 text-gray-400">{t.entry_date?.split('T')[0]}</td>
                        <td className="px-3 py-1.5 text-right text-gray-300 tabular-nums">${t.entry_price}</td>
                        <td className="px-3 py-1.5 text-right text-gray-300 tabular-nums">${t.exit_price}</td>
                        <td className="px-3 py-1.5 text-right"><PnL value={t.net_pnl} prefix="$" /></td>
                        <td className="px-3 py-1.5 text-right"><PnL value={t.return_pct} suffix="%" /></td>
                        <td className="px-3 py-1.5 text-right text-gray-500">{t.exit_reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-16 text-center">
              <LineChart className="w-16 h-16 text-gray-700 mx-auto mb-4" />
              <p className="text-gray-400 font-medium">Configure and run a backtest</p>
              <p className="text-gray-600 text-sm mt-1">Test strategies against real historical data</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// TRADE HISTORY
// ══════════════════════════════════════════════════════════════════════════════
function TradeHistoryPanel({ trades }) {
  const list = trades?.trades || []
  return (
    <div className="rounded-xl border border-gray-800 overflow-hidden">
      <div className="bg-gray-800/50 px-4 py-3 flex justify-between items-center">
        <span className="text-white font-medium text-sm">Trade History ({trades?.total || 0})</span>
        <span className="text-sm">Realized P&L: <PnL value={trades?.realized_pnl || 0} prefix="$" /></span>
      </div>
      {list.length === 0 ? (
        <div className="p-12 text-center text-gray-500">No trades yet</div>
      ) : (
        <table className="w-full text-xs">
          <thead className="bg-gray-800/30"><tr className="text-gray-400">
            <th className="text-left px-4 py-2">Symbol</th>
            <th className="text-left px-4 py-2">Side</th>
            <th className="text-right px-4 py-2">Entry</th>
            <th className="text-right px-4 py-2">Exit</th>
            <th className="text-right px-4 py-2">Qty</th>
            <th className="text-right px-4 py-2">Net P&L</th>
            <th className="text-right px-4 py-2">Return</th>
            <th className="text-right px-4 py-2">Strategy</th>
          </tr></thead>
          <tbody>
            {list.slice().reverse().map((t, i) => (
              <tr key={i} className="border-t border-gray-800/50 hover:bg-gray-800/20">
                <td className="px-4 py-2 text-white font-medium">{t.symbol}</td>
                <td className="px-4 py-2">
                  <span className={clsx('px-1.5 py-0.5 rounded text-xs',
                    t.side?.includes('long') || t.side === 'buy' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-red-500/20 text-red-400')}>
                    {t.side}
                  </span>
                </td>
                <td className="px-4 py-2 text-right text-gray-300 tabular-nums">${t.entry_price}</td>
                <td className="px-4 py-2 text-right text-gray-300 tabular-nums">${t.exit_price}</td>
                <td className="px-4 py-2 text-right text-gray-400 tabular-nums">{t.quantity}</td>
                <td className="px-4 py-2 text-right"><PnL value={t.net_pnl} prefix="$" /></td>
                <td className="px-4 py-2 text-right"><PnL value={t.return_pct} suffix="%" /></td>
                <td className="px-4 py-2 text-right text-gray-500">{t.strategy || 'manual'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// CAPITAL ALLOCATION
// ══════════════════════════════════════════════════════════════════════════════
function CapitalPanel({ api }) {
  const { data: portfolio } = useQuery({
    queryKey: ['paper-portfolio'],
    queryFn: () => api.get('/paper/portfolio').then(r => r.data),
  })

  const { data: fund } = useQuery({
    queryKey: ['capital-fund'],
    queryFn: () => api.get('/capital/fund').then(r => r.data),
    retry: 1,
  })

  const qc = useQueryClient()
  const templateMut = useMutation({
    mutationFn: (t) => api.post('/capital/fund/template', { template: t, total_capital: portfolio?.portfolio_value || 100000 }).then(r => r.data),
    onSuccess: (d) => {
      toast.success(d.message || 'Template applied!')
      qc.invalidateQueries({ queryKey: ['capital-fund'] })
    },
    onError: () => toast.error('Failed to apply template'),
  })

  const p = portfolio || {}
  const positions = p.positions || {}
  const posEntries = Object.entries(positions)
  const totalValue = p.portfolio_value || 100000
  const cashPct = totalValue > 0 ? (p.cash_balance / totalValue * 100) : 100
  const investedValue = totalValue - (p.cash_balance || 0)

  const f = fund || {}
  const tree = f.allocation_tree || []

  return (
    <div className="space-y-4">
      {/* Portfolio Capital Summary */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <SummaryCard label="Total Capital" value={`$${totalValue.toLocaleString(undefined, {maximumFractionDigits: 0})}`} icon={<PieChart className="w-5 h-5" />} color="blue" />
        <SummaryCard label="Cash" value={`$${(p.cash_balance||0).toLocaleString(undefined, {maximumFractionDigits: 0})}`} icon={<DollarSign className="w-5 h-5" />} color="cyan" sub={`${cashPct.toFixed(1)}%`} />
        <SummaryCard label="Invested" value={`$${investedValue.toLocaleString(undefined, {maximumFractionDigits: 0})}`} icon={<Target className="w-5 h-5" />} color="green" sub={`${(100-cashPct).toFixed(1)}%`} />
        <SummaryCard label="Unrealized P&L" value={<PnL value={p.unrealized_pnl||0} prefix="$" size="text-xl" />} icon={<Activity className="w-5 h-5" />} color={p.unrealized_pnl>=0?"green":"red"} />
        <SummaryCard label="Realized P&L" value={<PnL value={p.realized_pnl||0} prefix="$" size="text-xl" />} icon={<TrendingUp className="w-5 h-5" />} color={p.realized_pnl>=0?"green":"red"} />
      </div>

      {/* Position Allocations */}
      {posEntries.length > 0 && (
        <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-5">
          <h3 className="text-white font-semibold mb-3">Current Position Allocation</h3>
          <div className="space-y-2">
            {/* Cash */}
            <div className="rounded-lg border border-gray-700 bg-gray-800 p-3">
              <div className="flex justify-between items-center mb-1">
                <span className="text-gray-300 font-medium text-sm">💵 Cash Reserve</span>
                <div className="flex items-center gap-3">
                  <span className="text-gray-400 text-sm">{cashPct.toFixed(1)}%</span>
                  <span className="text-white font-semibold text-sm tabular-nums">${(p.cash_balance||0).toLocaleString(undefined, {maximumFractionDigits: 0})}</span>
                </div>
              </div>
              <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden">
                <div className="h-full bg-cyan-500 rounded-full" style={{width: `${cashPct}%`}} />
              </div>
            </div>
            {/* Positions */}
            {posEntries.map(([sym, pos]) => {
              const posValue = (pos.current_price || pos.avg_entry_price) * pos.quantity
              const pct = totalValue > 0 ? (posValue / totalValue * 100) : 0
              const isShort = pos.side === 'short'
              return (
                <div key={sym} className="rounded-lg border border-gray-700 bg-gray-800 p-3">
                  <div className="flex justify-between items-center mb-1">
                    <span className="text-gray-300 font-medium text-sm">
                      {isShort ? '🔴' : '🟢'} {sym.replace('USDT','')}/USDT
                      <span className={clsx('ml-2 text-xs px-1.5 py-0.5 rounded',
                        isShort ? 'bg-red-500/20 text-red-400' : 'bg-emerald-500/20 text-emerald-400')}>
                        {pos.side?.toUpperCase()}
                      </span>
                    </span>
                    <div className="flex items-center gap-3">
                      <span className="text-gray-400 text-sm">{pct.toFixed(1)}%</span>
                      <span className="text-white font-semibold text-sm tabular-nums">${posValue.toLocaleString(undefined, {maximumFractionDigits: 0})}</span>
                      <PnL value={pos.unrealized_pnl || 0} prefix="$" />
                    </div>
                  </div>
                  <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden">
                    <div className={clsx('h-full rounded-full', isShort ? 'bg-red-500' : 'bg-emerald-500')} style={{width: `${Math.min(pct, 100)}%`}} />
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Strategy Templates */}
      <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-5">
        <h3 className="text-white font-semibold mb-3">{tree.length > 0 ? 'Strategy Buckets' : 'Quick Start — Choose a Template'}</h3>
        {tree.length === 0 ? (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {[
              ['conservative', 'Conservative', 'Capital preservation, 20% cash', Shield, 'text-green-400'],
              ['balanced', 'Balanced', 'Mix of trend + mean reversion', BarChart3, 'text-blue-400'],
              ['aggressive', 'Aggressive', 'Multiple momentum strategies', Flame, 'text-orange-400'],
              ['crypto_diversified', 'Crypto Diversified', 'BTC 40% + ETH 25% + Alts 20%', PieChart, 'text-purple-400'],
            ].map(([key, name, desc, Icon, clr]) => (
              <button key={key} onClick={() => templateMut.mutate(key)}
                disabled={templateMut.isPending}
                className="rounded-xl border border-gray-700 bg-gray-800 p-4 text-left hover:border-blue-500/50 transition-all">
                <Icon className={`w-6 h-6 ${clr} mb-2`} />
                <div className="text-white font-semibold text-sm">{name}</div>
                <div className="text-gray-500 text-xs mt-1">{desc}</div>
              </button>
            ))}
          </div>
        ) : (
          <div className="space-y-2">
            {tree.map(bucket => (
              <div key={bucket.id} className="rounded-lg border border-gray-700 bg-gray-800 p-4">
                <div className="flex justify-between items-center">
                  <div>
                    <span className="text-white font-medium">{bucket.name}</span>
                    <span className="text-gray-500 text-xs ml-2">{bucket.strategy}</span>
                  </div>
                  <div className="flex items-center gap-4">
                    <span className="text-gray-400 text-sm">{bucket.allocation_pct}%</span>
                    <span className="text-white font-semibold text-sm tabular-nums">${bucket.allocated_capital?.toLocaleString()}</span>
                    <PnL value={bucket.return_pct || 0} suffix="%" />
                  </div>
                </div>
                <div className="mt-2 h-1.5 bg-gray-700 rounded-full overflow-hidden">
                  <div className="h-full bg-blue-500 rounded-full" style={{width: `${bucket.allocation_pct}%`}} />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════════════════
// LEADERBOARD
// ══════════════════════════════════════════════════════════════════════════════
function LeaderboardPanel({ data }) {
  const list = Array.isArray(data) ? data : []
  const medals = ['🥇','🥈','🥉']
  return (
    <div className="rounded-xl border border-gray-800 overflow-hidden">
      <div className="bg-gray-800/50 px-4 py-3">
        <span className="text-white font-medium text-sm flex items-center gap-2">
          <Trophy className="w-4 h-4 text-yellow-400" /> Paper Trading Leaderboard
        </span>
      </div>
      {list.length === 0 ? (
        <div className="p-12 text-center text-gray-500">No traders yet. Be the first!</div>
      ) : (
        <table className="w-full text-sm">
          <thead className="bg-gray-800/30"><tr className="text-xs text-gray-400">
            <th className="text-left px-4 py-2">Rank</th>
            <th className="text-left px-4 py-2">Trader</th>
            <th className="text-right px-4 py-2">Portfolio</th>
            <th className="text-right px-4 py-2">Return</th>
            <th className="text-right px-4 py-2">P&L</th>
            <th className="text-right px-4 py-2">Trades</th>
            <th className="text-right px-4 py-2">Win Rate</th>
          </tr></thead>
          <tbody>
            {list.map((u, i) => (
              <tr key={i} className="border-t border-gray-800/50 hover:bg-gray-800/20">
                <td className="px-4 py-2.5 text-center">{i < 3 ? medals[i] : `#${i+1}`}</td>
                <td className="px-4 py-2.5 text-white font-medium">{u.user_id?.slice(0,8)}***</td>
                <td className="px-4 py-2.5 text-right text-gray-300 tabular-nums">${u.portfolio_value?.toLocaleString()}</td>
                <td className="px-4 py-2.5 text-right"><PnL value={u.total_return_pct} suffix="%" /></td>
                <td className="px-4 py-2.5 text-right"><PnL value={u.realized_pnl} prefix="$" /></td>
                <td className="px-4 py-2.5 text-right text-gray-400 tabular-nums">{u.total_trades}</td>
                <td className="px-4 py-2.5 text-right text-gray-400 tabular-nums">{u.win_rate}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
