/**
 * Tests for scanner store state.
 */
import { act } from '@testing-library/react-hooks';
import { useStore } from '../src/store/useStore';

const MOCK_SCAN = {
  ranked_contracts: [
    { symbol: 'SOLUSD', rank: 1, composite_score: 0.48, action: 'BUY', confidence: 0.78,
      current_price: 185.5, change_24h_pct: 3.2, volume_24h: 12000, open_interest: 80e6,
      forecast_score: 0.55, derivatives_score: 0.31, volatility_score: 0.7, volume_score: 0.6,
      adx: 32.5, market_regime: 'trending', trend_direction: 'bullish', forecast_bias: 'bullish',
      regression_r2: 0.71, breakeven_move_pct: 0.5, expected_move_pct: 2.8,
      risk_reward_estimate: 2.1, suggested_size_pct: 55.0, scan_time_ms: 120,
      reasoning: 'ADX 32.5 (trending) | trend bullish | forecast bullish | R²=0.71' },
    { symbol: 'ETHUSD', rank: 2, composite_score: 0.31, action: 'BUY', confidence: 0.62,
      current_price: 3512, change_24h_pct: 1.8, volume_24h: 45000, open_interest: 300e6,
      forecast_score: 0.35, derivatives_score: 0.22, volatility_score: 0.6, volume_score: 0.65,
      adx: 26.1, market_regime: 'trending', trend_direction: 'bullish', forecast_bias: 'bullish',
      regression_r2: 0.55, breakeven_move_pct: 0.5, expected_move_pct: 1.9,
      risk_reward_estimate: 1.7, suggested_size_pct: 35.0, scan_time_ms: 115,
      reasoning: 'ADX 26.1 (trending) | trend bullish | forecast bullish' },
    { symbol: 'BTCUSD', rank: 3, composite_score: -0.12, action: 'HOLD', confidence: 0.35,
      current_price: 67200, change_24h_pct: -0.5, volume_24h: 280000, open_interest: 800e6,
      forecast_score: -0.15, derivatives_score: -0.08, volatility_score: 0.5, volume_score: 0.7,
      adx: 18.2, market_regime: 'ranging', trend_direction: 'neutral', forecast_bias: 'neutral',
      regression_r2: 0.22, breakeven_move_pct: 0.5, expected_move_pct: 0.8,
      risk_reward_estimate: 0.9, suggested_size_pct: 10.0, scan_time_ms: 130,
      reasoning: 'ADX 18.2 (ranging) | trend neutral' },
  ],
  top_opportunities: [],
  scan_timestamp: '2026-03-10T12:00:00Z',
  total_scanned: 10, total_actionable: 4,
  scan_duration_seconds: 3.2,
  market_summary: 'Scanned 10 contracts: 3 BUY / 1 SELL. Top opportunities: SOLUSD(BUY), ETHUSD(BUY).',
};

describe('Scanner store state', () => {
  beforeEach(() => {
    useStore.setState({ scanResult: null });
  });

  test('scanResult initial state is null', () => {
    expect(useStore.getState().scanResult).toBeNull();
  });

  test('setScanResult stores full scan result', () => {
    act(() => { useStore.getState().setScanResult(MOCK_SCAN); });
    const { scanResult } = useStore.getState();
    expect(scanResult).not.toBeNull();
    expect(scanResult.total_scanned).toBe(10);
    expect(scanResult.total_actionable).toBe(4);
    expect(scanResult.market_summary).toContain('SOLUSD');
  });

  test('setScanResult stores ranked_contracts list', () => {
    act(() => { useStore.getState().setScanResult(MOCK_SCAN); });
    const { scanResult } = useStore.getState();
    expect(scanResult.ranked_contracts).toHaveLength(3);
    expect(scanResult.ranked_contracts[0].symbol).toBe('SOLUSD');
    expect(scanResult.ranked_contracts[0].action).toBe('BUY');
  });

  test('setScanResult stores HOLD contract at correct rank', () => {
    act(() => { useStore.getState().setScanResult(MOCK_SCAN); });
    const btc = useStore.getState().scanResult.ranked_contracts.find(c => c.symbol === 'BTCUSD');
    expect(btc).toBeTruthy();
    expect(btc.action).toBe('HOLD');
    expect(btc.rank).toBe(3);
  });

  test('setScanResult stores sub-scores', () => {
    act(() => { useStore.getState().setScanResult(MOCK_SCAN); });
    const sol = useStore.getState().scanResult.ranked_contracts[0];
    expect(sol.forecast_score).toBeCloseTo(0.55);
    expect(sol.derivatives_score).toBeCloseTo(0.31);
    expect(sol.adx).toBeCloseTo(32.5);
    expect(sol.market_regime).toBe('trending');
  });

  test('setScanResult stores suggested_size_pct', () => {
    act(() => { useStore.getState().setScanResult(MOCK_SCAN); });
    const sol = useStore.getState().scanResult.ranked_contracts[0];
    expect(sol.suggested_size_pct).toBeCloseTo(55.0);
  });

  test('setScanResult can be updated with new scan', () => {
    act(() => { useStore.getState().setScanResult(MOCK_SCAN); });
    act(() => {
      useStore.getState().setScanResult({
        ...MOCK_SCAN,
        total_scanned: 15,
        market_summary: 'Scanned 15 contracts.',
      });
    });
    expect(useStore.getState().scanResult.total_scanned).toBe(15);
  });

  test('setScanResult does not affect other store state', () => {
    const preForecast = useStore.getState().forecast;
    act(() => { useStore.getState().setScanResult(MOCK_SCAN); });
    expect(useStore.getState().forecast).toEqual(preForecast);
  });
});
