import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useAuth } from '@/context/AuthContext'
import { RefreshCw, TrendingUp, TrendingDown, Activity, Zap, AlertCircle } from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'

const SYMBOLS = {
  delta:   ['BTCUSD','ETHUSD','SOLUSDT','BNBUSDT','XRPUSDT'],
  binance: ['BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT','XRPUSDT'],
}

function PriceCard({ symbol, exchange, api }) {
  const { data, isLoading, refetch, isRefetching } = useQuery({
    queryKey: ['ticker', exchange, symbol],
    queryFn: () => api.get(`/crypto/${exchange}/ticker/${symbol}`).then(r => r.data),
    refetchInterval: 10000,
  })

  const price  = data?.mark_price || data?.price || data?.lastPrice || '—'
  const change = data?.change_24h || data?.priceChangePercent || null
  const up     = parseFloat(change) >= 0

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-2">
        <div>
          <div className="text-sm font-bold text-white">{symbol}</div>
          <div className="text-xs text-gray-500 capitalize">{exchange}</div>
        </div>
        <button onClick={() => refetch()} className="text-gray-600 hover:text-gray-300">
          <RefreshCw size={12} className={isRefetching ? 'animate-spin' : ''}/>
        </button>
      </div>
      {isLoading ? (
        <div className="animate-pulse h-6 bg-gray-800 rounded w-24"/>
      ) : (
        <>
          <div className="text-xl font-bold text-white">
            ${parseFloat(price).toLocaleString(undefined, {maximumFractionDigits: 2})}
          </div>
          {change != null && (
            <div className={clsx('flex items-center gap-1 text-xs mt-1', up ? 'text-emerald-400':'text-red-400')}>
              {up ? <TrendingUp size={11}/> : <TrendingDown size={11}/>}
              {up ? '+' : ''}{parseFloat(change).toFixed(2)}%
            </div>
          )}
          {data?.volume_24h && (
            <div className="text-xs text-gray-600 mt-1">
              Vol: {parseFloat(data.volume_24h).toLocaleString(undefined,{maximumFractionDigits:0})}
            </div>
          )}
        </>
      )}
    </div>
  )
}

