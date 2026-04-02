// ── PortfolioPage ─────────────────────────────────────────────────────────────
import { useQuery } from '@tanstack/react-query'
import { getPositions } from '@/api/client'
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid } from 'recharts'

export function PortfolioPage() {
  const ALLOCATION = [
    { name:'NSE Equity', value:35, color:'#2E75B6' }, { name:'NSE F&O', value:20, color:'#5B9BD5' },
    { name:'BTC Perp',   value:15, color:'#F59E0B' }, { name:'ETH Perp', value:10, color:'#8B5CF6' },
    { name:'Delta Opts', value:10, color:'#10B981' }, { name:'Cash',     value:10, color:'#6B7280' },
  ]
  const DAILY_PNL = Array.from({length:20},(_,i)=>({ d:`D${i+1}`, pnl:(Math.random()-0.42)*12000 }))

  return (
    <div className="space-y-5">
      <h1 className="text-xl font-bold text-white">Portfolio</h1>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div className="card">
          <h2 className="section-title">Asset Allocation</h2>
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie data={ALLOCATION} cx="50%" cy="50%" innerRadius={60} outerRadius={90} dataKey="value">
                {ALLOCATION.map((e,i) => <Cell key={i} fill={e.color} />)}
              </Pie>
              <Tooltip formatter={v=>`${v}%`} contentStyle={{background:'#1e293b',border:'1px solid #334155',borderRadius:'8px',color:'#f1f5f9'}} />
            </PieChart>
          </ResponsiveContainer>
          <div className="grid grid-cols-3 gap-1 mt-2">
            {ALLOCATION.map(a => (
              <div key={a.name} className="flex items-center gap-1.5 text-xs">
                <span className="w-2 h-2 rounded-full flex-shrink-0" style={{backgroundColor:a.color}} />
                <span className="text-gray-400 truncate">{a.name} {a.value}%</span>
              </div>
            ))}
          </div>
        </div>
        <div className="card">
          <h2 className="section-title">Daily P&L (₹)</h2>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={DAILY_PNL}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey="d" tick={{fill:'#64748b',fontSize:10}} />
              <YAxis tick={{fill:'#64748b',fontSize:10}} tickFormatter={v=>`₹${(v/1000).toFixed(0)}k`} />
              <Tooltip formatter={v=>`₹${v.toLocaleString('en-IN')}`} contentStyle={{background:'#1e293b',border:'1px solid #334155',borderRadius:'8px',color:'#f1f5f9'}} />
              <Bar dataKey="pnl" fill="#2E75B6" radius={[2,2,0,0]}
                cell={(entry) => <Cell fill={entry.pnl>=0?'#10B981':'#EF4444'} />} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
      <div className="card">
        <h2 className="section-title">Open Positions</h2>
        <table className="w-full text-xs">
          <thead><tr className="text-gray-500 border-b border-gray-800">
            {['Symbol','Exchange','Side','Qty','Avg Cost','LTP','P&L','P&L%','Action'].map(h=><th key={h} className="pb-2 text-left font-medium pr-4">{h}</th>)}
          </tr></thead>
          <tbody>
            {[
              {sym:'RELIANCE',ex:'NSE',  side:'LONG', qty:50, avg:'2780',ltp:'2851',pnl:'+₹3,550',pct:'+2.55%'},
              {sym:'TCS',     ex:'NSE',  side:'LONG', qty:20, avg:'3920',ltp:'3975',pnl:'+₹1,100',pct:'+1.40%'},
              {sym:'NIFTY25MAYFUT',ex:'NSE F&O',side:'SHORT',qty:1,avg:'22,150',ltp:'22,080',pnl:'+₹3,500',pct:'+0.32%'},
              {sym:'BTCUSD',  ex:'Delta',side:'LONG', qty:1, avg:'67,200',ltp:'68,450',pnl:'+$125',pct:'+1.86%'},
              {sym:'ETHUSDT', ex:'Binance',side:'SHORT',qty:2,avg:'3,900',ltp:'3,820',pnl:'+$160',pct:'+2.05%'},
            ].map((r,i) => (
              <tr key={i} className="table-row">
                <td className="py-2 pr-4 font-medium text-white">{r.sym}</td>
                <td className="py-2 pr-4 text-gray-500">{r.ex}</td>
                <td className="py-2 pr-4"><span className={r.side==='LONG'?'badge-buy':'badge-sell'}>{r.side}</span></td>
                <td className="py-2 pr-4 text-gray-300">{r.qty}</td>
                <td className="py-2 pr-4 text-gray-300">{r.avg}</td>
                <td className="py-2 pr-4 text-gray-200">{r.ltp}</td>
                <td className={`py-2 pr-4 font-semibold ${r.pnl.startsWith('+')?'text-emerald-400':'text-red-400'}`}>{r.pnl}</td>
                <td className={`py-2 pr-4 ${r.pct.startsWith('+')?'text-emerald-400':'text-red-400'}`}>{r.pct}</td>
                <td className="py-2"><button className="text-xs text-red-400 hover:text-red-300">Close</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
