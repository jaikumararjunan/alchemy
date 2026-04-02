import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getRiskStatus, triggerEmergencyStop, resetEmergencyStop } from '@/api/client'
import { ShieldAlert, ShieldCheck, AlertTriangle } from 'lucide-react'
import toast from 'react-hot-toast'
import clsx from 'clsx'

export default function RiskPage() {
  const qc = useQueryClient()
  const { data: risk } = useQuery({ queryKey:['risk'], queryFn: getRiskStatus, refetchInterval:5000 })
  const stopMut  = useMutation({ mutationFn: triggerEmergencyStop, onSuccess: () => { toast.error('⚠️ Emergency stop activated'); qc.invalidateQueries(['risk']) } })
  const resetMut = useMutation({ mutationFn: resetEmergencyStop,   onSuccess: () => { toast.success('Emergency stop cleared');    qc.invalidateQueries(['risk']) } })
  const es = risk?.emergency_stop

  return (
    <div className="space-y-5">
      <h1 className="text-xl font-bold text-white flex items-center gap-2"><ShieldAlert size={20} className="text-amber-400" />Risk Manager</h1>
      <div className={clsx('card border-2', es ? 'border-red-500 bg-red-900/10' : 'border-emerald-500/30')}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            {es ? <ShieldAlert size={24} className="text-red-400" /> : <ShieldCheck size={24} className="text-emerald-400" />}
            <div>
              <div className={clsx('text-lg font-bold', es?'text-red-400':'text-emerald-400')}>{es?'EMERGENCY STOP ACTIVE':'System Normal'}</div>
              <div className="text-xs text-gray-400">{es?'All trading is halted. Clear to resume.':'All risk checks passing'}</div>
            </div>
          </div>
          <div className="flex gap-2">
            {!es && <button onClick={()=>stopMut.mutate()} className="btn-danger text-xs">Trigger Emergency Stop</button>}
            {es  && <button onClick={()=>resetMut.mutate()} className="btn-primary text-xs">Clear Emergency Stop</button>}
          </div>
        </div>
      </div>
      {risk && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[
            { label:'Daily P&L',        value:`₹${Number(risk.daily_pnl||0).toLocaleString('en-IN')}`,  color: risk.daily_pnl>=0?'text-emerald-400':'text-red-400' },
            { label:'Open Positions',   value: risk.open_positions||0,                                   color:'text-white' },
            { label:'Current Drawdown', value:`${((risk.current_drawdown||0)*100).toFixed(2)}%`,         color: Math.abs(risk.current_drawdown||0)>0.05?'text-amber-400':'text-emerald-400' },
            { label:'Max Daily Loss',   value:`₹${(risk.max_daily_loss_usd||5000).toLocaleString()}`,    color:'text-gray-300' },
          ].map(({label,value,color})=>(
            <div key={label} className="card-sm">
              <div className="text-xs text-gray-400">{label}</div>
              <div className={clsx('text-xl font-bold mt-1', color)}>{value}</div>
            </div>
          ))}
        </div>
      )}
      {risk?.blocked_tickers?.length > 0 && (
        <div className="card border-amber-500/30">
          <h2 className="section-title flex items-center gap-2"><AlertTriangle size={14} className="text-amber-400"/>Blocked Tickers</h2>
          <div className="flex flex-wrap gap-2">
            {risk.blocked_tickers.map(t=><span key={t} className="badge-sell">{t}</span>)}
          </div>
        </div>
      )}
    </div>
  )
}
