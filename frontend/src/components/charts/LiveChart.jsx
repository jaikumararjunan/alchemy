/**
 * LiveChart.jsx — Real-time candlestick/line/area chart
 * Pure SVG, zero extra deps, crash-safe, stable re-renders
 */
import { useEffect, useRef, useState, useCallback, memo } from 'react'
import { RefreshCw, ChevronDown, ZoomIn, ZoomOut } from 'lucide-react'
import clsx from 'clsx'

const SYMBOLS = ['BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT','XRPUSDT','DOGEUSDT','ADAUSDT']
const INTERVALS = [
  {l:'1m',w:'1m'},{l:'5m',w:'5m'},{l:'15m',w:'15m'},
  {l:'1h',w:'1h'},{l:'4h',w:'4h'},{l:'1d',w:'1d'},
]

/* ─── Indicators ───────────────────────────────────────── */
function calcEMA(arr, p) {
  if (!arr.length) return []
  const k=2/(p+1); let e=arr[0]
  return arr.map(v=>{e=v*k+e*(1-k);return e})
}
function calcRSI(cl, p=14) {
  if (cl.length<p+1) return cl.map(()=>null)
  const out=[]; let ag=0, al=0
  for(let i=1;i<=p;i++){const d=cl[i]-cl[i-1];d>0?ag+=d:al-=d}
  ag/=p; al/=p
  out.push(...Array(p).fill(null), al===0?100:100-100/(1+ag/al))
  for(let i=p+1;i<cl.length;i++){
    const d=cl[i]-cl[i-1]
    ag=(ag*(p-1)+Math.max(d,0))/p; al=(al*(p-1)+Math.max(-d,0))/p
    out.push(al===0?100:100-100/(1+ag/al))
  }
  return out
}
function calcBB(cl, p=20, m=2) {
  return cl.map((_,i)=>{
    if(i<p-1) return null
    const sl=cl.slice(i-p+1,i+1), mn=sl.reduce((a,b)=>a+b,0)/p
    const std=Math.sqrt(sl.reduce((a,b)=>a+(b-mn)**2,0)/p)
    return{up:mn+m*std, mid:mn, low:mn-m*std}
  })
}
function calcMACD(cl) {
  const e12=calcEMA(cl,12), e26=calcEMA(cl,26)
  const ml=e12.map((v,i)=>v-e26[i])
  const sg=calcEMA(ml.slice(25),9)
  return ml.map((v,i)=>i<25?null:{macd:v, sig:sg[i-25]??null, hist:sg[i-25]!=null?v-sg[i-25]:null})
}

const fmtP = n => !n||isNaN(n)?'—': n>=1000?n.toLocaleString(undefined,{maximumFractionDigits:2}):n.toFixed(4)
const fmtA = (n, range) => {
  if (n == null || isNaN(n)) return '—'
  // If range is provided, use it for smart formatting
  if (range != null && range > 0) {
    // Show enough decimals to differentiate ticks
    if (range < 0.01) return n.toFixed(6)
    if (range < 1) return n.toFixed(4)
    if (range < 10) return n.toFixed(2)
    if (range < 100) return n.toFixed(1)
    if (range < 1000) return n.toFixed(0)
    // For large prices (BTC): show full number with commas
    return n.toLocaleString(undefined, { maximumFractionDigits: 0 })
  }
  // Fallback (no range context)
  if (n >= 10000) return n.toLocaleString(undefined, { maximumFractionDigits: 0 })
  if (n >= 1000) return n.toFixed(1)
  if (n >= 1) return n.toFixed(2)
  return n.toFixed(4)
}

/* ─── SVG path builder ─────────────────────────────────── */
function buildPath(pts) {
  // pts = array of [x,y] or null
  const segs=[]; let s=[]
  for(const p of pts){
    if(p) s.push(p)
    else { if(s.length>=2) segs.push(s); s=[] }
  }
  if(s.length>=2) segs.push(s)
  return segs.map(seg=>`M${seg[0][0]},${seg[0][1]}L${seg.slice(1).map(p=>p.join(',')).join('L')}`).join(' ')
}

