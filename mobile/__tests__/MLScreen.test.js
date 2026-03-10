/**
 * Tests for MLScreen component rendering.
 */
import React from 'react';
import { render } from '@testing-library/react-native';
import MLScreen from '../src/screens/MLScreen';

// Mock dependencies
jest.mock('../src/store/useStore', () => ({
  useStore: () => ({
    mlAnalysis: {
      ml_composite_score: 0.3412,
      ml_action_suggestion: 'BUY',
      is_trained: true,
      trained_samples: 180,
      prediction: {
        direction: 'up', confidence: 0.74,
        prob_up: 0.74, prob_flat: 0.14, prob_down: 0.12,
        model_agreement: 0.67, is_actionable: true,
        top_features: { rsi_14: 0.12, macd_signal: 0.09, bb_position: 0.08 },
        note: '',
      },
      signal: {
        signal: 'BUY', confidence: 0.68,
        prob_buy: 0.68, prob_hold: 0.20, prob_sell: 0.12,
        ml_score: 0.56, anomaly_risk: 0.08, is_actionable: true, note: '',
      },
      anomaly_report: {
        anomalies: [
          {
            type: 'VOLUME_SURGE', severity: 'medium',
            z_score: 2.7, description: 'Volume surge detected',
            trading_implication: 'High conviction move',
          },
        ],
        overall_risk: 'elevated', risk_score: 0.3,
        anomaly_count: 1, regime_change_detected: false, cusum_stat: 1.2,
        summary: 'VOLUME_SURGE [MEDIUM] z=+2.70',
      },
      sentiment: {
        score: 0.28, label: 'positive', confidence: 0.62,
        lexicon_score: 0.31, ml_score: 0.25,
        top_keywords: ['bitcoin', 'rally', 'etf'],
      },
    },
    setMlAnalysis: jest.fn(),
    market: { symbol: 'BTCUSD' },
  }),
}));

jest.mock('../src/services/api', () => ({
  getMlAnalysis: jest.fn().mockResolvedValue({}),
  trainModels: jest.fn().mockResolvedValue({ status: 'training_started' }),
}));

describe('MLScreen', () => {
  test('renders without crashing', () => {
    const { getByText } = render(<MLScreen />);
    expect(getByText('ML / AI Analysis Engine')).toBeTruthy();
  });

  test('shows composite ML score', () => {
    const { getByText } = render(<MLScreen />);
    expect(getByText(/\+0\.34/)).toBeTruthy();
  });

  test('shows ML action suggestion BUY', () => {
    const { getAllByText } = render(<MLScreen />);
    // BUY may appear in header badge and signal section
    const buyElements = getAllByText('BUY');
    expect(buyElements.length).toBeGreaterThanOrEqual(1);
  });

  test('shows model trained status', () => {
    const { getAllByText } = render(<MLScreen />);
    expect(getAllByText('YES').length).toBeGreaterThanOrEqual(1);
  });

  test('shows trained samples count', () => {
    const { getByText } = render(<MLScreen />);
    expect(getByText('180')).toBeTruthy();
  });

  test('shows price direction prediction section', () => {
    const { getByText } = render(<MLScreen />);
    expect(getByText('Price Direction Prediction')).toBeTruthy();
  });

  test('shows UP direction with uppercase', () => {
    const { getByText } = render(<MLScreen />);
    expect(getByText('UP')).toBeTruthy();
  });

  test('shows probability bars labels', () => {
    const { getByText } = render(<MLScreen />);
    expect(getByText(/UP\s*↑/)).toBeTruthy();
    expect(getByText(/DOWN↓/)).toBeTruthy();
  });

  test('shows ML Signal Classifier section', () => {
    const { getByText } = render(<MLScreen />);
    expect(getByText('ML Signal Classifier')).toBeTruthy();
  });

  test('shows Anomaly Detection section', () => {
    const { getByText } = render(<MLScreen />);
    expect(getByText('Anomaly Detection')).toBeTruthy();
  });

  test('shows ELEVATED risk level', () => {
    const { getByText } = render(<MLScreen />);
    expect(getByText('ELEVATED')).toBeTruthy();
  });

  test('shows anomaly type and severity', () => {
    const { getAllByText } = render(<MLScreen />);
    expect(getAllByText(/VOLUME_SURGE.*MEDIUM/).length).toBeGreaterThanOrEqual(1);
  });

  test('shows NLP Headline Sentiment section', () => {
    const { getByText } = render(<MLScreen />);
    expect(getByText('NLP Headline Sentiment')).toBeTruthy();
  });

  test('shows sentiment label POSITIVE', () => {
    const { getByText } = render(<MLScreen />);
    expect(getByText('POSITIVE')).toBeTruthy();
  });

  test('shows top keywords', () => {
    const { getByText } = render(<MLScreen />);
    expect(getByText(/bitcoin.*rally.*etf/i)).toBeTruthy();
  });

  test('shows Retrain Models Now button', () => {
    const { getByText } = render(<MLScreen />);
    expect(getByText('Retrain Models Now')).toBeTruthy();
  });

  test('shows top features section', () => {
    const { getByText } = render(<MLScreen />);
    expect(getByText('TOP PREDICTIVE FEATURES')).toBeTruthy();
  });

  test('shows feature names', () => {
    const { getByText } = render(<MLScreen />);
    expect(getByText(/rsi_14/)).toBeTruthy();
  });
});
