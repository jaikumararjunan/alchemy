/**
 * LiveChart.jsx — Real-time financial chart
 * Pure SVG · Zero extra deps · Candlestick + Line + Area
 * Binance public WebSocket — no API key needed
 */
import { useEffect, useRef, useState, useCallback } from 'react'
import { RefreshCw, ChevronDown, ZoomIn, ZoomOut } from 'lucide-react'
import clsx from 'clsx'

const SYMBOLS   = ['BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT','XRPUSDT','DOGEUSDT','ADAUSDT','AVAXUSDT']
const INTERVALS = [
  {label:'1m',ws:'1m',rest:'1m'},   {label:'5m',ws:'5m',rest:'5m'},
  {label:'15m',ws:'15m',rest:'15m'},{label:'1h',ws:'1h',rest:'1h'},
  {label:'4h',ws:'4h',rest:'4h'},   {label:'1d',ws:'1d',rest:'1d'},
]
const CHART_TYPES = ['Candle','Line','Area']

/* ── math helpers ─────────────────────────────────────────────── */
const ema = (arr, p) => {
  if (!arr.length) return []
  const k=2/(p+1); let e=arr[0]
  return arr.map(v=>{e=v*k+e*(1-k);return e})
}
const calcRSI = (cl,p=14) => {
  if(cl.length<p+1) return cl.map(()=>null)
  const r=[]; let ag=0,al=0
  for(let i=1;i<=p;i++){const d=cl[i]-cl[i-1];d>0?ag+=d:al-=d}
  ag/=p;al/=p;r.push(...Array(p).fill(null),al===0?100:100-100/(1+ag/al))
  for(let i=p+1;i<cl.length;i++){
    const d=cl[i]-cl[i-1]
    ag=(ag*(p-1)+Math.max(d,0))/p;al=(al*(p-1)+Math.max(-d,0))/p
    r.push(al===0?100:100-100/(1+ag/al))
  }
  return r
}
const calcBB = (cl,p=20,m=2) => cl.map((_,i)=>{
  if(i<p-1) return null
  const sl=cl.slice(i-p+1,i+1),mn=sl.reduce((a,b)=>a+b,0)/p
  const s=Math.sqrt(sl.reduce((a,b)=>a+(b-mn)**2,0)/p)
  return{up:mn+m*s,mid:mn,low:mn-m*s}
})
const calcMACD = cl => {
  const e12=ema(cl,12),e26=ema(cl,26)
  const ml=e12.map((v,i)=>v-e26[i])
  const sg=ema(ml.slice(25),9)
  return ml.map((v,i)=>i<25?null:{macd:v,sig:sg[i-25]??null,hist:sg[i-25]!=null?v-sg[i-25]:null})
}

const fmtPrice = n => {
  if(n==null||isNaN(n)) return '—'
  if(n>=1000) return n.toLocaleString(undefined,{maximumFractionDigits:2})
  return n.toFixed(4)
}
const fmtAxis = n => {
  if(n>=10000) return `${(n/1000).toFixed(0)}K`
  if(n>=1000)  return `${(n/1000).toFixed(1)}K`
  return n.toFixed(2)
}

