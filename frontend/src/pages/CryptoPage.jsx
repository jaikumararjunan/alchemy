import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { getDeltaTicker, getDeltaPositions, getDeltaBalance, getDeltaFundingRate,
         getBinanceTicker, getBinancePositions, getBinanceBalance,
         getDeltaPlaceOrder, binancePlaceOrder } from '@/api/client'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { Bitcoin, TrendingUp, TrendingDown, Zap, RefreshCw, AlertTriangle } from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'

const TABS = ['Delta Exchange', 'Binance']
const DELTA_SYMBOLS = ['BTCUSD', 'ETHUSD', 'SOLUSD', 'BNBUSD', 'XRPUSD']
const BINANCE_SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT']

function TickerCard({ symbol, exchange }) {
  const isBinance = exchange === 'binance'
  const { data, isLoading } = useQuery({
    queryKey: ['ticker', exchange, symbol],
    queryFn: () => isBinance ? getBinanceTicker(symbol) : getDeltaTicker(symbol),
    refetchInterval: 3000,
  })

  const price  = data?.mark_price || data?.price || '—'
  const change = data?.change_24h || data?.price_change_percent || 0
  const up = Number(change) >= 0

  return (
    <div className={clsx('card-sm cursor-pointer hover:border-blue-500/50 transition-all', up ? 'border-l-2 border-l-emerald-500' : 'border-l-2 border-l-red-500')}>
      <div className="flex justify-between items-start">
        <div>
          <div className="text-xs text-gray-500">{symbol}</div>
          <div className="text-base font-bold text-white mt-0.5">
            {isLoading ? <span className="text-gray-600 animate-pulse">Loading…</span> : `$${Number(price).toLocaleString()}`}
          </div>
        </div>
        <span className={clsx('text-xs font-semibold', up ? 'stat-up' : 'stat-down')}>
          {up ? '+' : ''}{Number(change).toFixed(2)}%
        </span>
      </div>
    </div>
  )
}

