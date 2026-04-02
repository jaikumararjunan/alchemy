import { useAlchemyStore } from '@/store'
import { generateSignal } from '@/api/client'
import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { Zap, RefreshCw } from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'

export default function SignalsPage() {
  const signals = useAlchemyStore(s => s.signals)
  const addSignal = useAlchemyStore(s => s.addSignal)
  const [ticker, setTicker] = useState('RELIANCE')
  const [market, setMarket] = useState('NSE')

  const { mutate, isPending } = useMutation({
    mutationFn: () => generateSignal({ ticker, market, broker:'paper' }),
    onSuccess: (data) => { addSignal(data); toast.success(`Signal: ${data.signal} ${data.ticker}`) },
    onError: (e) => toast.error(`Agent error: ${e.message}`)
  })

  return (
    <div className="space-y-5">
      <h1 className="text-xl font-bold text-white flex items-center gap-2"><Zap size={20} className="text-blue-400" />AI Signals</h1>
      <div className="card max-w-md">
        <h2 className="section-title">Run Agent</h2>
        <div className="flex gap-2 mb-3">
          <input value={ticker} onChange={e=>setTicker(e.target.value.toUpperCase())} className="input-field" placeholder="RELIANCE" />
          <select value={market} onChange={e=>setMarket(e.target.value)} className="input-field w-32">
            {['NSE','BSE','NYSE','NASDAQ','CRYPTO'].map(m=><option key={m}>{m}</option>)}
          </select>
        </div>
        <button onClick={()=>mutate()} disabled={isPending} className="btn-primary w-full">
          {isPending ? <RefreshCw size={14} className="animate-spin inline mr-1" /> : <Zap size={14} className="inline mr-1" />}
          {isPending ? 'Running agents…' : 'Generate Signal'}
        </button>
      </div>
      <div className="card">
        <h2 className="section-title">Signal History ({signals.length})</h2>
        {signals.length === 0
          ? <p className="text-gray-500 text-sm text-center py-10">No signals yet</p>
          : <div className="space-y-2">
              {signals.map((s,i) => (
                <div key={i} className="flex items-start justify-between p-3 bg-gray-800/40 rounded-lg border border-gray-700/50">
                  <div className="flex items-center gap-3">
                    <span className={s.signal==='BUY'?'badge-buy':s.signal==='SELL'?'badge-sell':'badge-hold'}>{s.signal}</span>
                    <div>
                      <div className="text-sm font-semibold text-white">{s.ticker} <span className="text-gray-500 text-xs">{s.market}</span></div>
                      <div className="text-xs text-gray-400 mt-0.5">{s.reasoning?.slice(0,120)}…</div>
                    </div>
                  </div>
                  <div className="text-right text-xs flex-shrink-0 ml-4">
                    <div className="text-gray-300">{(s.position_pct*100).toFixed(1)}% position</div>
                    <div className="text-gray-500">Vol {(s.forecast_vol*100).toFixed(0)}%</div>
                    <div className="text-gray-500">Sent {s.sentiment_score?.toFixed(2)}</div>
                  </div>
                </div>
              ))}
            </div>}
      </div>
    </div>
  )
}