/* ── Main chart SVG ───────────────────────────────────────────── */
function ChartCanvas({ candles, chartType, indicator, width }) {
  const H      = 300
  const PL     = 8, PR = 68, PT = 10, PB = 24
  const W      = Math.max(100, width - PL - PR)

  /* zoom/pan state */
  const [zoom,    setZoom]    = useState(1)
  const [panEnd,  setPanEnd]  = useState(0)   // how many candles from END are hidden (pan right = show older)
  const [hoverI,  setHoverI]  = useState(null)
  const dragRef   = useRef(null)
  const svgRef    = useRef(null)

  /* which candles are visible */
  const maxVis  = Math.min(candles.length, Math.max(10, Math.round(100 / zoom)))
  const endHide = Math.min(Math.max(0, panEnd), Math.max(0, candles.length - maxVis))
  const startI  = Math.max(0, candles.length - maxVis - endHide)
  const endI    = candles.length - endHide
  const visible = candles.slice(startI, endI || candles.length)

  if (!visible.length) return (
    <div className="flex items-center justify-center text-gray-600 text-sm"
         style={{height:H+PT+PB}}>
      Waiting for data…
    </div>
  )

  /* price range with padding */
  const highs = visible.map(c=>c.high), lows = visible.map(c=>c.low)
  const pMax  = Math.max(...highs), pMin = Math.min(...lows)
  const pad   = (pMax-pMin)*0.06 || pMax*0.001
  const yMax  = pMax+pad, yMin = pMin-pad, yRng = yMax-yMin

  /* coordinate helpers */
  const py = v  => PT + H*(1-(v-yMin)/yRng)
  const cx = i  => PL + (i+0.5)*(W/visible.length)
  const bw      = Math.max(1.5, W/visible.length*0.7)

  /* indicator data (indexed on full candles, sliced to visible) */
  const closes  = candles.map(c=>c.close)
  const slClose = closes.slice(startI, endI||candles.length)
  const bbData  = indicator==='BB'  ? calcBB(closes).slice(startI,endI||candles.length) : null
  const e9Data  = indicator==='EMA' ? ema(closes,9).slice(startI,endI||candles.length)  : null
  const e21Data = indicator==='EMA' ? ema(closes,21).slice(startI,endI||candles.length) : null
  const rsiData = indicator==='RSI' ? calcRSI(closes).slice(startI,endI||candles.length): null
  const macdData= indicator==='MACD'? calcMACD(closes).slice(startI,endI||candles.length):null

  /* Y-axis ticks */
  const yTicks  = [0,1,2,3,4,5].map(i=>yMin+yRng*i/5)

  /* build SVG path from value array — safe with 0 or 1 points */
  const mkLine = vals => {
    const pts = vals.map((v,i)=>v!=null?`${cx(i).toFixed(1)},${py(v).toFixed(1)}`:null)
    const segs=[]; let s=[]
    for(const p of pts){if(p)s.push(p);else if(s.length>=2){segs.push(s);s=[]} else s=[]}
    if(s.length>=2)segs.push(s)
    return segs.map(s=>`M${s[0]}L${s.slice(1).join('L')}`).join(' ')
  }

  /* area fill path */
  const mkArea = vals => {
    const valid = vals.map((v,i)=>({v,i})).filter(d=>d.v!=null&&!isNaN(d.v))
    if(valid.length<2) return ''
    const top  = valid.map(d=>`${cx(d.i).toFixed(1)},${py(d.v).toFixed(1)}`).join('L')
    const base = `${cx(valid.at(-1).i).toFixed(1)},${py(yMin).toFixed(1)}L${cx(valid[0].i).toFixed(1)},${py(yMin).toFixed(1)}`
    return `M${top}L${base}Z`
  }

  /* events */
  const onWheelHandler = useCallback(e => {
    e.preventDefault()
    const factor = e.deltaY>0 ? 0.82 : 1.22
    setZoom(z=>Math.min(8, Math.max(0.15, z*factor)))
  }, [])

  /* Attach wheel listener with passive:false to allow preventDefault */
  useEffect(()=>{
    const el = svgRef.current
    if(!el) return
    el.addEventListener('wheel', onWheelHandler, {passive:false})
    return()=>el.removeEventListener('wheel', onWheelHandler)
  }, [onWheelHandler])
  const onMDown = e => {
    dragRef.current={x:e.clientX, pan:endHide}
  }
  const onMMove = e => {
    const rect = svgRef.current?.getBoundingClientRect()
    if(rect){
      const rx = e.clientX - rect.left - PL
      const idx = Math.floor(rx/(W/visible.length))
      setHoverI(idx>=0&&idx<visible.length?idx:null)
    }
    if(!dragRef.current) return
    const dx    = e.clientX - dragRef.current.x
    const shift = Math.round(dx/(W/visible.length))
    const next  = Math.max(0, Math.min(candles.length-maxVis, dragRef.current.pan-shift))
    setPanEnd(next)
  }
  const onMUp   = ()=>{dragRef.current=null}
  const onMLeave=()=>{dragRef.current=null;setHoverI(null)}
  const hC = hoverI!=null ? visible[hoverI] : null

  return (
    <div className="relative select-none">
      {/* OHLCV tooltip */}
      {hC && (
        <div className="absolute top-2 left-2 z-20 flex gap-3 text-xs font-mono px-3 py-1.5 rounded-lg border border-gray-700 bg-gray-900/95 pointer-events-none">
          <span className="text-gray-500">{hC.timeLabel}</span>
          {[['O',hC.open,'text-gray-200'],['H',hC.high,'text-emerald-400'],
            ['L',hC.low,'text-red-400'],
            ['C',hC.close,hC.close>=hC.open?'text-emerald-300':'text-red-300']].map(([k,v,col])=>(
            <span key={k}><span className="text-gray-600">{k} </span><span className={col}>{fmtPrice(v)}</span></span>
          ))}
          <span className="text-gray-600">V <span className="text-gray-400">{(hC.volume/1e6).toFixed(2)}M</span></span>
        </div>
      )}

      {/* Zoom buttons */}
      <div className="absolute top-2 right-2 z-20 flex gap-1">
        <button onClick={()=>setZoom(z=>Math.min(8,z*1.3))}
          className="p-1 rounded bg-gray-800/80 text-gray-400 hover:text-white hover:bg-gray-700 transition-colors">
          <ZoomIn size={12}/>
        </button>
        <button onClick={()=>setZoom(z=>Math.max(0.15,z/1.3))}
          className="p-1 rounded bg-gray-800/80 text-gray-400 hover:text-white hover:bg-gray-700 transition-colors">
          <ZoomOut size={12}/>
        </button>
        <button onClick={()=>{setZoom(1);setPanEnd(0)}}
          className="px-2 py-1 rounded bg-gray-800/80 text-gray-500 hover:text-white hover:bg-gray-700 text-xs transition-colors">
          Reset
        </button>
      </div>

      <svg ref={svgRef} width={width} height={H+PT+PB}
        style={{cursor:dragRef.current?'grabbing':'crosshair'}}
        onMouseDown={onMDown} onMouseMove={onMMove}
        onMouseUp={onMUp} onMouseLeave={onMLeave}>

        <defs>
          <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%"   stopColor="#3b82f6" stopOpacity="0.35"/>
            <stop offset="100%" stopColor="#3b82f6" stopOpacity="0.02"/>
          </linearGradient>
          <linearGradient id="areaGradG" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%"   stopColor="#10b981" stopOpacity="0.35"/>
            <stop offset="100%" stopColor="#10b981" stopOpacity="0.02"/>
          </linearGradient>
          <clipPath id="chartClip">
            <rect x={PL} y={PT} width={W} height={H}/>
          </clipPath>
        </defs>

        {/* Grid */}
        {yTicks.map((p,i)=>(
          <g key={i}>
            <line x1={PL} x2={width-PR} y1={py(p)} y2={py(p)} stroke="#1e293b" strokeWidth={1}/>
            <text x={width-PR+5} y={py(p)+4} fill="#475569" fontSize={9.5}>{fmtAxis(p)}</text>
          </g>
        ))}

        <g clipPath="url(#chartClip)">
          {/* ── Bollinger bands ── */}
          {bbData && (<>
            <path d={mkLine(bbData.map(v=>v?.up))}  fill="none" stroke="#3b82f644" strokeWidth={1} strokeDasharray="4 3"/>
            <path d={mkLine(bbData.map(v=>v?.mid))} fill="none" stroke="#3b82f677" strokeWidth={1} strokeDasharray="5 3"/>
            <path d={mkLine(bbData.map(v=>v?.low))} fill="none" stroke="#3b82f644" strokeWidth={1} strokeDasharray="4 3"/>
          </>)}

          {/* ── EMA lines ── */}
          {e9Data  && <path d={mkLine(e9Data)}  fill="none" stroke="#f59e0b" strokeWidth={1.5}/>}
          {e21Data && <path d={mkLine(e21Data)} fill="none" stroke="#60a5fa" strokeWidth={1.5}/>}

          {/* ── Volume bars at bottom 15% ── */}
          {(() => {
            const maxV = Math.max(...visible.map(c=>c.volume),1)
            return visible.map((c,i)=>{
              const vh = Math.max(1,(c.volume/maxV)*(H*0.15))
              return <rect key={`v${i}`}
                x={cx(i)-bw/2} y={PT+H-vh} width={bw} height={vh}
                fill={c.close>=c.open?'#10b98120':'#ef444420'}/>
            })
          })()}

          {/* ── AREA chart ── */}
          {chartType==='Area' && (
            <path d={mkArea(visible.map(c=>c.close))}
              fill="url(#areaGradG)" stroke="#10b981" strokeWidth={1.5}/>
          )}

          {/* ── LINE chart ── */}
          {chartType==='Line' && (
            <path d={mkLine(visible.map(c=>c.close))}
              fill="none" stroke="#3b82f6" strokeWidth={2}/>
          )}

          {/* ── CANDLESTICK ── */}
          {chartType==='Candle' && visible.map((c,i)=>{
            const up   = c.close>=c.open
            const col  = up?'#10B981':'#EF4444'
            const bodyT= py(Math.max(c.open,c.close))
            const bodyB= py(Math.min(c.open,c.close))
            const bodyH= Math.max(1, bodyB-bodyT)
            const isHov= hoverI===i
            return(
              <g key={`c${i}`}>
                {/* High wick */}
                <line x1={cx(i)} x2={cx(i)} y1={py(c.high)} y2={bodyT}
                  stroke={col} strokeWidth={Math.max(1,bw*0.15)}/>
                {/* Low wick */}
                <line x1={cx(i)} x2={cx(i)} y1={bodyB} y2={py(c.low)}
                  stroke={col} strokeWidth={Math.max(1,bw*0.15)}/>
                {/* Body */}
                <rect x={cx(i)-bw/2} y={bodyT} width={bw} height={bodyH}
                  fill={col} opacity={isHov?1:0.85}
                  stroke={isHov?'#ffffffaa':col} strokeWidth={isHov?0.5:0}
                  rx={bw>4?1:0}/>
              </g>
            )
          })}
        </g>

        {/* Crosshair price tag */}
        {hC && (<>
          <line x1={PL} x2={width-PR} y1={py(hC.close)} y2={py(hC.close)}
            stroke="#ffffff18" strokeWidth={1} strokeDasharray="3 3"/>
          <rect x={width-PR} y={py(hC.close)-8} width={PR-2} height={16}
            fill={hC.close>=hC.open?'#10B981':'#EF4444'} rx={3}/>
          <text x={width-PR+4} y={py(hC.close)+5} fill="#fff" fontSize={9} fontWeight="600">
            {fmtAxis(hC.close)}
          </text>
        </>)}

        {/* Last price line */}
        {!hC && visible.length>0 && (()=>{
          const last = visible.at(-1)
          const y = py(last.close)
          const up = last.close>=last.open
          return(<>
            <line x1={PL} x2={width-PR} y1={y} y2={y}
              stroke={up?'#10B98140':'#EF444440'} strokeWidth={1} strokeDasharray="3 3"/>
            <rect x={width-PR} y={y-8} width={PR-2} height={16}
              fill={up?'#10B981':'#EF4444'} rx={3}/>
            <text x={width-PR+4} y={y+5} fill="#fff" fontSize={9} fontWeight="600">
              {fmtAxis(last.close)}
            </text>
          </>)
        })()}

        {/* Time axis */}
        {visible.filter((_,i)=>i%Math.max(1,Math.floor(visible.length/7))===0).map((c,i)=>(
          <text key={i} x={cx(visible.indexOf(c))} y={PT+H+PB-3}
            fill="#475569" fontSize={9} textAnchor="middle">{c.timeLabel}</text>
        ))}

        {/* Border */}
        <rect x={PL} y={PT} width={W} height={H} fill="none" stroke="#1e293b" strokeWidth={1}/>
      </svg>

      <div className="text-center text-[10px] text-gray-700 -mt-1">
        Scroll to zoom · Drag to pan · {visible.length} candles shown
      </div>
    </div>
  )
}

