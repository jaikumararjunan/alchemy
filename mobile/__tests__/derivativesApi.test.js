/**
 * Tests for Derivatives API methods.
 */
global.fetch = jest.fn();

import api from '../src/services/api';

describe('Derivatives API methods', () => {
  beforeEach(() => jest.clearAllMocks());

  const mockOk = (data) =>
    fetch.mockResolvedValueOnce({ ok: true, json: async () => data });
  const mockFail = () =>
    fetch.mockResolvedValueOnce({ ok: false, status: 500 });

  // ── getDerivativesSignal ─────────────────────────────────────────────────

  test('getDerivativesSignal exists as function', () => {
    expect(typeof api.getDerivativesSignal).toBe('function');
  });

  test('getDerivativesSignal calls correct URL', async () => {
    mockOk({ composite_score: 0.2, action_suggestion: 'BUY' });
    await api.getDerivativesSignal('BTCUSD');
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/derivatives/signal?symbol=BTCUSD')
    );
  });

  test('getDerivativesSignal returns composite score', async () => {
    mockOk({ composite_score: 0.35, action_suggestion: 'BUY', confidence: 0.8 });
    const r = await api.getDerivativesSignal();
    expect(r.composite_score).toBeCloseTo(0.35);
    expect(r.action_suggestion).toBe('BUY');
  });

  test('getDerivativesSignal throws on HTTP error', async () => {
    mockFail();
    await expect(api.getDerivativesSignal()).rejects.toThrow();
  });

  // ── getDerivativesFunding ────────────────────────────────────────────────

  test('getDerivativesFunding exists as function', () => {
    expect(typeof api.getDerivativesFunding).toBe('function');
  });

  test('getDerivativesFunding calls /api/derivatives/funding', async () => {
    mockOk({ current_rate: 0.0001, signal: 'neutral' });
    await api.getDerivativesFunding('BTCUSD');
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/derivatives/funding?symbol=BTCUSD')
    );
  });

  test('getDerivativesFunding returns rate data', async () => {
    mockOk({ current_rate: 0.0008, rate_label: 'high_positive', signal: 'slightly_bearish' });
    const r = await api.getDerivativesFunding();
    expect(r.rate_label).toBe('high_positive');
  });

  // ── getDerivativesBasis ──────────────────────────────────────────────────

  test('getDerivativesBasis exists as function', () => {
    expect(typeof api.getDerivativesBasis).toBe('function');
  });

  test('getDerivativesBasis calls /api/derivatives/basis', async () => {
    mockOk({ basis_pct: 0.05, basis_label: 'contango' });
    await api.getDerivativesBasis('BTCUSD');
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/derivatives/basis?symbol=BTCUSD')
    );
  });

  // ── getDerivativesOI ─────────────────────────────────────────────────────

  test('getDerivativesOI exists as function', () => {
    expect(typeof api.getDerivativesOI).toBe('function');
  });

  test('getDerivativesOI calls /api/derivatives/oi', async () => {
    mockOk({ current_oi: 500e6, oi_trend: 'accumulating' });
    await api.getDerivativesOI('BTCUSD');
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/derivatives/oi?symbol=BTCUSD')
    );
  });

  test('getDerivativesOI returns OI data', async () => {
    mockOk({ current_oi: 650e6, price_oi_signal: 'bullish_confirmation' });
    const r = await api.getDerivativesOI();
    expect(r.price_oi_signal).toBe('bullish_confirmation');
  });

  // ── getDerivativesLiquidations ───────────────────────────────────────────

  test('getDerivativesLiquidations exists as function', () => {
    expect(typeof api.getDerivativesLiquidations).toBe('function');
  });

  test('getDerivativesLiquidations calls /api/derivatives/liquidations', async () => {
    mockOk({ cascade_risk_below_pct: 3.5, signal: 'neutral' });
    await api.getDerivativesLiquidations('BTCUSD');
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/derivatives/liquidations?symbol=BTCUSD')
    );
  });

  // ── getDerivativesOptions ────────────────────────────────────────────────

  test('getDerivativesOptions exists as function', () => {
    expect(typeof api.getDerivativesOptions).toBe('function');
  });

  test('getDerivativesOptions calls /api/derivatives/options', async () => {
    mockOk({ chain_count: 14, spot: 67000 });
    await api.getDerivativesOptions('BTCUSD');
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/derivatives/options?symbol=BTCUSD')
    );
  });

  test('getDerivativesOptions returns chain data', async () => {
    mockOk({
      spot: 67000, chain_count: 14,
      atm_call_greeks: { delta: 0.5, gamma: 0.00002, theta_daily: -5.2, vega_1pct: 42 },
    });
    const r = await api.getDerivativesOptions();
    expect(r.atm_call_greeks.delta).toBeCloseTo(0.5);
    expect(r.chain_count).toBe(14);
  });
});
