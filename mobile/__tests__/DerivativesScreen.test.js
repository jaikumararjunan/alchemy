/**
 * Tests for DerivativesScreen component.
 */
import React from 'react';
import { render } from '@testing-library/react-native';
import DerivativesScreen from '../src/screens/DerivativesScreen';

jest.mock('../src/store/useStore', () => ({
  useStore: () => ({
    derivativesSignal: {
      composite_score: 0.28,
      action_suggestion: 'BUY',
      confidence: 0.75,
      extreme_funding: false,
      short_squeeze_risk: true,
      long_squeeze_risk: false,
      high_oi_conviction: true,
      summary: 'Derivatives score: +0.280 → BUY. High OI conviction: bullish_confirmation.',
      funding_score: 0.42, basis_score: 0.12,
      oi_score: 0.35, liquidation_score: 0.10, options_score: 0.2,
    },
    setDerivativesSignal: jest.fn(),
  }),
}));

jest.mock('../src/services/api', () => ({
  getDerivativesSignal:      jest.fn().mockResolvedValue({}),
  getDerivativesFunding:     jest.fn().mockResolvedValue({
    current_rate: 0.0003, current_rate_pct: 0.03,
    annualized_rate_pct: 32.8, rate_label: 'high_positive',
    signal: 'slightly_bearish', signal_strength: 0.33,
    avg_rate_7d: 0.00025, cumulative_7d_pct: 0.525,
    trend: 'rising',
    interpretation: 'Funding elevated (+0.030%/8h). Longs paying premium.',
  }),
  getDerivativesBasis:       jest.fn().mockResolvedValue({
    spot_price: 66800, perp_price: 67000, basis_usd: 200, basis_pct: 0.30,
    basis_label: 'contango', signal: 'slightly_bearish',
    sentiment_score: -0.25, avg_basis_pct_1h: 0.28, basis_trend: 'stable',
    interpretation: 'Contango (+0.300%). Longs at a small premium.',
    annualized_basis_pct: null, futures_price: null, futures_days: null,
  }),
  getDerivativesOI:          jest.fn().mockResolvedValue({
    current_oi: 650000000, oi_change_pct: 2.3, oi_change_1h_pct: 4.1,
    price_oi_signal: 'bullish_confirmation', oi_trend: 'accumulating',
    signal: 'bullish', sentiment_score: 0.65, signal_strength: 0.65,
    large_oi_change: false,
    interpretation: 'OI +2.30% with price rising. New longs entering.',
  }),
  getDerivativesLiquidations: jest.fn().mockResolvedValue({
    current_price: 67000,
    signal: 'short_squeeze_risk', sentiment_score: 0.5,
    cascade_risk_below_pct: 8.2, cascade_risk_above_pct: 2.1,
    long_liquidation_levels: [
      { price: 61540, direction: 'long_liq', leverage: 10, estimated_entry: 66700,
        distance_pct: 8.15, severity: 'far', description: '10× long entry ~0.5% below current' },
    ],
    short_liquidation_levels: [
      { price: 68010, direction: 'short_liq', leverage: 50, estimated_entry: 67335,
        distance_pct: 1.51, severity: 'close', description: '50× short entry ~0.5% above current' },
    ],
    nearest_long_liq: null,
    nearest_short_liq: {
      price: 68010, direction: 'short_liq', leverage: 50,
      estimated_entry: 67335, distance_pct: 1.51, severity: 'close',
      description: '50× short entry ~0.5% above current',
    },
    interpretation: 'Short squeeze risk detected.',
  }),
  getDerivativesOptions:     jest.fn().mockResolvedValue({
    symbol: 'BTCUSD', spot: 67000, chain_count: 14,
    atm_call_greeks: {
      option_type: 'call', spot: 67000, strike: 67000, days_to_expiry: 7,
      implied_vol_pct: 80.0, risk_free_rate_pct: 6.5,
      theoretical_price: 1234.5, intrinsic_value: 0.0, time_value: 1234.5,
      delta: 0.5102, gamma: 0.000018, theta_daily: -52.4,
      vega_1pct: 42.1, rho_1pct: 3.2, d1: 0.025, d2: -0.186,
    },
    chain_summary: {
      put_call_ratio: 0.85, pc_signal: 'neutral', pc_sentiment_score: 0.0,
      total_call_oi: 1200, total_put_oi: 1020,
      max_pain_strike: 66000, iv_atm_pct: 80.0,
      iv_skew_pct: 3.2, skew_signal: 'neutral', gamma_exposure_usd: 4200000,
      interpretation: 'P/C ratio: 0.85 (neutral). Max pain: $66,000. ATM IV: 80.0%.',
    },
    timestamp: '2026-03-10T00:00:00Z',
  }),
}));