/* ── RSI sub-panel ──────────────────────────────────────────────── */
function RSIPanel({ candles, width }) {
  const H=70,PL=8,PR=68,PT=8,PB=16
  const W=Math.max(10,width-PL-PR)
  const all = calcRSI(candles.map(c=>c.close))
  const data = candles.map((c,i)=>all[i]!=null?{v:all[i],t:c.timeLabel}:null).filter(Boolean)
  if(data.length<5) return null
  const cx=(i)=>PL+(i/(data.length-1||1))*W
  const py=(v)=>PT+H*(1-v/100)
  const pts = data.map((d,i)=>`${cx(i).toFixed(1)},${py(d.v).toFixed(1)}`).join('L')
  const last = data.at(-1)
  const lastCol = last?.v>=70?'#ef4444':last?.v<=30?'#10b981':'#a78bfa'
  return(
    <div className="rounded-xl bg-gray-950 border border-gray-800 overflow-hidden">
      <div className="flex items-center justify-between px-3 pt-2">
        <span className="text-[10px] text-gray-500">RSI (14)</span>
        {last&&<span className="text-xs font-mono font-bold" style={{color:lastCol}}>{last.v.toFixed(1)}</span>}
      </div>
      <svg width={width} height={H+PT+PB}>
        {[70,50,30].map(v=><g key={v}>
          <line x1={PL} x2={width-PR} y1={py(v)} y2={py(v)} stroke={v===50?'#334155':'#1e293b'} strokeWidth={1} strokeDasharray={v===50?'':'3 3'}/>
          <text x={width-PR+5} y={py(v)+4} fill="#475569" fontSize={9}>{v}</text>
        </g>)}
        <polyline points={pts} fill="none" stroke="#a78bfa" strokeWidth={1.5}/>
        {last&&<circle cx={cx(data.length-1)} cy={py(last.v)} r={3} fill={lastCol}/>}
      </svg>
    </div>
  )
}