/* ─── Chart Canvas (stable component, defined OUTSIDE LiveChart) ─── */
const ChartCanvas = memo(function ChartCanvas({ candles, chartType, indicator, width }) {
  const svgRef  = useRef(null)
  const dragRef = useRef(null)
  const [zoom,    setZoom]    = useState(1)
  const [panEnd,  setPanEnd]  = useState(0)
  const [hoverI,  setHoverI]  = useState(null)

  /* Wheel with passive:false */
  useEffect(() => {
    const el = svgRef.current
    if (!el) return
    const handler = e => {
      e.preventDefault()
      setZoom(z => Math.min(8, Math.max(0.15, z * (e.deltaY>0 ? 0.82 : 1.22))))
    }
    el.addEventListener('wheel', handler, { passive: false })
    return () => el.removeEventListener('wheel', handler)
  }, []) // empty deps — runs once per mount

  const H=290, PL=8, PR=76, PT=10, PB=22
  const W = Math.max(50, width-PL-PR)

  const maxVis = Math.min(candles.length, Math.max(10, Math.round(100/zoom)))
  const maxPan = Math.max(0, candles.length-maxVis)
  const pe     = Math.min(maxPan, Math.max(0, panEnd))
  const si     = Math.max(0, candles.length-maxVis-pe)
  const vis    = candles.slice(si, si+maxVis)

  if (!vis.length) return (
    <div style={{height:H+PT+PB}} className="flex items-center justify-center text-gray-600 text-sm">
      Loading chart…
    </div>
  )

  const highs=vis.map(c=>c.high), lows=vis.map(c=>c.low)
  const pMx=Math.max(...highs), pMn=Math.min(...lows)
  const pad=(pMx-pMn)*0.07||pMx*0.001
  const yMx=pMx+pad, yMn=pMn-pad, yRng=yMx-yMn||1

  const py = v  => PT + H*(1-(v-yMn)/yRng)
  const cx = i  => PL + (i+0.5)*(W/vis.length)
  const bw      = Math.max(1.5, W/vis.length*0.68)

  /* Indicator data sliced to visible range */
  const closes  = candles.map(c=>c.close)
  const slBB  = indicator==='BB'  ? calcBB(closes).slice(si,si+vis.length)  : null
  const slE9  = indicator==='EMA' ? calcEMA(closes,9).slice(si,si+vis.length) : null
  const slE21 = indicator==='EMA' ? calcEMA(closes,21).slice(si,si+vis.length) : null

  const yTicks = [0,1,2,3,4,5,6,7].map(i=>yMn+yRng*i/7)
  const maxVol = Math.max(...vis.map(c=>c.volume), 1)

  const onMDown = e => { dragRef.current={x:e.clientX, pe} }
  const onMMove = e => {
    const rect = svgRef.current?.getBoundingClientRect()
    if (rect) {
      const rx  = e.clientX-rect.left-PL
      const idx = Math.floor(rx/(W/vis.length))
      setHoverI(idx>=0&&idx<vis.length?idx:null)
    }
    if (!dragRef.current) return
    const dx    = e.clientX-dragRef.current.x
    const shift = Math.round(dx/(W/vis.length))
    setPanEnd(Math.max(0, Math.min(maxPan, dragRef.current.pe-shift)))
  }
  const hC = hoverI!=null ? vis[hoverI] : null

  /* Area path */
  const areaPts = vis.map((c,i)=>[cx(i).toFixed(1), py(c.close).toFixed(1)])
  const areaPath = areaPts.length>=2
    ? `M${areaPts[0][0]},${areaPts[0][1]}L${areaPts.slice(1).map(p=>p.join(',')).join('L')}` +
      `L${areaPts.at(-1)[0]},${py(yMn).toFixed(1)}L${areaPts[0][0]},${py(yMn).toFixed(1)}Z`
    : ''
  const linePath = areaPts.length>=2
    ? `M${areaPts[0][0]},${areaPts[0][1]}L${areaPts.slice(1).map(p=>p.join(',')).join('L')}`
    : ''

  /* BB paths */
  const bbPath = key => buildPath(slBB ? slBB.map((v,i)=>v?[cx(i).toFixed(1),py(v[key]).toFixed(1)]:null) : [])
  const emaPth = vals => buildPath(vals ? vals.map((v,i)=>[cx(i).toFixed(1),py(v).toFixed(1)]) : [])

  const lastC = vis.at(-1)

  return (
    <div className="relative select-none">
      {/* OHLCV tooltip */}
      {hC && (
        <div className="absolute top-1.5 left-2 z-20 flex gap-3 text-xs font-mono px-3 py-1.5 rounded-lg border border-gray-700 bg-gray-900/95 pointer-events-none whitespace-nowrap">
          <span className="text-gray-500">{hC.timeLabel}</span>
          {[['O',hC.open,'#94a3b8'],['H',hC.high,'#10b981'],['L',hC.low,'#ef4444'],
            ['C',hC.close,hC.close>=hC.open?'#34d399':'#f87171']].map(([k,v,col])=>(
            <span key={k} style={{color:col}}>
              <span className="opacity-50">{k} </span>{fmtP(v)}
            </span>
          ))}
          <span className="text-gray-600">V <span className="text-gray-400">{(hC.volume/1e6).toFixed(2)}M</span></span>
        </div>
      )}

      {/* Zoom controls */}
      <div className="absolute top-1.5 right-1.5 z-20 flex gap-1">
        <button onClick={()=>setZoom(z=>Math.min(8,z*1.35))}
          className="p-1.5 rounded-lg bg-gray-800/80 text-gray-400 hover:text-white hover:bg-gray-700 transition-colors border border-gray-700">
          <ZoomIn size={11}/>
        </button>
        <button onClick={()=>setZoom(z=>Math.max(0.15,z/1.35))}
          className="p-1.5 rounded-lg bg-gray-800/80 text-gray-400 hover:text-white hover:bg-gray-700 transition-colors border border-gray-700">
          <ZoomOut size={11}/>
        </button>
        <button onClick={()=>{setZoom(1);setPanEnd(0)}}
          className="px-2 py-1 rounded-lg bg-gray-800/80 text-gray-500 hover:text-white hover:bg-gray-700 text-[10px] transition-colors border border-gray-700">
          Reset
        </button>
      </div>

      <svg ref={svgRef} width={width} height={H+PT+PB}
        style={{cursor:dragRef.current?'grabbing':'crosshair', display:'block'}}
        onMouseDown={onMDown}
        onMouseMove={onMMove}
        onMouseUp={()=>{dragRef.current=null}}
        onMouseLeave={()=>{dragRef.current=null; setHoverI(null)}}>

        <defs>
          <linearGradient id="gArea" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%"   stopColor="#10b981" stopOpacity="0.4"/>
            <stop offset="100%" stopColor="#10b981" stopOpacity="0.02"/>
          </linearGradient>
          <clipPath id="chartClip"><rect x={PL} y={PT} width={W} height={H}/></clipPath>
        </defs>

        {/* Grid */}
        {yTicks.map((p,i)=>(
          <g key={i}>
            <line x1={PL} x2={width-PR} y1={py(p)} y2={py(p)} stroke="#1e293b" strokeWidth={1}/>
            <text x={width-PR+5} y={py(p)+4} fill="#475569" fontSize={9.5}>{fmtA(p, yRng)}</text>
          </g>
        ))}

        <g clipPath="url(#chartClip)">
          {/* Bollinger */}
          {slBB && <>
            <path d={bbPath('up')}  fill="none" stroke="#3b82f640" strokeWidth={1} strokeDasharray="4 3"/>
            <path d={bbPath('mid')} fill="none" stroke="#3b82f670" strokeWidth={1} strokeDasharray="5 3"/>
            <path d={bbPath('low')} fill="none" stroke="#3b82f640" strokeWidth={1} strokeDasharray="4 3"/>
          </>}

          {/* EMA */}
          {slE9  && <path d={emaPth(slE9)}  fill="none" stroke="#f59e0b" strokeWidth={1.5}/>}
          {slE21 && <path d={emaPth(slE21)} fill="none" stroke="#60a5fa" strokeWidth={1.5}/>}

          {/* Volume */}
          {vis.map((c,i)=>{
            const vh=Math.max(1,(c.volume/maxVol)*(H*0.15))
            return <rect key={`v${i}`} x={cx(i)-bw/2} y={PT+H-vh} width={bw} height={vh}
              fill={c.close>=c.open?'#10b98120':'#ef444420'}/>
          })}

          {/* Area */}
          {chartType==='Area' && areaPath && (
            <path d={areaPath} fill="url(#gArea)" stroke="#10b981" strokeWidth={1.5}/>
          )}

          {/* Line */}
          {chartType==='Line' && linePath && (
            <path d={linePath} fill="none" stroke="#3b82f6" strokeWidth={2}/>
          )}

          {/* Candles */}
          {chartType==='Candle' && vis.map((c,i)=>{
            const up=c.close>=c.open, col=up?'#10B981':'#EF4444'
            const bT=py(Math.max(c.open,c.close)), bB=py(Math.min(c.open,c.close))
            const bH=Math.max(1, bB-bT)
            const wW=Math.max(0.8, bw*0.12)
            return(
              <g key={`c${i}`}>
                <line x1={cx(i)} x2={cx(i)} y1={py(c.high)} y2={bT} stroke={col} strokeWidth={wW}/>
                <line x1={cx(i)} x2={cx(i)} y1={bB} y2={py(c.low)} stroke={col} strokeWidth={wW}/>
                <rect x={cx(i)-bw/2} y={bT} width={bw} height={bH}
                  fill={col} opacity={hoverI===i?1:0.85}
                  stroke={hoverI===i?'#ffffffaa':col} strokeWidth={hoverI===i?0.5:0}
                  rx={bw>6?1.5:0}/>
              </g>
            )
          })}
        </g>

        {/* Last price tag */}
        {lastC && !hC && (()=>{
          const y=py(lastC.close), up=lastC.close>=lastC.open
          return(<>
            <line x1={PL} x2={width-PR} y1={y} y2={y}
              stroke={up?'#10B98140':'#EF444440'} strokeWidth={1} strokeDasharray="3 3"/>
            <rect x={width-PR} y={y-8} width={PR-2} height={16}
              fill={up?'#10B981':'#EF4444'} rx={3}/>
            <text x={width-PR+3} y={y+5} fill="#fff" fontSize={9} fontWeight="600">{fmtA(lastC.close, yRng)}</text>
          </>)
        })()}

        {/* Hover crosshair */}
        {hC && hoverI!=null && (
          <g>
            <line x1={cx(hoverI)} x2={cx(hoverI)} y1={PT} y2={PT+H} stroke="#ffffff18" strokeWidth={1}/>
            <line x1={PL} x2={width-PR} y1={py(hC.close)} y2={py(hC.close)} stroke="#ffffff18" strokeWidth={1}/>
            <rect x={width-PR} y={py(hC.close)-8} width={PR-2} height={16}
              fill={hC.close>=hC.open?'#10B981':'#EF4444'} rx={3}/>
            <text x={width-PR+3} y={py(hC.close)+5} fill="#fff" fontSize={9} fontWeight="600">{fmtA(hC.close, yRng)}</text>
          </g>
        )}

        {/* Time labels */}
        {(()=>{
          const step = Math.max(1, Math.floor(vis.length / 7))
          return vis.map((c, i) => {
            if (i % step !== 0) return null
            return <text key={i} x={cx(i)} y={PT+H+PB-3}
              fill="#475569" fontSize={9} textAnchor="middle">{c.timeLabel}</text>
          })
        })()}

        <rect x={PL} y={PT} width={W} height={H} fill="none" stroke="#1e293b" strokeWidth={1}/>
      </svg>

      <div className="text-center text-[10px] text-gray-700 mt-0.5">
        ↕ scroll to zoom · ← drag to pan → · {vis.length} candles · total {candles.length}
      </div>
    </div>
  )
})

