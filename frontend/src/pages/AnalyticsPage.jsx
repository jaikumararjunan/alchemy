import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'
export default function AnalyticsPage() {
  const data = Array.from({length:60},(_,i)=>({ d:`D${i+1}`, strategy:(1+Math.sin(i/8)*0.05+i*0.003)*100000, benchmark:(1+Math.cos(i/10)*0.03+i*0.002)*100000 }))
  return (
    <div className="space-y-5">
      <h1 className="text-xl font-bold text-white">Analytics</h1>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[['Sharpe Ratio','1.84','text-emerald-400'],['Sortino Ratio','2.31','text-emerald-400'],['Max Drawdown','-8.2%','text-red-400'],['Calmar Ratio','2.10','text-emerald-400']].map(([l,v,c])=>(
          <div key={l} className="card-sm"><div className="text-xs text-gray-400">{l}</div><div className={`text-2xl font-bold mt-1 ${c}`}>{v}</div></div>
        ))}
      </div>
      <div className="card">
        <h2 className="section-title">Cumulative Returns vs Benchmark</h2>
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis dataKey="d" tick={{fill:'#64748b',fontSize:10}} />
            <YAxis tick={{fill:'#64748b',fontSize:10}} tickFormatter={v=>`₹${(v/100000).toFixed(1)}L`} />
            <Tooltip contentStyle={{background:'#1e293b',border:'1px solid #334155',borderRadius:'8px',color:'#f1f5f9'}} />
            <Legend />
            <Line type="monotone" dataKey="strategy"  stroke="#2E75B6" strokeWidth={2} dot={false} name="Alchemy Strategy" />
            <Line type="monotone" dataKey="benchmark" stroke="#6B7280" strokeWidth={1.5} dot={false} strokeDasharray="4 2" name="NIFTY 50" />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