/* ── MACD sub-panel ─────────────────────────────────────────────── */
function MACDPanel({ candles, width }) {
  const H=80,PL=8,PR=68,PT=8,PB=16
  const W=Math.max(10,width-PL-PR)
  const all = calcMACD(candles.map(c=>c.close))
  const data = candles.map((c,i)=>all[i]).filter(d=>d?.sig!=null)
  if(data.length<5) return null
  const vals=[...data.map(d=>d.macd),...data.map(d=>d.sig),...data.map(d=>d.hist||0)]
  const mn=Math.min(...vals)*1.1, mx=Math.max(...vals)*1.1, rng=mx-mn||1
  const py=v=>PT+H*(1-(v-mn)/rng)
  const cx=i=>PL+(i/(data.length-1||1))*W
  const bw=Math.max(1,(W/data.length)*0.6)
  const zero=py(0)
  const macdPts=data.map((d,i)=>`${cx(i).toFixed(1)},${py(d.macd).toFixed(1)}`).join('L')
  const sigPts =data.map((d,i)=>`${cx(i).toFixed(1)},${py(d.sig).toFixed(1)}`).join('L')
  return(
    <div className="rounded-xl bg-gray-950 border border-gray-800 overflow-hidden">
      <div className="px-3 pt-2">
        <span className="text-[10px] text-gray-500">MACD (12, 26, 9)</span>
        <span className="ml-3 text-[10px]"><span className="text-blue-400">━</span> MACD </span>
        <span className="text-[10px]"><span className="text-amber-400">━</span> Signal</span>
      </div>
      <svg width={width} height={H+PT+PB}>
        <line x1={PL} x2={width-PR} y1={zero} y2={zero} stroke="#334155" strokeWidth={1}/>
        {data.map((d,i)=>d.hist!=null&&(
          <rect key={i} x={cx(i)-bw/2}
            y={d.hist>=0?py(d.hist):zero} width={bw}
            height={Math.abs(py(d.hist)-zero)}
            fill={d.hist>=0?'#10b98155':'#ef444455'}/>
        ))}
        <polyline points={macdPts} fill="none" stroke="#3b82f6" strokeWidth={1.5}/>
        <polyline points={sigPts}  fill="none" stroke="#f59e0b" strokeWidth={1}/>
      </svg>
    </div>
  )
}