/* ─── RSI Panel ────────────────────────────────────────── */
const RSIPanel = memo(function RSIPanel({ candles, width }) {
  const H=72, PL=8, PR=66, PT=8, PB=16
  const W=Math.max(50, width-PL-PR)
  const closes = candles.map(c=>c.close)
  const rsi    = calcRSI(closes)
  const valid  = candles.map((c,i)=>rsi[i]!=null?{v:rsi[i],i}:null).filter(Boolean)
  if (valid.length < 5) return null
  const cx = i => PL+(i/(valid.length-1||1))*W
  const py = v => PT+H*(1-v/100)
  const pts = valid.map((d,k)=>[cx(k).toFixed(1), py(d.v).toFixed(1)])
  const path = pts.length>=2 ? `M${pts[0][0]},${pts[0][1]}L${pts.slice(1).map(p=>p.join(',')).join('L')}` : ''
  const last = valid.at(-1)
  const lCol = last?.v>=70?'#ef4444':last?.v<=30?'#10b981':'#a78bfa'
  return(
    <div className="rounded-xl bg-gray-950 border border-gray-800 overflow-hidden">
      <div className="flex items-center justify-between px-3 pt-1.5">
        <span className="text-[10px] text-gray-500">RSI (14)</span>
        {last && <span className="text-xs font-mono font-bold" style={{color:lCol}}>{last.v.toFixed(1)}</span>}
      </div>
      <svg width={width} height={H+PT+PB}>
        {[70,50,30].map(v=><g key={v}>
          <line x1={PL} x2={width-PR} y1={py(v)} y2={py(v)}
            stroke={v===50?'#334155':'#1e293b'} strokeWidth={1} strokeDasharray={v===50?undefined:'3 3'}/>
          <text x={width-PR+5} y={py(v)+4} fill="#475569" fontSize={9}>{v}</text>
        </g>)}
        {path && <path d={path} fill="none" stroke="#a78bfa" strokeWidth={1.5}/>}
        {last && <circle cx={cx(valid.length-1)} cy={py(last.v)} r={3} fill={lCol}/>}
      </svg>
    </div>
  )
})

