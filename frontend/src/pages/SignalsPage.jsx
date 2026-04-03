import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useAuth } from '@/context/AuthContext'
import { useAlchemyStore } from '@/store'
import { Zap, RefreshCw, AlertCircle, TrendingUp, TrendingDown, Brain, Activity } from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'

export default function SignalsPage() {
  const { apiClient } = useAuth()
  const api = apiClient()
  const wsSignals = useAlchemyStore(s => s.signals)
  const [filter, setFilter] = useState('all')

  // Market intelligence signals
  const { data: intelData, isLoading: il, refetch: refetchIntel } = useQuery({
    queryKey: ['intel-signals'],
    queryFn: () => api.get('/intelligence/signals?limit=50').then(r => r.data).catch(() => ({ signals: [] })),
    refetchInterval: 30000,
  })

  // Market view / bias
  const { data: marketView } = useQuery({
    queryKey: ['market-view'],
    queryFn: () => api.get('/intelligence/market-view').then(r => r.data).catch(() => null),
    refetchInterval: 60000,
  })

  // Emotional intelligence state
  const { data: eiData } = useQuery({
    queryKey: ['ei-state'],
    queryFn: () => api.get('/intelligence/emotional-state').then(r => r.data).catch(() => null),
    refetchInterval: 60000,
  })

  // Trigger news crawl
  const crawlMut = useMutation({
    mutationFn: () => api.post('/intelligence/crawl-now').then(r => r.data),
    onSuccess: () => { toast.success('News crawl triggered'); setTimeout(() => refetchIntel(), 5000) },
  })

  const signals      = intelData?.signals || []
  const allSignals   = filter === 'ws' ? wsSignals : filter === 'geo' ? signals.filter(s => s.geopolitical) : signals
  const bias         = marketView?.market_bias || 'neutral'
  const eiState      = eiData?.state
  const fg           = eiState?.fear_greed_index ?? 50

  const biasColor = { bullish: 'text-emerald-400', bearish: 'text-red-400', neutral: 'text-gray-400', mixed: 'text-amber-400' }
  const urgencyColor = { immediate: 'text-red-400', short_term: 'text-amber-400', medium_term: 'text-blue-400', long_term: 'text-gray-400' }

  // Fear & Greed gauge color
  const fgColor = fg <= 25 ? '#EF4444' : fg <= 45 ? '#F97316' : fg <= 55 ? '#EAB308' : fg <= 75 ? '#84CC16' : '#10B981'
  const fgLabel = fg <= 20 ? 'Extreme Fear' : fg <= 40 ? 'Fear' : fg <= 60 ? 'Neutral' : fg <= 80 ? 'Greed' : 'Extreme Greed'

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white flex items-center gap-2">
            <Zap size={20} className="text-yellow-400"/> AI Market Intelligence
          </h1>
          <p className="text-sm text-gray-400">Geopolitical news · Market signals · Emotional intelligence</p>
        </div>
        <button onClick={() => crawlMut.mutate()} disabled={crawlMut.isPending}
          className="btn-primary text-xs flex items-center gap-2">
          {crawlMut.isPending ? <RefreshCw size={12} className="animate-spin"/> : <RefreshCw size={12}/>}
          Crawl News Now
        </button>
      </div>

      {/* Market overview row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Market bias */}
        <div className="card text-center">
          <p className="text-xs text-gray-500 mb-1">Market Bias</p>
          <p className={clsx('text-xl font-bold capitalize', biasColor[bias])}>{bias}</p>
          <p className="text-xs text-gray-600 mt-1">{marketView?.signals_count || 0} signals</p>
        </div>

        {/* Fear & Greed */}
        <div className="card text-center">
          <p className="text-xs text-gray-500 mb-1">Fear & Greed</p>
          <p className="text-2xl font-bold" style={{ color: fgColor }}>{Math.round(fg)}</p>
          <p className="text-xs mt-1" style={{ color: fgColor }}>{fgLabel}</p>
        </div>

        {/* Trader emotion */}
        <div className="card text-center">
          <p className="text-xs text-gray-500 mb-1">Market Emotion</p>
          <p className="text-lg font-bold text-white capitalize">{eiState?.trader_emotion || '—'}</p>
          <p className="text-xs text-gray-600 mt-1">
            Sizing: {eiState ? `${(eiState.recommended_sizing * 100).toFixed(0)}%` : '—'}
          </p>
        </div>

        {/* Geo signals */}
        <div className="card text-center">
          <p className="text-xs text-gray-500 mb-1">Geo Signals</p>
          <p className="text-2xl font-bold text-amber-400">{signals.filter(s => s.geopolitical).length}</p>
          <p className="text-xs text-gray-600 mt-1">Geopolitical alerts</p>
        </div>
      </div>

      {/* EI guidance */}
      {eiData?.guidance?.recommendations?.length > 0 && (
        <div className="card border-purple-500/20 bg-purple-900/10">
          <div className="flex items-center gap-2 mb-2">
            <Brain size={16} className="text-purple-400"/>
            <h3 className="text-sm font-semibold text-white">AI Emotional Intelligence Guidance</h3>
            <span className="text-xs text-gray-500 capitalize">— {eiState?.regime}</span>
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-1">
            {eiData.guidance.recommendations.map((r, i) => (
              <div key={i} className="flex items-start gap-2 text-xs text-gray-300">
                <span className="text-purple-400 flex-shrink-0">→</span> {r}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Top impacted sectors */}
      {marketView?.top_sectors?.length > 0 && (
        <div className="card">
          <h3 className="text-sm font-semibold text-white mb-3">Most Impacted Sectors</h3>
          <div className="flex flex-wrap gap-2">
            {marketView.top_sectors.map(([sector, score]) => (
              <span key={sector} className="px-3 py-1.5 rounded-full text-xs bg-blue-900/30 border border-blue-500/20 text-blue-300 capitalize">
                {sector} <span className="text-blue-500 ml-1">{score.toFixed(2)}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Filter tabs */}
      <div className="flex gap-2">
        {[['all','All Intelligence'],['geo','Geopolitical Only'],['ws','Live WS Signals']].map(([k,l]) => (
          <button key={k} onClick={() => setFilter(k)}
            className={clsx('px-3 py-1.5 rounded-lg text-xs font-medium',
              filter === k ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700')}>
            {l}
          </button>
        ))}
      </div>

      {/* Signals list */}
      <div className="space-y-2">
        {il ? (
          <div className="text-center py-8 text-gray-500 animate-pulse">Loading signals...</div>
        ) : allSignals.length === 0 ? (
          <div className="text-center py-12 card">
            <AlertCircle size={24} className="mx-auto mb-2 text-gray-600"/>
            <p className="text-sm text-gray-500">No signals yet</p>
            <p className="text-xs text-gray-600 mt-1">Click "Crawl News Now" to fetch latest market intelligence</p>
          </div>
        ) : allSignals.map((s, i) => {
          const score = s.impact_score ?? s.score ?? 0
          const isUp  = score > 0
          return (
            <div key={s.id || i} className={clsx(
              'card border transition-all hover:border-gray-600',
              s.geopolitical ? 'border-amber-500/20 bg-amber-900/5' : 'border-gray-800')}>
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap mb-1">
                    {s.geopolitical && (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-amber-900/30 text-amber-400 border border-amber-500/20 flex-shrink-0">
                        🌍 Geopolitical
                      </span>
                    )}
                    <span className={clsx('text-xs px-2 py-0.5 rounded-full flex-shrink-0',
                      urgencyColor[s.urgency] || 'text-gray-400',
                      'bg-gray-800 border border-gray-700')}>
                      {s.urgency?.replace('_',' ')}
                    </span>
                    <span className="text-xs text-gray-600 capitalize">{s.source}</span>
                  </div>
                  <p className="text-sm text-white font-medium line-clamp-2 mb-1">{s.title || s.signal}</p>
                  {s.summary && <p className="text-xs text-gray-400 line-clamp-2">{s.summary}</p>}
                  {s.affected_sectors?.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {s.affected_sectors.slice(0,4).map(sec => (
                        <span key={sec} className="text-xs px-1.5 py-0.5 rounded bg-gray-800 text-gray-400 capitalize">{sec}</span>
                      ))}
                    </div>
                  )}
                </div>
                <div className="text-right flex-shrink-0">
                  <div className={clsx('flex items-center gap-1 font-bold text-sm justify-end',
                    isUp ? 'text-emerald-400' : score < 0 ? 'text-red-400' : 'text-gray-400')}>
                    {isUp ? <TrendingUp size={14}/> : score < 0 ? <TrendingDown size={14}/> : <Activity size={14}/>}
                    {score > 0 ? '+' : ''}{score.toFixed(2)}
                  </div>
                  <div className={clsx('text-xs mt-0.5 capitalize', biasColor[s.market_impact] || 'text-gray-400')}>
                    {s.market_impact}
                  </div>
                  <div className="text-xs text-gray-600 mt-1">
                    conf: {((s.confidence || 0) * 100).toFixed(0)}%
                  </div>
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
