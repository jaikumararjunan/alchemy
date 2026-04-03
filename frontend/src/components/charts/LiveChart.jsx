/**
 * LiveChart.jsx — Real-time candlestick chart
 * Uses TradingView lightweight-charts for proper OHLC rendering
 * Data: Binance public WebSocket (no API key needed)
 */
import { useEffect, useRef, useState, useCallback } from 'react'
import { createChart, ColorType, CrosshairMode } from 'lightweight-charts'
import { RefreshCw, Wifi, WifiOff, TrendingUp, TrendingDown, ChevronDown } from 'lucide-react'
import clsx from 'clsx'

const SYMBOLS   = ['BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT','XRPUSDT','DOGEUSDT','ADAUSDT','AVAXUSDT']
const INTERVALS = [
  { label:'1m',  ws:'1m',  rest:'1m',  seconds:60 },
  { label:'5m',  ws:'5m',  rest:'5m',  seconds:300 },
  { label:'15m', ws:'15m', rest:'15m', seconds:900 },
  { label:'1h',  ws:'1h',  rest:'1h',  seconds:3600 },
  { label:'4h',  ws:'4h',  rest:'4h',  seconds:14400 },
  { label:'1d',  ws:'1d',  rest:'1d',  seconds:86400 },
]

// ── Indicator calculations ───────────────────────────────────────────────────
function ema(arr, period) {
  const k = 2 / (period + 1), out = []
  let e = arr[0]
  for (const v of arr) { e = v * k + e * (1 - k); out.push(e) }
  return out
}

function calcRSI(closes, period = 14) {
  if (closes.length < period + 1) return []
  const out = []
  let ag = 0, al = 0
  for (let i = 1; i <= period; i++) {
    const d = closes[i] - closes[i-1]
    if (d > 0) ag += d; else al -= d
  }
  ag /= period; al /= period
  const first = al === 0 ? 100 : 100 - 100 / (1 + ag / al)
  out.push(...new Array(period).fill(null), first)
  for (let i = period + 1; i < closes.length; i++) {
    const d = closes[i] - closes[i-1]
    ag = (ag * (period-1) + Math.max(d,0))  / period
    al = (al * (period-1) + Math.max(-d,0)) / period
    out.push(al === 0 ? 100 : 100 - 100 / (1 + ag / al))
  }
  return out
}

function calcMACD(closes) {
  const e12 = ema(closes, 12), e26 = ema(closes, 26)
  const macdLine  = e12.map((v,i) => v - e26[i])
  const sigLine   = ema(macdLine.slice(25), 9)
  return macdLine.map((v, i) => i < 25
    ? { macd: null, signal: null, hist: null }
    : { macd: v, signal: sigLine[i-25] ?? null, hist: sigLine[i-25] != null ? v - sigLine[i-25] : null })
}

function calcBB(closes, period = 20, mult = 2) {
  return closes.map((_, i) => {
    if (i < period - 1) return null
    const sl  = closes.slice(i - period + 1, i + 1)
    const m   = sl.reduce((a,b) => a+b,0) / period
    const std = Math.sqrt(sl.reduce((a,b) => a+(b-m)**2,0) / period)
    return { upper: m + mult*std, mid: m, lower: m - mult*std }
  })
}