describe('DerivativesScreen', () => {
  test('renders without crashing', () => {
    const { getByText } = render(<DerivativesScreen />);
    expect(getByText('Aggregate Derivatives Signal')).toBeTruthy();
  });

  test('shows composite score', () => {
    const { getAllByText } = render(<DerivativesScreen />);
    expect(getAllByText(/\+0\.28/).length).toBeGreaterThanOrEqual(1);
  });

  test('shows BUY action badge', () => {
    const { getAllByText } = render(<DerivativesScreen />);
    expect(getAllByText('BUY').length).toBeGreaterThanOrEqual(1);
  });

  test('shows SHORT SQUEEZE flag badge', () => {
    const { getByText } = render(<DerivativesScreen />);
    expect(getByText('SHORT SQUEEZE')).toBeTruthy();
  });

  test('shows HIGH OI CONVICTION badge', () => {
    const { getByText } = render(<DerivativesScreen />);
    expect(getByText('HIGH OI CONVICTION')).toBeTruthy();
  });

  test('shows sub-score labels', () => {
    const { getByText } = render(<DerivativesScreen />);
    expect(getByText('Funding')).toBeTruthy();
    expect(getByText('Basis')).toBeTruthy();
    expect(getByText('OI')).toBeTruthy();
  });

  test('shows summary text', () => {
    const { getByText } = render(<DerivativesScreen />);
    expect(getByText(/Derivatives score.*BUY/)).toBeTruthy();
  });

  test('shows Perpetual Funding Rate section after load', async () => {
    const { findByText } = render(<DerivativesScreen />);
    expect(await findByText('Perpetual Funding Rate', {}, { timeout: 5000 })).toBeTruthy();
  });

  test('shows funding rate value', async () => {
    const { findByText } = render(<DerivativesScreen />);
    // Funding rate 0.03% / 8h
    expect(await findByText(/0\.0300%/, {}, { timeout: 5000 })).toBeTruthy();
  });

  test('shows Spot-Perp Basis section', async () => {
    const { findByText } = render(<DerivativesScreen />);
    expect(await findByText('Spot-Perp Basis', {}, { timeout: 5000 })).toBeTruthy();
  });

  test('shows basis pct with + sign', async () => {
    const { findByText } = render(<DerivativesScreen />);
    expect(await findByText(/\+0\.3000%/, {}, { timeout: 5000 })).toBeTruthy();
  });

  test('shows Open Interest section', async () => {
    const { findByText } = render(<DerivativesScreen />);
    expect(await findByText('Open Interest', {}, { timeout: 5000 })).toBeTruthy();
  });

  test('shows OI in millions', async () => {
    const { findByText } = render(<DerivativesScreen />);
    expect(await findByText(/\$650\.0M/, {}, { timeout: 5000 })).toBeTruthy();
  });

  test('shows Liquidation Heatmap section', async () => {
    const { findByText } = render(<DerivativesScreen />);
    expect(await findByText('Liquidation Heatmap', {}, { timeout: 5000 })).toBeTruthy();
  });

  test('shows SHORT SQUEEZE RISK signal in liquidation section', async () => {
    const { findAllByText } = render(<DerivativesScreen />);
    const els = await findAllByText(/SHORT SQUEEZE RISK/i, {}, { timeout: 5000 });
    expect(els.length).toBeGreaterThanOrEqual(1);
  });

  test('shows Options Chain section', async () => {
    const { findByText } = render(<DerivativesScreen />);
    expect(await findByText('Options Chain', {}, { timeout: 5000 })).toBeTruthy();
  });

  test('shows P/C ratio', async () => {
    const { findByText } = render(<DerivativesScreen />);
    expect(await findByText(/P\/C 0\.85/, {}, { timeout: 5000 })).toBeTruthy();
  });

  test('shows ATM CALL GREEKS section', async () => {
    const { findByText } = render(<DerivativesScreen />);
    expect(await findByText(/ATM CALL GREEKS/, {}, { timeout: 5000 })).toBeTruthy();
  });

  test('shows delta value', async () => {
    const { findByText } = render(<DerivativesScreen />);
    expect(await findByText('0.5102', {}, { timeout: 5000 })).toBeTruthy();
  });

  test('shows IV value', async () => {
    const { findAllByText } = render(<DerivativesScreen />);
    const els = await findAllByText('80.0%', {}, { timeout: 8000 });
    expect(els.length).toBeGreaterThanOrEqual(1);
  }, 10000);
});
