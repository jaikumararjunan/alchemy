/**
 * Tests for ForecastCard component (mobile/src/components/ForecastCard.js)
 */
import React from 'react';
import { render } from '@testing-library/react-native';
import ForecastCard from '../src/components/ForecastCard';

const baseForecast = {
  adx: 38.0,
  trend_direction: 'bullish',
  trend_strength: 'strong',
  market_regime: 'trending',
  regime_confidence: 0.75,
  forecast_bias: 'bullish',
  forecast_price_3: 68500,
  regression_r2: 0.63,
  vwap: 67400,
  vwap_position: 'above',
  vwap_distance_pct: 0.45,
  support_levels: [66800, 65900, 65000],
  resistance_levels: [68500, 69100, 70000],
  breakeven_move_pct: 0.5,
  forecast_score: 0.52,
  current_price: 67800,
};

describe('ForecastCard', () => {
  test('renders without crashing with empty props', () => {
    const { getByText } = render(<ForecastCard />);
    expect(getByText('Market Forecast')).toBeTruthy();
  });

  test('displays ADX value', () => {
    const { getByText } = render(<ForecastCard forecast={baseForecast} />);
    expect(getByText('38.0')).toBeTruthy();
  });

  test('displays STRONG trend strength', () => {
    const { getByText } = render(<ForecastCard forecast={baseForecast} />);
    expect(getByText('STRONG')).toBeTruthy();
  });

  test('displays TRENDING regime', () => {
    const { getByText } = render(<ForecastCard forecast={baseForecast} />);
    expect(getByText('TRENDING')).toBeTruthy();
  });

  test('displays forecast bias somewhere on card', () => {
    // BULLISH appears in both forecast_bias and trend_direction — use getAllByText
    const { getAllByText } = render(<ForecastCard forecast={baseForecast} />);
    const bullishNodes = getAllByText('BULLISH');
    expect(bullishNodes.length).toBeGreaterThanOrEqual(1);
  });

  test('displays breakeven move percentage', () => {
    const { getByText } = render(<ForecastCard forecast={baseForecast} />);
    expect(getByText('0.50%')).toBeTruthy();
  });

  test('displays VWAP position label ABOVE', () => {
    const { getByText } = render(<ForecastCard forecast={baseForecast} />);
    // vwap_position 'above' renders the word ABOVE somewhere on the card
    expect(getByText(/ABOVE/)).toBeTruthy();
  });

  test('shows at least one resistance and one support level', () => {
    const { getAllByText } = render(<ForecastCard forecast={baseForecast} />);
    // R1 label present
    expect(getAllByText('R1').length).toBeGreaterThanOrEqual(1);
    // S1 label present
    expect(getAllByText('S1').length).toBeGreaterThanOrEqual(1);
  });

  test('renders bearish state — at least one BEARISH text node', () => {
    const fc = { ...baseForecast, forecast_bias: 'bearish', trend_direction: 'bearish', forecast_score: -0.45 };
    const { getAllByText } = render(<ForecastCard forecast={fc} />);
    expect(getAllByText('BEARISH').length).toBeGreaterThanOrEqual(1);
  });

  test('renders with zero/default values gracefully', () => {
    const { getByText } = render(<ForecastCard forecast={{ adx: 0, forecast_score: 0 }} />);
    expect(getByText('0.0')).toBeTruthy();   // ADX 0.0
    expect(getByText('NONE')).toBeTruthy();   // trend strength none
  });

  test('does not show forecast prices when forecast_price_3 is null', () => {
    const fc = { ...baseForecast, current_price: 0, forecast_price_3: null };
    const { queryByText } = render(<ForecastCard forecast={fc} />);
    expect(queryByText('3-BAR TARGET')).toBeNull();
  });

  test('shows positive forecast_score with + prefix', () => {
    // Component renders with `toFixed(3)` → "0.520"; + prefix is a separate text node
    const { getByText } = render(<ForecastCard forecast={baseForecast} />);
    // Use regex to match across text-node splits
    expect(getByText(/\+0\.52/)).toBeTruthy();
  });
});
