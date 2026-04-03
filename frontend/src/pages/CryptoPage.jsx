import { useState, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/context/AuthContext'
import LiveChart from '@/components/charts/LiveChart'
import { RefreshCw, AlertCircle, Lock, Wifi, TrendingUp, TrendingDown } from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'

const EXCHANGE_SYMBOLS = {
  delta:   { symbols: ['BTCUSDT','ETHUSDT','SOLUSDT'], suffix: '' },
  binance: { symbols: ['BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT','XRPUSDT'], suffix: 'USDT' },
}

// ── Live Order Book from Binance public WS ────────────────────────────────────
function OrderBook({ symbol }) {
  const [book, setBook] = useState({ bids: [], asks: [] })
  const wsRef = useRef(null)

  useEffect(() => {
    if (wsRef.current) wsRef.current.close()
    const ws = new WebSocket(`wss://stream.binance.com:9443/ws/${symbol.toLowerCase()}@depth10@100ms`)
    wsRef.current = ws
    ws.onmessage = e => {
      const d = JSON.parse(e.data)
      setBook({
        bids: (d.bids || []).slice(0, 8).map(b => ({ price: parseFloat(b[0]), size: parseFloat(b[1]) })),
        asks: (d.asks || []).slice(0, 8).map(a => ({ price: parseFloat(a[0]), size: parseFloat(a[1]) })),
      })
    }
    return () => ws.close()
  }, [symbol])

  const maxSize = Math.max(...book.bids.map(b => b.size), ...book.asks.map(a => a.size), 1)
  const spread = book.asks[0] && book.bids[0]
    ? (book.asks[0].price - book.bids[0].price).toFixed(2)
    : null

  return (
    <div className="card h-full">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-white">Order Book</h3>
        {spread && <span className="text-xs text-gray-500">Spread: {spread}</span>}
      </div>
      <div className="text-xs font-mono space-y-0.5">
        <div className="flex justify-between text-gray-600 pb-1 border-b border-gray-800 text-[10px]">
          <span>Price (USDT)</span><span>Size</span>
        </div>
        {book.asks.slice().reverse().map((a, i) => (
          <div key={i} className="relative flex justify-between text-red-400 py-0.5">
            <div className="absolute inset-0 bg-red-500/10 rounded"
                 style={{ width: `${(a.size / maxSize) * 100}%` }}/>
            <span className="relative z-10">{a.price.toLocaleString()}</span>
            <span className="relative z-10 text-gray-400">{a.size.toFixed(4)}</span>
          </div>
        ))}
        <div className="border-t border-b border-gray-700 my-1 py-1 text-center text-white font-bold text-sm">
          {book.bids[0]?.price.toLocaleString() ?? '—'}
        </div>
        {book.bids.map((b, i) => (
          <div key={i} className="relative flex justify-between text-emerald-400 py-0.5">
            <div className="absolute inset-0 bg-emerald-500/10 rounded"
                 style={{ width: `${(b.size / maxSize) * 100}%` }}/>
            <span className="relative z-10">{b.price.toLocaleString()}</span>
            <span className="relative z-10 text-gray-400">{b.size.toFixed(4)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Recent Trades from Binance public WS ──────────────────────────────────────
function RecentTrades({ symbol }) {
  const [trades, setTrades] = useState([])
  const wsRef = useRef(null)

  useEffect(() => {
    if (wsRef.current) wsRef.current.close()
    const ws = new WebSocket(`wss://stream.binance.com:9443/ws/${symbol.toLowerCase()}@trade`)
    wsRef.current = ws
    ws.onmessage = e => {
      const d = JSON.parse(e.data)
      setTrades(prev => [{
        price: parseFloat(d.p),
        qty:   parseFloat(d.q),
        side:  d.m ? 'sell' : 'buy',   // m=true means market maker (sell)
        time:  new Date(d.T).toLocaleTimeString([], { hour12: false }),
      }, ...prev].slice(0, 25))
    }
    return () => ws.close()
  }, [symbol])

  return (
    <div className="card h-full">
      <h3 className="text-sm font-semibold text-white mb-3">Recent Trades</h3>
      <div className="text-xs font-mono space-y-0.5 max-h-64 overflow-hidden">
        <div className="flex justify-between text-gray-600 pb-1 border-b border-gray-800 text-[10px]">
          <span>Price</span><span>Qty</span><span>Time</span>
        </div>
        {trades.map((t, i) => (
          <div key={i} className="flex justify-between py-0.5">
            <span className={t.side === 'buy' ? 'text-emerald-400' : 'text-red-400'}>
              {t.price.toLocaleString()}
            </span>
            <span className="text-gray-400">{t.qty.toFixed(4)}</span>
            <span className="text-gray-600">{t.time}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Place Order (live only) ───────────────────────────────────────────────────
function PlaceOrder({ exchange, api, tokens, symbol }) {
  const [form, setForm] = useState({
    side: 'BUY', type: 'MARKET', qty: '', price: '', leverage: '1'
  })
  const token = tokens[exchange]
  const isLive = token && !token.paper_trading

  const mut = useMutation({
    mutationFn: (payload) => api.post(`/crypto/${exchange}/order`, payload).then(r => r.data),
    onSuccess: (d) => toast.success(`Order placed: ${JSON.stringify(d).slice(0, 80)}`),
    onError: (e) => toast.error(e.response?.data?.detail || 'Order failed'),
  })

  if (!token) return (
    <div className="card flex items-center gap-2 text-amber-400 text-sm">
      <AlertCircle size={16}/> Connect {exchange} in Tokens page
    </div>
  )

  if (!isLive) return (
    <div className="card text-center py-6">
      <Lock size={24} className="mx-auto mb-2 text-gray-600"/>
      <p className="text-sm text-gray-400">Paper mode — read only</p>
      <p className="text-xs text-gray-600 mt-1">Switch to Live mode in Tokens to trade</p>
      <div className="mt-3 p-2 bg-blue-900/20 rounded-lg text-xs text-blue-400">
        Live prices streaming from exchange ✓<br/>Buy/Sell requires live credentials
      </div>
    </div>
  )

  return (
    <div className="card space-y-3">
      <h3 className="text-sm font-semibold text-white">Place Order — {symbol}</h3>
      <div className="grid grid-cols-2 gap-1">
        {['BUY','SELL'].map(s => (
          <button key={s} onClick={() => setForm(f => ({...f, side: s}))}
            className={clsx('py-2 rounded-xl text-xs font-bold transition-colors',
              form.side === s
                ? s === 'BUY' ? 'bg-emerald-600 text-white' : 'bg-red-600 text-white'
                : 'bg-gray-800 text-gray-400')}>
            {s}
          </button>
        ))}
      </div>
      <div>
        <label className="text-xs text-gray-400">Order Type</label>
        <select value={form.type} onChange={e => setForm(f => ({...f, type: e.target.value}))}
          className="input-field text-xs mt-1 w-full">
          <option value="MARKET">Market</option>
          <option value="LIMIT">Limit</option>
        </select>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="text-xs text-gray-400">Quantity</label>
          <input type="number" value={form.qty} placeholder="0.001"
            onChange={e => setForm(f => ({...f, qty: e.target.value}))}
            className="input-field text-xs mt-1 w-full" min="0" step="0.001"/>
        </div>
        {form.type === 'LIMIT' && (
          <div>
            <label className="text-xs text-gray-400">Price</label>
            <input type="number" value={form.price} placeholder="Market"
              onChange={e => setForm(f => ({...f, price: e.target.value}))}
              className="input-field text-xs mt-1 w-full"/>
          </div>
        )}
        <div>
          <label className="text-xs text-gray-400">Leverage</label>
          <input type="number" value={form.leverage} min="1" max="100"
            onChange={e => setForm(f => ({...f, leverage: e.target.value}))}
            className="input-field text-xs mt-1 w-full"/>
        </div>
      </div>
      <button onClick={() => mut.mutate({
          symbol, side: form.side, size: parseFloat(form.qty),
          order_type: form.type === 'MARKET' ? 'market_order' : 'limit_order',
          leverage: parseInt(form.leverage), price: form.price ? parseFloat(form.price) : undefined,
        })}
        disabled={mut.isPending || !form.qty}
        className={clsx('w-full py-3 rounded-xl text-sm font-bold text-white transition-all flex items-center justify-center gap-2',
          form.side === 'BUY' ? 'bg-emerald-600 hover:bg-emerald-500' : 'bg-red-600 hover:bg-red-500',
          (!form.qty || mut.isPending) && 'opacity-50 cursor-not-allowed')}>
        {mut.isPending ? <RefreshCw size={14} className="animate-spin"/> : null}
        {form.side} {symbol}
      </button>
    </div>
  )
}

// ── Mini ticker for multiple symbols ─────────────────────────────────────────
function MultiTicker({ symbols }) {
  const [tickers, setTickers] = useState({})
  const wsRef = useRef(null)

  useEffect(() => {
    if (wsRef.current) wsRef.current.close()
    const streams = symbols.map(s => `${s.toLowerCase()}@miniTicker`).join('/')
    const ws = new WebSocket(`wss://stream.binance.com:9443/stream?streams=${streams}`)
    wsRef.current = ws
    ws.onmessage = e => {
      const { data: d } = JSON.parse(e.data)
      if (!d?.s) return
      setTickers(prev => ({
        ...prev,
        [d.s]: {
          price: parseFloat(d.c),
          change: ((parseFloat(d.c) - parseFloat(d.o)) / parseFloat(d.o) * 100),
        }
      }))
    }
    return () => ws.close()
  }, [symbols.join(',')])

  return (
    <div className="flex gap-2 overflow-x-auto pb-1">
      {symbols.map(sym => {
        const t = tickers[sym]
        const up = (t?.change ?? 0) >= 0
        return (
          <div key={sym} className="card-sm flex-shrink-0 min-w-[120px]">
            <div className="text-xs text-gray-500">{sym.replace('USDT','')}</div>
            <div className="text-sm font-bold text-white">
              {t?.price?.toLocaleString(undefined, { maximumFractionDigits: 2 }) ?? <span className="text-gray-600 animate-pulse">…</span>}
            </div>
            <div className={clsx('text-xs', up ? 'text-emerald-400' : 'text-red-400')}>
              {t ? `${up ? '+' : ''}${t.change.toFixed(2)}%` : '—'}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function CryptoPage() {
  const { apiClient } = useAuth()
  const api = apiClient()
  const [chartSymbol, setChartSymbol] = useState('BTCUSDT')
  const [activeExchange, setActiveExchange] = useState('binance')

  const { data: tokenData } = useQuery({
    queryKey: ['token-status'],
    queryFn: () => api.get('/tokens/status').then(r => r.data).catch(() => ({ tokens: {} })),
    refetchInterval: 60000,
  })
  const tokens = tokenData?.tokens || {}
  const tickerSymbols = ['BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT','XRPUSDT','DOGEUSDT']

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">Crypto Markets</h1>
          <p className="text-sm text-gray-400 flex items-center gap-1.5">
            <Wifi size={11} className="text-emerald-400"/>
            Live data from Binance WebSocket — no API key required
          </p>
        </div>
        <div className="flex gap-1">
          {['binance','delta'].map(ex => (
            <button key={ex} onClick={() => setActiveExchange(ex)}
              className={clsx('px-3 py-1.5 rounded-lg text-xs font-medium capitalize transition-colors',
                activeExchange === ex ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400')}>
              {ex} {tokens[ex] && <span className="ml-1 w-1.5 h-1.5 bg-emerald-400 rounded-full inline-block"/>}
            </button>
          ))}
        </div>
      </div>

      {/* Multi-symbol ticker strip — always live */}
      <MultiTicker symbols={tickerSymbols}/>

      {/* Main chart — always live via Binance public WS */}
      <div className="card">
        <LiveChart defaultSymbol={chartSymbol}/>
      </div>

      {/* Order book + trades + order panel */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <OrderBook    symbol={chartSymbol}/>
        <RecentTrades symbol={chartSymbol}/>
        <PlaceOrder   exchange={activeExchange} api={api} tokens={tokens} symbol={chartSymbol}/>
      </div>
    </div>
  )
}