function OrderForm({ exchange, onSubmit }) {
  const symbols = exchange === 'Delta Exchange' ? DELTA_SYMBOLS : BINANCE_SYMBOLS
  const [form, setForm] = useState({ symbol: symbols[0], side:'buy', qty:'', order_type:'market', leverage: '10' })

  const { mutate, isPending } = useMutation({
    mutationFn: (payload) => exchange === 'Delta Exchange' ? getDeltaPlaceOrder(payload) : binancePlaceOrder(payload),
    onSuccess: (data) => toast.success(`Order placed: ${data?.id || 'OK'}`),
    onError: (err)  => toast.error(`Order failed: ${err.message}`),
  })

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!form.qty) return toast.error('Enter quantity')
    mutate({ ...form, qty: Number(form.qty), leverage: Number(form.leverage) })
  }

  return (
    <div className="card">
      <h3 className="text-sm font-semibold text-gray-200 mb-3">Place Order · {exchange}</h3>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <label className="text-xs text-gray-400 mb-1 block">Symbol</label>
          <select value={form.symbol} onChange={e => setForm(f => ({...f, symbol: e.target.value}))} className="input-field">
            {symbols.map(s => <option key={s}>{s}</option>)}
          </select>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="text-xs text-gray-400 mb-1 block">Side</label>
            <div className="flex gap-1">
              {['buy','sell'].map(s => (
                <button key={s} type="button"
                  onClick={() => setForm(f => ({...f, side: s}))}
                  className={clsx('flex-1 py-1.5 text-xs font-semibold rounded-lg transition-colors',
                    form.side === s
                      ? (s === 'buy' ? 'bg-emerald-600 text-white' : 'bg-red-600 text-white')
                      : 'bg-gray-800 text-gray-400 hover:bg-gray-700')}>
                  {s.toUpperCase()}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="text-xs text-gray-400 mb-1 block">Order Type</label>
            <select value={form.order_type} onChange={e => setForm(f => ({...f, order_type: e.target.value}))} className="input-field text-xs">
              <option value="market">Market</option>
              <option value="limit">Limit</option>
              <option value="stop_market">Stop Market</option>
            </select>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="text-xs text-gray-400 mb-1 block">Quantity (contracts)</label>
            <input type="number" placeholder="1" value={form.qty} onChange={e => setForm(f => ({...f, qty: e.target.value}))} className="input-field" />
          </div>
          <div>
            <label className="text-xs text-gray-400 mb-1 block">Leverage</label>
            <select value={form.leverage} onChange={e => setForm(f => ({...f, leverage: e.target.value}))} className="input-field">
              {['1','2','3','5','10','20','50'].map(l => <option key={l}>{l}x</option>)}
            </select>
          </div>
        </div>
        <button type="submit" disabled={isPending}
          className={clsx('w-full py-2 rounded-lg text-sm font-semibold transition-colors',
            form.side === 'buy'
              ? 'bg-emerald-600 hover:bg-emerald-500 text-white disabled:opacity-50'
              : 'bg-red-600 hover:bg-red-500 text-white disabled:opacity-50')}>
          {isPending ? <RefreshCw size={14} className="animate-spin inline mr-1" /> : null}
          {form.side === 'buy' ? '▲ Long' : '▼ Short'} {form.symbol}
        </button>
      </form>
    </div>
  )
}

function PositionsTable({ exchange }) {
  const isBinance = exchange === 'Binance'
  const { data: positions = [], isLoading } = useQuery({
    queryKey:  ['positions', exchange],
    queryFn:   isBinance ? getBinancePositions : getDeltaPositions,
    refetchInterval: 5000,
  })

  // Use mock data for display
  const mockPositions = [
    { symbol: isBinance ? 'BTCUSDT' : 'BTCUSD', side:'LONG',  size:'0.1',  entryPrice:'67,200', markPrice:'68,450', pnl:'+$125.00', pnlPct:'+1.86%', liq:'$60,000' },
    { symbol: isBinance ? 'ETHUSD'  : 'ETHUSD',  side:'SHORT', size:'2',    entryPrice:'3,900',  markPrice:'3,820',  pnl:'+$160.00', pnlPct:'+2.05%', liq:'$4,500'  },
  ]

  const rows = positions.length > 0 ? positions : mockPositions

  return (
    <div className="card">
      <h3 className="text-sm font-semibold text-gray-200 mb-3">Open Positions · {exchange}</h3>
      {isLoading
        ? <div className="text-gray-500 text-xs text-center py-6 animate-pulse">Loading positions…</div>
        : <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-gray-500 border-b border-gray-800">
                  {['Symbol','Side','Size','Entry','Mark','PnL','PnL%','Liq.'].map(h => (
                    <th key={h} className="pb-2 text-left font-medium pr-4">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((p, i) => (
                  <tr key={i} className="table-row">
                    <td className="py-2 pr-4 font-medium text-white">{p.symbol}</td>
                    <td className="py-2 pr-4"><span className={p.side==='LONG'?'badge-buy':'badge-sell'}>{p.side}</span></td>
                    <td className="py-2 pr-4 text-gray-300">{p.size}</td>
                    <td className="py-2 pr-4 text-gray-300">${p.entryPrice}</td>
                    <td className="py-2 pr-4 text-gray-200">${p.markPrice}</td>
                    <td className={clsx('py-2 pr-4 font-semibold', p.pnl.startsWith('+') ? 'text-emerald-400' : 'text-red-400')}>{p.pnl}</td>
                    <td className={clsx('py-2 pr-4', p.pnlPct.startsWith('+') ? 'text-emerald-400' : 'text-red-400')}>{p.pnlPct}</td>
                    <td className="py-2 text-amber-400">${p.liq}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
      }
    </div>
  )
}

export default function CryptoPage() {
  const [tab, setTab] = useState('Delta Exchange')
  const symbols = tab === 'Delta Exchange' ? DELTA_SYMBOLS : BINANCE_SYMBOLS

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white flex items-center gap-2"><Bitcoin size={20} className="text-amber-400" /> Crypto Trading</h1>
          <p className="text-sm text-gray-400">Delta Exchange (derivatives) · Binance (spot + futures)</p>
        </div>
        <div className="flex gap-1 bg-gray-800 rounded-lg p-1">
          {TABS.map(t => (
            <button key={t} onClick={() => setTab(t)}
              className={clsx('px-3 py-1.5 text-xs font-medium rounded-md transition-colors',
                tab === t ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-gray-200')}>
              {t}
            </button>
          ))}
        </div>
      </div>

      {/* Ticker cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        {symbols.map(s => <TickerCard key={s} symbol={s} exchange={tab === 'Binance' ? 'binance' : 'delta'} />)}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Order Form */}
        <div className="lg:col-span-1">
          <OrderForm exchange={tab} />

          {/* Balance */}
          <div className="card mt-4">
            <h3 className="text-sm font-semibold text-gray-200 mb-3">Account Balance</h3>
            <div className="space-y-2 text-xs">
              {tab === 'Delta Exchange'
                ? [['USDT', '$12,450.00'], ['BTC', '0.2150'], ['ETH', '1.8500']].map(([asset, bal]) => (
                    <div key={asset} className="flex justify-between"><span className="text-gray-400">{asset}</span><span className="text-white font-medium">{bal}</span></div>
                  ))
                : [['USDT', '$8,320.00'], ['BTC', '0.1050'], ['ETH', '0.9200']].map(([asset, bal]) => (
                    <div key={asset} className="flex justify-between"><span className="text-gray-400">{asset}</span><span className="text-white font-medium">{bal}</span></div>
                  ))
              }
            </div>
          </div>

          {/* Funding Rates */}
          <div className="card mt-4">
            <h3 className="text-sm font-semibold text-gray-200 mb-3">Funding Rates</h3>
            <div className="space-y-1.5 text-xs">
              {[['BTC', '+0.0125%', '7h 23m'], ['ETH', '-0.0085%', '7h 23m'], ['SOL', '+0.0210%', '7h 23m']].map(([s, r, t]) => (
                <div key={s} className="flex justify-between items-center">
                  <span className="text-gray-400">{s}</span>
                  <span className={r.startsWith('+') ? 'text-emerald-400 font-medium' : 'text-red-400 font-medium'}>{r}</span>
                  <span className="text-gray-500">{t}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Positions */}
        <div className="lg:col-span-2 space-y-4">
          <PositionsTable exchange={tab} />

          {/* AI Signal for Crypto */}
          <div className="card border-blue-500/20">
            <h3 className="text-sm font-semibold text-gray-200 mb-3 flex items-center gap-2">
              <Zap size={14} className="text-blue-400" /> AI Crypto Signal
            </h3>
            <div className="grid grid-cols-2 gap-3 text-xs">
              {[
                { sym:'BTCUSD', sig:'LONG',  conf:78, vol:'52%', entry:'67,800', tp:'70,500', sl:'66,200' },
                { sym:'ETHUSD', sig:'SHORT', conf:65, vol:'68%', entry:'3,900',  tp:'3,600',  sl:'4,050'  },
              ].map(({ sym, sig, conf, vol, entry, tp, sl }) => (
                <div key={sym} className="bg-gray-800/60 rounded-lg p-3 space-y-1.5">
                  <div className="flex justify-between"><span className="font-medium text-white">{sym}</span><span className={sig==='LONG'?'badge-buy':'badge-sell'}>{sig}</span></div>
                  <div className="text-gray-400">Confidence: <span className="text-white">{conf}%</span></div>
                  <div className="text-gray-400">Vol regime: <span className="text-amber-400">{vol}</span></div>
                  <div className="text-gray-400">Entry: <span className="text-white">${entry}</span></div>
                  <div className="text-gray-400">TP / SL: <span className="text-emerald-400">${tp}</span> / <span className="text-red-400">${sl}</span></div>
                </div>
              ))}
            </div>
            <div className="mt-3 flex items-center gap-2 text-xs text-amber-400 bg-amber-900/20 border border-amber-500/20 rounded-lg px-3 py-2">
              <AlertTriangle size={12} /> AI signals are for reference only. Always validate with your own analysis.
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