function OrderBook({ symbol, exchange, api }) {
  const { data, isLoading } = useQuery({
    queryKey: ['orderbook', exchange, symbol],
    queryFn: () => api.get(`/crypto/${exchange}/orderbook/${symbol}?depth=8`).then(r => r.data),
    refetchInterval: 5000,
    enabled: !!symbol,
  })

  const bids = data?.buy || data?.bids || []
  const asks = data?.sell || data?.asks || []

  return (
    <div className="card h-full">
      <h3 className="text-sm font-semibold text-white mb-3">{symbol} Order Book</h3>
      {isLoading ? (
        <div className="animate-pulse space-y-1">{Array(6).fill(0).map((_,i) => (
          <div key={i} className="h-4 bg-gray-800 rounded"/>
        ))}</div>
      ) : (
        <div className="text-xs font-mono">
          <div className="flex justify-between text-gray-500 mb-1 pb-1 border-b border-gray-800">
            <span>Price</span><span>Size</span>
          </div>
          {asks.slice(0,6).reverse().map((a,i) => (
            <div key={i} className="flex justify-between text-red-400 py-0.5">
              <span>{parseFloat(a.price || a[0]).toLocaleString()}</span>
              <span className="text-gray-400">{parseFloat(a.size || a[1]).toFixed(3)}</span>
            </div>
          ))}
          <div className="border-t border-b border-gray-700 my-1 py-1 text-center text-white text-sm font-bold">
            {bids[0] && asks[0] ? (
              ((parseFloat(bids[0].price || bids[0][0]) + parseFloat(asks[0].price || asks[0][0]))/2).toLocaleString()
            ) : '—'}
          </div>
          {bids.slice(0,6).map((b,i) => (
            <div key={i} className="flex justify-between text-emerald-400 py-0.5">
              <span>{parseFloat(b.price || b[0]).toLocaleString()}</span>
              <span className="text-gray-400">{parseFloat(b.size || b[1]).toFixed(3)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function PlaceOrder({ exchange, api, tokens }) {
  const [form, setForm] = useState({ symbol:'BTCUSD', side:'buy', size:'1', order_type:'market_order', leverage:'1' })
  const token = tokens[exchange]

  const mut = useMutation({
    mutationFn: (payload) => api.post(`/crypto/${exchange}/order`, payload).then(r => r.data),
    onSuccess: (d) => toast.success(`Order placed: ${JSON.stringify(d).slice(0,80)}`),
    onError: (e) => toast.error(e.response?.data?.detail || 'Order failed'),
  })

  const handleSubmit = () => {
    if (!token) { toast.error(`Connect ${exchange} first in Tokens`); return }
    mut.mutate({ ...form, size: parseFloat(form.size), leverage: parseInt(form.leverage) })
  }

  return (
    <div className="card">
      <h3 className="text-sm font-semibold text-white mb-3 capitalize">{exchange} — Place Order</h3>
      {!token ? (
        <div className="text-xs text-amber-400 flex items-center gap-1.5 p-3 bg-amber-900/20 rounded-lg">
          <AlertCircle size={12}/> Connect {exchange} in the Tokens page first
        </div>
      ) : (
        <div className="space-y-3">
          <div>
            <label className="text-xs text-gray-400">Symbol</label>
            <select value={form.symbol} onChange={e=>setForm(f=>({...f,symbol:e.target.value}))}
              className="input-field text-xs mt-1 w-full">
              {SYMBOLS[exchange]?.map(s => <option key={s}>{s}</option>)}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-xs text-gray-400">Side</label>
              <select value={form.side} onChange={e=>setForm(f=>({...f,side:e.target.value}))}
                className={clsx('input-field text-xs mt-1 w-full font-bold',
                  form.side==='buy'||form.side==='BUY' ? 'text-emerald-400':'text-red-400')}>
                <option value="buy">BUY</option>
                <option value="sell">SELL</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-400">Type</label>
              <select value={form.order_type} onChange={e=>setForm(f=>({...f,order_type:e.target.value}))}
                className="input-field text-xs mt-1 w-full">
                <option value="market_order">Market</option>
                <option value="limit_order">Limit</option>
              </select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-xs text-gray-400">Size</label>
              <input type="number" value={form.size} onChange={e=>setForm(f=>({...f,size:e.target.value}))}
                className="input-field text-xs mt-1 w-full" min="0.001" step="0.001"/>
            </div>
            <div>
              <label className="text-xs text-gray-400">Leverage</label>
              <input type="number" value={form.leverage} onChange={e=>setForm(f=>({...f,leverage:e.target.value}))}
                className="input-field text-xs mt-1 w-full" min="1" max="100"/>
            </div>
          </div>
          {token?.paper_trading && (
            <div className="text-xs text-blue-400 bg-blue-900/20 px-2 py-1.5 rounded-lg">
              Paper mode — no real money
            </div>
          )}
          <button onClick={handleSubmit} disabled={mut.isPending}
            className={clsx('w-full py-2.5 rounded-xl text-xs font-bold text-white transition-colors flex items-center justify-center gap-2',
              form.side==='buy'||form.side==='BUY' ? 'bg-emerald-600 hover:bg-emerald-500' : 'bg-red-600 hover:bg-red-500')}>
            {mut.isPending ? <RefreshCw size={12} className="animate-spin"/> : null}
            {form.side?.toUpperCase()} {form.symbol}
          </button>
        </div>
      )}
    </div>
  )
}

export default function CryptoPage() {
  const { apiClient } = useAuth()
  const api = apiClient()
  const [activeTab, setActiveTab] = useState('delta')

  const { data: tokenData } = useQuery({
    queryKey: ['token-status'],
    queryFn: () => api.get('/tokens/status').then(r => r.data).catch(() => ({ tokens: {} })),
  })
  const tokens = tokenData?.tokens || {}

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">Crypto Trading</h1>
          <p className="text-sm text-gray-400">Live market data · Delta Exchange & Binance</p>
        </div>
        <div className="flex gap-1">
          {['delta','binance'].map(ex => (
            <button key={ex} onClick={() => setActiveTab(ex)}
              className={clsx('px-4 py-1.5 rounded-lg text-xs font-medium capitalize transition-colors',
                activeTab===ex ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700')}>
              {ex}
              {tokens[ex] && (
                <span className="ml-1.5 w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block animate-pulse"/>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Price cards */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        {SYMBOLS[activeTab].map(sym => (
          <PriceCard key={sym} symbol={sym} exchange={activeTab} api={api}/>
        ))}
      </div>

      {/* Order book + Trade panel */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2">
          <OrderBook symbol={SYMBOLS[activeTab][0]} exchange={activeTab} api={api}/>
        </div>
        <PlaceOrder exchange={activeTab} api={api} tokens={tokens}/>
      </div>
    </div>
  )
}
