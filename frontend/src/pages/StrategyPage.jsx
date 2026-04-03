import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useAuth } from '@/context/AuthContext'
import { Brain, RefreshCw, TrendingUp, TrendingDown, Minus, Target, Shield, Zap, AlertCircle } from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'

const DIRECTION_ICON = { long: TrendingUp, short: TrendingDown, flat: Minus }
const STRATEGY_COLOR = {
  scalping:      'text-yellow-400 bg-yellow-900/20 border-yellow-500/20',
  momentum:      'text-blue-400   bg-blue-900/20   border-blue-500/20',
  mean_reversion:'text-purple-400 bg-purple-900/20 border-purple-500/20',
  breakout:      'text-orange-400 bg-orange-900/20 border-orange-500/20',
  news_driven:   'text-emerald-400 bg-emerald-900/20 border-emerald-500/20',
}

function ConfidenceBar({ value }) {
  const pct = Math.round((value || 0) * 100)
  const color = pct >= 70 ? 'bg-emerald-500' : pct >= 50 ? 'bg-blue-500' : 'bg-amber-500'
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-gray-800 rounded-full overflow-hidden">
        <div className={clsx('h-full rounded-full transition-all', color)} style={{ width: `${pct}%` }}/>
      </div>
      <span className="text-xs text-gray-400 w-8 text-right">{pct}%</span>
    </div>
  )
}

function IdeaCard({ idea, onRecord }) {
  const DirIcon = DIRECTION_ICON[idea.direction] || Minus
  const stratCls = STRATEGY_COLOR[idea.strategy] || 'text-gray-400 bg-gray-800 border-gray-700'
  const isLong   = idea.direction === 'long'
  const rr       = idea.risk_reward

  return (
    <div className="card hover:border-gray-600 transition-all">
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-center gap-2 flex-wrap">
          <span className={clsx('text-xs px-2 py-0.5 rounded-full border capitalize', stratCls)}>
            {idea.strategy?.replace('_',' ')}
          </span>
          <span className={clsx('flex items-center gap-1 text-xs font-bold px-2 py-0.5 rounded',
            isLong ? 'bg-emerald-900/40 text-emerald-400' : 'bg-red-900/40 text-red-400')}>
            <DirIcon size={11}/> {idea.direction?.toUpperCase()}
          </span>
          <span className="text-sm font-bold text-white">{idea.symbol}</span>
        </div>
        <div className="text-right">
          <div className="text-xs text-gray-500">R:R</div>
          <div className="text-sm font-bold text-white">{rr?.toFixed(1)}:1</div>
        </div>
      </div>

      <ConfidenceBar value={idea.confidence}/>

      {idea.entry_price > 0 && (
        <div className="grid grid-cols-3 gap-2 mt-3 text-xs">
          <div className="text-center p-2 rounded-lg bg-gray-900/60">
            <div className="text-gray-500 mb-0.5">Entry</div>
            <div className="text-white font-mono">{idea.entry_price.toLocaleString()}</div>
          </div>
          <div className="text-center p-2 rounded-lg bg-red-900/20">
            <div className="text-gray-500 mb-0.5">Stop</div>
            <div className="text-red-400 font-mono">{idea.stop_loss?.toLocaleString()}</div>
          </div>
          <div className="text-center p-2 rounded-lg bg-emerald-900/20">
            <div className="text-gray-500 mb-0.5">TP2</div>
            <div className="text-emerald-400 font-mono">{idea.take_profit_2?.toLocaleString()}</div>
          </div>
        </div>
      )}

      {idea.reasoning && (
        <p className="text-xs text-gray-500 mt-2 italic line-clamp-2">{idea.reasoning}</p>
      )}

      <div className="flex items-center justify-between mt-3 pt-3 border-t border-gray-800">
        <div className="flex items-center gap-3 text-xs text-gray-600">
          <span className="flex items-center gap-1"><Target size={10}/> {idea.timeframe}</span>
          <span className="flex items-center gap-1"><Shield size={10}/> {((idea.position_size_pct||0)*100).toFixed(1)}% capital</span>
        </div>
        <button onClick={() => onRecord(idea)}
          className="text-xs px-3 py-1.5 rounded-lg bg-blue-900/30 text-blue-400 hover:bg-blue-900/50 transition-colors">
          Record Trade
        </button>
      </div>
    </div>
  )
}

