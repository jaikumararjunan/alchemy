/**
 * LiveChart.jsx — Real-time candlestick chart
 * Pure React + SVG — zero additional dependencies
 * Data from Binance public WebSocket (no API key needed)
 */
import { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import { RefreshCw, ChevronDown } from 'lucide-react'
import clsx from 'clsx'

const SYMBOLS   = ['BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT','XRPUSDT','DOGEUSDT','ADAUSDT','AVAXUSDT']
const INTERVALS = [
  { label:'1m',  ws:'1m',  rest:'1m'  },
  { label:'5m',  ws:'5m',  rest:'5m'  },
  { label:'15m', ws:'15m', rest:'15m' },
  { label:'1h',  ws:'1h',  rest:'1h'  },
  { label:'4h',  ws:'4h',  rest:'4h'  },
  { label:'1d',  ws:'1d',  rest:'1d'  },
]

// ── Math helpers ─────────────────────────────────────────────────────────────
function ema(arr, p) {
  const k=2/(p+1); let e=arr[0]; return arr.map(v=>{e=v*k+e*(1-k);return e})
}
function calcRSI(closes, p=14) {
  if(closes.length<p+1) return closes.map(()=>null)
  const out=[]; let ag=0,al=0
  for(let i=1;i<=p;i++){const d=closes[i]-closes[i-1];if(d>0)ag+=d;else al-=d}
  ag/=p;al/=p;out.push(...new Array(p).fill(null),al===0?100:100-100/(1+ag/al))
  for(let i=p+1;i<closes.length;i++){
    const d=closes[i]-closes[i-1]
    ag=(ag*(p-1)+Math.max(d,0))/p;al=(al*(p-1)+Math.max(-d,0))/p
    out.push(al===0?100:100-100/(1+ag/al))
  }
  return out
}
function calcBB(closes,p=20,m=2){
  return closes.map((_,i)=>{
    if(i<p-1)return null
    const sl=closes.slice(i-p+1,i+1),mn=sl.reduce((a,b)=>a+b,0)/p
    const std=Math.sqrt(sl.reduce((a,b)=>a+(b-mn)**2,0)/p)
    return{up:mn+m*std,mid:mn,low:mn-m*std}
  })
}

// ── SVG Candlestick chart ────────────────────────────────────────────────────
function CandlestickSVG({ candles, indicator, width = 800, height = 280 }) {
  const [hover, setHover] = useState(null)
  const [viewStart, setViewStart] = useState(0)
  const [zoom, setZoom] = useState(1)
  const svgRef = useRef(null)
  const dragRef = useRef(null)

  const PAD = { top: 12, right: 60, bottom: 24, left: 8 }
  const W = width - PAD.left - PAD.right
  const H = height - PAD.top - PAD.bottom

  // Visible candles
  const totalVisible = Math.max(30, Math.floor(80 / zoom))
  const maxStart = Math.max(0, candles.length - totalVisible)
  const start = Math.min(Math.max(0, viewStart), maxStart)
  const visible = candles.slice(start, start + totalVisible)

  const closes = candles.map(c => c.close)
  const bbAll  = indicator === 'BB'  ? calcBB(closes) : null
  const rsiAll = indicator === 'RSI' ? calcRSI(closes) : null
  const ema9   = indicator === 'EMA' ? ema(closes, 9)  : null
  const ema21  = indicator === 'EMA' ? ema(closes, 21) : null

  const visibleBB  = bbAll  ? bbAll.slice(start, start + totalVisible) : null
  const visibleRSI = rsiAll ? rsiAll.slice(start, start + totalVisible) : null
  const visE9  = ema9  ? ema9.slice(start, start + totalVisible) : null
  const visE21 = ema21 ? ema21.slice(start, start + totalVisible) : null

  if (!visible.length) return (
    <div className="flex items-center justify-center text-gray-600 text-sm" style={{height}}>
      <RefreshCw size={16} className="animate-spin mr-2"/> Loading…
    </div>
  )

  const priceMin = Math.min(...visible.map(c => c.low))  * 0.9998
  const priceMax = Math.max(...visible.map(c => c.high)) * 1.0002
  const priceRange = priceMax - priceMin || 1

  const py = (price) => PAD.top + H - ((price - priceMin) / priceRange) * H
  const cx = (i) => PAD.left + (i + 0.5) * (W / visible.length)
  const bw = Math.max(1, W / visible.length * 0.7)

  // Price labels
  const priceSteps = 5
  const priceTicks = Array.from({length: priceSteps}, (_, i) =>
    priceMin + (priceRange / (priceSteps-1)) * i)

  // Time labels (show ~5)
  const timeTicks = visible.filter((_, i) => i % Math.floor(visible.length / 5) === 0)

  // Wheel zoom
  const onWheel = (e) => {
    e.preventDefault()
    const delta = e.deltaY > 0 ? 0.8 : 1.25
    setZoom(z => Math.max(0.3, Math.min(5, z * delta)))
  }

  // Drag pan
  const onMouseDown = (e) => {
    dragRef.current = { x: e.clientX, start }
  }
  const onMouseMove = (e) => {
    if (!dragRef.current) return
    const dx = e.clientX - dragRef.current.x
    const shift = -Math.round(dx / (W / totalVisible))
    setViewStart(Math.max(0, Math.min(maxStart, dragRef.current.start + shift)))
    // Track hover candle
    const rect = svgRef.current?.getBoundingClientRect()
    if (rect) {
      const relX = e.clientX - rect.left - PAD.left
      const idx = Math.floor(relX / (W / visible.length))
      if (idx >= 0 && idx < visible.length) setHover(idx)
    }
  }
  const onMouseUp = () => { dragRef.current = null }
  const onMouseLeave = () => { dragRef.current = null; setHover(null) }

  const hoverCandle = hover != null ? visible[hover] : null

  // Build BB path
  const bbPath = (vals, key) => {
    if (!vals) return ''
    const pts = vals.map((v,i) => v ? `${cx(i)},${py(v[key])}` : null).filter(Boolean)
    if (pts.length < 2) return ''
    return `M ${pts[0]} L ${pts.slice(1).join(' L ')}`
  }

  // Build line path for EMA
  const linePath = (vals) => {
    if (!vals) return ''
    const pts = vals.map((v,i) => `${cx(i)},${py(v)}`)
    return `M ${pts[0]} L ${pts.slice(1).join(' L ')}`
  }

  return (
    <div className="relative select-none">
      {/* Hover info bar */}
      {hoverCandle && (
        <div className="absolute top-1 left-2 z-10 flex gap-3 text-xs font-mono bg-gray-900/90 px-3 py-1.5 rounded-lg border border-gray-700">
          <span className="text-gray-400">{hoverCandle.timeLabel}</span>
          {[['O',hoverCandle.open],['H',hoverCandle.high],['L',hoverCandle.low],['C',hoverCandle.close]].map(([k,v])=>(
            <span key={k}>
              <span className="text-gray-500">{k}:</span>
              <span className={k==='C'?(hoverCandle.close>=hoverCandle.open?'text-emerald-400':'text-red-400'):'text-white'}>
                {v?.toLocaleString(undefined,{maximumFractionDigits:2})}
              </span>
            </span>
          ))}
          <span><span className="text-gray-500">V:</span><span className="text-gray-300">{(hoverCandle.volume/1e6).toFixed(2)}M</span></span>
        </div>
      )}

      <svg
        ref={svgRef}
        width={width} height={height}
        style={{ cursor: dragRef.current ? 'grabbing' : 'crosshair' }}
        onWheel={onWheel}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={onMouseLeave}
      >
        {/* Grid */}
        {priceTicks.map((p,i) => (
          <g key={i}>
            <line x1={PAD.left} y1={py(p)} x2={width-PAD.right} y2={py(p)} stroke="#1e293b" strokeWidth={1}/>
            <text x={width-PAD.right+4} y={py(p)+4} fill="#64748b" fontSize={9}>
              {p >= 1000 ? (p/1000).toFixed(0)+'K' : p.toFixed(2)}
            </text>
          </g>
        ))}

        {/* Time labels */}
        {timeTicks.map((c,i) => (
          <text key={i} x={cx(visible.indexOf(c))} y={height-4} fill="#64748b" fontSize={9} textAnchor="middle">
            {c.timeLabel}
          </text>
        ))}

        {/* Bollinger Bands */}
        {visibleBB && <>
          <path d={bbPath(visibleBB,'up')}  fill="none" stroke="#3b82f680" strokeWidth={1} strokeDasharray="3 2"/>
          <path d={bbPath(visibleBB,'mid')} fill="none" stroke="#3b82f6aa" strokeWidth={1} strokeDasharray="4 2"/>
          <path d={bbPath(visibleBB,'low')} fill="none" stroke="#3b82f680" strokeWidth={1} strokeDasharray="3 2"/>
        </>}

        {/* EMA lines */}
        {visE9  && <path d={linePath(visE9)}  fill="none" stroke="#f59e0b" strokeWidth={1.5}/>}
        {visE21 && <path d={linePath(visE21)} fill="none" stroke="#3b82f6" strokeWidth={1.5}/>}

        {/* Volume bars */}
        {visible.map((c,i) => {
          const volH = Math.max(1, (c.volume / Math.max(...visible.map(v=>v.volume))) * (H*0.15))
          return (
            <rect key={`v${i}`}
              x={cx(i)-bw/2} y={PAD.top+H-volH} width={bw} height={volH}
              fill={c.close>=c.open ? '#10B98133' : '#EF444433'}/>
          )
        })}

        {/* Candles */}
        {visible.map((c,i) => {
          const isUp  = c.close >= c.open
          const col   = isUp ? '#10B981' : '#EF4444'
          const bodyT = py(Math.max(c.open, c.close))
          const bodyB = py(Math.min(c.open, c.close))
          const bodyH = Math.max(1, bodyB - bodyT)
          const isHov = hover === i
          return (
            <g key={`c${i}`}>
              {/* Wick */}
              <line x1={cx(i)} y1={py(c.high)} x2={cx(i)} y2={py(c.low)}
                stroke={col} strokeWidth={1} opacity={0.9}/>
              {/* Body */}
              <rect
                x={cx(i)-bw/2} y={bodyT} width={bw} height={bodyH}
                fill={col} opacity={isHov ? 1 : 0.85}
                stroke={isHov ? '#fff' : col} strokeWidth={isHov ? 0.5 : 0}
              />
            </g>
          )
        })}

        {/* Hover crosshair */}
        {hover != null && (
          <g>
            <line x1={cx(hover)} y1={PAD.top} x2={cx(hover)} y2={PAD.top+H} stroke="#ffffff22" strokeWidth={1}/>
            {hoverCandle && (
              <line x1={PAD.left} y1={py(hoverCandle.close)} x2={width-PAD.right} y2={py(hoverCandle.close)}
                stroke="#ffffff22" strokeWidth={1}/>
            )}
          </g>
        )}
      </svg>

      {/* Scroll hint */}
      <div className="text-center text-xs text-gray-700 mt-1">
        Scroll to zoom · Drag to pan
      </div>
    </div>
  )
}

// ── RSI mini chart ────────────────────────────────────────────────────────────
function RSIPanel({ candles, rsiVals, width = 800 }) {
  const H = 70, PAD = { top:8, right:60, bottom:16, left:8 }
  const W = width - PAD.left - PAD.right
  const valid = rsiVals.map((v,i) => v != null ? { v, c: candles[i] } : null).filter(Boolean)
  if (valid.length < 2) return null
  const cx = (i) => PAD.left + (i / (valid.length-1)) * W
  const py = (v) => PAD.top + H - ((v/100)*H)
  const pts = valid.map((d,i) => `${cx(i)},${py(d.v)}`).join(' ')
  const last = valid.at(-1)

  return (
    <div className="rounded-xl bg-gray-950 border border-gray-800 overflow-hidden">
      <div className="flex items-center justify-between px-3 pt-2">
        <span className="text-xs text-gray-500">RSI (14)</span>
        {last && <span className={clsx('text-xs font-mono', last.v>=70?'text-red-400':last.v<=30?'text-emerald-400':'text-gray-300')}>{last.v.toFixed(1)}</span>}
      </div>
      <svg width={width} height={H+PAD.top+PAD.bottom}>
        <line x1={PAD.left} y1={py(70)} x2={width-PAD.right} y2={py(70)} stroke="#EF444440" strokeWidth={1} strokeDasharray="3 2"/>
        <line x1={PAD.left} y1={py(50)} x2={width-PAD.right} y2={py(50)} stroke="#33415540" strokeWidth={1}/>
        <line x1={PAD.left} y1={py(30)} x2={width-PAD.right} y2={py(30)} stroke="#10B98140" strokeWidth={1} strokeDasharray="3 2"/>
        {[70,50,30].map(v=><text key={v} x={width-PAD.right+4} y={py(v)+4} fill="#64748b" fontSize={9}>{v}</text>)}
        <polyline points={pts} fill="none" stroke="#a78bfa" strokeWidth={1.5}/>
        {last && <circle cx={cx(valid.length-1)} cy={py(last.v)} r={2.5} fill="#a78bfa"/>}
      </svg>
    </div>
  )
}

// ── MACD mini chart ───────────────────────────────────────────────────────────
function MACDPanel({ candles, width = 800 }) {
  const closes = candles.map(c => c.close)
  const e12 = ema(closes, 12), e26 = ema(closes, 26)
  const macdLine = e12.map((v,i) => v - e26[i])
  const sigLine  = ema(macdLine.slice(25), 9)
  const hist     = macdLine.map((v,i) => i>=25 && sigLine[i-25]!=null ? v-sigLine[i-25] : null)
  const data = candles.slice(25).map((c,i)=>({
    t:c.timeLabel, macd:macdLine[i+25], sig:sigLine[i]??null, hist:hist[i+25]
  })).filter(d=>d.sig!=null)
  if (data.length < 5) return null

  const H=70, PAD={top:8,right:60,bottom:16,left:8}
  const W=width-PAD.left-PAD.right
  const vals = [...data.map(d=>d.macd),...data.map(d=>d.sig??0),...data.map(d=>d.hist??0)]
  const mn=Math.min(...vals)*1.1, mx=Math.max(...vals)*1.1, rng=mx-mn||1
  const py=(v)=>PAD.top+H-((v-mn)/rng)*H
  const cx=(i)=>PAD.left+(i/(data.length-1))*W
  const macdPts = data.map((d,i)=>`${cx(i)},${py(d.macd)}`).join(' ')
  const sigPts  = data.map((d,i)=>`${cx(i)},${py(d.sig??0)}`).join(' ')
  const bw = Math.max(1,(W/data.length)*0.7)
  const zero = py(0)

  return (
    <div className="rounded-xl bg-gray-950 border border-gray-800 overflow-hidden">
      <div className="px-3 pt-2 text-xs text-gray-500">MACD (12, 26, 9)</div>
      <svg width={width} height={H+PAD.top+PAD.bottom}>
        <line x1={PAD.left} y1={zero} x2={width-PAD.right} y2={zero} stroke="#334155" strokeWidth={1}/>
        {data.map((d,i)=> d.hist!=null && (
          <rect key={i} x={cx(i)-bw/2} y={d.hist>=0?py(d.hist):zero} width={bw}
            height={Math.abs(py(d.hist)-zero)} fill={d.hist>=0?'#10B98166':'#EF444466'}/>
        ))}
        <polyline points={macdPts} fill="none" stroke="#3b82f6" strokeWidth={1.5}/>
        <polyline points={sigPts}  fill="none" stroke="#f59e0b" strokeWidth={1}/>
      </svg>
    </div>
  )
}

// ── Main export ───────────────────────────────────────────────────────────────
export default function LiveChart({ defaultSymbol = 'BTCUSDT', height = 300 }) {
  const containerRef   = useRef(null)
  const [width, setWidth] = useState(800)
  const wsRef          = useRef(null)
  const candleMapRef   = useRef({})

  const [symbol,    setSymbol]    = useState(defaultSymbol)
  const [interval,  setInterval]  = useState(INTERVALS[0])
  const [indicator, setIndicator] = useState('BB')
  const [ticker,    setTicker]    = useState(null)
  const [candles,   setCandles]   = useState([])
  const [connected, setConnected] = useState(false)
  const [loading,   setLoading]   = useState(true)

  // Responsive width
  useEffect(() => {
    if (!containerRef.current) return
    const ro = new ResizeObserver(() => {
      if (containerRef.current) setWidth(containerRef.current.clientWidth)
    })
    ro.observe(containerRef.current)
    setWidth(containerRef.current.clientWidth)
    return () => ro.disconnect()
  }, [])

  const refresh = useCallback(async (sym, intv) => {
    setLoading(true); candleMapRef.current = {}
    try {
      const r    = await fetch(`https://api.binance.com/api/v3/klines?symbol=${sym}&interval=${intv.rest}&limit=250`)
      const data = await r.json()
      const parsed = data.map(k => ({
        time:      Math.floor(k[0]/1000),
        openTime:  k[0],
        timeLabel: new Date(k[0]).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit',hour12:false}),
        open:  parseFloat(k[1]), high:  parseFloat(k[2]),
        low:   parseFloat(k[3]), close: parseFloat(k[4]),
        volume:parseFloat(k[5]),
      }))
      parsed.forEach(c => { candleMapRef.current[c.openTime] = c })
      setCandles(parsed)
    } catch(e) { console.error(e) }
    setLoading(false)
  }, [])

  useEffect(() => {
    refresh(symbol, interval)
    if (wsRef.current) wsRef.current.close()

    const streams = `${symbol.toLowerCase()}@kline_${interval.ws}/${symbol.toLowerCase()}@miniTicker`
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
          time:      Math.floor(k.t/1000), openTime: k.t,
          timeLabel: new Date(k.t).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit',hour12:false}),
          open:parseFloat(k.o), high:parseFloat(k.h), low:parseFloat(k.l), close:parseFloat(k.c),
          volume:parseFloat(k.v),
        }
        candleMapRef.current[k.t] = c
        setCandles(Object.values(candleMapRef.current).sort((a,b)=>a.openTime-b.openTime))
      }
      if (s?.includes('miniTicker')) {
        setTicker({
          price:parseFloat(d.c), open:parseFloat(d.o), high:parseFloat(d.h),
          low:parseFloat(d.l),  volume:parseFloat(d.v),
          changePct:(parseFloat(d.c)-parseFloat(d.o))/parseFloat(d.o)*100,
        })
      }
    }
    return () => ws.close()
  }, [symbol, interval])

  const closes  = candles.map(c => c.close)
  const rsiVals = indicator === 'RSI' ? calcRSI(closes) : []
  const isUp    = (ticker?.changePct ?? 0) >= 0
  const price   = ticker?.price ?? candles.at(-1)?.close

  return (
    <div ref={containerRef} className="space-y-2 w-full">
      {/* Ticker */}
      <div className="flex items-start justify-between flex-wrap gap-2">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-3xl font-bold text-white font-mono">
              {loading && !price
                ? <span className="text-gray-600 animate-pulse">————</span>
                : price?.toLocaleString(undefined,{maximumFractionDigits:2})}
            </span>
            {ticker && (
              <span className={clsx('text-sm font-semibold px-2 py-0.5 rounded-lg',
                isUp?'text-emerald-400 bg-emerald-900/30':'text-red-400 bg-red-900/30')}>
                {isUp?'+':''}{ticker.changePct?.toFixed(2)}%
              </span>
            )}
            <span className={clsx('w-2 h-2 rounded-full',connected?'bg-emerald-400 animate-pulse':'bg-gray-600')}/>
          </div>
          {ticker && (
            <div className="flex gap-4 text-xs text-gray-500 mt-1 font-mono">
              <span>H: <span className="text-emerald-400">{ticker.high?.toLocaleString()}</span></span>
              <span>L: <span className="text-red-400">{ticker.low?.toLocaleString()}</span></span>
              <span>Vol: {(ticker.volume/1e6).toFixed(2)}M</span>
            </div>
          )}
        </div>
      </div>

      {/* Controls */}
      <div className="flex items-center gap-2 flex-wrap">
        <div className="relative">
          <select value={symbol} onChange={e=>setSymbol(e.target.value)}
            className="appearance-none bg-gray-800 border border-gray-700 rounded-lg pl-3 pr-7 py-1.5 text-xs text-white focus:border-blue-500 focus:outline-none font-medium cursor-pointer">
            {SYMBOLS.map(s=><option key={s}>{s}</option>)}
          </select>
          <ChevronDown size={10} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none"/>
        </div>
        <div className="flex gap-1 bg-gray-900 rounded-lg p-1">
          {INTERVALS.map(iv=>(
            <button key={iv.label} onClick={()=>setInterval(iv)}
              className={clsx('px-2.5 py-1 rounded text-xs font-medium transition-all',
                interval.label===iv.label?'bg-blue-600 text-white':'text-gray-400 hover:text-white')}>
              {iv.label}
            </button>
          ))}
        </div>
        <div className="flex gap-1 bg-gray-900 rounded-lg p-1 ml-auto">
          {['EMA','BB','RSI','MACD','None'].map(ind=>(
            <button key={ind} onClick={()=>setIndicator(ind)}
              className={clsx('px-2.5 py-1 rounded text-xs font-medium transition-all',
                indicator===ind?'bg-purple-600 text-white':'text-gray-400 hover:text-white')}>
              {ind}
            </button>
          ))}
        </div>
      </div>

      {/* Main chart */}
      <div className="rounded-xl overflow-hidden bg-gray-950 border border-gray-800 relative">
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-gray-950/80 z-10">
            <RefreshCw size={18} className="animate-spin text-blue-400 mr-2"/>
            <span className="text-gray-400 text-sm">Loading chart…</span>
          </div>
        )}
        {candles.length > 0 && (
          <CandlestickSVG
            candles={candles} indicator={indicator}
            width={width} height={height}
          />
        )}
      </div>

      {indicator === 'RSI'  && <RSIPanel  candles={candles} rsiVals={rsiVals} width={width}/>}
      {indicator === 'MACD' && candles.length > 30 && <MACDPanel candles={candles} width={width}/>}
    </div>
  )
}