// ── Main Chart ───────────────────────────────────────────────────────────────
export default function LiveChart({ defaultSymbol = 'BTCUSDT', height = 340 }) {
  const containerRef = useRef(null)
  const chartRef     = useRef(null)
  const candleRef    = useRef(null)
  const volumeRef    = useRef(null)
  const ind1Ref      = useRef(null) // overlay: EMA9, EMA21, BB
  const ind2Ref      = useRef(null) // overlay: EMA9 signal
  const wsRef        = useRef(null)
  const candleMapRef = useRef({})   // openTime → candle

  const [symbol,    setSymbol]    = useState(defaultSymbol)
  const [interval,  setInterval]  = useState(INTERVALS[0])
  const [indicator, setIndicator] = useState('BB')
  const [ticker,    setTicker]    = useState(null)
  const [connected, setConnected] = useState(false)
  const [loading,   setLoading]   = useState(true)
  const [lastPrice, setLastPrice] = useState(null)

  // ── Create chart ─────────────────────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current) return
    const chart = createChart(containerRef.current, {
      layout: {
        background:  { type: ColorType.Solid, color: 'transparent' },
        textColor:   '#94a3b8',
        fontSize:    11,
        fontFamily:  'ui-monospace, monospace',
      },
      grid:       { vertLines: { color: '#1e293b' }, horzLines: { color: '#1e293b' } },
      crosshair:  { mode: CrosshairMode.Normal },
      timeScale:  { borderColor: '#334155', timeVisible: true, secondsVisible: false, rightOffset: 5 },
      rightPriceScale: { borderColor: '#334155', scaleMargins: { top: 0.1, bottom: 0.3 } },
      handleScroll:   true,
      handleScale:    true,
      width:  containerRef.current.clientWidth,
      height: height,
    })
    chartRef.current = chart

    // Candlestick series
    const candleSeries = chart.addCandlestickSeries({
      upColor:          '#10B981', downColor:     '#EF4444',
      borderUpColor:    '#10B981', borderDownColor: '#EF4444',
      wickUpColor:      '#10B981', wickDownColor:   '#EF4444',
    })
    candleRef.current = candleSeries

    // Volume series (histogram at bottom)
    const volSeries = chart.addHistogramSeries({
      priceFormat:     { type: 'volume' },
      priceScaleId:    'volume',
      scaleMargins:    { top: 0.8, bottom: 0 },
    })
    chart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } })
    volumeRef.current = volSeries

    // Resize observer
    const ro = new ResizeObserver(() => {
      if (containerRef.current)
        chart.resize(containerRef.current.clientWidth, height)
    })
    ro.observe(containerRef.current)

    return () => { ro.disconnect(); chart.remove() }
  }, [height])

  // ── Update indicator overlays ────────────────────────────────────────────
  const updateIndicators = useCallback((candles) => {
    if (!chartRef.current || !candleRef.current) return
    const chart  = chartRef.current
    const closes = candles.map(c => c.close)
    const times  = candles.map(c => c.time)

    // Remove old indicator series
    if (ind1Ref.current) { try { chart.removeSeries(ind1Ref.current) } catch {} ind1Ref.current = null }
    if (ind2Ref.current) { try { chart.removeSeries(ind2Ref.current) } catch {} ind2Ref.current = null }

    const mkLine = (color, width = 1, dotted = false) => chart.addLineSeries({
      color, lineWidth: width, crosshairMarkerVisible: false,
      priceLineVisible: false, lastValueVisible: false,
      lineStyle: dotted ? 2 : 0,
    })

    if (indicator === 'EMA') {
      const e9  = ema(closes, 9)
      const e21 = ema(closes, 21)
      const s1  = mkLine('#f59e0b', 1)
      const s2  = mkLine('#3b82f6', 1)
      s1.setData(times.map((t,i) => ({ time: t, value: e9[i] })))
      s2.setData(times.map((t,i) => ({ time: t, value: e21[i] })))
      ind1Ref.current = s1; ind2Ref.current = s2

    } else if (indicator === 'BB') {
      const bb = calcBB(closes)
      const sU = mkLine('#3b82f680', 1, true)
      const sM = mkLine('#3b82f6aa', 1, true)
      const sL = mkLine('#3b82f680', 1, true)
      const data = times.map((t,i) => bb[i] ? { up: bb[i].upper, mid: bb[i].mid, low: bb[i].lower, t } : null).filter(Boolean)
      sU.setData(data.map(d => ({ time: d.t, value: d.up })))
      sM.setData(data.map(d => ({ time: d.t, value: d.mid })))
      sL.setData(data.map(d => ({ time: d.t, value: d.low })))
      ind1Ref.current = sU; ind2Ref.current = sL
    }
    // RSI/MACD shown in separate panel (handled below)
  }, [indicator])

  // ── Load history via REST + connect WS ──────────────────────────────────
  const loadAndConnect = useCallback(async (sym, intv) => {
    setLoading(true)
    candleMapRef.current = {}

    try {
      const r    = await fetch(`https://api.binance.com/api/v3/klines?symbol=${sym}&interval=${intv.rest}&limit=300`)
      const data = await r.json()
      const parsed = data.map(k => ({
        time:     Math.floor(k[0] / 1000),
        open:     parseFloat(k[1]),
        high:     parseFloat(k[2]),
        low:      parseFloat(k[3]),
        close:    parseFloat(k[4]),
        volume:   parseFloat(k[5]),
      }))
      parsed.forEach(c => { candleMapRef.current[c.time] = c })

      if (candleRef.current) {
        candleRef.current.setData(parsed)
        volumeRef.current?.setData(parsed.map(c => ({
          time:  c.time, value: c.volume,
          color: c.close >= c.open ? '#10B98133' : '#EF444433',
        })))
        updateIndicators(parsed)
        chartRef.current?.timeScale().fitContent()
        setLastPrice(parsed.at(-1)?.close)
      }
    } catch(e) { console.error('klines fetch error', e) }

    setLoading(false)

    // Connect WebSocket for live updates
    if (wsRef.current) wsRef.current.close()
    const streams = `${sym.toLowerCase()}@kline_${intv.ws}/${sym.toLowerCase()}@miniTicker`
    const ws = new WebSocket(`wss://stream.binance.com:9443/stream?streams=${streams}`)
    wsRef.current = ws

    ws.onopen  = () => setConnected(true)
    ws.onclose = () => setConnected(false)
    ws.onerror = () => setConnected(false)

    ws.onmessage = (e) => {
      const { stream: s, data: d } = JSON.parse(e.data)

      if (s?.includes('kline')) {
        const k = d.k
        const c = {
          time:   Math.floor(k.t / 1000),
          open:   parseFloat(k.o),
          high:   parseFloat(k.h),
          low:    parseFloat(k.l),
          close:  parseFloat(k.c),
          volume: parseFloat(k.v),
        }
        candleMapRef.current[c.time] = c

        if (candleRef.current) {
          candleRef.current.update(c)
          volumeRef.current?.update({
            time:  c.time, value: c.volume,
            color: c.close >= c.open ? '#10B98133' : '#EF444433',
          })
          setLastPrice(c.close)

          // Update indicators every closed candle
          if (k.x) {
            const all = Object.values(candleMapRef.current).sort((a,b) => a.time - b.time)
            updateIndicators(all)
          }
        }
      }

      if (s?.includes('miniTicker')) {
        setTicker({
          price:     parseFloat(d.c),
          open:      parseFloat(d.o),
          high:      parseFloat(d.h),
          low:       parseFloat(d.l),
          volume:    parseFloat(d.v),
          change:    parseFloat(d.c) - parseFloat(d.o),
          changePct: (parseFloat(d.c) - parseFloat(d.o)) / parseFloat(d.o) * 100,
        })
        setLastPrice(parseFloat(d.c))
      }
    }
  }, [updateIndicators])

  // Re-init when symbol or interval changes
  useEffect(() => {
    loadAndConnect(symbol, interval)
    return () => { if (wsRef.current) wsRef.current.close() }
  }, [symbol, interval])

  // Re-compute indicators when indicator type changes
  useEffect(() => {
    const all = Object.values(candleMapRef.current).sort((a,b) => a.time - b.time)
    if (all.length > 0) updateIndicators(all)
  }, [indicator])

  // ── RSI / MACD panels (recharts, smaller panels) ─────────────────────────
  const allCandles = Object.values(candleMapRef.current).sort((a,b) => a.time-b.time)
  const closes     = allCandles.map(c => c.close)
  const rsiVals    = calcRSI(closes)
  const macdVals   = calcMACD(closes)

  const isUp       = (ticker?.changePct ?? 0) >= 0
  const price      = ticker?.price ?? lastPrice
  const priceStr   = price?.toLocaleString(undefined, { maximumFractionDigits: 2 })

  return (
    <div className="space-y-2">
      {/* Ticker row */}
      <div className="flex items-start justify-between flex-wrap gap-2">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-3xl font-bold text-white font-mono tracking-tight">
              {loading && !price ? <span className="animate-pulse text-gray-600">———</span> : priceStr}
            </span>
            {ticker && (
              <span className={clsx('text-sm font-semibold px-2 py-0.5 rounded-lg',
                isUp ? 'text-emerald-400 bg-emerald-900/30' : 'text-red-400 bg-red-900/30')}>
                {isUp ? '+' : ''}{ticker.changePct?.toFixed(2)}%
              </span>
            )}
            <span className={clsx('w-2 h-2 rounded-full flex-shrink-0',
              connected ? 'bg-emerald-400 animate-pulse' : 'bg-gray-600')}/>
          </div>
          {ticker && (
            <div className="flex gap-4 text-xs text-gray-500 mt-1 font-mono">
              <span>H: <span className="text-emerald-400">{ticker.high?.toLocaleString()}</span></span>
              <span>L: <span className="text-red-400">{ticker.low?.toLocaleString()}</span></span>
              <span>Vol: {ticker.volume ? (ticker.volume/1e6).toFixed(2)+'M' : '—'}</span>
            </div>
          )}
        </div>
      </div>

      {/* Controls */}
      <div className="flex items-center gap-2 flex-wrap">
        {/* Symbol dropdown */}
        <div className="relative">
          <select value={symbol} onChange={e => setSymbol(e.target.value)}
            className="appearance-none bg-gray-800 border border-gray-700 rounded-lg pl-3 pr-7 py-1.5 text-xs text-white focus:border-blue-500 focus:outline-none font-medium cursor-pointer">
            {SYMBOLS.map(s => <option key={s}>{s}</option>)}
          </select>
          <ChevronDown size={10} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none"/>
        </div>

        {/* Intervals */}
        <div className="flex gap-1 bg-gray-900 rounded-lg p-1">
          {INTERVALS.map(iv => (
            <button key={iv.label} onClick={() => setInterval(iv)}
              className={clsx('px-2.5 py-1 rounded text-xs font-medium transition-all',
                interval.label === iv.label
                  ? 'bg-blue-600 text-white shadow'
                  : 'text-gray-400 hover:text-white')}>
              {iv.label}
            </button>
          ))}
        </div>

        {/* Indicators */}
        <div className="flex gap-1 bg-gray-900 rounded-lg p-1 ml-auto">
          {['EMA','BB','RSI','MACD','None'].map(ind => (
            <button key={ind} onClick={() => setIndicator(ind)}
              className={clsx('px-2.5 py-1 rounded text-xs font-medium transition-all',
                indicator === ind
                  ? 'bg-purple-600 text-white shadow'
                  : 'text-gray-400 hover:text-white')}>
              {ind}
            </button>
          ))}
        </div>
      </div>

      {/* Chart container */}
      <div className="relative rounded-xl overflow-hidden bg-gray-950 border border-gray-800">
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-gray-950/80 z-10">
            <div className="flex items-center gap-2 text-gray-400 text-sm">
              <RefreshCw size={16} className="animate-spin"/> Loading chart data…
            </div>
          </div>
        )}
        <div ref={containerRef} style={{ height: `${height}px` }}/>
      </div>

      {/* RSI panel */}
      {indicator === 'RSI' && rsiVals.length > 14 && (
        <RsiPanel candles={allCandles} rsi={rsiVals}/>
      )}

      {/* MACD panel */}
      {indicator === 'MACD' && macdVals.length > 26 && (
        <MacdPanel candles={allCandles} macd={macdVals}/>
      )}
    </div>
  )
}

