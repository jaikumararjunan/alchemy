/**
 * Tests for derivatives store state.
 */
import { act } from '@testing-library/react-hooks';
import { useStore } from '../src/store/useStore';

describe('Derivatives store state', () => {
  beforeEach(() => {
    useStore.setState({ derivativesSignal: null });
  });

  test('derivativesSignal initial state is null', () => {
    expect(useStore.getState().derivativesSignal).toBeNull();
  });

  test('setDerivativesSignal stores composite signal', () => {
    const sig = {
      composite_score: 0.28,
      action_suggestion: 'BUY',
      confidence: 0.75,
      extreme_funding: false,
      short_squeeze_risk: false,
      long_squeeze_risk: false,
      high_oi_conviction: true,
      summary: 'Derivatives score: +0.280 → BUY.',
      funding_score: 0.40, basis_score: 0.10,
      oi_score: 0.35, liquidation_score: 0.0, options_score: 0.2,
    };
    act(() => { useStore.getState().setDerivativesSignal(sig); });
    const { derivativesSignal: ds } = useStore.getState();
    expect(ds.composite_score).toBeCloseTo(0.28);
    expect(ds.action_suggestion).toBe('BUY');
    expect(ds.high_oi_conviction).toBe(true);
  });

  test('setDerivativesSignal stores SELL signal', () => {
    act(() => {
      useStore.getState().setDerivativesSignal({
        composite_score: -0.52,
        action_suggestion: 'SELL',
        extreme_funding: true,
      });
    });
    const ds = useStore.getState().derivativesSignal;
    expect(ds.action_suggestion).toBe('SELL');
    expect(ds.extreme_funding).toBe(true);
  });

  test('setDerivativesSignal stores HOLD with short squeeze flag', () => {
    act(() => {
      useStore.getState().setDerivativesSignal({
        composite_score: 0.1,
        action_suggestion: 'HOLD',
        short_squeeze_risk: true,
        long_squeeze_risk: false,
      });
    });
    const ds = useStore.getState().derivativesSignal;
    expect(ds.short_squeeze_risk).toBe(true);
    expect(ds.long_squeeze_risk).toBe(false);
  });

  test('setDerivativesSignal can be updated with new data', () => {
    act(() => { useStore.getState().setDerivativesSignal({ composite_score: 0.1, action_suggestion: 'HOLD' }); });
    act(() => { useStore.getState().setDerivativesSignal({ composite_score: -0.4, action_suggestion: 'SELL' }); });
    expect(useStore.getState().derivativesSignal.action_suggestion).toBe('SELL');
  });

  test('setDerivativesSignal stores sub-signal scores', () => {
    act(() => {
      useStore.getState().setDerivativesSignal({
        composite_score: -0.3,
        funding_score: -0.8,
        basis_score: -0.2,
        oi_score: -0.5,
        liquidation_score: 0.0,
        options_score: -0.4,
      });
    });
    const ds = useStore.getState().derivativesSignal;
    expect(ds.funding_score).toBeCloseTo(-0.8);
    expect(ds.oi_score).toBeCloseTo(-0.5);
  });

  test('derivativesSignal does not affect other state', () => {
    const preForecast = useStore.getState().forecast;
    act(() => { useStore.getState().setDerivativesSignal({ composite_score: 0.5 }); });
    expect(useStore.getState().forecast).toEqual(preForecast);
  });
});
