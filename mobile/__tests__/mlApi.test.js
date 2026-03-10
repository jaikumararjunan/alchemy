/**
 * Tests for ML/AI API methods.
 */

// Mock fetch globally
global.fetch = jest.fn();

import api from '../src/services/api';

describe('ML API methods', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  const mockOk = (data) =>
    fetch.mockResolvedValueOnce({ ok: true, json: async () => data });

  const mockFail = (status = 500) =>
    fetch.mockResolvedValueOnce({ ok: false, status });

  // ── getMlAnalysis ────────────────────────────────────────────────────

  test('getMlAnalysis exists as function', () => {
    expect(typeof api.getMlAnalysis).toBe('function');
  });

  test('getMlAnalysis calls correct URL for BTCUSD', async () => {
    mockOk({ ml_composite_score: 0.25, ml_action_suggestion: 'BUY' });
    await api.getMlAnalysis('BTCUSD');
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/ml/analyze?symbol=BTCUSD')
    );
  });

  test('getMlAnalysis uses default symbol BTCUSD', async () => {
    mockOk({ ml_composite_score: 0.0 });
    await api.getMlAnalysis();
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/ml/analyze?symbol=BTCUSD')
    );
  });

  test('getMlAnalysis returns parsed JSON response', async () => {
    const mockData = {
      ml_composite_score: 0.42,
      ml_action_suggestion: 'BUY',
      is_trained: true,
      trained_samples: 200,
    };
    mockOk(mockData);
    const result = await api.getMlAnalysis('BTCUSD');
    expect(result.ml_composite_score).toBeCloseTo(0.42);
    expect(result.ml_action_suggestion).toBe('BUY');
    expect(result.is_trained).toBe(true);
  });

  test('getMlAnalysis throws on HTTP error', async () => {
    mockFail(500);
    await expect(api.getMlAnalysis('BTCUSD')).rejects.toThrow();
  });

  // ── trainModels ──────────────────────────────────────────────────────

  test('trainModels exists as function', () => {
    expect(typeof api.trainModels).toBe('function');
  });

  test('trainModels sends POST to /api/ml/train', async () => {
    mockOk({ status: 'training_started' });
    await api.trainModels();
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/ml/train'),
      expect.objectContaining({ method: 'POST' })
    );
  });

  test('trainModels returns training_started status', async () => {
    mockOk({ status: 'training_started', message: 'ML models training in background' });
    const result = await api.trainModels();
    expect(result.status).toBe('training_started');
  });

  // ── getMlStatus ──────────────────────────────────────────────────────

  test('getMlStatus exists as function', () => {
    expect(typeof api.getMlStatus).toBe('function');
  });

  test('getMlStatus calls correct URL', async () => {
    mockOk({ price_predictor: { trained: true }, signal_classifier: { trained: false } });
    await api.getMlStatus();
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/ml/status')
    );
  });

  test('getMlStatus returns model status data', async () => {
    const mockStatus = {
      price_predictor: { trained: true, samples: 150 },
      signal_classifier: { trained: true, samples: 150 },
      sentiment_analyzer: { trained: false, samples: 0 },
    };
    mockOk(mockStatus);
    const result = await api.getMlStatus();
    expect(result.price_predictor.trained).toBe(true);
    expect(result.sentiment_analyzer.trained).toBe(false);
  });

  // ── analyzeSentiment ─────────────────────────────────────────────────

  test('analyzeSentiment exists as function', () => {
    expect(typeof api.analyzeSentiment).toBe('function');
  });

  test('analyzeSentiment sends headlines in POST body', async () => {
    mockOk({ aggregate: { score: 0.3, label: 'positive' }, count: 2 });
    const headlines = ['Bitcoin surges to new ATH', 'ETF approved by SEC'];
    await api.analyzeSentiment(headlines);
    const callArgs = fetch.mock.calls[0];
    const body = JSON.parse(callArgs[1].body);
    expect(body.headlines).toEqual(headlines);
    expect(callArgs[0]).toContain('/api/ml/sentiment');
  });

  test('analyzeSentiment returns aggregate and individual results', async () => {
    const mockResp = {
      aggregate: { score: 0.5, label: 'positive', confidence: 0.7, n: 1 },
      individual: [{ score: 0.5, label: 'positive', confidence: 0.7 }],
      count: 1,
    };
    mockOk(mockResp);
    const result = await api.analyzeSentiment(['Bitcoin ETF approved']);
    expect(result.aggregate.label).toBe('positive');
    expect(result.count).toBe(1);
  });

  test('analyzeSentiment throws on HTTP error', async () => {
    mockFail(422);
    await expect(api.analyzeSentiment([])).rejects.toThrow();
  });
});
