import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/context/AuthContext'
import { ShieldAlert, ShieldCheck, AlertTriangle, Activity, RefreshCw, Save, Sliders } from 'lucide-react'
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

  const { data: capital } = useQuery({
    queryKey: ['capital-summary'],
    queryFn: () => api.get('/capital-engine/summary').then(r => r.data).catch(() => null),
    refetchInterval: 10000,
  })

  const { data: drawdown } = useQuery({
    queryKey: ['capital-drawdown'],
    queryFn: () => api.get('/capital-engine/drawdown').then(r => r.data).catch(() => null),
    refetchInterval: 10000,
  })

  // Editable risk parameters
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState({
    base_risk_pct: 1.0,
    max_position_pct: 10.0,
    max_daily_loss_pct: 3.0,
    max_daily_trades: 20,
    min_risk_reward: 1.5,
    min_confidence: 0.55,
    drawdown_pause_pct: 15.0,
    consecutive_loss_pause: 5,
    profit_lock_pct: 20.0,
    reinvest_mode: 'moderate',
  })

  // Load current config when capital data arrives
  useState(() => {
    if (capital) {
      setForm(f => ({
        ...f,
        reinvest_mode: capital.reinvest_mode || 'moderate',
      }))
    }
  })

  const configMut = useMutation({
    mutationFn: (data) => api.post('/capital-engine/configure', data).then(r => r.data),
    onSuccess: () => {
      toast.success('Risk parameters saved!')
      setEditing(false)
      qc.invalidateQueries(['capital-summary'])
      qc.invalidateQueries(['capital-drawdown'])
    },
    onError: (e) => toast.error(e.response?.data?.detail || 'Failed to save'),
  })

  const stopMut = useMutation({
    mutationFn: () => api.post('/risk/emergency-stop').then(r => r.data),
    onSuccess: () => { toast.error('Emergency stop activated'); qc.invalidateQueries(['risk']) },
  })
  const resetMut = useMutation({
    mutationFn: () => api.delete('/risk/emergency-stop').then(r => r.data),
    onSuccess: () => { toast.success('Emergency stop cleared'); qc.invalidateQueries(['risk']) },
  })

  const es = risk?.emergency_stop
  const dd = drawdown || {}

  return (
    <div className="space-y-5">
      <h1 className="text-xl font-display font-bold text-white tracking-tight flex items-center gap-2">
        <ShieldAlert size={20} className="text-amber-400"/> Risk Manager
      </h1>

      {/* Emergency stop */}
      <div className={clsx('card border', es ? 'border-red-500 bg-red-900/10' : 'border-emerald-500/30')}>
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            {es ? <ShieldAlert size={24} className="text-red-400 animate-pulse"/>
                 : <ShieldCheck size={24} className="text-emerald-400"/>}
            <div>
              <div className={clsx('text-base font-bold', es ? 'text-red-400' : 'text-emerald-400')}>
                {es ? 'EMERGENCY STOP ACTIVE' : 'System Normal'}
              </div>
              <div className="text-xs text-gray-500">{es ? 'All trading halted' : 'All risk checks passing'}</div>
            </div>
          </div>
          {!es ? (
            <button onClick={() => stopMut.mutate()} disabled={stopMut.isPending}
              className="px-4 py-2 rounded-xl text-xs font-bold bg-red-600 hover:bg-red-500 text-white flex items-center gap-1.5">
              {stopMut.isPending ? <RefreshCw size={12} className="animate-spin"/> : <ShieldAlert size={12}/>}
              Trigger Emergency Stop
            </button>
          ) : (
            <button onClick={() => resetMut.mutate()} disabled={resetMut.isPending}
              className="px-4 py-2 rounded-xl text-xs font-bold bg-emerald-600 hover:bg-emerald-500 text-white flex items-center gap-1.5">
              {resetMut.isPending ? <RefreshCw size={12} className="animate-spin"/> : <ShieldCheck size={12}/>}
              Clear Emergency Stop
            </button>
          )}
        </div>
      </div>

      {/* Live metrics */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {[
          { label: 'Daily P&L', value: `$${(capital?.daily_pnl || risk?.daily_pnl || 0).toFixed(2)}`,
            color: (capital?.daily_pnl || 0) >= 0 ? 'text-emerald-400' : 'text-rose-400' },
          { label: 'Drawdown', value: `${(dd.current_drawdown_pct || 0).toFixed(2)}%`,
            color: (dd.current_drawdown_pct || 0) > 5 ? 'text-amber-400' : 'text-emerald-400' },
          { label: 'Drawdown Mode', value: dd.drawdown_mode || 'normal',
            color: dd.drawdown_mode === 'normal' ? 'text-emerald-400' : dd.drawdown_mode === 'warning' ? 'text-amber-400' : 'text-rose-400' },
          { label: 'Open Positions', value: risk?.open_positions || 0, color: 'text-white' },
          { label: 'Win Rate', value: `${capital?.win_rate || 0}%`, color: 'text-blue-400' },
          { label: 'Total Trades', value: capital?.total_trades || 0, color: 'text-gray-300' },
          { label: 'Consecutive Losses', value: capital?.consecutive_losses || 0,
            color: (capital?.consecutive_losses || 0) >= 3 ? 'text-rose-400' : 'text-gray-300' },
          { label: 'Locked Reserve', value: `$${(capital?.locked_reserve || 0).toFixed(0)}`, color: 'text-purple-400' },
        ].map(s => (
          <div key={s.label} className="rounded-xl p-3 border border-white/[0.06]" style={{ background: 'var(--surface-2)' }}>
            <div className="text-[10px] text-gray-500 uppercase tracking-wider">{s.label}</div>
            <div className={clsx('text-lg font-bold font-mono mt-0.5', s.color)}>{s.value}</div>
          </div>
        ))}
      </div>

      {/* Drawdown circuit breakers */}
      {dd.thresholds && (
        <div className="card">
          <h2 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
            <AlertTriangle size={14} className="text-amber-400"/> Drawdown Circuit Breakers
          </h2>
          <div className="space-y-2">
            {[
              { label: 'Warning', pct: dd.thresholds.warning, color: 'bg-amber-500', active: dd.drawdown_mode === 'warning' },
              { label: 'Reduce Size', pct: dd.thresholds.reduce, color: 'bg-orange-500', active: dd.drawdown_mode === 'reduced' },
              { label: 'Pause Trading', pct: dd.thresholds.pause, color: 'bg-rose-500', active: dd.drawdown_mode === 'paused' },
              { label: 'Kill Switch', pct: dd.thresholds.kill, color: 'bg-red-600', active: dd.drawdown_mode === 'killed' },
            ].map(t => (
              <div key={t.label} className="flex items-center gap-3">
                <div className="w-24 text-xs text-gray-400">{t.label}</div>
                <div className="flex-1 h-2 rounded-full bg-white/[0.06] overflow-hidden">
                  <div className={clsx('h-full rounded-full transition-all', t.color)}
                    style={{ width: `${Math.min((dd.current_drawdown_pct || 0) / (t.pct || 1) * 100, 100)}%` }} />
                </div>
                <div className={clsx('text-xs font-mono w-10 text-right', t.active ? 'text-rose-400 font-bold' : 'text-gray-500')}>
                  {t.pct}%
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Editable Risk Parameters */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2">
            <Sliders size={14} className="text-blue-400"/> Risk Parameters
          </h2>
          {!editing ? (
            <button onClick={() => setEditing(true)} className="btn-ghost text-xs flex items-center gap-1">
              <Sliders size={12}/> Edit
            </button>
          ) : (
            <div className="flex gap-2">
              <button onClick={() => setEditing(false)} className="btn-ghost text-xs">Cancel</button>
              <button onClick={() => configMut.mutate(form)} disabled={configMut.isPending}
                className="btn-primary text-xs flex items-center gap-1">
                {configMut.isPending ? <RefreshCw size={12} className="animate-spin"/> : <Save size={12}/>}
                Save
              </button>
            </div>
          )}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {[
            { key: 'max_daily_loss_pct', label: 'Max Daily Loss', suffix: '% of capital', min: 0.5, max: 20, step: 0.5 },
            { key: 'base_risk_pct', label: 'Risk Per Trade', suffix: '% of capital', min: 0.1, max: 5, step: 0.1 },
            { key: 'max_position_pct', label: 'Max Position Size', suffix: '% of capital', min: 1, max: 50, step: 1 },
            { key: 'max_daily_trades', label: 'Max Daily Trades', suffix: 'trades', min: 1, max: 100, step: 1 },
            { key: 'min_risk_reward', label: 'Min Risk:Reward', suffix: 'ratio', min: 0.5, max: 10, step: 0.1 },
            { key: 'min_confidence', label: 'Min Signal Confidence', suffix: '', min: 0.1, max: 1.0, step: 0.05,
              display: (v) => `${(v * 100).toFixed(0)}%` },
            { key: 'drawdown_pause_pct', label: 'Drawdown Pause At', suffix: '%', min: 5, max: 50, step: 1 },
            { key: 'consecutive_loss_pause', label: 'Pause After Losses', suffix: 'consecutive', min: 2, max: 20, step: 1 },
            { key: 'profit_lock_pct', label: 'Profit Lock', suffix: '% of profits', min: 0, max: 100, step: 5 },
          ].map(param => (
            <div key={param.key} className="flex items-center justify-between p-3 rounded-xl" style={{ background: 'var(--surface-1)' }}>
              <div>
                <div className="text-xs text-gray-400">{param.label}</div>
                {editing && (
                  <input
                    type="range" min={param.min} max={param.max} step={param.step}
                    value={form[param.key]}
                    onChange={(e) => setForm(f => ({ ...f, [param.key]: Number(e.target.value) }))}
                    className="w-full mt-1 accent-blue-500"
                  />
                )}
              </div>
              <div className="text-right">
                <div className="text-sm font-bold text-white font-mono">
                  {editing
                    ? (param.display ? param.display(form[param.key]) : form[param.key])
                    : (param.display
                        ? param.display(form[param.key])
                        : form[param.key]
                      )
                  }
                </div>
                <div className="text-[10px] text-gray-600">{param.suffix}</div>
              </div>
            </div>
          ))}
        </div>

        {/* Reinvestment mode */}
        {editing && (
          <div className="mt-4">
            <div className="text-xs text-gray-400 mb-2">Reinvestment Mode</div>
            <div className="flex gap-2 flex-wrap">
              {['preserve', 'conservative', 'moderate', 'aggressive', 'full_compound'].map(mode => (
                <button key={mode} onClick={() => setForm(f => ({ ...f, reinvest_mode: mode }))}
                  className={clsx('px-3 py-1.5 rounded-lg text-xs font-medium transition-colors border',
                    form.reinvest_mode === mode
                      ? 'bg-blue-500/15 border-blue-500/30 text-blue-400'
                      : 'border-white/[0.06] text-gray-500 hover:text-gray-300 hover:bg-white/[0.03]'
                  )}>
                  {mode.replace('_', ' ')}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
