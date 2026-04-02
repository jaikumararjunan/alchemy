import { useState } from 'react'
import { BookOpen, Play } from 'lucide-react'
export default function StrategyPage() {
  const [selected, setSelected] = useState('SMA Crossover')
  const strategies = ['SMA Crossover','Momentum Factor','Mean Reversion','GARCH Vol','AI News Sentiment','Crypto Momentum']
  return (
    <div className="space-y-5">
      <h1 className="text-xl font-bold text-white flex items-center gap-2"><BookOpen size={20} className="text-blue-400"/>Strategy Library</h1>
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
        {strategies.map(s=>(
          <div key={s} onClick={()=>setSelected(s)} className={`card cursor-pointer transition-all ${selected===s?'border-blue-500':'hover:border-gray-600'}`}>
            <div className="font-medium text-white text-sm">{s}</div>
            <div className="text-xs text-gray-500 mt-1">Blueshift Strategy · Python</div>
            <button className="mt-3 flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300"><Play size={11}/>Run Backtest</button>
          </div>
        ))}
      </div>
    </div>
  )
}
