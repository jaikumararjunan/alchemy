import { useQuery } from '@tanstack/react-query'
import { useAuth } from '@/context/AuthContext'
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell, Legend } from 'recharts'
import { AlertCircle, TrendingUp, TrendingDown } from 'lucide-react'
import clsx from 'clsx'

function Empty({ msg }) {
  return (
    <div className="text-center py-12 text-gray-500">
      <AlertCircle size={24} className="mx-auto mb-2 opacity-40"/>
      <p className="text-sm">{msg}</p>
      <p className="text-xs mt-1 text-gray-600">Record trades via the API or Intelligence → Record Trade</p>
    </div>
  )
}

export default function AnalyticsPage() {
  const { apiClient } = useAuth()
  const api = apiClient()

  const { data: summaryData } = useQuery({
    queryKey: ['pnl-summary'],
    queryFn: () => api.get('/intelligence/analytics/pnl-summary?days=90').then(r => r.data).catch(() => null),
    staleTime: 60000,
  })

  const { data: perfData } = useQuery({
    queryKey: ['strategy-perf'],
    queryFn: () => api.get('/intelligence/analytics/strategy-performance?months=3').then(r => r.data).catch(() => null),
    staleTime: 60000,
  })

  const { data: tradesData } = useQuery({
    queryKey: ['all-trades'],
    queryFn: () => api.get('/intelligence/analytics/trades?limit=200').then(r => r.data).catch(() => null),
    staleTime: 60000,
  })

  const trades    = tradesData?.trades || []
  const perfList  = perfData?.performance || []
  const totals    = summaryData?.totals || {}
  const byOutcome = summaryData?.by_outcome || []

  const wins   = byOutcome.find(b => b.outcome === 'win')
  const losses = byOutcome.find(b => b.outcome === 'loss')
  const winRate = totals.total_trades > 0 ? ((totals.wins || 0) / totals.total_trades * 100).toFixed(1) : null

  // Build daily cumulative P&L from real trades
  const dailyCum = (() => {
    if (!trades.length) return []
    const byDay = {}
    trades.filter(t => t.closed_at).forEach(t => {
      const d = t.closed_at.slice(0,10)
      byDay[d] = (byDay[d] || 0) + (t.pnl || 0)
    })
    let cum = 0
    return Object.entries(byDay).sort().map(([d, pnl]) => {
      cum += pnl
      return { d: d.slice(5), pnl: parseFloat(pnl.toFixed(2)), cum: parseFloat(cum.toFixed(2)) }
    })
  })()

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-display font-bold text-white tracking-tight">Analytics</h1>
        <p className="text-sm text-gray-400">Real trade performance from your connected exchanges</p>
      </div>

      {/* Key metrics from real data */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: 'Total Trades', value: totals.total_trades || 0, color: 'text-white' },
          { label: 'Win Rate',     value: winRate ? `${winRate}%` : '—',
            color: parseFloat(winRate) >= 50 ? 'text-emerald-400' : 'text-red-400' },
          { label: 'Net P&L',     value: totals.net_pnl != null ? `$${parseFloat(totals.net_pnl).toFixed(2)}` : '—',
            color: (totals.net_pnl||0) >= 0 ? 'text-emerald-400' : 'text-red-400' },
          { label: 'Total Fees',  value: totals.total_fees != null ? `$${parseFloat(totals.total_fees).toFixed(2)}` : '—',
            color: 'text-amber-400' },
        ].map(({ label, value, color }) => (
          <div key={label} className="card-sm">
            <div className="text-xs text-gray-400">{label}</div>
            <div className={clsx('text-2xl font-bold mt-1', color)}>{value}</div>
          </div>
        ))}
      </div>

      {/* Cumulative P&L chart — real data */}
      <div className="card">
        <h2 className="section-title">Cumulative P&L (real trades)</h2>
        {dailyCum.length === 0 ? (
          <Empty msg="No closed trades yet"/>
        ) : (
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={dailyCum}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b"/>
              <XAxis dataKey="d" tick={{fill:'#64748b',fontSize:10}}/>
              <YAxis tick={{fill:'#64748b',fontSize:10}} tickFormatter={v=>`$${v}`}/>
              <Tooltip formatter={(v,n) => [`$${v}`, n === 'cum' ? 'Cumulative P&L' : 'Daily P&L']}
                contentStyle={{background:'#1e293b',border:'1px solid #334155',borderRadius:'8px',color:'#f1f5f9'}}/>
              <Legend/>
              <Bar  dataKey="pnl"  name="Daily P&L"       radius={[2,2,0,0]} opacity={0.4}>
                {dailyCum.map((e,i) => <Cell key={i} fill={e.pnl >= 0 ? '#10B981' : '#EF4444'}/>)}
              </Bar>
              <Line dataKey="cum"  name="Cumulative P&L"  stroke="#2E75B6" strokeWidth={2} dot={false}/>
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Strategy performance — real data */}
      <div className="card">
        <h2 className="section-title">Strategy Performance (last 3 months)</h2>
        {perfList.length === 0 ? (
          <Empty msg="No strategy data yet — strategies are tracked as trades are recorded"/>
        ) : (
          <table className="w-full min-w-[500px] text-xs">
            <thead>
              <tr className="text-gray-500 border-b border-gray-800">
                {['Strategy','Trades','Wins','Win Rate','Net P&L','Avg P&L/Trade'].map(h => (
                  <th key={h} className="pb-2 text-left font-medium pr-4">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {perfList.map((p, i) => (
                <tr key={i} className="border-b border-gray-800/30 hover:bg-gray-800/20">
                  <td className="py-2 pr-4 font-medium text-white capitalize">{p.strategy}</td>
                  <td className="py-2 pr-4 text-gray-300">{p.total_trades}</td>
                  <td className="py-2 pr-4 text-emerald-400">{p.total_wins}</td>
                  <td className="py-2 pr-4">
                    <span className={clsx('font-semibold', parseFloat(p.avg_win_rate*100) >= 50 ? 'text-emerald-400' : 'text-red-400')}>
                      {(p.avg_win_rate*100).toFixed(1)}%
                    </span>
                  </td>
                  <td className={clsx('py-2 pr-4 font-semibold', p.net_pnl >= 0 ? 'text-emerald-400' : 'text-red-400')}>
                    {p.net_pnl >= 0 ? '+' : ''}${parseFloat(p.net_pnl).toFixed(2)}
                  </td>
                  <td className={clsx('py-2 text-gray-300', p.avg_pnl_pct >= 0 ? 'text-emerald-400' : 'text-red-400')}>
                    {p.avg_pnl_pct >= 0 ? '+' : ''}{parseFloat(p.avg_pnl_pct).toFixed(2)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Win/Loss breakdown */}
      {byOutcome.length > 0 && (
        <div className="grid grid-cols-2 gap-4">
          {[wins, losses].filter(Boolean).map(o => (
            <div key={o.outcome} className={clsx('card', o.outcome === 'win' ? 'border-emerald-500/20' : 'border-red-500/20')}>
              <div className="flex items-center gap-2 mb-2">
                {o.outcome === 'win' ? <TrendingUp size={16} className="text-emerald-400"/> : <TrendingDown size={16} className="text-red-400"/>}
                <h3 className="text-sm font-semibold text-white capitalize">{o.outcome}ning Trades</h3>
              </div>
              <div className="space-y-1 text-xs text-gray-400">
                <div className="flex justify-between"><span>Count</span><span className="text-white">{o.count}</span></div>
                <div className="flex justify-between"><span>Total P&L</span>
                  <span className={o.outcome==='win'?'text-emerald-400':'text-red-400'}>
                    ${parseFloat(o.total_pnl||0).toFixed(2)}
                  </span>
                </div>
                <div className="flex justify-between"><span>Best</span><span className="text-emerald-400">${parseFloat(o.best||0).toFixed(2)}</span></div>
                <div className="flex justify-between"><span>Worst</span><span className="text-red-400">${parseFloat(o.worst||0).toFixed(2)}</span></div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