export default function StrategyPage() {
  const { apiClient } = useAuth()
  const api = apiClient()
  const [symbols, setSymbols] = useState('BTCUSDT,ETHUSDT,BNBUSDT')

  const { data: ideasData, isLoading, refetch } = useQuery({
    queryKey: ['trade-ideas'],
    queryFn: () => api.post('/intelligence/strategies/generate', {
      symbols: symbols.split(',').map(s => s.trim()).filter(Boolean),
      price_data: {},
    }).then(r => r.data).catch(() => null),
    enabled: false,
  })

  const { data: eiData } = useQuery({
    queryKey: ['ei-state'],
    queryFn: () => api.get('/intelligence/emotional-state').then(r => r.data).catch(() => null),
    refetchInterval: 60000,
  })

  const { data: stratPerf } = useQuery({
    queryKey: ['strategy-perf'],
    queryFn: () => api.get('/intelligence/analytics/strategy-performance').then(r => r.data).catch(() => null),
  })

  const recordMut = useMutation({
    mutationFn: (idea) => api.post('/intelligence/analytics/record-trade', {
      symbol: idea.symbol, strategy: idea.strategy,
      direction: idea.direction, entry_price: idea.entry_price,
      stop_loss: idea.stop_loss, take_profit: idea.take_profit_2,
      status: 'open', opened_at: new Date().toISOString(),
    }).then(r => r.data),
    onSuccess: () => toast.success('Trade recorded in analytics DB'),
    onError: (e) => toast.error(e.response?.data?.detail || 'Record failed'),
  })

  const ideas   = ideasData?.ideas || []
  const fg      = eiData?.state?.fear_greed_index ?? 50
  const regime  = eiData?.state?.regime
  const sizing  = eiData?.state?.recommended_sizing
  const fgColor = fg <= 25 ? '#EF4444' : fg <= 45 ? '#F97316' : fg <= 55 ? '#EAB308' : fg <= 75 ? '#84CC16' : '#10B981'
  const perf    = stratPerf?.performance || []

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-bold text-white flex items-center gap-2">
          <Brain size={20} className="text-purple-400"/> Strategy Engine
        </h1>
        <p className="text-sm text-gray-400">AI-generated trade ideas · Scalping · Momentum · Breakout · News-driven</p>
      </div>

      {/* EI dashboard */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <div className="card text-center">
          <div className="text-xs text-gray-500 mb-1">Fear & Greed</div>
          <div className="text-2xl font-bold" style={{ color: fgColor }}>{Math.round(fg)}</div>
          <div className="text-xs mt-1 capitalize" style={{ color: fgColor }}>
            {regime?.replace('_',' ') || '—'}
          </div>
        </div>
        <div className="card text-center">
          <div className="text-xs text-gray-500 mb-1">Position Sizing</div>
          <div className="text-2xl font-bold text-white">{sizing ? `${(sizing*100).toFixed(0)}%` : '—'}</div>
          <div className="text-xs text-gray-500 mt-1">of base size</div>
        </div>
        <div className="card text-center">
          <div className="text-xs text-gray-500 mb-1">Ideas Generated</div>
          <div className="text-2xl font-bold text-blue-400">{ideas.length}</div>
          <div className="text-xs text-gray-500 mt-1">this session</div>
        </div>
        <div className="card text-center">
          <div className="text-xs text-gray-500 mb-1">Market Bias</div>
          <div className="text-xl font-bold text-white capitalize">{ideasData?.market_bias || '—'}</div>
          <div className="text-xs text-gray-500 mt-1">{ideasData?.signal_count || 0} intel signals</div>
        </div>
      </div>

      {/* Generate ideas */}
      <div className="card">
        <div className="flex flex-col lg:flex-row gap-3">
          <div className="flex-1">
            <label className="text-xs text-gray-400 block mb-1">Symbols to analyse (comma-separated)</label>
            <input value={symbols} onChange={e => setSymbols(e.target.value)}
              className="input-field text-sm w-full"
              placeholder="BTCUSDT,ETHUSDT,SOLUSDT,NIFTY50"/>
          </div>
          <div className="flex items-end">
            <button onClick={() => refetch()} disabled={isLoading}
              className="btn-primary flex items-center gap-2 h-10 px-6">
              {isLoading ? <RefreshCw size={14} className="animate-spin"/> : <Zap size={14}/>}
              {isLoading ? 'Generating...' : 'Generate Ideas'}
            </button>
          </div>
        </div>
        {eiData?.guidance?.recommendations?.length > 0 && (
          <div className="mt-3 pt-3 border-t border-gray-800">
            <p className="text-xs text-gray-500 mb-1">EI Guidance for current {regime} regime:</p>
            <div className="flex flex-wrap gap-1">
              {eiData.guidance.recommendations.slice(0,3).map((r, i) => (
                <span key={i} className="text-xs px-2 py-1 rounded bg-purple-900/20 text-purple-300 border border-purple-500/20">
                  {r}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Ideas grid */}
      {ideas.length > 0 ? (
        <div>
          <h2 className="section-title mb-3">
            {ideas.length} Trade Ideas — ranked by confidence × R:R × EI multiplier
          </h2>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {ideas.map((idea, i) => (
              <IdeaCard key={idea.id || i} idea={idea} onRecord={(id) => recordMut.mutate(id)}/>
            ))}
          </div>
        </div>
      ) : !isLoading && (
        <div className="card text-center py-12">
          <Brain size={32} className="mx-auto mb-3 text-gray-600"/>
          <p className="text-sm text-gray-400">Click "Generate Ideas" to run all strategies</p>
          <p className="text-xs text-gray-600 mt-1">
            Uses scalping, momentum, breakout, and news-driven strategies
          </p>
        </div>
      )}

      {/* Strategy performance */}
      {perf.length > 0 && (
        <div className="card">
          <h2 className="section-title mb-3">Strategy Performance (last 3 months)</h2>
          <div className="space-y-2">
            {perf.map((p, i) => (
              <div key={i} className="flex items-center gap-3">
                <span className={clsx('text-xs px-2 py-0.5 rounded border capitalize w-28 text-center flex-shrink-0',
                  STRATEGY_COLOR[p.strategy] || 'text-gray-400 bg-gray-800 border-gray-700')}>
                  {p.strategy?.replace('_',' ')}
                </span>
                <div className="flex-1">
                  <ConfidenceBar value={p.avg_win_rate}/>
                </div>
                <div className="text-xs text-right w-24 flex-shrink-0">
                  <span className={p.net_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}>
                    {p.net_pnl >= 0 ? '+' : ''}${parseFloat(p.net_pnl).toFixed(2)}
                  </span>
                  <span className="text-gray-600 ml-1">({p.total_trades}T)</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
