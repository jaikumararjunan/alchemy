import { useState, useEffect, useRef, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/context/AuthContext'
import LiveChart from '@/components/charts/LiveChart'
import {
  Bot, Play, Square, Settings, RefreshCw, TrendingUp, TrendingDown,
  Activity, Wifi, Clock, Target, AlertTriangle, CheckCircle, XCircle,
  ChevronDown, Zap, BarChart3,
} from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'

const STRATEGY_OPTIONS = [
  { id: 'scalping',       label: 'Scalping',        desc: '1-5m tight stops', color: 'text-amber-400' },
  { id: 'momentum',       label: 'Momentum',        desc: 'Trend + EMA crossover', color: 'text-blue-400' },
  { id: 'breakout',       label: 'Breakout',        desc: 'Volume-confirmed', color: 'text-emerald-400' },
]

const SYMBOL_OPTIONS = ['BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT','XRPUSDT','DOGEUSDT','ADAUSDT']
const TIMEFRAMES = ['1m','5m','15m','1h','4h','1d']

// ── Signal card ─────────────────────────────────────────────────────────────
function SignalCard({ trade }) {
  const isLong = trade.direction === 'long'
  return (
    <div className={clsx(
      'rounded-xl border p-3 space-y-2 transition-all',
      isLong ? 'bg-emerald-900/10 border-emerald-500/20' : 'bg-red-900/10 border-red-500/20'
    )}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={clsx('text-xs font-bold px-2 py-0.5 rounded',
            isLong ? 'bg-emerald-900/40 text-emerald-400' : 'bg-red-900/40 text-red-400')}>
            {trade.direction?.toUpperCase()}
          </span>
          <span className="text-sm font-bold text-white">{trade.symbol}</span>
          <span className="text-xs text-gray-500 capitalize">{trade.strategy}</span>
        </div>
        <div className="flex items-center gap-1.5">
          {trade.executed ? (
            <CheckCircle size={12} className="text-emerald-400"/>
          ) : (
            <Clock size={12} className="text-amber-400"/>
          )}
          <span className="text-xs text-gray-500">{trade.status}</span>
        </div>
      </div>
      <div className="grid grid-cols-3 gap-2 text-xs">
        <div className="bg-gray-900/60 rounded-lg px-2 py-1.5">
          <span className="text-gray-500">Entry </span>
          <span className="text-white font-mono">${trade.entry_price?.toLocaleString(undefined,{maximumFractionDigits:2})}</span>
        </div>
        <div className="bg-gray-900/60 rounded-lg px-2 py-1.5">
          <span className="text-gray-500">Stop </span>
          <span className="text-red-400 font-mono">${trade.stop_loss?.toLocaleString(undefined,{maximumFractionDigits:2})}</span>
        </div>
        <div className="bg-gray-900/60 rounded-lg px-2 py-1.5">
          <span className="text-gray-500">TP </span>
          <span className="text-emerald-400 font-mono">${trade.take_profit?.toLocaleString(undefined,{maximumFractionDigits:2})}</span>
        </div>
      </div>
      <div className="flex items-center justify-between text-xs">
        <span className="text-gray-500">{trade.reasoning?.slice(0, 80)}</span>
        <span className="text-gray-600">{trade.confidence ? `${(trade.confidence*100).toFixed(0)}%` : ''}</span>
      </div>
      {trade.created_at && (
        <div className="text-[10px] text-gray-700">
          {new Date(trade.created_at).toLocaleString()}
        </div>
      )}
    </div>
  )
}

// ── Live signal feed via WebSocket ──────────────────────────────────────────
function useAutoTradeWS() {
  const [signals, setSignals] = useState([])
  const [scanStatus, setScanStatus] = useState(null)
  const wsRef = useRef(null)

  useEffect(() => {
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${window.location.host}/ws`)
    wsRef.current = ws

    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data)
        if (msg.event === 'autonomous_signal') {
          setSignals(prev => [msg, ...prev].slice(0, 50))
        }
        if (msg.event === 'autonomous_scan' || msg.event === 'autonomous_scan_complete') {
          setScanStatus(msg)
        }
      } catch {}
    }
    return () => ws.close()
  }, [])

  return { signals, scanStatus }
}

// ── Main Page ───────────────────────────────────────────────────────────────
export default function AutonomousTradingPage() {
  const { apiClient } = useAuth()
  const api = useMemo(() => apiClient(), [apiClient])
  const qc = useQueryClient()
  const { signals: wsSignals, scanStatus } = useAutoTradeWS()

  // Config state
  const [selectedSymbols, setSelectedSymbols] = useState(['BTCUSDT', 'ETHUSDT', 'SOLUSDT'])
  const [selectedStrategies, setSelectedStrategies] = useState(['scalping', 'momentum', 'breakout'])
  const [intervalSec, setIntervalSec] = useState(60)
  const [timeframe, setTimeframe] = useState('15m')
  const [autoExecute, setAutoExecute] = useState(false)
  const [showConfig, setShowConfig] = useState(false)
  const [chartSymbol, setChartSymbol] = useState('BTCUSDT')

  // Query engine status
  const { data: statusData, isLoading: statusLoading } = useQuery({
    queryKey: ['autonomous-status'],
    queryFn: () => api.get('/autonomous/status').then(r => r.data),
    refetchInterval: 5000,
  })

  // Query trade history
  const { data: historyData } = useQuery({
    queryKey: ['autonomous-history'],
    queryFn: () => api.get('/autonomous/history?limit=50').then(r => r.data),
    refetchInterval: 10000,
  })

  const isRunning = statusData?.status === 'running'
  const history = historyData?.trades || []

  // Mutations
  const startMut = useMutation({
    mutationFn: () => api.post('/autonomous/start', {
      symbols: selectedSymbols,
      strategies: selectedStrategies,
      interval_seconds: intervalSec,
      auto_execute: autoExecute,
      timeframe: timeframe,
    }).then(r => r.data),
    onSuccess: () => {
      toast.success('Autonomous trading started!')
      qc.invalidateQueries(['autonomous-status'])
    },
    onError: (e) => toast.error(e.response?.data?.detail || 'Failed to start'),
  })

  const stopMut = useMutation({
    mutationFn: () => api.post('/autonomous/stop').then(r => r.data),
    onSuccess: () => {
      toast.success('Autonomous trading stopped')
      qc.invalidateQueries(['autonomous-status'])
    },
    onError: (e) => toast.error(e.response?.data?.detail || 'Failed to stop'),
  })

  const toggleSymbol = (sym) => {
    setSelectedSymbols(prev =>
      prev.includes(sym) ? prev.filter(s => s !== sym) : [...prev, sym]
    )
  }

  const toggleStrategy = (id) => {
    setSelectedStrategies(prev =>
      prev.includes(id) ? prev.filter(s => s !== id) : [...prev, id]
    )
  }

  // Combine WS signals with history, dedup by id
  // WS messages have shape { event, ...fields } (broadcast spreads data at top level)
  const allSignals = [...wsSignals, ...history]
    .reduce((acc, s) => {
      // Strip the 'event' key so signal cards see only trade fields
      if (s.event) {
        const { event, ...rest } = s
        if (!acc.find(x => x.id === rest.id)) acc.push(rest)
      } else {
        if (!acc.find(x => x.id === s.id)) acc.push(s)
      }
      return acc
    }, [])
    .slice(0, 30)

  return (
    <div className="space-y-4 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-display font-bold text-white tracking-tight flex items-center gap-2">
            <Bot size={22} className="text-blue-400"/>
            Autonomous Trading
          </h1>
          <p className="text-sm text-gray-500 flex items-center gap-1.5">
            <Wifi size={11} className={isRunning ? 'text-emerald-400 animate-pulse' : 'text-gray-600'}/>
            {isRunning ? 'Live scanning' : 'Idle'}
            {statusData?.scan_count > 0 && (
              <span className="text-gray-600"> · {statusData.scan_count} scans · {statusData.total_signals} signals</span>
            )}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button onClick={() => setShowConfig(c => !c)}
            className="btn-ghost text-xs flex items-center gap-1.5">
            <Settings size={13}/> Config
          </button>
          {isRunning ? (
            <button onClick={() => stopMut.mutate()}
              disabled={stopMut.isPending}
              className="px-4 py-2 rounded-xl bg-red-600 hover:bg-red-500 text-white text-sm font-bold flex items-center gap-2 transition-all">
              {stopMut.isPending ? <RefreshCw size={14} className="animate-spin"/> : <Square size={14}/>}
              Stop
            </button>
          ) : (
            <button onClick={() => startMut.mutate()}
              disabled={startMut.isPending || selectedSymbols.length === 0 || selectedStrategies.length === 0}
              className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-bold flex items-center gap-2 transition-all disabled:opacity-50 disabled:cursor-not-allowed">
              {startMut.isPending ? <RefreshCw size={14} className="animate-spin"/> : <Play size={14}/>}
              Start Trading
            </button>
          )}
        </div>
      </div>

      {/* Status banner */}
      {isRunning && (
        <div className="card bg-emerald-900/10 border-emerald-500/20 flex items-center gap-3 py-3">
          <Activity size={16} className="text-emerald-400 animate-pulse"/>
          <div className="flex-1">
            <div className="text-sm text-emerald-300 font-medium">Engine Running</div>
            <div className="text-xs text-gray-500">
              Scanning {statusData?.symbols?.join(', ')} every {statusData?.interval_seconds}s
              using {statusData?.strategies?.join(', ')}
              {statusData?.auto_execute && <span className="text-amber-400 ml-1">· Auto-Execute ON</span>}
            </div>
          </div>
          {statusData?.last_scan_at && (
            <div className="text-xs text-gray-600">
              Last scan: {new Date(statusData.last_scan_at).toLocaleTimeString()}
            </div>
          )}
        </div>
      )}

      {/* Configuration panel */}
      {showConfig && (
        <div className="card space-y-4">
          <h3 className="text-sm font-semibold text-white flex items-center gap-2">
            <Settings size={14} className="text-gray-400"/> Configuration
          </h3>

          {/* Symbols */}
          <div>
            <label className="text-xs text-gray-400 mb-2 block">Symbols</label>
            <div className="flex gap-1.5 flex-wrap">
              {SYMBOL_OPTIONS.map(sym => (
                <button key={sym} onClick={() => toggleSymbol(sym)}
                  className={clsx('px-3 py-1.5 rounded-lg text-xs font-medium transition-all border',
                    selectedSymbols.includes(sym)
                      ? 'bg-blue-600/20 border-blue-500/50 text-blue-400'
                      : 'bg-gray-900 border-gray-800 text-gray-500 hover:border-gray-600')}>
                  {sym.replace('USDT', '')}
                </button>
              ))}
            </div>
          </div>

          {/* Strategies */}
          <div>
            <label className="text-xs text-gray-400 mb-2 block">Strategies</label>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              {STRATEGY_OPTIONS.map(strat => (
                <button key={strat.id} onClick={() => toggleStrategy(strat.id)}
                  className={clsx('p-2.5 rounded-xl border text-left transition-all',
                    selectedStrategies.includes(strat.id)
                      ? 'bg-blue-900/20 border-blue-500/40'
                      : 'bg-gray-900/60 border-gray-800 hover:border-gray-600')}>
                  <div className={clsx('text-xs font-medium', strat.color)}>{strat.label}</div>
                  <div className="text-[10px] text-gray-600 mt-0.5">{strat.desc}</div>
                </button>
              ))}
            </div>
          </div>

          {/* Timeframe + Interval */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Timeframe</label>
              <div className="flex bg-gray-900 rounded-lg p-1 gap-0.5">
                {TIMEFRAMES.map(tf => (
                  <button key={tf} onClick={() => setTimeframe(tf)}
                    className={clsx('px-2 py-1 rounded text-xs font-medium transition-all flex-1',
                      timeframe === tf ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-white')}>
                    {tf}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className="text-xs text-gray-400 mb-1 block">Scan Interval</label>
              <select value={intervalSec} onChange={e => setIntervalSec(Number(e.target.value))}
                className="input-field text-xs w-full">
                <option value={30}>30 seconds</option>
                <option value={60}>1 minute</option>
                <option value={120}>2 minutes</option>
                <option value={300}>5 minutes</option>
              </select>
            </div>
            <div className="col-span-2 md:col-span-2 flex items-end">
              <label className="flex items-center gap-2 cursor-pointer">
                <div className={clsx('relative w-9 h-5 rounded-full transition-colors',
                  autoExecute ? 'bg-amber-600' : 'bg-gray-700')}
                  onClick={() => setAutoExecute(!autoExecute)}>
                  <div className={clsx('absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full transition-transform',
                    autoExecute ? 'translate-x-4' : '')} />
                </div>
                <div>
                  <span className="text-xs text-gray-400">Auto-Execute</span>
                  {autoExecute && (
                    <div className="flex items-center gap-1 text-[10px] text-amber-400">
                      <AlertTriangle size={9}/> Paper orders will be simulated
                    </div>
                  )}
                </div>
              </label>
            </div>
          </div>
        </div>
      )}

      {/* Stats cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <div className="card py-3 text-center">
          <div className="text-2xl font-display font-bold text-white tracking-tight">{statusData?.scan_count || 0}</div>
          <div className="text-xs text-gray-500">Scans</div>
        </div>
        <div className="card py-3 text-center">
          <div className="text-2xl font-bold text-blue-400">{statusData?.total_signals || 0}</div>
          <div className="text-xs text-gray-500">Signals</div>
        </div>
        <div className="card py-3 text-center">
          <div className="text-2xl font-bold text-emerald-400">{statusData?.total_executed || 0}</div>
          <div className="text-xs text-gray-500">Executed</div>
        </div>
        <div className="card py-3 text-center">
          <div className="text-2xl font-bold text-amber-400">
            {selectedSymbols.length}×{selectedStrategies.length}
          </div>
          <div className="text-xs text-gray-500">Symbol×Strategy</div>
        </div>
      </div>

      {/* Chart + Signal feed */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        {/* Chart — 2/3 width */}
        <div className="xl:col-span-2 space-y-3">
          {/* Symbol quick-select for chart */}
          <div className="flex gap-1.5 flex-wrap">
            {selectedSymbols.map(sym => (
              <button key={sym} onClick={() => setChartSymbol(sym)}
                className={clsx('px-3 py-1.5 rounded-lg text-xs font-medium transition-all border',
                  chartSymbol === sym
                    ? 'bg-blue-600/20 border-blue-500/50 text-blue-400'
                    : 'bg-gray-900 border-gray-800 text-gray-400 hover:border-gray-600')}>
                {sym.replace('USDT', '')}
              </button>
            ))}
          </div>
          <div className="card overflow-hidden">
            <LiveChart key={chartSymbol} defaultSymbol={chartSymbol} height={300}/>
          </div>
        </div>

        {/* Live signal feed — 1/3 width */}
        <div className="card flex flex-col max-h-[520px]">
          <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-1.5">
            <Zap size={13} className="text-amber-400"/>
            Live Signals
            {wsSignals.length > 0 && (
              <span className="text-[10px] text-gray-500 ml-auto">{wsSignals.length} new</span>
            )}
          </h3>
          <div className="flex-1 overflow-y-auto space-y-2 pr-1">
            {allSignals.length === 0 ? (
              <div className="text-center py-8 text-gray-600 text-xs">
                <Bot size={24} className="mx-auto mb-2 opacity-30"/>
                {isRunning ? 'Scanning markets... signals will appear here' : 'Start the engine to see signals'}
              </div>
            ) : (
              allSignals.map((trade, i) => (
                <SignalCard key={trade.id || i} trade={trade}/>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Trade history table */}
      {history.length > 0 && (
        <div className="card">
          <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-1.5">
            <BarChart3 size={13} className="text-blue-400"/> Trade History
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[500px] text-xs">
              <thead>
                <tr className="text-gray-500 border-b border-gray-800">
                  <th className="text-left py-2 px-2">Symbol</th>
                  <th className="text-left py-2 px-2">Direction</th>
                  <th className="text-left py-2 px-2">Strategy</th>
                  <th className="text-right py-2 px-2">Entry</th>
                  <th className="text-right py-2 px-2">Stop</th>
                  <th className="text-right py-2 px-2">TP</th>
                  <th className="text-center py-2 px-2">Conf</th>
                  <th className="text-center py-2 px-2">Status</th>
                  <th className="text-right py-2 px-2">Time</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800/50">
                {history.map((t, i) => (
                  <tr key={t.id || i} className="hover:bg-gray-900/40 transition-colors">
                    <td className="py-2 px-2 font-medium text-white">{t.symbol}</td>
                    <td className="py-2 px-2">
                      <span className={clsx('px-1.5 py-0.5 rounded text-xs font-bold',
                        t.direction === 'long' ? 'bg-emerald-900/40 text-emerald-400' : 'bg-red-900/40 text-red-400')}>
                        {t.direction?.toUpperCase()}
                      </span>
                    </td>
                    <td className="py-2 px-2 text-gray-400 capitalize">{t.strategy}</td>
                    <td className="py-2 px-2 text-right font-mono text-white">
                      ${t.entry_price?.toLocaleString(undefined,{maximumFractionDigits:2})}
                    </td>
                    <td className="py-2 px-2 text-right font-mono text-red-400">
                      ${t.stop_loss?.toLocaleString(undefined,{maximumFractionDigits:2})}
                    </td>
                    <td className="py-2 px-2 text-right font-mono text-emerald-400">
                      ${t.take_profit?.toLocaleString(undefined,{maximumFractionDigits:2})}
                    </td>
                    <td className="py-2 px-2 text-center text-gray-400">
                      {t.confidence ? `${(t.confidence*100).toFixed(0)}%` : '-'}
                    </td>
                    <td className="py-2 px-2 text-center">
                      <span className={clsx('px-1.5 py-0.5 rounded text-[10px] font-medium',
                        t.status === 'executed' ? 'bg-emerald-900/30 text-emerald-400' :
                        t.status === 'error' ? 'bg-red-900/30 text-red-400' :
                        'bg-blue-900/30 text-blue-400')}>
                        {t.status}
                      </span>
                    </td>
                    <td className="py-2 px-2 text-right text-gray-600">
                      {t.created_at ? new Date(t.created_at).toLocaleTimeString() : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Notification info */}
      <div className="card bg-blue-900/10 border-blue-500/20 text-xs text-gray-400 flex items-start gap-2 py-3">
        <Activity size={14} className="text-blue-400 flex-shrink-0 mt-0.5"/>
        <div>
          <span className="text-blue-300 font-medium">Real-time notifications active</span> — 
          Trade signals are automatically sent to your configured Telegram and Email channels.
          Set up channels in <a href="/notifications" className="text-blue-400 underline">Notifications</a> page.
        </div>
      </div>
    </div>
  )
}
