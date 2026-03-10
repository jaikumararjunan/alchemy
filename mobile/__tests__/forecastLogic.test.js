/**
 * Pure-logic tests for forecast and fee calculations.
 * These test the business rules used by the forecaster and risk manager
 * without needing any React Native components.
 */

// ── Net R:R calculation ───────────────────────────────────────────────────────

describe('Net R:R after fees', () => {
  function netRR(entry, sl, tp, takerFee = 0.0005) {
    const fee = entry * takerFee * 2;         // round-trip fee in price terms
    const grossReward = Math.abs(tp - entry);
    const grossRisk   = Math.abs(entry - sl);
    const netReward   = grossReward - fee;
    const netRisk     = grossRisk   + fee;
    return netRisk > 0 ? netReward / netRisk : 0;
  }

  test('standard buy: SL 2%, TP 4.5% yields net R:R > 1.5', () => {
    const entry = 68000;
    const sl    = entry * 0.98;     // -2%
    const tp    = entry * 1.045;    // +4.5%
    const rr    = netRR(entry, sl, tp);
    expect(rr).toBeGreaterThan(1.5);
  });

  test('old TP 4.0% may not always clear 1.5 net R:R at high fees', () => {
    // With tight spreads fee is small — just validate the formula works
    const entry = 68000;
    const sl    = entry * 0.98;
    const tp    = entry * 1.04;
    const rr    = netRR(entry, sl, tp);
    // 4% reward vs 2% risk gross is 2:1 — minus small fee still > 1.5
    expect(rr).toBeGreaterThan(1.0);
  });

  test('trade too close to entry (0.2% TP) fails net R:R', () => {
    const entry = 68000;
    const sl    = entry * 0.98;
    const tp    = entry * 1.002;    // 0.2% TP — less than fee cost
    const rr    = netRR(entry, sl, tp);
    expect(rr).toBeLessThan(0.5);
  });

  test('sell trade: SL 2% above, TP 4.5% below — symmetric', () => {
    const entry = 68000;
    const sl    = entry * 1.02;
    const tp    = entry * 0.955;
    const fee   = entry * 0.0005 * 2;
    const netReward = Math.abs(entry - tp) - fee;
    const netRisk   = Math.abs(sl - entry) + fee;
    const rr = netReward / netRisk;
    expect(rr).toBeGreaterThan(1.5);
  });
});

// ── Break-even calculation ────────────────────────────────────────────────────

describe('Break-even move percentage', () => {
  function breakevenPct(takerFeeRate = 0.0005, leverage = 5) {
    // Round-trip fee on notional, expressed as % of margin
    return takerFeeRate * 2 * leverage * 100;
  }

  test('default 0.05% taker fee at 5x leverage gives 0.50% breakeven', () => {
    expect(breakevenPct()).toBeCloseTo(0.5, 4);
  });

  test('higher leverage increases breakeven cost proportionally', () => {
    expect(breakevenPct(0.0005, 10)).toBeCloseTo(1.0, 4);
  });

  test('lower taker fee reduces breakeven', () => {
    expect(breakevenPct(0.0002, 5)).toBeCloseTo(0.2, 4);
  });
});

// ── Regime threshold adjustment ───────────────────────────────────────────────

describe('Regime-aware entry thresholds', () => {
  const BASE_BULL = 0.6;
  const BASE_BEAR = -0.6;

  function regimeThresholds(regime, adx) {
    let mult;
    if (regime === 'trending' && adx >= 35) mult = 0.80;
    else if (regime === 'trending') mult = 0.90;
    else if (regime === 'volatile') mult = 1.30;
    else mult = 1.15;
    return [BASE_BULL * mult, BASE_BEAR * mult];
  }

  test('strong trending market loosens threshold to 0.48', () => {
    const [bull] = regimeThresholds('trending', 40);
    expect(bull).toBeCloseTo(0.48, 4);
  });

  test('moderate trending market: threshold 0.54', () => {
    const [bull] = regimeThresholds('trending', 28);
    expect(bull).toBeCloseTo(0.54, 4);
  });

  test('ranging market tightens threshold to 0.69', () => {
    const [bull] = regimeThresholds('ranging', 15);
    expect(bull).toBeCloseTo(0.69, 4);
  });

  test('volatile market has tightest threshold 0.78', () => {
    const [bull] = regimeThresholds('volatile', 20);
    expect(bull).toBeCloseTo(0.78, 4);
  });
});

