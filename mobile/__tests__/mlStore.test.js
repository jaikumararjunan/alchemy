/**
 * Tests for ML/AI store state (mlAnalysis, setMlAnalysis).
 */
import { act } from '@testing-library/react-hooks';
import { useStore } from '../src/store/useStore';

describe('ML store state', () => {
  beforeEach(() => {
    useStore.setState({
      mlAnalysis: null,
    });
  });

  test('mlAnalysis initial state is null', () => {
    const { mlAnalysis } = useStore.getState();
    expect(mlAnalysis).toBeNull();
  });

  test('setMlAnalysis stores full analysis object', () => {
    const mockAnalysis = {
      ml_composite_score: 0.3456,
      ml_action_suggestion: 'BUY',
      is_trained: true,
      trained_samples: 150,
      prediction: {
        direction: 'up', confidence: 0.72, prob_up: 0.72,
        prob_flat: 0.15, prob_down: 0.13, is_actionable: true,
      },
      signal: {
        signal: 'BUY', confidence: 0.65, prob_buy: 0.65,
        prob_hold: 0.22, prob_sell: 0.13, ml_score: 0.52,
        anomaly_risk: 0.1, is_actionable: true,
      },
      anomaly_report: {
        anomalies: [], overall_risk: 'normal',
        risk_score: 0.0, anomaly_count: 0,
        regime_change_detected: false, cusum_stat: 0.12,
      },
      sentiment: {
        score: 0.25, label: 'positive', confidence: 0.68,
        lexicon_score: 0.3, ml_score: 0.2, top_keywords: ['bitcoin', 'rally'],
      },
    };

    act(() => {
      useStore.getState().setMlAnalysis(mockAnalysis);
    });

    const { mlAnalysis } = useStore.getState();
    expect(mlAnalysis).not.toBeNull();
    expect(mlAnalysis.ml_composite_score).toBeCloseTo(0.3456);
    expect(mlAnalysis.ml_action_suggestion).toBe('BUY');
    expect(mlAnalysis.is_trained).toBe(true);
    expect(mlAnalysis.trained_samples).toBe(150);
  });

  test('setMlAnalysis stores prediction sub-object', () => {
    act(() => {
      useStore.getState().setMlAnalysis({
        prediction: { direction: 'down', confidence: 0.81, prob_down: 0.81 },
        signal: {}, anomaly_report: {}, sentiment: {},
      });
    });
    const { mlAnalysis } = useStore.getState();
    expect(mlAnalysis.prediction.direction).toBe('down');
    expect(mlAnalysis.prediction.confidence).toBeCloseTo(0.81);
  });

  test('setMlAnalysis stores anomaly_report with anomalies list', () => {
    const anomalyReport = {
      anomalies: [
        { type: 'PRICE_SPIKE', severity: 'high', z_score: 3.2, description: 'Price spike detected' },
      ],
      overall_risk: 'high', risk_score: 0.6,
      anomaly_count: 1, regime_change_detected: false, cusum_stat: 2.1,
    };
    act(() => {
      useStore.getState().setMlAnalysis({ anomaly_report: anomalyReport });
    });
    const { mlAnalysis } = useStore.getState();
    expect(mlAnalysis.anomaly_report.anomalies).toHaveLength(1);
    expect(mlAnalysis.anomaly_report.overall_risk).toBe('high');
    expect(mlAnalysis.anomaly_report.anomaly_count).toBe(1);
  });

  test('setMlAnalysis stores sentiment with keywords', () => {
    act(() => {
      useStore.getState().setMlAnalysis({
        sentiment: {
          score: -0.42, label: 'negative', confidence: 0.55,
          lexicon_score: -0.5, ml_score: -0.35,
          top_keywords: ['crash', 'ban', 'lawsuit'],
        },
      });
    });
    const { mlAnalysis } = useStore.getState();
    expect(mlAnalysis.sentiment.label).toBe('negative');
    expect(mlAnalysis.sentiment.top_keywords).toContain('crash');
  });

  test('setMlAnalysis can be updated with new data', () => {
    act(() => {
      useStore.getState().setMlAnalysis({ ml_composite_score: 0.1, ml_action_suggestion: 'HOLD' });
    });
    act(() => {
      useStore.getState().setMlAnalysis({ ml_composite_score: -0.3, ml_action_suggestion: 'SELL' });
    });
    const { mlAnalysis } = useStore.getState();
    expect(mlAnalysis.ml_action_suggestion).toBe('SELL');
    expect(mlAnalysis.ml_composite_score).toBeCloseTo(-0.3);
  });

  test('setMlAnalysis with regime_change in anomaly_report', () => {
    act(() => {
      useStore.getState().setMlAnalysis({
        anomaly_report: {
          anomalies: [], overall_risk: 'critical', risk_score: 0.85,
          anomaly_count: 0, regime_change_detected: true, cusum_stat: 4.8,
        },
      });
    });
    expect(useStore.getState().mlAnalysis.anomaly_report.regime_change_detected).toBe(true);
    expect(useStore.getState().mlAnalysis.anomaly_report.cusum_stat).toBeCloseTo(4.8);
  });

  test('other store state unaffected by setMlAnalysis', () => {
    const initialForecast = useStore.getState().forecast;
    act(() => {
      useStore.getState().setMlAnalysis({ ml_composite_score: 0.5 });
    });
    expect(useStore.getState().forecast).toEqual(initialForecast);
  });
});
