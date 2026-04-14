import { useEffect, useRef, useState } from 'react'
import { createChart, ColorType, CrosshairMode } from 'lightweight-charts'
import clsx from 'clsx'

export default function CandlestickChart({
  symbol = 'BTCUSDT',
  data = [],
  height = 400,
  onCrosshairMove,
  className = '',
}) {
  const containerRef = useRef(null)
  const chartRef = useRef(null)
  const [crosshair, setCrosshair] = useState(null)

  useEffect(() => {
    if (!containerRef.current) return

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#94A3B8',
        fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: '#1E293B', style: 1 },
        horzLines: { color: '#1E293B', style: 1 },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: '#64748B', width: 1, style: 2 },
        horzLine: { color: '#64748B', width: 1, style: 2 },
      },
      rightPriceScale: { borderColor: '#1E293B', scaleMargins: { top: 0.1, bottom: 0.25 } },
      timeScale: { borderColor: '#1E293B', timeVisible: true, secondsVisible: false },
      handleScroll: { mouseWheel: true, pressedMouseMove: true },
      handleScale: { mouseWheel: true, pinch: true },
    })

    const candleSeries = chart.addCandlestickSeries({
      upColor: '#10B981', downColor: '#F43F5E',
      borderUpColor: '#10B981', borderDownColor: '#F43F5E',
      wickUpColor: '#10B981', wickDownColor: '#F43F5E',
    })

    const volumeSeries = chart.addHistogramSeries({
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    })
    chart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } })

    if (data.length > 0) {
      const toTs = d => typeof d.time === 'string' ? Math.floor(new Date(d.time).getTime() / 1000) : d.time
      candleSeries.setData(data.map(d => ({ time: toTs(d), open: d.open, high: d.high, low: d.low, close: d.close })))
      volumeSeries.setData(data.map(d => ({
        time: toTs(d), value: d.volume || 0,
        color: d.close >= d.open ? 'rgba(16,185,129,0.3)' : 'rgba(244,63,94,0.3)',
      })))
      chart.timeScale().fitContent()
    }

    chart.subscribeCrosshairMove(param => {
      if (param.time) {
        const price = param.seriesData?.get(candleSeries)
        if (price) { setCrosshair({ time: param.time, ...price }); onCrosshairMove?.({ time: param.time, ...price }) }
      } else { setCrosshair(null) }
    })

    const ro = new ResizeObserver(entries => chart.applyOptions({ width: entries[0].contentRect.width }))
    ro.observe(containerRef.current)
    chartRef.current = chart

    return () => { ro.disconnect(); chart.remove() }
  }, [data, height])

  return (
    <div className={clsx('relative rounded-xl overflow-hidden', className)}
      style={{ background: 'var(--surface-2)', border: '1px solid var(--border)' }}>
      {crosshair && (
        <div className="absolute top-2 left-3 z-10 flex items-center gap-3 text-[11px] font-mono">
          <span className="text-gray-500">{symbol}</span>
          <span className="text-gray-400">O <span className="text-white">{crosshair.open?.toFixed(2)}</span></span>
          <span className="text-gray-400">H <span className="text-emerald-400">{crosshair.high?.toFixed(2)}</span></span>
          <span className="text-gray-400">L <span className="text-rose-400">{crosshair.low?.toFixed(2)}</span></span>
          <span className="text-gray-400">C <span className={crosshair.close >= crosshair.open ? 'text-emerald-400' : 'text-rose-400'}>
            {crosshair.close?.toFixed(2)}
          </span></span>
        </div>
      )}
      <div ref={containerRef} style={{ height }} />
    </div>
  )
}