// ── Position size with fee deduction ─────────────────────────────────────────

describe('Position sizing with fee deduction', () => {
  function estimateFeeUSD(sizeUSD, leverage = 5, takerFee = 0.0005) {
    return sizeUSD * leverage * takerFee * 2;
  }

  function calcSize(baseUSD, quality, maxLossUSD, stopDistPct, leverage, takerFee) {
    const feeCost       = estimateFeeUSD(baseUSD * quality, leverage, takerFee);
    const adjustedBudget = Math.max(maxLossUSD - feeCost, maxLossUSD * 0.5);
    const riskLimited   = adjustedBudget / stopDistPct;
    return Math.min(baseUSD * quality, riskLimited);
  }

  test('fee deduction reduces available risk budget', () => {
    const base = 100, quality = 1.0, maxLoss = 50, stopDist = 0.02;
    const sizeNoFee  = Math.min(base, maxLoss / stopDist);
    const sizeWithFee = calcSize(base, quality, maxLoss, stopDist, 5, 0.0005);
    expect(sizeWithFee).toBeLessThanOrEqual(sizeNoFee);
  });

  test('estimate fee $100 margin at 5x = $0.50', () => {
    expect(estimateFeeUSD(100, 5, 0.0005)).toBeCloseTo(0.5, 4);
  });

  test('estimate fee $1000 margin at 5x = $5.00', () => {
    expect(estimateFeeUSD(1000, 5, 0.0005)).toBeCloseTo(5.0, 4);
  });
});

// ── Composite forecast score ──────────────────────────────────────────────────

describe('Composite forecast score', () => {
  // Simplified version of the _composite formula
  function compositeScore({ adx, plusDI, minusDI, r2, forecastBias, vwapDistPct }) {
    let score = 0, weight = 0;

    // ADX directional
    if (adx > 15) {
      const diSum  = plusDI + minusDI;
      const diDiff = diSum > 0 ? (plusDI - minusDI) / diSum : 0;
      const adxW   = Math.min(adx / 50, 1.0);
      score  += diDiff * adxW * 0.40;
      weight += 0.40;
    }

    // Regression
    if (r2 > 0.25) {
      const biasMap = { bullish: 1, bearish: -1, neutral: 0 };
      score  += (biasMap[forecastBias] ?? 0) * r2 * 0.35;
      weight += 0.35;
    }

    // VWAP
    const vwapSig = Math.max(-1, Math.min(vwapDistPct / 2.0, 1));
    score  += vwapSig * 0.25;
    weight += 0.25;

    return weight > 0 ? score / Math.max(weight, 1.0) : 0;
  }

  test('all-bullish inputs yield positive score', () => {
    const s = compositeScore({ adx: 40, plusDI: 30, minusDI: 10, r2: 0.7, forecastBias: 'bullish', vwapDistPct: 1.0 });
    expect(s).toBeGreaterThan(0.2);
  });

  test('all-bearish inputs yield negative score', () => {
    const s = compositeScore({ adx: 38, plusDI: 10, minusDI: 32, r2: 0.65, forecastBias: 'bearish', vwapDistPct: -1.5 });
    expect(s).toBeLessThan(-0.1);
  });

  test('low ADX with neutral bias returns score near zero', () => {
    const s = compositeScore({ adx: 10, plusDI: 15, minusDI: 14, r2: 0.1, forecastBias: 'neutral', vwapDistPct: 0.05 });
    expect(Math.abs(s)).toBeLessThan(0.15);
  });

  test('score is bounded within reasonable range', () => {
    const s = compositeScore({ adx: 100, plusDI: 50, minusDI: 0, r2: 1.0, forecastBias: 'bullish', vwapDistPct: 10 });
    expect(s).toBeLessThanOrEqual(1.0);
    expect(s).toBeGreaterThan(0);
  });
});
