/**
 * LiveChart.jsx
 * Interactive candlestick chart using Binance public WebSocket streams.
 * No API key required — uses public market data feeds.
 *
 * Binance WS: wss://stream.binance.com:9443/ws/<symbol>@kline_<interval>
 * Docs: https://developers.binance.com/docs/binance-spot-api-docs/web-socket-streams
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import {
  ComposedChart, CandlestickChart, Bar, Line, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, Area,
} from 'recharts'
import { RefreshCw, Wifi, WifiOff, TrendingUp, TrendingDown, Activity } from 'lucide-react'
import clsx from 'clsx'

const SYMBOLS = ['BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT','XRPUSDT','DOGEUSDT','ADAUSDT']
const INTERVALS = [
  { label: '1m',  ws: '1m',  rest: '1m',  ms: 60000 },
  { label: '5m',  ws: '5m',  rest: '5m',  ms: 300000 },
  { label: '15m', ws: '15m', rest: '15m', ms: 900000 },
  { label: '1h',  ws: '1h',  rest: '1h',  ms: 3600000 },
  { label: '4h',  ws: '4h',  rest: '4h',  ms: 14400000 },
  { label: '1d',  ws: '1d',  rest: '1d',  ms: 86400000 },
]

// ── RSI calculation ───────────────────────────────────────────────────────────
function calcRSI(closes, period = 14) {
  if (closes.length < period + 1) return closes.map(() => null)
  const results = new Array(period).fill(null)
  let gains = 0, losses = 0
  for (let i = 1; i <= period; i++) {
    const d = closes[i] - closes[i - 1]
    if (d > 0) gains += d; else losses -= d
  }
  let avgGain = gains / period
  let avgLoss = losses / period
  results.push(avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss))
  for (let i = period + 1; i < closes.length; i++) {
    const d = closes[i] - closes[i - 1]
    avgGain = (avgGain * (period - 1) + Math.max(d, 0)) / period
    avgLoss = (avgLoss * (period - 1) + Math.max(-d, 0)) / period
    results.push(avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss))
  }
  return results
}

// ── EMA calculation ───────────────────────────────────────────────────────────
function calcEMA(values, period) {
  const k = 2 / (period + 1)
  const result = []
  let ema = null
  for (const v of values) {
    if (ema === null) { ema = v }
    else { ema = v * k + ema * (1 - k) }
    result.push(ema)
  }
  return result
}

// ── MACD calculation ──────────────────────────────────────────────────────────
function calcMACD(closes) {
  if (closes.length < 26) return closes.map(() => ({ macd: null, signal: null, hist: null }))
  const ema12 = calcEMA(closes, 12)
  const ema26 = calcEMA(closes, 26)
  const macdLine = ema12.map((v, i) => v - ema26[i])
  const signalLine = calcEMA(macdLine.slice(25), 9)
  return macdLine.map((v, i) => ({
    macd: i >= 25 ? parseFloat(v.toFixed(4)) : null,
    signal: i >= 25 ? parseFloat(signalLine[i - 25]?.toFixed(4) ?? null) : null,
    hist: i >= 25 && signalLine[i - 25] != null
      ? parseFloat((v - signalLine[i - 25]).toFixed(4))
      : null,
  }))
}

// ── Bollinger Bands ───────────────────────────────────────────────────────────
function calcBB(closes, period = 20, stdMult = 2) {
  return closes.map((_, i) => {
    if (i < period - 1) return { mid: null, upper: null, lower: null }
    const slice = closes.slice(i - period + 1, i + 1)
    const mean = slice.reduce((a, b) => a + b, 0) / period
    const std = Math.sqrt(slice.reduce((a, b) => a + (b - mean) ** 2, 0) / period)
    return {
      mid:   parseFloat(mean.toFixed(2)),
      upper: parseFloat((mean + stdMult * std).toFixed(2)),
      lower: parseFloat((mean - stdMult * std).toFixed(2)),
    }
  })
}

// ── Custom OHLC bar ───────────────────────────────────────────────────────────
function OHLCBar({ x, y, width, height, payload }) {
  if (!payload) return null
  const { open, high, low, close, time } = payload
  if ([open, high, low, close].some(v => v == null)) return null

  const isUp = close >= open
  const color = isUp ? '#10B981' : '#EF4444'
  const bodyTop = Math.min(open, close)
  const bodyBot = Math.max(open, close)

  // We don't have yScale here so we compute manually via the chart's y domain
  // recharts passes the computed pixel values through the bar shape
  // For a composed chart we use a Bar with a custom shape
  return (
    <g>
      <line x1={x + width / 2} y1={y} x2={x + width / 2} y2={y + height}
        stroke={color} strokeWidth={1} />
      <rect x={x + 1} y={y} width={Math.max(width - 2, 1)} height={height}
        fill={color} opacity={0.9} />
    </g>
  )
}

// ── Tooltip formatter ─────────────────────────────────────────────────────────
function CandleTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0]?.payload
  if (!d) return null
  const isUp = d.close >= d.open
  return (
    <div className="bg-gray-900 border border-gray-700 rounded-xl p-3 text-xs shadow-xl">
      <div className="text-gray-400 mb-1">{d.time}</div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-0.5">
        {[['O', d.open], ['H', d.high], ['L', d.low], ['C', d.close]].map(([k, v]) => (
          <div key={k} className="flex justify-between gap-2">
            <span className="text-gray-500">{k}</span>
            <span className={k === 'C' ? (isUp ? 'text-emerald-400' : 'text-red-400') : 'text-white'}>
              {v?.toLocaleString(undefined, { maximumFractionDigits: 2 })}
            </span>
          </div>
        ))}
      </div>
      {d.volume != null && (
        <div className="mt-1 text-gray-500">Vol: {(d.volume / 1e6).toFixed(2)}M</div>
      )}
    </div>
  )
}

// ── Main chart component ──────────────────────────────────────────────────────
export default function LiveChart({ defaultSymbol = 'BTCUSDT' }) {
  const [symbol,   setSymbol]   = useState(defaultSymbol)
  const [interval, setInterval] = useState(INTERVALS[0])
  const [candles,  setCandles]  = useState([])    // [{time,open,high,low,close,volume}]
  const [ticker,   setTicker]   = useState(null)  // current ticker data
  const [connected, setConnected] = useState(false)
  const [indicator, setIndicator] = useState('RSI') // RSI | MACD | BB | none
  const [loading,  setLoading]  = useState(true)

  const wsRef     = useRef(null)
  const candleMap = useRef({})  // key = openTime, deduped

  // ── Load historical klines via REST ─────────────────────────────────────────
  const loadHistory = useCallback(async (sym, intv) => {
    setLoading(true)
    try {
      const base = 'https://api.binance.com'
      const url  = `${base}/api/v3/klines?symbol=${sym}&interval=${intv.rest}&limit=200`
      const r    = await fetch(url)
      const data = await r.json()
      if (!Array.isArray(data)) return
      const parsed = data.map(k => ({
        time:   new Date(k[0]).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false }),
        openTime: k[0],
        open:   parseFloat(k[1]),
        high:   parseFloat(k[2]),
        low:    parseFloat(k[3]),
        close:  parseFloat(k[4]),
        volume: parseFloat(k[5]),
      }))
      candleMap.current = {}
      parsed.forEach(c => { candleMap.current[c.openTime] = c })
      setCandles(parsed)
    } catch (e) {
      console.error('klines error', e)
    } finally {
      setLoading(false)
    }
  }, [])

  // ── WebSocket live feed ──────────────────────────────────────────────────────
  const connectWS = useCallback((sym, intv) => {
    if (wsRef.current) wsRef.current.close()
    // Combine kline + mini-ticker in one stream
    const stream = `${sym.toLowerCase()}@kline_${intv.ws}/${sym.toLowerCase()}@miniTicker`
    const ws = new WebSocket(`wss://stream.binance.com:9443/stream?streams=${stream}`)
    wsRef.current = ws

    ws.onopen  = () => setConnected(true)
    ws.onclose = () => { setConnected(false) }
    ws.onerror = () => setConnected(false)

    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data)
      const { stream: s, data: d } = msg

      if (s?.includes('kline')) {
        const k = d.k
        const candle = {
          time:     new Date(k.t).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false }),
          openTime: k.t,
          open:     parseFloat(k.o),
          high:     parseFloat(k.h),
          low:      parseFloat(k.l),
          close:    parseFloat(k.c),
          volume:   parseFloat(k.v),
        }
        candleMap.current[k.t] = candle
        setCandles(Object.values(candleMap.current).sort((a, b) => a.openTime - b.openTime))
      }

      if (s?.includes('miniTicker')) {
        setTicker({
          price:     parseFloat(d.c),
          open:      parseFloat(d.o),
          high:      parseFloat(d.h),
          low:       parseFloat(d.l),
          volume:    parseFloat(d.v),
          change:    parseFloat(d.c) - parseFloat(d.o),
          changePct: ((parseFloat(d.c) - parseFloat(d.o)) / parseFloat(d.o) * 100),
        })
      }
    }
  }, [])

  useEffect(() => {
    loadHistory(symbol, interval)
    connectWS(symbol, interval)
    return () => { if (wsRef.current) wsRef.current.close() }
  }, [symbol, interval])

  // ── Enrich candles with indicators ──────────────────────────────────────────
  const closes  = candles.map(c => c.close)
  const rsiVals = calcRSI(closes)
  const macdVals = calcMACD(closes)
  const bbVals  = calcBB(closes)

  const enriched = candles.map((c, i) => ({
    ...c,
    rsi:    rsiVals[i] ? parseFloat(rsiVals[i].toFixed(1)) : null,
    macd:   macdVals[i]?.macd,
    signal: macdVals[i]?.signal,
    hist:   macdVals[i]?.hist,
    bbMid:  bbVals[i]?.mid,
    bbUp:   bbVals[i]?.upper,
    bbLow:  bbVals[i]?.lower,
    // Encode OHLC as single value for bar chart (use close for y-axis domain)
    ohlcHigh: c.high,
    ohlcLow:  c.low,
    ohlcMid:  c.close,
    // Price range for bar: bottom=low, bar height=high-low
    barBottom: c.low,
    barRange:  c.high - c.low,
    // Color-coded close vs open
    bullish: c.close >= c.open,
  }))

  const priceMin = enriched.length ? Math.min(...enriched.map(c => c.low))  * 0.9995 : 0
  const priceMax = enriched.length ? Math.max(...enriched.map(c => c.high)) * 1.0005 : 1

  const isUp = (ticker?.changePct ?? 0) >= 0

  const ttStyle = {
    background: '#1e293b', border: '1px solid #334155',
    borderRadius: '10px', color: '#f1f5f9',
  }

  return (
    <div className="space-y-3">
      {/* Ticker strip */}
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-2xl font-bold text-white">
              {ticker?.price?.toLocaleString(undefined, { maximumFractionDigits: 2 }) ?? '…'}
            </span>
            <span className={clsx('text-sm font-semibold px-2 py-0.5 rounded',
              isUp ? 'text-emerald-400 bg-emerald-900/30' : 'text-red-400 bg-red-900/30')}>
              {isUp ? '+' : ''}{ticker?.changePct?.toFixed(2) ?? '0.00'}%
            </span>
            <span className={clsx('w-2 h-2 rounded-full', connected ? 'bg-emerald-400 animate-pulse' : 'bg-gray-600')}/>
          </div>
          <div className="flex gap-4 text-xs text-gray-500 mt-0.5">
            <span>H: {ticker?.high?.toLocaleString()}</span>
            <span>L: {ticker?.low?.toLocaleString()}</span>
            <span>Vol: {ticker?.volume ? (ticker.volume / 1e6).toFixed(2) + 'M' : '—'}</span>
          </div>
        </div>
      </div>

      {/* Controls */}
      <div className="flex flex-wrap gap-2 items-center">
        {/* Symbol */}
        <select value={symbol} onChange={e => setSymbol(e.target.value)}
          className="bg-gray-800 border border-gray-700 rounded-lg px-2 py-1.5 text-xs text-white focus:border-blue-500 focus:outline-none">
          {SYMBOLS.map(s => <option key={s}>{s}</option>)}
        </select>

        {/* Intervals */}
        <div className="flex gap-1">
          {INTERVALS.map(iv => (
            <button key={iv.label} onClick={() => setInterval(iv)}
              className={clsx('px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors',
                interval.label === iv.label
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-white')}>
              {iv.label}
            </button>
          ))}
        </div>

        {/* Indicators */}
        <div className="flex gap-1 ml-auto">
          {['RSI','MACD','BB','None'].map(ind => (
            <button key={ind} onClick={() => setIndicator(ind)}
              className={clsx('px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors',
                indicator === ind
                  ? 'bg-purple-600 text-white'
                  : 'bg-gray-800 text-gray-400 hover:bg-gray-700')}>
              {ind}
            </button>
          ))}
        </div>
      </div>

      {/* Main price chart */}
      {loading ? (
        <div className="animate-pulse bg-gray-800 rounded-2xl h-56 flex items-center justify-center text-gray-600">
          <RefreshCw size={20} className="animate-spin mr-2"/> Loading market data…
        </div>
      ) : (
        <div className="bg-gray-900/50 rounded-2xl p-2 border border-gray-800">
          <ResponsiveContainer width="100%" height={280}>
            <ComposedChart data={enriched} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="2 4" stroke="#1e293b"/>
              <XAxis dataKey="time" tick={{ fill: '#64748b', fontSize: 9 }}
                tickLine={false} interval="preserveStartEnd"/>
              <YAxis domain={[priceMin, priceMax]}
                tick={{ fill: '#64748b', fontSize: 9 }}
                tickLine={false} axisLine={false}
                tickFormatter={v => v.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                width={60}/>
              <Tooltip content={<CandleTooltip/>}/>

              {/* Bollinger bands */}
              {indicator === 'BB' && <>
                <Area dataKey="bbUp"  fill="#3b82f633" stroke="#3b82f6" strokeWidth={1} dot={false} activeDot={false}/>
                <Area dataKey="bbLow" fill="#3b82f600" stroke="#3b82f6" strokeWidth={1} dot={false} activeDot={false}/>
                <Line dataKey="bbMid" stroke="#60a5fa" strokeWidth={1} strokeDasharray="3 2" dot={false}/>
              </>}

              {/* Volume bars at bottom */}
              <Bar dataKey="volume" yAxisId="vol" fill="#334155" opacity={0.4} maxBarSize={6}/>
              <YAxis yAxisId="vol" orientation="right" hide domain={[0, d => d * 8]}/>

              {/* OHLC bars — green/red based on open vs close */}
              {enriched.map((c, i) => null)}
              <Bar dataKey="barRange" stackId="ohlc"
                shape={(props) => {
                  const { x, y, width, payload } = props
                  if (!payload) return null
                  const isUp2 = payload.close >= payload.open
                  const col = isUp2 ? '#10B981' : '#EF4444'
                  return (
                    <g key={payload.openTime}>
                      <rect x={x + width * 0.25} y={y} width={Math.max(width * 0.5, 1)}
                        height={props.height} fill={col} opacity={0.85} rx={0.5}/>
                    </g>
                  )
                }}
                maxBarSize={12}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* RSI panel */}
      {indicator === 'RSI' && enriched.length > 14 && (
        <div className="bg-gray-900/50 rounded-2xl p-2 border border-gray-800">
          <div className="text-xs text-gray-500 mb-1 px-1">RSI (14)</div>
          <ResponsiveContainer width="100%" height={80}>
            <ComposedChart data={enriched} margin={{ top: 2, right: 4, left: 0, bottom: 0 }}>
              <XAxis dataKey="time" hide/>
              <YAxis domain={[0, 100]} tick={{ fill: '#64748b', fontSize: 9 }}
                tickLine={false} axisLine={false} width={28}
                ticks={[30, 50, 70]}/>
              <CartesianGrid strokeDasharray="2 4" stroke="#1e293b"/>
              <Tooltip formatter={v => [v?.toFixed(1), 'RSI']}
                contentStyle={ttStyle}/>
              <ReferenceLine y={70} stroke="#EF444466" strokeDasharray="3 2"/>
              <ReferenceLine y={30} stroke="#10B98166" strokeDasharray="3 2"/>
              <Line dataKey="rsi" stroke="#a78bfa" strokeWidth={1.5} dot={false}/>
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* MACD panel */}
      {indicator === 'MACD' && enriched.length > 26 && (
        <div className="bg-gray-900/50 rounded-2xl p-2 border border-gray-800">
          <div className="text-xs text-gray-500 mb-1 px-1">MACD (12,26,9)</div>
          <ResponsiveContainer width="100%" height={80}>
            <ComposedChart data={enriched} margin={{ top: 2, right: 4, left: 0, bottom: 0 }}>
              <XAxis dataKey="time" hide/>
              <YAxis tick={{ fill: '#64748b', fontSize: 9 }} tickLine={false}
                axisLine={false} width={40}
                tickFormatter={v => v?.toFixed(1)}/>
              <CartesianGrid strokeDasharray="2 4" stroke="#1e293b"/>
              <Tooltip formatter={v => [v?.toFixed(4)]} contentStyle={ttStyle}/>
              <ReferenceLine y={0} stroke="#334155"/>
              <Bar dataKey="hist" maxBarSize={6}
                shape={({ x, y, width, height, payload }) => (
                  <rect x={x} y={y} width={Math.max(width, 1)} height={height}
                    fill={(payload?.hist ?? 0) >= 0 ? '#10B981' : '#EF4444'} opacity={0.8}/>
                )}/>
              <Line dataKey="macd"   stroke="#3b82f6" strokeWidth={1.5} dot={false}/>
              <Line dataKey="signal" stroke="#f59e0b" strokeWidth={1}   dot={false}/>
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}
