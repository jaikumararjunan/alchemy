import { useQuery } from '@tanstack/react-query'
import { getHealth, getRiskStatus, getPortfolioNAV } from '@/api/client'
import { useAlchemyStore } from '@/store'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import { TrendingUp, TrendingDown, Zap, ShieldCheck, Activity, Bitcoin } from 'lucide-react'
import clsx from 'clsx'

function StatCard({ label, value, sub, trend, icon: Icon, color = 'blue' }) {
  const colors = {
    blue:  'from-blue-600/20 to-blue-600/5 border-blue-500/30 text-blue-400',
    green: 'from-emerald-600/20 to-emerald-600/5 border-emerald-500/30 text-emerald-400',
    red:   'from-red-600/20 to-red-600/5 border-red-500/30 text-red-400',
    amber: 'from-amber-600/20 to-amber-600/5 border-amber-500/30 text-amber-400',
  }
  return (
    <div className={clsx('card bg-gradient-to-br', colors[color])}>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs text-gray-400 mb-1">{label}</p>
          <p className="text-2xl font-bold text-white">{value}</p>
          {sub && <p className={clsx('text-xs mt-1', trend >= 0 ? 'text-emerald-400' : 'text-red-400')}>{sub}</p>}
        </div>
        {Icon && <div className="p-2 bg-gray-800/60 rounded-lg"><Icon size={20} className={colors[color].split(' ')[3]} /></div>}
      </div>
    </div>
  )
}

const MOCK_NAV = Array.from({ length: 30 }, (_, i) => ({
  day: `D${i+1}`,
  nav: 1000000 + Math.sin(i/4) * 30000 + i * 800 + Math.random() * 5000,
  pnl: (Math.random() - 0.4) * 8000,
}))

export default function DashboardPage() {
  const signals  = useAlchemyStore(s => s.signals)
  const { data: health } = useQuery({ queryKey:['health'], queryFn: getHealth, refetchInterval:30000 })
  const { data: risk   } = useQuery({ queryKey:['risk'],   queryFn: getRiskStatus, refetchInterval:10000 })

  const recentSignals = signals.slice(0, 5)

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-white">Dashboard</h1>
        <p className="text-sm text-gray-400">Real-time overview · Alchemy AI Trading Platform</p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Portfolio NAV"    value="₹10.2L"  sub="+₹8,400 today" trend={1}  icon={TrendingUp}  color="green" />
        <StatCard label="Day P&L"          value="+0.84%"  sub="₹8,400"        trend={1}  icon={Activity}    color="blue"  />
        <StatCard label="Open Positions"   value="12"      sub="4 Equity · 3 F&O · 5 Crypto" trend={0} icon={ShieldCheck} color="amber" />
        <StatCard label="AI Signals Today" value={signals.length || 0} sub="3 BUY · 1 SELL" trend={1} icon={Zap} color="blue" />
      </div>

      {/* NAV chart */}
      <div className="card">
        <h2 className="section-title">Portfolio NAV — 30 Days</h2>
        <ResponsiveContainer width="100%" height={220}>
          <AreaChart data={MOCK_NAV}>
            <defs>
              <linearGradient id="navGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor="#2E75B6" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#2E75B6" stopOpacity={0}   />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis dataKey="day" tick={{ fill:'#64748b', fontSize:11 }} />
            <YAxis tickFormatter={v => `₹${(v/100000).toFixed(1)}L`} tick={{ fill:'#64748b', fontSize:11 }} />
            <Tooltip formatter={v => `₹${v.toLocaleString('en-IN')}`} contentStyle={{ background:'#1e293b', border:'1px solid #334155', borderRadius:'8px', color:'#f1f5f9' }} />
            <Area type="monotone" dataKey="nav" stroke="#2E75B6" fill="url(#navGrad)" strokeWidth={2} />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Signals */}
        <div className="card">
          <h2 className="section-title flex items-center gap-2"><Zap size={16} className="text-blue-400" /> Recent AI Signals</h2>
          {recentSignals.length === 0
            ? <p className="text-gray-500 text-sm text-center py-8">No signals yet — run an agent to generate signals</p>
            : <div className="space-y-2">
                {recentSignals.map((s, i) => (
                  <div key={i} className="flex items-center justify-between p-2 bg-gray-800/50 rounded-lg">
                    <div className="flex items-center gap-2">
                      <span className={clsx('text-xs font-bold', s.signal==='BUY'?'badge-buy':s.signal==='SELL'?'badge-sell':'badge-hold')}>{s.signal}</span>
                      <span className="text-sm font-medium text-white">{s.ticker}</span>
                    </div>
                    <div className="text-right">
                      <div className="text-xs text-gray-400">{(s.position_pct*100).toFixed(1)}% · vol {(s.forecast_vol*100).toFixed(0)}%</div>
                      <div className="text-xs text-gray-500">sentiment {(s.sentiment_score).toFixed(2)}</div>
                    </div>
                  </div>
                ))}
              </div>
          }
        </div>

        {/* Crypto Snapshot */}
        <div className="card">
          <h2 className="section-title flex items-center gap-2"><Bitcoin size={16} className="text-amber-400" /> Crypto Snapshot</h2>
          <div className="space-y-2">
            {[
              { s:'BTC-USDT', p:'68,450', ch:'+2.3%', ex:'Binance', pos:'LONG 0.1' },
              { s:'ETH-USDT', p:'3,820',  ch:'-0.8%', ex:'Binance', pos:'FLAT' },
              { s:'BTCUSD',   p:'68,380', ch:'+2.1%', ex:'Delta',   pos:'LONG 1 lot' },
              { s:'ETHUSD',   p:'3,815',  ch:'-0.9%', ex:'Delta',   pos:'SHORT 2 lots' },
            ].map(({ s, p, ch, ex, pos }) => (
              <div key={s} className="flex items-center justify-between p-2 bg-gray-800/50 rounded-lg">
                <div>
                  <span className="text-sm font-medium text-white">{s}</span>
                  <span className="ml-2 text-xs text-gray-500">{ex}</span>
                </div>
                <div className="text-right">
                  <div className="text-sm font-semibold text-white">${p}</div>
                  <div className="flex items-center gap-1 justify-end">
                    <span className={ch.startsWith('+') ? 'stat-up text-xs' : 'stat-down text-xs'}>{ch}</span>
                    <span className="text-xs text-gray-500">· {pos}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Risk status footer */}
      {risk && (
        <div className={clsx('card flex items-center gap-3 p-3', risk.emergency_stop ? 'border-red-500/50 bg-red-900/10' : 'border-emerald-500/20')}>
          <ShieldCheck size={18} className={risk.emergency_stop ? 'text-red-400' : 'text-emerald-400'} />
          <div className="flex gap-6 text-xs">
            <span className="text-gray-400">Emergency Stop: <span className={risk.emergency_stop ? 'text-red-400 font-bold' : 'text-emerald-400 font-bold'}>{risk.emergency_stop ? 'ACTIVE' : 'OFF'}</span></span>
            <span className="text-gray-400">Daily P&L: <span className="text-white">₹{Number(risk.daily_pnl||0).toLocaleString('en-IN')}</span></span>
            <span className="text-gray-400">Open Positions: <span className="text-white">{risk.open_positions||0}</span></span>
            <span className="text-gray-400">Drawdown: <span className={Math.abs(risk.current_drawdown||0) > 0.05 ? 'text-amber-400' : 'text-emerald-400'}>{((risk.current_drawdown||0)*100).toFixed(2)}%</span></span>
          </div>
        </div>
      )}
    </div>
  )
}