// ── RSI sub-panel using lightweight-charts ────────────────────────────────────
function RsiPanel({ candles, rsi }) {
  const ref   = useRef(null)
  const chart = useRef(null)
  const line  = useRef(null)

  useEffect(() => {
    if (!ref.current) return
    const c = createChart(ref.current, {
      layout:    { background: { type: ColorType.Solid, color: 'transparent' }, textColor: '#64748b', fontSize: 10 },
      grid:      { vertLines: { color: '#1e293b' }, horzLines: { color: '#1e293b' } },
      crosshair: { mode: CrosshairMode.Normal },
      timeScale: { visible: false },
      rightPriceScale: { scaleMargins: { top: 0.1, bottom: 0.1 }, borderColor: '#334155' },
      height: 80, width: ref.current.clientWidth,
    })
    const l = c.addLineSeries({ color: '#a78bfa', lineWidth: 1.5, lastValueVisible: true, priceLineVisible: false })
    c.addLineSeries({ color: '#ef444466', lineWidth: 1, lastValueVisible: false, priceLineVisible: false })
      .setData(candles.map(c2 => ({ time: c2.time, value: 70 })))
    c.addLineSeries({ color: '#10b98166', lineWidth: 1, lastValueVisible: false, priceLineVisible: false })
      .setData(candles.map(c2 => ({ time: c2.time, value: 30 })))
    chart.current = c; line.current = l
    const ro = new ResizeObserver(() => { if (ref.current) c.resize(ref.current.clientWidth, 80) })
    ro.observe(ref.current)
    return () => { ro.disconnect(); c.remove() }
  }, [])

  useEffect(() => {
    if (!line.current) return
    const data = candles.map((c, i) => rsi[i] != null ? { time: c.time, value: rsi[i] } : null).filter(Boolean)
    line.current.setData(data)
  }, [candles, rsi])

  return (
    <div className="rounded-xl bg-gray-950 border border-gray-800 overflow-hidden">
      <div className="px-3 pt-2 text-xs text-gray-500">RSI (14)</div>
      <div ref={ref}/>
    </div>
  )
}

