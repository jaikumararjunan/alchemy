import { useState, useEffect, useRef, useMemo } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useAuth } from '@/context/AuthContext'
import LiveChart from '@/components/charts/LiveChart'
import { RefreshCw, AlertCircle, Lock, Wifi, TrendingUp, TrendingDown, Activity } from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'

const TICKER_SYMBOLS = ['BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT','XRPUSDT','DOGEUSDT']

// ── Live multi-ticker via single combined WS ─────────────────────────────────
function MultiTicker({ onSelect, selected }) {
  const [tickers, setTickers] = useState({})
  const wsRef = useRef(null)

  useEffect(() => {
    const streams = TICKER_SYMBOLS.map(s => `${s.toLowerCase()}@miniTicker`).join('/')
    const ws = new WebSocket(`wss://stream.binance.com:9443/stream?streams=${streams}`)
    wsRef.current = ws
    ws.onmessage = e => {
      try {
        const { data: d } = JSON.parse(e.data)
        if (!d?.s) return
        setTickers(prev => ({
          ...prev,
          [d.s]: {
            price:     parseFloat(d.c),
            changePct: (parseFloat(d.c)-parseFloat(d.o))/parseFloat(d.o)*100,
          }
        }))
      } catch {}
    }
    return () => { ws.close() }
  }, [])

  return (
    <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-hide">
      {TICKER_SYMBOLS.map(sym => {
        const t  = tickers[sym]
        const up = (t?.changePct ?? 0) >= 0
        return (
          <button key={sym} onClick={() => onSelect(sym)}
            className={clsx(
              'flex-shrink-0 px-4 py-2.5 rounded-xl border transition-all text-left',
              selected === sym
                ? 'bg-blue-600/20 border-blue-500/50'
                : 'bg-gray-900/60 border-gray-800 hover:border-gray-600'
            )}>
            <div className="text-xs text-gray-500 mb-0.5">{sym.replace('USDT','')}</div>
            <div className="text-sm font-bold text-white font-mono">
              {t ? `$${t.price.toLocaleString(undefined,{maximumFractionDigits:2})}` : <span className="text-gray-700 animate-pulse">—</span>}
            </div>
            <div className={clsx('text-xs font-mono', up ? 'text-emerald-400':'text-red-400')}>
              {t ? `${up?'+':''}${t.changePct.toFixed(2)}%` : ''}
            </div>
          </button>
        )
      })}
    </div>
  )
}

