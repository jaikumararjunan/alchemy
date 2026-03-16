/**
 * Tests for AlchemyAPI service (mobile/src/services/api.js)
 */

// ── Helpers ──────────────────────────────────────────────────────────────────

function mockFetch(responseBody, ok = true, status = 200) {
  global.fetch = jest.fn(() =>
    Promise.resolve({
      ok,
      status,
      json: () => Promise.resolve(responseBody),
    })
  );
}

// Reset modules so each test gets a fresh AlchemyAPI instance
beforeEach(() => {
  jest.resetModules();
  global.WebSocket = jest.fn(() => ({
    onopen: null, onmessage: null, onclose: null, onerror: null,
    close: jest.fn(), send: jest.fn(),
  }));
});

// ── GET helpers ───────────────────────────────────────────────────────────────

describe('AlchemyAPI REST methods', () => {
  test('getHealth returns server health object', async () => {
    const payload = { status: 'ok', bot_running: false, ws_clients: 0 };
    mockFetch(payload);
    const api = require('../src/services/api').default;
    const result = await api.getHealth();
    expect(result).toEqual(payload);
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/health'));
  });

  test('getPortfolio calls /api/portfolio', async () => {
    mockFetch({ stats: { equity: 10000 } });
    const api = require('../src/services/api').default;
    const result = await api.getPortfolio();
    expect(result.stats.equity).toBe(10000);
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/api/portfolio'));
  });

  test('getMarket appends symbol to path', async () => {
    mockFetch({ symbol: 'ETHUSD', mark_price: 3200 });
    const api = require('../src/services/api').default;
    await api.getMarket('ETHUSD');
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/api/market/ETHUSD'));
  });

  test('getForecast sends correct query string', async () => {
    const payload = {
      adx: 32.5, market_regime: 'trending', forecast_bias: 'bullish',
      breakeven_move_pct: 0.5, round_trip_fee_pct: 0.5, forecast_score: 0.42,
    };
    mockFetch(payload);
    const api = require('../src/services/api').default;
    const result = await api.getForecast('BTCUSD');
    expect(result.adx).toBe(32.5);
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/api/forecast?symbol=BTCUSD'));
  });

  test('getForecast defaults to BTCUSD when no symbol passed', async () => {
    mockFetch({ adx: 10 });
    const api = require('../src/services/api').default;
    await api.getForecast();
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('symbol=BTCUSD'));
  });

  test('getEmotion returns emotion + geopolitical', async () => {
    const payload = {
      emotion: { sentiment_score: 0.3, dominant_emotion: 'optimism' },
      geopolitical: { total_impact: 0.1, risk_level: 'low' },
    };
    mockFetch(payload);
    const api = require('../src/services/api').default;
    const result = await api.getEmotion();
    expect(result.emotion.dominant_emotion).toBe('optimism');
  });

  test('get() throws on non-ok response', async () => {
    mockFetch({ detail: 'Server Error' }, false, 500);
    const api = require('../src/services/api').default;
    await expect(api.getHealth()).rejects.toThrow('API error: 500');
  });
});

// ── POST helpers ──────────────────────────────────────────────────────────────

describe('AlchemyAPI POST methods', () => {
  test('botControl posts correct action and interval', async () => {
    mockFetch({ status: 'started', interval_minutes: 30 });
    const api = require('../src/services/api').default;
    const result = await api.botControl('start', 30);
    expect(result.status).toBe('started');

    const [url, opts] = fetch.mock.calls[0];
    expect(url).toContain('/api/bot/control');
    const body = JSON.parse(opts.body);
    expect(body.action).toBe('start');
    expect(body.interval_minutes).toBe(30);
  });

  test('updateConfig posts partial config', async () => {
    mockFetch({ dry_run: true, symbol: 'ETHUSD' });
    const api = require('../src/services/api').default;
    await api.updateConfig({ dry_run: true, symbol: 'ETHUSD' });
    const [, opts] = fetch.mock.calls[0];
    const body = JSON.parse(opts.body);
    expect(body.dry_run).toBe(true);
    expect(body.symbol).toBe('ETHUSD');
  });
});

// ── WebSocket ─────────────────────────────────────────────────────────────────

describe('AlchemyAPI WebSocket', () => {
  test('connectWS creates a WebSocket connection', () => {
    const api = require('../src/services/api').default;
    const onMsg = jest.fn();
    const onConn = jest.fn();
    const onDisc = jest.fn();
    api.connectWS(onMsg, onConn, onDisc);
    expect(WebSocket).toHaveBeenCalledWith(expect.stringContaining('ws://'));
  });

  test('disconnectWS closes the socket', () => {
    const api = require('../src/services/api').default;
    const mockWS = { close: jest.fn(), onopen: null, onmessage: null, onclose: null, onerror: null };
    global.WebSocket = jest.fn(() => mockWS);
    api.connectWS(jest.fn(), jest.fn(), jest.fn());
    api.disconnectWS();
    expect(mockWS.close).toHaveBeenCalled();
  });
});
