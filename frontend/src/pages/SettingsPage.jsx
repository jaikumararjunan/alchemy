import { useState } from 'react'
import { Settings } from 'lucide-react'
export default function SettingsPage() {
  const [env, setEnv] = useState('paper')
  return (
    <div className="space-y-5">
      <h1 className="text-xl font-bold text-white flex items-center gap-2"><Settings size={20}/>Settings</h1>
      <div className="card max-w-lg">
        <h2 className="section-title">Trading Environment</h2>
        <div className="flex gap-2">
          {['paper','live'].map(e=>(
            <button key={e} onClick={()=>setEnv(e)} className={`px-4 py-2 rounded-lg text-sm font-medium capitalize transition-colors ${env===e?'bg-blue-600 text-white':'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}>{e}</button>
          ))}
        </div>
        <p className="text-xs text-gray-500 mt-3">{env==='paper'?'Paper trading — no real money at risk':'⚠️ Live trading — real funds will be used'}</p>
      </div>
      <div className="card max-w-lg">
        <h2 className="section-title">Broker Connections</h2>
        {[['Interactive Brokers','IB Gateway','connected'],['Zerodha Kite','NSE/BSE','connected'],['Delta Exchange','Crypto Derivatives','disconnected'],['Binance','Spot + Futures','connected']].map(([name,desc,status])=>(
          <div key={name} className="flex items-center justify-between py-3 border-b border-gray-800 last:border-0">
            <div><div className="text-sm font-medium text-white">{name}</div><div className="text-xs text-gray-500">{desc}</div></div>
            <span className={`text-xs font-medium ${status==='connected'?'text-emerald-400':'text-red-400'}`}>{status}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
