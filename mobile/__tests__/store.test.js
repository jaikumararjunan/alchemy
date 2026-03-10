/**
 * Tests for Zustand store (mobile/src/store/useStore.js)
 */
const { act } = require('@testing-library/react-hooks');

// zustand needs a simple mock for React Native
jest.mock('zustand', () => {
  const { create: realCreate } = jest.requireActual('zustand');
  return { create: realCreate };
});

let useStore;
beforeEach(() => {
  jest.resetModules();
  useStore = require('../src/store/useStore').useStore;
});

// ── Helpers ───────────────────────────────────────────────────────────────────

function getState() {
  return useStore.getState();
}

// ── Basic setters ─────────────────────────────────────────────────────────────

describe('useStore setters', () => {
  test('setConnected toggles connection flag', () => {
    getState().setConnected(true);
    expect(getState().connected).toBe(true);
    getState().setConnected(false);
    expect(getState().connected).toBe(false);
  });

  test('setMarket updates mark_price', () => {
    getState().setMarket({ mark_price: 67500, symbol: 'BTCUSD' });
    expect(getState().market.mark_price).toBe(67500);
  });

  test('setEmotion updates dominant_emotion', () => {
    getState().setEmotion({ dominant_emotion: 'greed', sentiment_score: 0.7, confidence: 0.85 });
    expect(getState().emotion.dominant_emotion).toBe('greed');
    expect(getState().emotion.confidence).toBe(0.85);
  });

  test('setPortfolio updates equity and win_rate', () => {
    getState().setPortfolio({ equity: 12000, win_rate: 62.5, total_trades: 8 });
    expect(getState().portfolio.equity).toBe(12000);
    expect(getState().portfolio.win_rate).toBe(62.5);
  });

  test('setForecast stores full forecast object', () => {
    const fc = {
      adx: 38.2, trend_direction: 'bullish', trend_strength: 'strong',
      market_regime: 'trending', regime_confidence: 0.75,
      forecast_bias: 'bullish', forecast_price_3: 68200,
      regression_r2: 0.61, vwap: 67400, vwap_position: 'above',
      vwap_distance_pct: 0.45, support_levels: [66800, 65900],
      resistance_levels: [68500, 69100], breakeven_move_pct: 0.5,
      round_trip_fee_pct: 0.5, leverage: 5, forecast_score: 0.52,
      current_price: 67800, timestamp: '2026-03-10T10:00:00Z',
    };
    getState().setForecast(fc);
    const stored = getState().forecast;
    expect(stored.adx).toBe(38.2);
    expect(stored.market_regime).toBe('trending');
    expect(stored.forecast_bias).toBe('bullish');
    expect(stored.breakeven_move_pct).toBe(0.5);
    expect(stored.support_levels).toEqual([66800, 65900]);
  });

  test('setPositions and setTrades update arrays', () => {
    getState().setPositions([{ symbol: 'BTCUSD', side: 'long', size: 1 }]);
    expect(getState().positions).toHaveLength(1);

    getState().setTrades([{ id: 'T1', pnl: 42 }, { id: 'T2', pnl: -10 }]);
    expect(getState().trades).toHaveLength(2);
  });

  test('setConfig updates config fields', () => {
    getState().setConfig({ dry_run: false, symbol: 'ETHUSD', leverage: 10 });
    expect(getState().config.dry_run).toBe(false);
    expect(getState().config.symbol).toBe('ETHUSD');
    expect(getState().config.leverage).toBe(10);
  });
});

// ── Sentiment history ─────────────────────────────────────────────────────────

describe('addSentimentPoint', () => {
  test('appends score to history', () => {
    getState().addSentimentPoint(0.42);
    getState().addSentimentPoint(-0.11);
    const h = getState().sentimentHistory;
    expect(h.length).toBe(2);
    expect(h[0].score).toBe(0.42);
    expect(h[1].score).toBe(-0.11);
  });

  test('caps history at 30 entries', () => {
    for (let i = 0; i < 35; i++) getState().addSentimentPoint(i * 0.01);
    expect(getState().sentimentHistory.length).toBe(30);
  });
});

// ── processWSData ─────────────────────────────────────────────────────────────

describe('processWSData', () => {
  test('processes cycle_complete type', () => {
    getState().processWSData({
      type: 'cycle_complete',
      portfolio: { equity: 10500, win_rate: 55 },
      trade_log: [{ id: 'T1', pnl: 30 }],
      equity_curve: [10000, 10200, 10500],
    });
    expect(getState().portfolio.equity).toBe(10500);
    expect(getState().trades).toHaveLength(1);
  });

  test('processes cached_data from websocket frame', () => {
    getState().processWSData({
      cached_data: {
        market: { mark_price: 68100 },
        emotion: { sentiment_score: 0.6, dominant_emotion: 'greed' },
        geo: { total_impact: 0.15, risk_level: 'medium' },
        bot_state: { cycle: 5, mode: 'aggressive', bot_running: true },
        recent_decisions: [{ action: 'BUY', price: 68000 }],
        top_articles: [{ title: 'Crypto rally', source: 'Reuters' }],
      },
    });
    expect(getState().market.mark_price).toBe(68100);
    expect(getState().emotion.dominant_emotion).toBe('greed');
    expect(getState().geo.risk_level).toBe('medium');
    expect(getState().botState.cycle).toBe(5);
    expect(getState().news).toHaveLength(1);
  });
});
