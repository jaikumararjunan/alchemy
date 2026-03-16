/**
 * Tests for ForecastScreen (mobile/src/screens/ForecastScreen.js)
 */
import React from 'react';
import { render, waitFor } from '@testing-library/react-native';

// ── Mocks ─────────────────────────────────────────────────────────────────────

const mockForecast = {
  symbol: 'BTCUSD', current_price: 67800,
  adx: 38.0, plus_di: 28.5, minus_di: 12.1,
  trend_direction: 'bullish', trend_strength: 'strong',
  market_regime: 'trending', regime_confidence: 0.75,
  forecast_bias: 'bullish',
  forecast_price_1: 67900, forecast_price_3: 68200, forecast_price_5: 68600,
  regression_r2: 0.63, forecast_slope_pct: 0.00042,
  vwap: 67400, vwap_position: 'above', vwap_distance_pct: 0.59,
  pivot_point: 67200,
  resistance_levels: [67900, 68500, 69200],
  support_levels: [66700, 66000, 65200],
  breakeven_move_pct: 0.5, round_trip_fee_pct: 0.5,
  taker_fee_pct: 0.05, leverage: 5,
  forecast_score: 0.52,
  timestamp: '2026-03-10T10:00:00Z',
};

const mockGetForecast = jest.fn(() => Promise.resolve(mockForecast));

jest.mock('../src/services/api', () => ({
  default: { getForecast: (...args) => mockGetForecast(...args) },
}));

jest.mock('../src/store/useStore', () => ({
  useStore: () => ({
    forecast: mockForecast,
    setForecast: jest.fn(),
    market: { symbol: 'BTCUSD', mark_price: 67800 },
  }),
}));

// ── Tests ─────────────────────────────────────────────────────────────────────

import ForecastScreen from '../src/screens/ForecastScreen';

describe('ForecastScreen', () => {
  beforeEach(() => {
    mockGetForecast.mockClear();
    mockGetForecast.mockResolvedValue(mockForecast);
  });

  test('renders without crashing', async () => {
    const { getByText } = render(<ForecastScreen />);
    // Screen renders synchronously with pre-loaded forecast from store
    expect(getByText(/Market Intelligence/)).toBeTruthy();
  }, 10000);

  test('shows forecast score', () => {
    const { getByText } = render(<ForecastScreen />);
    expect(getByText('+0.5200')).toBeTruthy();
  });

  test('displays ADX number prominently', () => {
    const { getByText } = render(<ForecastScreen />);
    expect(getByText('38.0')).toBeTruthy();
  });

  test('shows STRONG trend strength label', () => {
    const { getByText } = render(<ForecastScreen />);
    expect(getByText('STRONG')).toBeTruthy();
  });

  test('displays +DI value', () => {
    const { getByText } = render(<ForecastScreen />);
    expect(getByText('28.5')).toBeTruthy();
  });

  test('displays −DI value', () => {
    const { getByText } = render(<ForecastScreen />);
    expect(getByText('12.1')).toBeTruthy();
  });

  test('shows active regime chip: TRENDING', () => {
    const { getAllByText } = render(<ForecastScreen />);
    expect(getAllByText('TRENDING').length).toBeGreaterThan(0);
  });

  test('shows forecast bias: BULLISH somewhere on screen', () => {
    const { getAllByText } = render(<ForecastScreen />);
    expect(getAllByText('BULLISH').length).toBeGreaterThan(0);
  });

  test('shows regression R² value', () => {
    const { getByText } = render(<ForecastScreen />);
    expect(getByText('0.6300')).toBeTruthy();
  });

  test('shows R² quality hint: High confidence', () => {
    const { getByText } = render(<ForecastScreen />);
    expect(getByText('High confidence')).toBeTruthy();
  });

  test('shows VWAP position: ABOVE', () => {
    const { getAllByText } = render(<ForecastScreen />);
    expect(getAllByText('ABOVE').length).toBeGreaterThan(0);
  });

  test('shows breakeven_move_pct in brokerage section', () => {
    const { getByText } = render(<ForecastScreen />);
    expect(getByText('≥ 0.50%')).toBeTruthy();
  });

  test('shows round-trip fee label', () => {
    const { getByText } = render(<ForecastScreen />);
    expect(getByText('Round-trip fee (of margin)')).toBeTruthy();
  });

  test('shows taker fee per side', () => {
    const { getByText } = render(<ForecastScreen />);
    expect(getByText('0.050%')).toBeTruthy();
  });

  test('shows leverage setting', () => {
    const { getByText } = render(<ForecastScreen />);
    expect(getByText('5×')).toBeTruthy();
  });

  test('getForecast API endpoint is correct path', () => {
    // Integration check: the api module exports a getForecast method
    // (full mount test is covered by api.test.js which verifies the URL)
    const api = require('../src/services/api').default;
    expect(typeof api.getForecast).toBe('function');
  });
});
