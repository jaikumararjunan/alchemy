import { useQuery } from '@tanstack/react-query'
import { useAuth } from '@/context/AuthContext'
import { useAlchemyStore } from '@/store'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import { TrendingUp, TrendingDown, Zap, ShieldCheck, Activity, Bitcoin, RefreshCw, AlertCircle } from 'lucide-react'
import clsx from 'clsx'

function StatCard({ label, value, sub, trend, icon: Icon, color = 'blue', loading }) {
  const palette = {
    blue:  { bg:'from-blue-500/10 to-blue-600/5', border:'border-blue-500/20', icon:'text-blue-400', glow:'shadow-blue-500/10' },
    green: { bg:'from-emerald-500/10 to-emerald-600/5', border:'border-emerald-500/20', icon:'text-emerald-400', glow:'shadow-emerald-500/10' },
    red:   { bg:'from-rose-500/10 to-rose-600/5', border:'border-rose-500/20', icon:'text-rose-400', glow:'shadow-rose-500/10' },
    amber: { bg:'from-amber-500/10 to-amber-600/5', border:'border-amber-500/20', icon:'text-amber-400', glow:'shadow-amber-500/10' },
  }
  const p = palette[color]
  return (
    <div className={clsx('rounded-2xl p-4 bg-gradient-to-br border transition-all duration-300 hover:shadow-lg', p.bg, p.border, p.glow)}
      style={{background:'var(--surface-2)', borderColor:'var(--border)'}}>
      <div className="flex items-start justify-between">
        <div className="space-y-1">
          <p className="text-[11px] font-semibold text-gray-500 uppercase tracking-wider">{label}</p>
          <p className="text-2xl font-display font-bold text-white tracking-tight">
            {loading ? <span className="skeleton inline-block w-20 h-7" /> : value}
          </p>
          {sub && !loading && (
            <p className={clsx('text-xs font-medium', trend >= 0 ? 'text-emerald-400' : 'text-rose-400')}>{sub}</p>
          )}
        </div>
        {Icon && (
          <div className={clsx('p-2.5 rounded-xl', `bg-gradient-to-br ${p.bg}`)}>
            <Icon size={18} className={p.icon} />
          </div>
        )}
      </div>
    </div>
  )
}

function fmt(n) {
  if (n == null) return '—'
  if (Math.abs(n) >= 1e7) return `₹${(n/1e7).toFixed(2)}Cr`
  if (Math.abs(n) >= 1e5) return `₹${(n/1e5).toFixed(2)}L`
  return `₹${n.toFixed(0)}`
}