/* ─── MACD Panel ───────────────────────────────────────── */
const MACDPanel = memo(function MACDPanel({ candles, width }) {
  const H=80, PL=8, PR=66, PT=8, PB=16
  const W=Math.max(50, width-PL-PR)
  const closes = candles.map(c=>c.close)
  const all    = calcMACD(closes)
  const data   = all.map((d,i)=>d?.sig!=null?{...d,t:candles[i].timeLabel,i}:null).filter(Boolean)
  if (data.length < 5) return null
  const vals = [...data.map(d=>d.macd),...data.map(d=>d.sig),...data.map(d=>d.hist||0)]
  const mn=Math.min(...vals)*1.1, mx=Math.max(...vals)*1.1, rng=mx-mn||1
  const py = v => PT+H*(1-(v-mn)/rng)
  const cx = i => PL+(i/(data.length-1||1))*W
  const zero = py(0)
  const bw = Math.max(1,(W/data.length)*0.6)
  const mkL = key => {
    const pts = data.map((d,i)=>[cx(i).toFixed(1), py(d[key]).toFixed(1)])
    return pts.length>=2 ? `M${pts[0][0]},${pts[0][1]}L${pts.slice(1).map(p=>p.join(',')).join('L')}` : ''
  }
  return(
    <div className="rounded-xl bg-gray-950 border border-gray-800 overflow-hidden">
      <div className="flex items-center gap-3 px-3 pt-1.5">
        <span className="text-[10px] text-gray-500">MACD (12,26,9)</span>
        <span className="text-[10px] text-blue-400">━ MACD</span>
        <span className="text-[10px] text-amber-400">━ Signal</span>
      </div>
      <svg width={width} height={H+PT+PB}>
        <line x1={PL} x2={width-PR} y1={zero} y2={zero} stroke="#334155" strokeWidth={1}/>
        {data.map((d,i)=>d.hist!=null&&(
          <rect key={i} x={cx(i)-bw/2}
            y={d.hist>=0?py(d.hist):zero} width={bw}
            height={Math.max(1,Math.abs(py(d.hist)-zero))}
            fill={d.hist>=0?'#10b98155':'#ef444455'}/>
        ))}
        {mkL('macd') && <path d={mkL('macd')} fill="none" stroke="#3b82f6" strokeWidth={1.5}/>}
        {mkL('sig')  && <path d={mkL('sig')}  fill="none" stroke="#f59e0b" strokeWidth={1}/>}
      </svg>
    </div>
  )
})

