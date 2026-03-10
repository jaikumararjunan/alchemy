/**
 * Zustand global state store for Alchemy mobile app
 */
import { create } from 'zustand';

export const useStore = create((set, get) => ({
  // Connection
  connected: false,
  setConnected: (connected) => set({ connected }),

  // Market Data
  market: { mark_price: 0, change_24h_pct: 0, volume_24h: 0, bid: 0, ask: 0 },
  setMarket: (market) => set({ market }),

  // Emotion Intelligence
  emotion: {
    sentiment_score: 0,
    crypto_sentiment: 0,
    dominant_emotion: 'neutral',
    confidence: 0,
    geopolitical_risk: 'low',
    trading_bias: 'neutral',
    key_events: [],
    reasoning: '',
    emotions: {},
  },
  setEmotion: (emotion) => set({ emotion }),

  // Geopolitical
  geo: { total_impact: 0, risk_level: 'low', event_count: 0, dominant_events: [] },
  setGeo: (geo) => set({ geo }),

  // Technical Indicators
  technicals: {},
  setTechnicals: (technicals) => set({ technicals }),

  // Portfolio & Performance
  portfolio: {
    equity: 0, balance: 0, daily_pnl: 0, total_pnl: 0, total_pnl_pct: 0,
    win_rate: 0, total_trades: 0, open_positions: 0, max_drawdown_pct: 0,
    profit_factor: 0, avg_win: 0, avg_loss: 0,
  },
  setPortfolio: (portfolio) => set({ portfolio }),

  // Positions
  positions: [],
  setPositions: (positions) => set({ positions }),

  // Equity Curve
  equityCurve: [],
  setEquityCurve: (equityCurve) => set({ equityCurve }),

  // Trade History
  trades: [],
  setTrades: (trades) => set({ trades }),

  // Market Forecast
  forecast: {
    adx: 0, trend_direction: 'neutral', trend_strength: 'none',
    market_regime: 'ranging', regime_confidence: 0,
    forecast_bias: 'neutral', forecast_price_3: null, regression_r2: 0,
    vwap: null, vwap_position: 'at', vwap_distance_pct: 0,
    support_levels: [], resistance_levels: [],
    breakeven_move_pct: 0, round_trip_fee_pct: 0, leverage: 5,
    forecast_score: 0, current_price: 0, timestamp: null,
  },
  setForecast: (forecast) => set({ forecast }),

  // Bot State
  botState: {
    cycle: 0, mode: 'monitoring', total_trades: 0,
    last_action: '-', last_action_time: '', status: 'Waiting...',
    bot_running: false,
  },
  setBotState: (botState) => set({ botState }),

  // AI Decisions
  decisions: [],
  setDecisions: (decisions) => set({ decisions }),

  // News
  news: [],
  setNews: (news) => set({ news }),

  // Sentiment history for mini chart
  sentimentHistory: [],
  addSentimentPoint: (score) => {
    const h = get().sentimentHistory;
    const next = [...h, { time: new Date().toLocaleTimeString(), score }].slice(-30);
    set({ sentimentHistory: next });
  },

  // ML / AI Analysis
  mlAnalysis: null,
  setMlAnalysis: (mlAnalysis) => set({ mlAnalysis }),

  // Config
  config: { dry_run: true, symbol: 'BTCUSD', interval_minutes: 30, leverage: 5 },
  setConfig: (config) => set({ config }),

  // Process incoming WebSocket data
  processWSData: (data) => {
    const s = get();
    if (data.type === 'cycle_complete') {
      if (data.portfolio) s.setPortfolio(data.portfolio);
      if (data.equity_curve) s.setEquityCurve(data.equity_curve.slice(-100));
      if (data.trade_log) s.setTrades(data.trade_log);
    }
    const cd = data.cached_data || data;
    if (cd.market) s.setMarket(cd.market);
    if (cd.emotion) {
      s.setEmotion(cd.emotion);
      s.addSentimentPoint(cd.emotion.sentiment_score || 0);
    }
    if (cd.geo) s.setGeo(cd.geo);
    if (cd.technicals) s.setTechnicals(cd.technicals);
    if (cd.bot_state) s.setBotState({ ...cd.bot_state });
    if (cd.recent_decisions) s.setDecisions(cd.recent_decisions);
    if (cd.top_articles) s.setNews(cd.top_articles);
  },
}));