export default function DashboardPage() {
  const { apiClient } = useAuth()
  const api = apiClient()
  const signals = useAlchemyStore(s => s.signals)
  const connected = useAlchemyStore(s => s.connected)

  const { data: health, isLoading: hl } = useQuery({
    queryKey: ['health'],
    queryFn: () => api.get('/health').then(r => r.data),
    refetchInterval: 30000,
  })

  const { data: risk, isLoading: rl } = useQuery({
    queryKey: ['risk'],
    queryFn: () => api.get('/risk/status').then(r => r.data).catch(() => null),
    refetchInterval: 10000,
  })

  const { data: btcData } = useQuery({
    queryKey: ['btc-price'],
    queryFn: () => api.get('/crypto/market/btc-price').then(r => r.data).catch(() => null),
    refetchInterval: 15000,
  })

  const { data: tokenData } = useQuery({
    queryKey: ['token-status'],
    queryFn: () => api.get('/tokens/status').then(r => r.data).catch(() => ({ tokens: {} })),
    refetchInterval: 60000,
  })

  const tokens = tokenData?.tokens || {}
  const connectedExchanges = Object.values(tokens).filter(t => t?.status === 'active' || t?.status === 'paper').length
  const recentSignals = signals.slice(0, 5)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-display font-bold text-white tracking-tight">Dashboard</h1>
          <p className="text-sm text-gray-500">
            Real-time overview
            <span className={clsx('ml-2 inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full',
              connected ? 'bg-emerald-900/30 text-emerald-400' : 'bg-gray-800 text-gray-500')}>
              <span className={clsx('w-1.5 h-1.5 rounded-full', connected ? 'bg-emerald-400 animate-pulse' : 'bg-gray-600')}/>
              {connected ? 'Live' : 'Offline'}
            </span>
          </p>
        </div>
        {btcData?.price && (
          <div className="card px-4 py-2 flex items-center gap-2">
            <Bitcoin size={14} className="text-orange-400"/>
            <span className="text-white font-bold text-sm">${Number(btcData.price).toLocaleString()}</span>
            <span className="text-xs text-gray-500">BTC</span>
          </div>
        )}
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 stagger-children">
        <StatCard
          label="Exchanges Connected"
          value={connectedExchanges}
          sub={connectedExchanges === 0 ? 'Go to Tokens to connect' : `${connectedExchanges} active`}
          trend={connectedExchanges} icon={ShieldCheck} color={connectedExchanges > 0 ? 'green' : 'amber'}
        />
        <StatCard label="AI Signals" value={signals.length}
          sub={recentSignals.length > 0 ? `Latest: ${recentSignals[0]?.signal || '—'}` : 'No signals yet'}
          trend={1} icon={Zap} color="blue" />
        <StatCard label="System Status"
          value={health?.status === 'ok' ? 'Healthy' : 'Checking...'}
          sub={`v${health?.version || '—'}`} trend={1}
          icon={Activity} color="green" loading={hl} />
        <StatCard label="Risk Status"
          value={risk?.emergency_stop ? 'STOPPED' : 'Normal'}
          sub={risk?.emergency_stop ? 'Emergency stop active' : 'No risk alerts'}
          trend={risk?.emergency_stop ? -1 : 1}
          icon={risk?.emergency_stop ? TrendingDown : TrendingUp}
          color={risk?.emergency_stop ? 'red' : 'green'} loading={rl} />
      </div>

      {/* Exchange status */}
      {connectedExchanges === 0 && (
        <div className="card border-dashed border-amber-500/30 bg-amber-900/10">
          <div className="flex items-start gap-3">
            <AlertCircle size={18} className="text-amber-400 flex-shrink-0 mt-0.5"/>
            <div>
              <p className="text-sm font-medium text-amber-300">No exchanges connected</p>
              <p className="text-xs text-gray-400 mt-1">
                Go to <strong>Tokens</strong> in the sidebar to connect Delta Exchange, Binance, Angel Broking, or Zerodha Kite.
                Start with paper/testnet mode — no real money needed.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Connected exchanges */}
      {connectedExchanges > 0 && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 stagger-children">
          {Object.entries(tokens).map(([ex, t]) => (
            <div key={ex} className="card py-3 text-center">
              <div className="text-xs text-gray-500 mb-1 capitalize">{ex}</div>
              <div className={clsx('text-xs font-medium px-2 py-0.5 rounded-full inline-flex items-center gap-1',
                t.status === 'active' ? 'text-emerald-400 bg-emerald-900/30' : 'text-blue-400 bg-blue-900/30')}>
                <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse"/>
                {t.status === 'active' ? 'Live' : 'Paper'}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Recent signals */}
      <div className="card">
        <h2 className="text-base font-display font-semibold text-gray-200 mb-3 tracking-tight">Recent AI Signals</h2>
        {recentSignals.length === 0 ? (
          <div className="text-center py-8 text-gray-500">
            <Zap size={24} className="mx-auto mb-2 opacity-30"/>
            <p className="text-sm">No signals yet. Signals appear here in real-time via WebSocket.</p>
          </div>
        ) : (
          <div className="divide-y divide-gray-800">
            {recentSignals.map((s, i) => (
              <div key={i} className="py-2.5 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className={clsx('text-xs font-bold px-2 py-0.5 rounded',
                    s.signal === 'BUY' ? 'bg-emerald-900/40 text-emerald-400' : 'bg-red-900/40 text-red-400')}>
                    {s.signal}
                  </span>
                  <span className="text-sm text-white">{s.ticker}</span>
                </div>
                <span className="text-xs text-gray-500">{new Date(s.ts || Date.now()).toLocaleTimeString()}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
