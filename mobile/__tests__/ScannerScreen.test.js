/**
 * Tests for ScannerScreen component.
 */
import React from 'react';
import { render } from '@testing-library/react-native';
import ScannerScreen from '../src/screens/ScannerScreen';

const mockScanResult = {
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
      reasoning: 'ADX 26.1 (trending) | trend bullish' },
    { symbol: 'XRPUSD', rank: 3, composite_score: -0.29, action: 'SELL', confidence: 0.58,
      current_price: 0.62, change_24h_pct: -4.1, volume_24h: 5000, open_interest: 20e6,
      forecast_score: -0.35, derivatives_score: -0.18, volatility_score: 0.5, volume_score: 0.4,
      adx: 28.3, market_regime: 'trending', trend_direction: 'bearish', forecast_bias: 'bearish',
      regression_r2: 0.60, breakeven_move_pct: 0.5, expected_move_pct: 2.1,
      risk_reward_estimate: 1.8, suggested_size_pct: 10.0, scan_time_ms: 108,
      reasoning: 'ADX 28.3 (trending) | trend bearish | forecast bearish' },
  ],
  top_opportunities: [
    { symbol: 'SOLUSD', rank: 1, composite_score: 0.48, action: 'BUY', confidence: 0.78,
      current_price: 185.5, change_24h_pct: 3.2, volume_24h: 12000, open_interest: 80e6,
      forecast_score: 0.55, derivatives_score: 0.31, volatility_score: 0.7, volume_score: 0.6,
      adx: 32.5, market_regime: 'trending', trend_direction: 'bullish', forecast_bias: 'bullish',
      regression_r2: 0.71, breakeven_move_pct: 0.5, expected_move_pct: 2.8,
      risk_reward_estimate: 2.1, suggested_size_pct: 55.0, scan_time_ms: 120,
      reasoning: 'ADX 32.5 (trending) | trend bullish | forecast bullish | R²=0.71' },
  ],
  scan_timestamp: '2026-03-10T12:00:00Z',
  total_scanned: 10, total_actionable: 4,
  scan_duration_seconds: 3.2,
  market_summary: 'Scanned 10 contracts: 3 BUY / 1 SELL. Top opportunities: SOLUSD(BUY), ETHUSD(BUY). Trending: SOLUSD, ETHUSD.',
};

jest.mock('../src/store/useStore', () => ({
  useStore: () => ({
    scanResult: mockScanResult,
    setScanResult: jest.fn(),
  }),
}));

jest.mock('../src/services/api', () => ({
  scanContracts: jest.fn().mockResolvedValue(mockScanResult),
}));

describe('ScannerScreen', () => {
  test('renders without crashing', () => {
    const { getByText } = render(<ScannerScreen />);
    expect(getByText('Market Scan')).toBeTruthy();
  });

  test('shows total scanned count', () => {
    const { getByText } = render(<ScannerScreen />);
    expect(getByText('10')).toBeTruthy();
  });

  test('shows actionable count', () => {
    const { getByText } = render(<ScannerScreen />);
    expect(getByText('4')).toBeTruthy();
  });

  test('shows scan duration', () => {
    const { getByText } = render(<ScannerScreen />);
    expect(getByText('3.2s')).toBeTruthy();
  });

  test('shows market summary headline', () => {
    const { getByText } = render(<ScannerScreen />);
    expect(getByText(/Scanned 10 contracts/)).toBeTruthy();
  });

  test('shows Top Opportunities section', () => {
    const { getByText } = render(<ScannerScreen />);
    expect(getByText('Top Opportunities')).toBeTruthy();
  });

  test('shows SOLUSD in top opportunities', () => {
    const { getAllByText } = render(<ScannerScreen />);
    expect(getAllByText('SOLUSD').length).toBeGreaterThanOrEqual(1);
  });

  test('shows BUY action badge for SOLUSD', () => {
    const { getAllByText } = render(<ScannerScreen />);
    expect(getAllByText('BUY').length).toBeGreaterThanOrEqual(1);
  });

  test('shows SELL action badge for XRPUSD', () => {
    const { getAllByText } = render(<ScannerScreen />);
    expect(getAllByText('SELL').length).toBeGreaterThanOrEqual(1);
  });

  test('shows composite score for SOLUSD', () => {
    const { getAllByText } = render(<ScannerScreen />);
    expect(getAllByText(/\+0\.48/).length).toBeGreaterThanOrEqual(1);
  });

  test('shows TRENDING regime for SOLUSD', () => {
    const { getAllByText } = render(<ScannerScreen />);
    expect(getAllByText('TRENDING').length).toBeGreaterThanOrEqual(1);
  });

  test('shows All Contracts Ranked section', () => {
    const { getByText } = render(<ScannerScreen />);
    expect(getByText('All Contracts Ranked')).toBeTruthy();
  });

  test('shows ETHUSD in ranked list', () => {
    const { getAllByText } = render(<ScannerScreen />);
    expect(getAllByText('ETHUSD').length).toBeGreaterThanOrEqual(1);
  });

  test('shows XRPUSD in ranked list', () => {
    const { getAllByText } = render(<ScannerScreen />);
    expect(getAllByText('XRPUSD').length).toBeGreaterThanOrEqual(1);
  });

  test('shows ADX value', () => {
    const { getAllByText } = render(<ScannerScreen />);
    expect(getAllByText(/32\.5/).length).toBeGreaterThanOrEqual(1);
  });

  test('shows R² value', () => {
    const { getAllByText } = render(<ScannerScreen />);
    expect(getAllByText(/0\.71/).length).toBeGreaterThanOrEqual(1);
  });

  test('shows confidence percentage', () => {
    const { getAllByText } = render(<ScannerScreen />);
    expect(getAllByText('78%').length).toBeGreaterThanOrEqual(1);
  });

  test('shows allocation percentage', () => {
    const { getAllByText } = render(<ScannerScreen />);
    expect(getAllByText(/55\.0%/).length).toBeGreaterThanOrEqual(1);
  });

  test('shows reasoning text', () => {
    const { getByText } = render(<ScannerScreen />);
    expect(getByText(/ADX 32\.5.*trending.*bullish/)).toBeTruthy();
  });

  test('shows sub-score labels', () => {
    const { getByText } = render(<ScannerScreen />);
    expect(getByText('Forecast')).toBeTruthy();
    expect(getByText('Deriv')).toBeTruthy();
  });
});
