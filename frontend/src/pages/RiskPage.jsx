import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/context/AuthContext'
import { ShieldAlert, ShieldCheck, AlertTriangle, TrendingDown, Activity, RefreshCw } from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'

export default function RiskPage() {
  const { apiClient } = useAuth()
  const api = apiClient()
  const qc = useQueryClient()

  const { data: risk, isLoading } = useQuery({
    queryKey: ['risk'],
    queryFn: () => api.get('/risk/status').then(r => r.data).catch(() => null),
    refetchInterval: 5000,
  })

  const stopMut  = useMutation({
    mutationFn: () => api.post('/risk/emergency-stop').then(r => r.data),
    onSuccess: () => { toast.error('Emergency stop activated'); qc.invalidateQueries(['risk']) },
  })
  const resetMut = useMutation({
    mutationFn: () => api.delete('/risk/emergency-stop').then(r => r.data),
    onSuccess: () => { toast.success('Emergency stop cleared'); qc.invalidateQueries(['risk']) },
  })

  const es = risk?.emergency_stop

  const stats = risk ? [
    { label: 'Daily P&L',        value: risk.daily_pnl != null ? `$${Number(risk.daily_pnl).toFixed(2)}` : '—',
      color: (risk.daily_pnl || 0) >= 0 ? 'text-emerald-400' : 'text-red-400' },
    { label: 'Current Drawdown', value: `${((risk.current_drawdown || 0) * 100).toFixed(2)}%`,
      color: Math.abs(risk.current_drawdown || 0) > 0.05 ? 'text-amber-400' : 'text-emerald-400' },
    { label: 'Max Daily Loss',   value: `$${(risk.max_daily_loss_usd || 5000).toLocaleString()}`,
      color: 'text-gray-300' },
    { label: 'Open Positions',   value: risk.open_positions || 0, color: 'text-white' },
  ] : []

  return (
    <div className="space-y-5">
      <h1 className="text-xl font-display font-bold text-white tracking-tight flex items-center gap-2">
        <ShieldAlert size={20} className="text-amber-400"/> Risk Manager
      </h1>

      {/* Emergency stop panel */}
      <div className={clsx('card border-2', es ? 'border-red-500 bg-red-900/10' : 'border-emerald-500/30')}>
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            {es
              ? <ShieldAlert size={28} className="text-red-400 animate-pulse"/>
              : <ShieldCheck size={28} className="text-emerald-400"/>}
            <div>
              <div className={clsx('text-lg font-bold', es ? 'text-red-400' : 'text-emerald-400')}>
                {es ? 'EMERGENCY STOP ACTIVE' : 'System Normal'}
              </div>
              <div className="text-xs text-gray-400">
                {es ? 'All trading halted. Clear to resume.' : 'All risk checks passing'}
              </div>
            </div>
          </div>
          <div className="flex gap-2">
            {!es && (
              <button onClick={() => stopMut.mutate()} disabled={stopMut.isPending}
                className="px-4 py-2 rounded-xl text-xs font-semibold bg-red-600 hover:bg-red-500 text-white flex items-center gap-1.5 transition-colors">
                {stopMut.isPending ? <RefreshCw size={12} className="animate-spin"/> : <ShieldAlert size={12}/>}
                Trigger Emergency Stop
              </button>
            )}
            {es && (
              <button onClick={() => resetMut.mutate()} disabled={resetMut.isPending}
                className="px-4 py-2 rounded-xl text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white flex items-center gap-1.5 transition-colors">
                {resetMut.isPending ? <RefreshCw size={12} className="animate-spin"/> : <ShieldCheck size={12}/>}
                Clear Emergency Stop
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Risk stats */}
      {isLoading ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[1,2,3,4].map(i => <div key={i} className="card animate-pulse h-16"/>)}
        </div>
      ) : risk ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {stats.map(({ label, value, color }) => (
            <div key={label} className="card-sm">
              <div className="text-xs text-gray-400">{label}</div>
              <div className={clsx('text-xl font-bold mt-1', color)}>{value}</div>
            </div>
          ))}
        </div>
      ) : (
        <div className="card text-center py-6 text-gray-500 text-sm">
          Risk data unavailable — connect an exchange to see live risk metrics
        </div>
      )}

      {/* Risk limits */}
      <div className="card">
        <h2 className="section-title mb-3 flex items-center gap-2">
          <Activity size={14} className="text-blue-400"/> Risk Parameters
        </h2>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 text-xs">
          {[
            { label: 'Max Position Size',      value: `${((risk?.max_position_pct || 0.05) * 100).toFixed(0)}% of capital` },
            { label: 'Max Portfolio Drawdown', value: `${((risk?.max_drawdown_pct  || 0.10) * 100).toFixed(0)}%` },
            { label: 'Max Daily Loss',         value: `$${(risk?.max_daily_loss_usd || 5000).toLocaleString()}` },
            { label: 'Vol Scaling',            value: risk?.vol_scaling_enabled ? 'Enabled' : 'Disabled' },
          ].map(({ label, value }) => (
            <div key={label} className="flex justify-between items-center p-3 bg-gray-900/60 rounded-xl">
              <span className="text-gray-400">{label}</span>
              <span className="text-white font-medium">{value}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Blocked tickers */}
      {risk?.blocked_tickers?.length > 0 && (
        <div className="card border-amber-500/30">
          <h2 className="section-title flex items-center gap-2 mb-3">
            <AlertTriangle size={14} className="text-amber-400"/> Blocked Tickers
          </h2>
          <div className="flex flex-wrap gap-2">
            {risk.blocked_tickers.map(t => (
              <span key={t} className="px-3 py-1 rounded-full text-xs bg-red-900/30 text-red-400 border border-red-500/30">{t}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