// ── MACD sub-panel ────────────────────────────────────────────────────────────
function MacdPanel({ candles, macd }) {
  const ref  = useRef(null)
  const chart = useRef(null)
  const macdL = useRef(null)
  const sigL  = useRef(null)
  const histH = useRef(null)

  useEffect(() => {
    if (!ref.current) return
    const c = createChart(ref.current, {
      layout:    { background: { type: ColorType.Solid, color: 'transparent' }, textColor: '#64748b', fontSize: 10 },
      grid:      { vertLines: { color: '#1e293b' }, horzLines: { color: '#1e293b' } },
      crosshair: { mode: CrosshairMode.Normal },
      timeScale: { visible: false },
      rightPriceScale: { scaleMargins: { top: 0.1, bottom: 0.1 }, borderColor: '#334155' },
      height: 90, width: ref.current.clientWidth,
    })
    macdL.current = c.addLineSeries({ color: '#3b82f6', lineWidth: 1.5, lastValueVisible: true, priceLineVisible: false })
    sigL.current  = c.addLineSeries({ color: '#f59e0b', lineWidth: 1, lastValueVisible: false, priceLineVisible: false })
    histH.current = c.addHistogramSeries({ priceLineVisible: false, lastValueVisible: false })
    chart.current = c
    const ro = new ResizeObserver(() => { if (ref.current) c.resize(ref.current.clientWidth, 90) })
    ro.observe(ref.current)
    return () => { ro.disconnect(); c.remove() }
  }, [])

  useEffect(() => {
    if (!macdL.current) return
    const md = candles.map((c,i) => macd[i]?.macd != null ? { time: c.time, value: macd[i].macd } : null).filter(Boolean)
    const sg = candles.map((c,i) => macd[i]?.signal != null ? { time: c.time, value: macd[i].signal } : null).filter(Boolean)
    const ht = candles.map((c,i) => macd[i]?.hist != null
      ? { time: c.time, value: macd[i].hist, color: macd[i].hist >= 0 ? '#10B98166' : '#EF444466' } : null).filter(Boolean)
    macdL.current.setData(md)
    sigL.current.setData(sg)
    histH.current.setData(ht)
  }, [candles, macd])

  return (
    <div className="rounded-xl bg-gray-950 border border-gray-800 overflow-hidden">
      <div className="px-3 pt-2 text-xs text-gray-500">MACD (12, 26, 9)</div>
      <div ref={ref}/>
    </div>
  )
}