/* ─── Main export ──────────────────────────────────────── */
export default function LiveChart({ defaultSymbol='BTCUSDT', height=290 }) {
  const containerRef = useRef(null)
  const wsRef        = useRef(null)
  const mapRef       = useRef({})

  const [width,     setWidth]     = useState(800)
  const [symbol,    setSymbol]    = useState(defaultSymbol)
  const [interval,  setInterval]  = useState('1m')
  const [chartType, setChartType] = useState('Candle')
  const [indicator, setIndicator] = useState('BB')
  const [candles,   setCandles]   = useState([])
  const [ticker,    setTicker]    = useState(null)
  const [status,    setStatus]    = useState('idle')

  /* Responsive width */
  useEffect(()=>{
    if(!containerRef.current) return
    const ro=new ResizeObserver(entries=>{
      const w=entries[0]?.contentRect?.width
      if(w>0) setWidth(w)
    })
    ro.observe(containerRef.current)
    const w=containerRef.current.getBoundingClientRect().width
    if(w>0) setWidth(w)
    return()=>ro.disconnect()
  },[])

  /* Load history + WS */
  useEffect(()=>{
    setStatus('loading')
    mapRef.current={}
    if(wsRef.current){wsRef.current.close();wsRef.current=null}

    const rest = `https://api.binance.com/api/v3/klines?symbol=${symbol}&interval=${interval}&limit=250`
    const proxy = `/api/crypto/proxy/klines?symbol=${symbol}&interval=${interval}&limit=250`

    fetch(rest)
      .catch(()=>fetch(proxy))
      .then(r=>r.json())
      .then(data=>{
        if(!Array.isArray(data)||!data.length) return
        const parsed=data.map(k=>({
          openTime: k[0],
          timeLabel:new Date(k[0]).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit',hour12:false}),
          open:parseFloat(k[1]),high:parseFloat(k[2]),
          low:parseFloat(k[3]),close:parseFloat(k[4]),
          volume:parseFloat(k[5]),
        }))
        parsed.forEach(c=>{mapRef.current[c.openTime]=c})
        setCandles([...parsed])
      })
      .catch(e=>{ console.error('klines error',e); setStatus('error') })

    /* WebSocket */
    const streams=`${symbol.toLowerCase()}@kline_${interval}/${symbol.toLowerCase()}@miniTicker`
    const ws=new WebSocket(`wss://stream.binance.com:9443/stream?streams=${streams}`)
    wsRef.current=ws
    ws.onopen=()=>setStatus('live')
    ws.onclose=()=>setStatus(s=>s==='live'?'reconnecting':s)
    ws.onerror=()=>{}
    ws.onmessage=e=>{
      try{
        const {stream:s, data:d}=JSON.parse(e.data)
        if(s?.includes('kline')){
          const k=d.k
          const c={
            openTime:k.t,
            timeLabel:new Date(k.t).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit',hour12:false}),
            open:parseFloat(k.o),high:parseFloat(k.h),
            low:parseFloat(k.l),close:parseFloat(k.c),
            volume:parseFloat(k.v),
          }
          mapRef.current[k.t]=c
          setCandles(Object.values(mapRef.current).sort((a,b)=>a.openTime-b.openTime))
        }
        if(s?.includes('miniTicker')){
          setTicker({
            price:parseFloat(d.c),
            changePct:(parseFloat(d.c)-parseFloat(d.o))/parseFloat(d.o)*100,
            high:parseFloat(d.h), low:parseFloat(d.l), volume:parseFloat(d.v),
          })
        }
      }catch{}
    }
    return()=>{if(wsRef.current){wsRef.current.close();wsRef.current=null}}
  },[symbol, interval])

  const isUp   = (ticker?.changePct??0)>=0
  const price  = ticker?.price ?? candles.at(-1)?.close
  const stCol  = {live:'#10b981',loading:'#94a3b8',idle:'#94a3b8',error:'#ef4444',reconnecting:'#f59e0b'}

  return(
    <div ref={containerRef} className="space-y-2 w-full min-w-0">
      {/* Ticker */}
      <div className="flex items-start justify-between flex-wrap gap-2">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-3xl font-bold text-white font-mono tracking-tight leading-none">
              {price ? `$${fmtP(price)}` : <span className="text-gray-700 animate-pulse">———</span>}
            </span>
            {ticker&&(
              <span className={clsx('text-sm font-bold px-2 py-0.5 rounded-lg font-mono',
                isUp?'text-emerald-400 bg-emerald-900/30':'text-red-400 bg-red-900/30')}>
                {isUp?'+':''}{ticker.changePct?.toFixed(2)}%
              </span>
            )}
            <span className="flex items-center gap-1 text-[10px] font-medium" style={{color:stCol[status]}}>
              <span className="w-1.5 h-1.5 rounded-full inline-block animate-pulse" style={{background:stCol[status]}}/>
              {status}
            </span>
          </div>
          {ticker&&(
            <div className="flex gap-4 text-xs text-gray-500 mt-1 font-mono">
              <span>H: <span className="text-emerald-400">{fmtP(ticker.high)}</span></span>
              <span>L: <span className="text-red-400">{fmtP(ticker.low)}</span></span>
              <span>Vol: {(ticker.volume/1e6).toFixed(2)}M</span>
              <span className="text-gray-700">{candles.length} bars</span>
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
          <ChevronDown size={10} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 pointer-events-none"/>
        </div>

        {/* Intervals */}
        <div className="flex bg-gray-900 rounded-lg p-1 gap-0.5">
          {INTERVALS.map(iv=>(
            <button key={iv.l} onClick={()=>setInterval(iv.l)}
              className={clsx('px-2.5 py-1 rounded text-xs font-medium transition-all',
                interval===iv.l?'bg-blue-600 text-white shadow':'text-gray-400 hover:text-white')}>
              {iv.l}
            </button>
          ))}
        </div>

        {/* Chart type */}
        <div className="flex bg-gray-900 rounded-lg p-1 gap-0.5">
          {['Candle','Line','Area'].map(t=>(
            <button key={t} onClick={()=>setChartType(t)}
              className={clsx('px-2.5 py-1 rounded text-xs font-medium transition-all',
                chartType===t?'bg-emerald-700 text-white shadow':'text-gray-400 hover:text-white')}>
              {t}
            </button>
          ))}
        </div>

        {/* Indicators */}
        <div className="flex bg-gray-900 rounded-lg p-1 gap-0.5 ml-auto">
          {['EMA','BB','RSI','MACD','None'].map(ind=>(
            <button key={ind} onClick={()=>setIndicator(ind)}
              className={clsx('px-2.5 py-1 rounded text-xs font-medium transition-all',
                indicator===ind?'bg-purple-600 text-white shadow':'text-gray-400 hover:text-white')}>
              {ind}
            </button>
          ))}
        </div>
      </div>

      {/* Chart */}
      <div className="rounded-xl bg-gray-950 border border-gray-800 overflow-hidden relative">
        {(status==='loading'||status==='idle')&&!candles.length&&(
          <div className="absolute inset-0 flex items-center justify-center bg-gray-950/95 z-10">
            <RefreshCw size={18} className="animate-spin text-blue-400 mr-2"/>
            <span className="text-gray-400 text-sm">Loading 250 candles from Binance…</span>
          </div>
        )}
        {status==='error'&&!candles.length&&(
          <div className="flex items-center justify-center py-16 text-gray-600 text-sm">
            Failed to load chart data. Check internet connection.
          </div>
        )}
        {candles.length>0&&(
          <ChartCanvas
            candles={candles}
            chartType={chartType}
            indicator={indicator}
            width={width}
          />
        )}
      </div>

      {/* Sub-panels */}
      {indicator==='RSI'&&candles.length>14&&<RSIPanel candles={candles} width={width}/>}
      {indicator==='MACD'&&candles.length>30&&<MACDPanel candles={candles} width={width}/>}
    </div>
  )
}