// ── Real-time order book via WS ───────────────────────────────────────────────
function OrderBook({ symbol }) {
  const [book, setBook] = useState({ bids: [], asks: [] })
  const wsRef = useRef(null)

  useEffect(() => {
    if (!symbol) return
    if (wsRef.current) wsRef.current.close()
    const ws = new WebSocket(`wss://stream.binance.com:9443/ws/${symbol.toLowerCase()}@depth10@100ms`)
    wsRef.current = ws
    ws.onmessage = e => {
      try {
        const d = JSON.parse(e.data)
        setBook({
          bids: (d.bids||[]).slice(0,10).map(b=>({price:parseFloat(b[0]),size:parseFloat(b[1])})),
          asks: (d.asks||[]).slice(0,10).map(a=>({price:parseFloat(a[0]),size:parseFloat(a[1])})),
        })
      } catch {}
    }
    return () => ws.close()
  }, [symbol])

  const maxSize = Math.max(...book.bids.map(b=>b.size), ...book.asks.map(a=>a.size), 1)
  const spread  = book.asks[0]&&book.bids[0]
    ? (book.asks[0].price - book.bids[0].price).toFixed(2) : null
  const midPrice = book.asks[0]&&book.bids[0]
    ? ((book.asks[0].price+book.bids[0].price)/2) : null

  return (
    <div className="card h-full flex flex-col">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-white flex items-center gap-1.5">
          <Activity size={13} className="text-blue-400"/> Order Book
        </h3>
        {spread && <span className="text-xs text-gray-600">Spread: <span className="text-gray-400">{spread}</span></span>}
      </div>
      <div className="text-xs font-mono flex-1">
        <div className="flex justify-between text-gray-600 pb-1.5 border-b border-gray-800/60 text-[10px]">
          <span>Price (USDT)</span><span>Size</span>
        </div>
        <div className="space-y-0.5 mt-1">
          {book.asks.slice().reverse().map((a,i) => (
            <div key={i} className="relative flex justify-between items-center py-0.5 px-1 rounded overflow-hidden">
              <div className="absolute right-0 top-0 bottom-0 bg-red-500/10 rounded"
                   style={{width:`${(a.size/maxSize*100).toFixed(1)}%`}}/>
              <span className="relative text-red-400">{a.price.toLocaleString(undefined,{maximumFractionDigits:2})}</span>
              <span className="relative text-gray-500">{a.size.toFixed(4)}</span>
            </div>
          ))}
          <div className="border-y border-gray-700/50 my-1.5 py-1.5 text-center text-white font-bold text-sm">
            {midPrice ? `$${midPrice.toLocaleString(undefined,{maximumFractionDigits:2})}` : '—'}
          </div>
          {book.bids.map((b,i) => (
            <div key={i} className="relative flex justify-between items-center py-0.5 px-1 rounded overflow-hidden">
              <div className="absolute right-0 top-0 bottom-0 bg-emerald-500/10 rounded"
                   style={{width:`${(b.size/maxSize*100).toFixed(1)}%`}}/>
              <span className="relative text-emerald-400">{b.price.toLocaleString(undefined,{maximumFractionDigits:2})}</span>
              <span className="relative text-gray-500">{b.size.toFixed(4)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── Live trade feed via WS ────────────────────────────────────────────────────
function TradeFeed({ symbol }) {
  const [trades, setTrades] = useState([])
  const wsRef = useRef(null)

  useEffect(() => {
    if (!symbol) return
    if (wsRef.current) wsRef.current.close()
    setTrades([])
    const ws = new WebSocket(`wss://stream.binance.com:9443/ws/${symbol.toLowerCase()}@trade`)
    wsRef.current = ws
    ws.onmessage = e => {
      try {
        const d = JSON.parse(e.data)
        setTrades(prev => [{
          price: parseFloat(d.p),
          qty:   parseFloat(d.q),
          buy:   !d.m,
          time:  new Date(d.T).toLocaleTimeString([],{hour12:false}),
        }, ...prev].slice(0,30))
      } catch {}
    }
    return () => ws.close()
  }, [symbol])

  return (
    <div className="card h-full flex flex-col">
      <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-1.5">
        <Wifi size={13} className="text-emerald-400 animate-pulse"/> Live Trades
      </h3>
      <div className="text-xs font-mono flex-1 overflow-hidden">
        <div className="flex justify-between text-gray-600 pb-1.5 border-b border-gray-800/60 text-[10px]">
          <span>Price</span><span>Qty</span><span>Time</span>
        </div>
        <div className="space-y-0.5 mt-1">
          {trades.map((t,i) => (
            <div key={i} className="flex justify-between py-0.5">
              <span className={t.buy ? 'text-emerald-400':'text-red-400'}>
                {t.price.toLocaleString(undefined,{maximumFractionDigits:2})}
              </span>
              <span className="text-gray-500">{t.qty.toFixed(4)}</span>
              <span className="text-gray-700">{t.time}</span>
            </div>
          ))}
          {trades.length === 0 && (
            <div className="text-center py-4 text-gray-700 text-xs animate-pulse">Connecting…</div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Place Order ───────────────────────────────────────────────────────────────
function PlaceOrder({ exchange, symbol, tokens, api }) {
  const [form, setForm] = useState({ side:'BUY', type:'MARKET', qty:'', price:'', leverage:'1' })
  const token  = tokens[exchange]
  const isLive = token && !token.paper_trading

  const mut = useMutation({
    mutationFn: p => api.post(`/crypto/${exchange}/order`, p).then(r => r.data),
    onSuccess:  d => toast.success(`Order placed: ${d.order_id||'OK'}`),
    onError:    e => toast.error(e.response?.data?.detail || 'Order failed'),
  })

  if (!token) return (
    <div className="card flex flex-col items-center justify-center gap-2 py-8 text-center">
      <AlertCircle size={20} className="text-amber-400"/>
      <p className="text-sm text-gray-400">Connect {exchange} in Tokens page</p>
    </div>
  )

  if (!isLive) return (
    <div className="card flex flex-col items-center justify-center gap-2 py-8 text-center">
      <Lock size={20} className="text-gray-600"/>
      <p className="text-sm text-gray-400">Paper mode — read only</p>
      <p className="text-xs text-gray-600">Switch to Live in Tokens to trade</p>
      <div className="mt-2 px-3 py-2 bg-blue-900/20 rounded-xl text-xs text-blue-400">
        Live prices ✓ · Orders blocked in paper mode
      </div>
    </div>
  )

  return (
    <div className="card space-y-3">
      <h3 className="text-sm font-semibold text-white">Place Order</h3>
      <div className="text-xs text-white font-mono bg-gray-900/60 px-2 py-1.5 rounded-lg">{symbol}</div>
      <div className="grid grid-cols-2 gap-1">
        {['BUY','SELL'].map(s => (
          <button key={s} onClick={()=>setForm(f=>({...f,side:s}))}
            className={clsx('py-2.5 rounded-xl text-xs font-bold transition-colors',
              form.side===s
                ? s==='BUY'?'bg-emerald-600 text-white':'bg-red-600 text-white'
                : 'bg-gray-800 text-gray-400 hover:bg-gray-700')}>
            {s}
          </button>
        ))}
      </div>
      <select value={form.type} onChange={e=>setForm(f=>({...f,type:e.target.value}))}
        className="input-field text-xs w-full">
        <option value="MARKET">Market</option>
        <option value="LIMIT">Limit</option>
      </select>
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="text-xs text-gray-500">Quantity</label>
          <input type="number" value={form.qty} placeholder="0.001" min="0" step="0.001"
            onChange={e=>setForm(f=>({...f,qty:e.target.value}))}
            className="input-field text-xs mt-1 w-full"/>
        </div>
        <div>
          <label className="text-xs text-gray-500">Leverage</label>
          <input type="number" value={form.leverage} min="1" max="100"
            onChange={e=>setForm(f=>({...f,leverage:e.target.value}))}
            className="input-field text-xs mt-1 w-full"/>
        </div>
      </div>
      {form.type==='LIMIT' && (
        <div>
          <label className="text-xs text-gray-500">Limit Price</label>
          <input type="number" value={form.price}
            onChange={e=>setForm(f=>({...f,price:e.target.value}))}
            className="input-field text-xs mt-1 w-full"/>
        </div>
      )}
      <button
        onClick={()=>mut.mutate({
          symbol, side:form.side, size:parseFloat(form.qty)||0,
          order_type:form.type==='MARKET'?'market_order':'limit_order',
          leverage:parseInt(form.leverage)||1,
          price:form.price?parseFloat(form.price):undefined,
        })}
        disabled={mut.isPending || !form.qty || parseFloat(form.qty)<=0}
        className={clsx('w-full py-3 rounded-xl text-sm font-bold text-white flex items-center justify-center gap-2 transition-all',
          form.side==='BUY'?'bg-emerald-600 hover:bg-emerald-500':'bg-red-600 hover:bg-red-500',
          (mut.isPending||!form.qty)?'opacity-50 cursor-not-allowed':'')}>
        {mut.isPending && <RefreshCw size={14} className="animate-spin"/>}
        {form.side} {symbol}
      </button>
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function CryptoPage() {
  const { apiClient } = useAuth()
  const api = useMemo(() => apiClient(), [apiClient])

  const [chartSymbol,    setChartSymbol]    = useState('BTCUSDT')
  const [activeExchange, setActiveExchange] = useState('binance')

  const { data: tokenData } = useQuery({
    queryKey: ['token-status'],
    queryFn:  () => api.get('/tokens/status').then(r=>r.data).catch(()=>({tokens:{}})),
    refetchInterval: 60000,
  })
  const tokens = tokenData?.tokens || {}

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-xl font-bold text-white">Crypto Markets</h1>
          <p className="text-sm text-gray-500 flex items-center gap-1.5">
            <Wifi size={11} className="text-emerald-400"/>
            Live data · Binance WebSocket · No API key required
          </p>
        </div>
        <div className="flex gap-1 bg-gray-900 rounded-xl p-1">
          {['binance','delta'].map(ex => (
            <button key={ex} onClick={()=>setActiveExchange(ex)}
              className={clsx('px-4 py-1.5 rounded-lg text-xs font-medium capitalize transition-colors',
                activeExchange===ex?'bg-blue-600 text-white':'text-gray-400 hover:text-white')}>
              {ex}
              {tokens[ex] && (
                <span className="ml-1.5 w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block animate-pulse"/>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Multi-symbol live ticker strip */}
      <MultiTicker onSelect={setChartSymbol} selected={chartSymbol}/>

      {/* Main chart */}
      <div className="card overflow-hidden">
        <LiveChart defaultSymbol={chartSymbol} height={300}/>
      </div>

      {/* Order book · Trade feed · Order form */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <OrderBook symbol={chartSymbol}/>
        <TradeFeed symbol={chartSymbol}/>
        <PlaceOrder exchange={activeExchange} symbol={chartSymbol} tokens={tokens} api={api}/>
      </div>
    </div>
  )
}