/* ── Main export ─────────────────────────────────────────────────── */
export default function LiveChart({ defaultSymbol='BTCUSDT', height=300 }) {
  const containerRef = useRef(null)
  const wsRef        = useRef(null)
  const mapRef       = useRef({})   // openTime → candle

  const [width,     setWidth]     = useState(800)
  const [symbol,    setSymbol]    = useState(defaultSymbol)
  const [interval,  setInterval]  = useState(INTERVALS[0])
  const [chartType, setChartType] = useState('Candle')
  const [indicator, setIndicator] = useState('BB')
  const [candles,   setCandles]   = useState([])
  const [ticker,    setTicker]    = useState(null)
  const [status,    setStatus]    = useState('loading')  // loading | live | error

  /* responsive width */
  useEffect(()=>{
    if(!containerRef.current) return
    const ro=new ResizeObserver(()=>{
      if(containerRef.current) setWidth(containerRef.current.clientWidth||800)
    })
    ro.observe(containerRef.current)
    setWidth(containerRef.current.clientWidth||800)
    return()=>ro.disconnect()
  },[])

  /* load history + connect WS */
  useEffect(()=>{
    setStatus('loading')
    setCandles([])
    mapRef.current={}
    if(wsRef.current){wsRef.current.close();wsRef.current=null}

    /* 1. Load 250 historical candles first */
    /* Try direct first; if blocked by CSP fall back to backend proxy */
    const klineURL = `https://api.binance.com/api/v3/klines?symbol=${symbol}&interval=${interval.rest}&limit=250`
    const proxyURL = `/api/crypto/proxy/klines?symbol=${symbol}&interval=${interval.rest}&limit=250`
    fetch(klineURL)
      .catch(()=>fetch(proxyURL))
      .then(r=>r.json())
      .then(data=>{
        if(!Array.isArray(data)||!data.length) return
        const parsed=data.map(k=>({
          openTime:  k[0],
          timeLabel: new Date(k[0]).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit',hour12:false}),
          open:parseFloat(k[1]),high:parseFloat(k[2]),
          low:parseFloat(k[3]),close:parseFloat(k[4]),
          volume:parseFloat(k[5]),
        }))
        parsed.forEach(c=>{mapRef.current[c.openTime]=c})
        setCandles(parsed)
      })
      .catch(()=>setStatus('error'))

    /* 2. Connect WS for live updates */
    const streams=`${symbol.toLowerCase()}@kline_${interval.ws}/${symbol.toLowerCase()}@miniTicker`
    const ws=new WebSocket(`wss://stream.binance.com:9443/stream?streams=${streams}`)
    wsRef.current=ws

    ws.onopen=()=>setStatus('live')
    ws.onclose=()=>setStatus('offline')
    ws.onerror=()=>setStatus('error')

    ws.onmessage=e=>{
      try{
        const {stream:s,data:d}=JSON.parse(e.data)
        if(s?.includes('kline')){
          const k=d.k
          const c={
            openTime:  k.t,
            timeLabel: new Date(k.t).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit',hour12:false}),
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
            high:parseFloat(d.h),low:parseFloat(d.l),volume:parseFloat(d.v),
          })
        }
      }catch{}
    }

    return()=>{if(wsRef.current){wsRef.current.close();wsRef.current=null}}
  },[symbol,interval])

  const isUp=((ticker?.changePct)??0)>=0
  const price=ticker?.price??candles.at(-1)?.close
  const statusColor={loading:'text-gray-500',live:'text-emerald-400',error:'text-red-400',offline:'text-amber-400'}

  return(
    <div ref={containerRef} className="space-y-2 w-full">
      {/* Ticker row */}
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-3xl font-bold text-white font-mono tracking-tight">
              {price ? fmtPrice(price) : <span className="text-gray-700 animate-pulse">———</span>}
            </span>
            {ticker&&(
              <span className={clsx('text-sm font-bold px-2 py-0.5 rounded-lg font-mono',
                isUp?'text-emerald-400 bg-emerald-900/30':'text-red-400 bg-red-900/30')}>
                {isUp?'+':''}{ticker.changePct?.toFixed(2)}%
              </span>
            )}
            <span className={clsx('text-[10px] font-medium flex items-center gap-1',statusColor[status])}>
              <span className={clsx('w-1.5 h-1.5 rounded-full inline-block',
                status==='live'?'bg-emerald-400 animate-pulse':
                status==='loading'?'bg-gray-500 animate-pulse':'bg-red-400')}/>
              {status==='live'?'Live':status==='loading'?'Loading…':status}
            </span>
          </div>
          {ticker&&(
            <div className="flex gap-4 text-xs text-gray-500 mt-1 font-mono">
              <span>H: <span className="text-emerald-400">{fmtPrice(ticker.high)}</span></span>
              <span>L: <span className="text-red-400">{fmtPrice(ticker.low)}</span></span>
              <span>Vol: {(ticker.volume/1e6).toFixed(2)}M</span>
              <span className="text-gray-600">{candles.length} bars loaded</span>
            </div>
          )}
        </div>
      </div>

      {/* Controls row */}
      <div className="flex items-center gap-2 flex-wrap">
        {/* Symbol */}
        <div className="relative">
          <select value={symbol} onChange={e=>setSymbol(e.target.value)}
            className="appearance-none bg-gray-800 border border-gray-700 rounded-lg pl-3 pr-7 py-1.5 text-xs text-white focus:border-blue-500 focus:outline-none font-medium cursor-pointer">
            {SYMBOLS.map(s=><option key={s}>{s}</option>)}
          </select>
          <ChevronDown size={10} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 pointer-events-none"/>
        </div>

        {/* Interval */}
        <div className="flex bg-gray-900 rounded-lg p-1 gap-0.5">
          {INTERVALS.map(iv=>(
            <button key={iv.label} onClick={()=>setInterval(iv)}
              className={clsx('px-2.5 py-1 rounded text-xs font-medium transition-all',
                interval.label===iv.label?'bg-blue-600 text-white shadow':'text-gray-400 hover:text-white')}>
              {iv.label}
            </button>
          ))}
        </div>

        {/* Chart type */}
        <div className="flex bg-gray-900 rounded-lg p-1 gap-0.5">
          {CHART_TYPES.map(t=>(
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
        {status==='loading'&&!candles.length&&(
          <div className="absolute inset-0 flex items-center justify-center bg-gray-950/90 z-10">
            <RefreshCw size={18} className="animate-spin text-blue-400 mr-2"/>
            <span className="text-gray-400 text-sm">Loading 250 candles…</span>
          </div>
        )}
        <ChartCanvas candles={candles} chartType={chartType} indicator={indicator} width={width}/>
      </div>

      {/* Sub-panels */}
      {indicator==='RSI'  && candles.length>14 && <RSIPanel  candles={candles} width={width}/>}
      {indicator==='MACD' && candles.length>30 && <MACDPanel candles={candles} width={width}/>}
    </div>
  )
}
