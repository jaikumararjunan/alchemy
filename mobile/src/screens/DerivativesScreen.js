/**
 * DerivativesScreen — derivatives market intelligence dashboard.
 *
 * Sections:
 *  1. Aggregate Signal  — composite score + action badge
 *  2. Funding Rate      — 8h rate, annualized, contrarian signal
 *  3. Basis / Premium   — perp vs spot, contango / backwardation
 *  4. Open Interest     — OI trend, price+OI matrix signal
 *  5. Liquidation Map   — nearest liq levels, cascade / squeeze risk
 *  6. Options Chain     — P/C ratio, max pain, ATM Greeks, IV skew
 */
import React, { useEffect, useState } from 'react';
import {
  View, Text, ScrollView, StyleSheet, RefreshControl,
  ActivityIndicator, TouchableOpacity,
} from 'react-native';
import { useStore } from '../store/useStore';
import { colors, card } from '../theme';
import api from '../services/api';

const ACTION_COLOR = { BUY: colors.green, SELL: colors.red, HOLD: colors.yellow };
const SIGNAL_COLOR = {
  bullish: colors.green, slightly_bullish: '#6ee7b7',
  neutral: colors.text2,
  slightly_bearish: '#fca5a5', bearish: colors.red,
  cautious_bullish: '#6ee7b7', cautious_bearish: '#fca5a5',
  short_squeeze_risk: colors.yellow, long_squeeze_risk: colors.red,
};

function Row({ label, value, valueColor, sub }) {
  return (
    <View style={styles.tableRow}>
      <Text style={styles.tableLabel}>{label}</Text>
      <View style={{ alignItems: 'flex-end' }}>
        <Text style={[styles.tableVal, valueColor && { color: valueColor }]}>{value}</Text>
        {sub ? <Text style={styles.tableSub}>{sub}</Text> : null}
      </View>
    </View>
  );
}

function Section({ title, children }) {
  return (
    <View style={card}>
      <Text style={styles.sectionTitle}>{title}</Text>
      {children}
    </View>
  );
}

function Badge({ label, color }) {
  return (
    <View style={[styles.badge, { borderColor: color, backgroundColor: color + '22' }]}>
      <Text style={[styles.badgeText, { color }]}>{label}</Text>
    </View>
  );
}

function ScoreBar({ score }) {
  const pct  = ((score + 1) / 2) * 100;
  const clr  = score > 0.2 ? colors.green : score < -0.2 ? colors.red : colors.yellow;
  return (
    <View style={styles.scoreBarWrap}>
      <View style={styles.scoreBarTrack}>
        <View style={[styles.scoreBarFill, { width: `${pct}%`, backgroundColor: clr }]} />
        <View style={styles.scoreBarMid} />
      </View>
      <Text style={[styles.scoreNum, { color: clr }]}>
        {score >= 0 ? '+' : ''}{score.toFixed(3)}
      </Text>
    </View>
  );
}

function LiqLevel({ level, color }) {
  return (
    <View style={[styles.liqRow, { borderLeftColor: color }]}>
      <Text style={[styles.liqPrice, { color }]}>${level.price.toLocaleString()}</Text>
      <Text style={styles.liqMeta}>{level.leverage}× · {level.distance_pct.toFixed(2)}% away</Text>
      <Text style={styles.liqDesc}>{level.description}</Text>
    </View>
  );
}

export default function DerivativesScreen() {
  const { derivativesSignal, setDerivativesSignal } = useStore();
  const [loading, setLoading]     = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError]         = useState(null);

  // Additional detail data
  const [fundingData, setFundingData]   = useState(null);
  const [basisData, setBasisData]       = useState(null);
  const [oiData, setOiData]             = useState(null);
  const [liqData, setLiqData]           = useState(null);
  const [optionsData, setOptionsData]   = useState(null);

  const fetchAll = async (isRefresh = false) => {
    if (!isRefresh) setLoading(true);
    setError(null);
    try {
      const [sig, funding, basis, oi, liq, opts] = await Promise.allSettled([
        api.getDerivativesSignal(),
        api.getDerivativesFunding(),
        api.getDerivativesBasis(),
        api.getDerivativesOI(),
        api.getDerivativesLiquidations(),
        api.getDerivativesOptions(),
      ]);

      if (sig.status === 'fulfilled')     setDerivativesSignal(sig.value);
      if (funding.status === 'fulfilled') setFundingData(funding.value);
      if (basis.status === 'fulfilled')   setBasisData(basis.value);
      if (oi.status === 'fulfilled')      setOiData(oi.value);
      if (liq.status === 'fulfilled')     setLiqData(liq.value);
      if (opts.status === 'fulfilled')    setOptionsData(opts.value);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => { fetchAll(); }, []);

  const onRefresh = () => { setRefreshing(true); fetchAll(true); };

  if (loading && !derivativesSignal) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color={colors.accent} />
        <Text style={styles.loadingText}>Loading derivatives data…</Text>
      </View>
    );
  }

  const sig = derivativesSignal;

  return (
    <ScrollView
      style={styles.container}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.accent} />}
    >
      {error ? <Text style={styles.error}>{error}</Text> : null}

      {/* ── 1. Aggregate Signal ───────────────────────────────────── */}
      <Section title="Aggregate Derivatives Signal">
        {sig ? (
          <>
            <View style={styles.scoreRow}>
              <View style={{ flex: 1 }}>
                <Text style={styles.scoreLabel}>COMPOSITE SCORE</Text>
                <ScoreBar score={sig.composite_score} />
              </View>
              <Badge
                label={sig.action_suggestion}
                color={ACTION_COLOR[sig.action_suggestion] || colors.text2}
              />
            </View>
            <Text style={styles.summaryText}>{sig.summary}</Text>
            <View style={styles.flagRow}>
              {sig.extreme_funding      && <Badge label="EXTREME FUNDING" color={colors.red} />}
              {sig.short_squeeze_risk   && <Badge label="SHORT SQUEEZE" color={colors.yellow} />}
              {sig.long_squeeze_risk    && <Badge label="LONG CASCADE" color={colors.red} />}
              {sig.high_oi_conviction   && <Badge label="HIGH OI CONVICTION" color={colors.green} />}
            </View>
            <View style={styles.subscoreGrid}>
              {[
                ['Funding', sig.funding_score],
                ['Basis', sig.basis_score],
                ['OI', sig.oi_score],
                ['Liq', sig.liquidation_score],
                ['Options', sig.options_score],
              ].map(([label, score]) => (
                <View key={label} style={styles.subscoreItem}>
                  <Text style={styles.subscoreLabel}>{label}</Text>
                  <Text style={[styles.subscoreVal,
                    { color: score > 0 ? colors.green : score < 0 ? colors.red : colors.text2 }]}>
                    {score >= 0 ? '+' : ''}{score.toFixed(3)}
                  </Text>
                </View>
              ))}
            </View>
          </>
        ) : <Text style={styles.tableLabel}>No data — pull to refresh</Text>}
      </Section>

      {/* ── 2. Funding Rate ───────────────────────────────────────── */}
      {fundingData && (
        <Section title="Perpetual Funding Rate">
          <View style={styles.fundingHeader}>
            <View>
              <Text style={styles.fundingRate}>
                {(fundingData.current_rate_pct || 0).toFixed(4)}%
                <Text style={styles.fundingPer}> / 8h</Text>
              </Text>
              <Text style={styles.fundingAnn}>
                {(fundingData.annualized_rate_pct || 0).toFixed(1)}% annualized
              </Text>
            </View>
            <Badge
              label={fundingData.signal?.replace(/_/g, ' ').toUpperCase()}
              color={SIGNAL_COLOR[fundingData.signal] || colors.text2}
            />
          </View>
          <Row label="Rate Label"     value={fundingData.rate_label?.toUpperCase().replace(/_/g, ' ')} />
          <Row label="7-day Average"  value={`${((fundingData.avg_rate_7d || 0) * 100).toFixed(4)}%`} />
          <Row label="7-day Cum. Paid" value={`${(fundingData.cumulative_7d_pct || 0).toFixed(3)}%`} />
          <Row label="Trend"          value={fundingData.trend?.toUpperCase()} />
          <Text style={styles.interpretText}>{fundingData.interpretation}</Text>
        </Section>
      )}

      {/* ── 3. Basis / Premium ───────────────────────────────────── */}
      {basisData && (
        <Section title="Spot-Perp Basis">
          <View style={styles.fundingHeader}>
            <View>
              <Text style={[styles.fundingRate,
                { color: (basisData.basis_pct || 0) >= 0 ? colors.yellow : colors.green }]}>
                {(basisData.basis_pct || 0) >= 0 ? '+' : ''}{(basisData.basis_pct || 0).toFixed(4)}%
              </Text>
              <Text style={styles.fundingAnn}>{basisData.basis_label?.replace(/_/g, ' ')}</Text>
            </View>
            <Badge
              label={basisData.signal?.replace(/_/g, ' ').toUpperCase()}
              color={SIGNAL_COLOR[basisData.signal] || colors.text2}
            />
          </View>
          <Row label="Perp Price"   value={`$${(basisData.perp_price || 0).toLocaleString()}`} />
          <Row label="Spot Price"   value={`$${(basisData.spot_price || 0).toLocaleString()}`} />
          <Row label="Basis USD"    value={`$${(basisData.basis_usd || 0).toFixed(2)}`} />
          <Row label="1h Avg Basis" value={`${(basisData.avg_basis_pct_1h || 0).toFixed(4)}%`} />
          <Row label="Trend"        value={basisData.basis_trend?.toUpperCase()} />
          <Text style={styles.interpretText}>{basisData.interpretation}</Text>
        </Section>
      )}

      {/* ── 4. Open Interest ─────────────────────────────────────── */}
      {oiData && (
        <Section title="Open Interest">
          <View style={styles.fundingHeader}>
            <View>
              <Text style={styles.fundingRate}>
                ${((oiData.current_oi || 0) / 1e6).toFixed(1)}M
              </Text>
              <Text style={styles.fundingAnn}>Open Interest (notional)</Text>
            </View>
            <Badge
              label={oiData.signal?.replace(/_/g, ' ').toUpperCase()}
              color={SIGNAL_COLOR[oiData.signal] || colors.text2}
            />
          </View>
          <Row label="OI Change (tick)"  value={`${(oiData.oi_change_pct || 0) >= 0 ? '+' : ''}${(oiData.oi_change_pct || 0).toFixed(3)}%`}
               valueColor={(oiData.oi_change_pct || 0) >= 0 ? colors.green : colors.red} />
          <Row label="OI Change (1h)"    value={`${(oiData.oi_change_1h_pct || 0) >= 0 ? '+' : ''}${(oiData.oi_change_1h_pct || 0).toFixed(3)}%`} />
          <Row label="OI Trend"          value={oiData.oi_trend?.toUpperCase()} />
          <Row label="Price+OI Signal"   value={oiData.price_oi_signal?.replace(/_/g, ' ').toUpperCase()}
               valueColor={oiData.price_oi_signal?.includes('bullish') ? colors.green : colors.red} />
          {oiData.large_oi_change && <Badge label="LARGE OI MOVE" color={colors.yellow} />}
          <Text style={styles.interpretText}>{oiData.interpretation}</Text>
        </Section>
      )}

      {/* ── 5. Liquidation Map ───────────────────────────────────── */}
      {liqData && (
        <Section title="Liquidation Heatmap">
          <View style={styles.fundingHeader}>
            <View>
              <Text style={styles.fundingRate}>${(liqData.current_price || 0).toLocaleString()}</Text>
              <Text style={styles.fundingAnn}>Current Price</Text>
            </View>
            <Badge
              label={liqData.signal?.replace(/_/g, ' ').toUpperCase()}
              color={liqData.signal === 'neutral' ? colors.text2 :
                     liqData.signal === 'short_squeeze_risk' ? colors.yellow : colors.red}
            />
          </View>
          <Row label="Cascade Risk Below" value={`${(liqData.cascade_risk_below_pct || 0).toFixed(2)}%`}
               valueColor={liqData.cascade_risk_below_pct < 5 ? colors.red : colors.text2} />
          <Row label="Cascade Risk Above" value={`${(liqData.cascade_risk_above_pct || 0).toFixed(2)}%`}
               valueColor={liqData.cascade_risk_above_pct < 5 ? colors.yellow : colors.text2} />

          <Text style={styles.liqSectionLabel}>NEAREST LONG LIQUIDATIONS (below)</Text>
          {(liqData.long_liquidation_levels || []).slice(0, 3).map((l, i) => (
            <LiqLevel key={i} level={l} color={colors.red} />
          ))}

          <Text style={[styles.liqSectionLabel, { marginTop: 8 }]}>NEAREST SHORT LIQUIDATIONS (above)</Text>
          {(liqData.short_liquidation_levels || []).slice(0, 3).map((l, i) => (
            <LiqLevel key={i} level={l} color={colors.yellow} />
          ))}
          <Text style={styles.interpretText}>{liqData.interpretation}</Text>
        </Section>
      )}

      {/* ── 6. Options ───────────────────────────────────────────── */}
      {optionsData && (
        <Section title="Options Chain">
          {optionsData.chain_summary && (
            <>
              <View style={styles.fundingHeader}>
                <View>
                  <Text style={styles.fundingRate}>
                    P/C {(optionsData.chain_summary.put_call_ratio || 0).toFixed(2)}
                  </Text>
                  <Text style={styles.fundingAnn}>Put / Call Ratio</Text>
                </View>
                <Badge
                  label={optionsData.chain_summary.pc_signal?.replace(/_/g, ' ').toUpperCase()}
                  color={SIGNAL_COLOR[optionsData.chain_summary.pc_signal] || colors.text2}
                />
              </View>
              <Row label="Total Call OI" value={(optionsData.chain_summary.total_call_oi || 0).toLocaleString()} />
              <Row label="Total Put OI"  value={(optionsData.chain_summary.total_put_oi || 0).toLocaleString()} />
              <Row label="Max Pain"      value={optionsData.chain_summary.max_pain_strike
                ? `$${optionsData.chain_summary.max_pain_strike.toLocaleString()}` : 'N/A'} />
              <Row label="ATM IV"        value={optionsData.chain_summary.iv_atm_pct
                ? `${optionsData.chain_summary.iv_atm_pct.toFixed(1)}%` : 'N/A'} />
              <Row label="IV Skew"       value={optionsData.chain_summary.iv_skew_pct
                ? `${optionsData.chain_summary.iv_skew_pct.toFixed(2)}%` : 'N/A'} />
              <Row label="Skew Signal"   value={optionsData.chain_summary.skew_signal?.toUpperCase()} />
              <Text style={styles.interpretText}>{optionsData.chain_summary.interpretation}</Text>
            </>
          )}

          {optionsData.atm_call_greeks && (
            <>
              <Text style={[styles.liqSectionLabel, { marginTop: 12 }]}>ATM CALL GREEKS (7-day)</Text>
              <Row label="Spot"          value={`$${(optionsData.spot || 0).toLocaleString()}`} />
              <Row label="Theoretical Px" value={`$${(optionsData.atm_call_greeks.theoretical_price || 0).toFixed(2)}`} />
              <Row label="Delta"         value={(optionsData.atm_call_greeks.delta || 0).toFixed(4)} />
              <Row label="Gamma"         value={(optionsData.atm_call_greeks.gamma || 0).toFixed(6)} />
              <Row label="Theta (daily)" value={(optionsData.atm_call_greeks.theta_daily || 0).toFixed(4)} />
              <Row label="Vega (1% IV)"  value={(optionsData.atm_call_greeks.vega_1pct || 0).toFixed(4)} />
              <Row label="IV"            value={`${(optionsData.atm_call_greeks.implied_vol_pct || 0).toFixed(1)}%`} />
            </>
          )}
        </Section>
      )}

      <View style={{ height: 32 }} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container:        { flex: 1, backgroundColor: colors.bg, padding: 12 },
  center:           { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: colors.bg },
  loadingText:      { color: colors.text2, marginTop: 12 },
  error:            { color: colors.red, padding: 12, textAlign: 'center' },
  sectionTitle:     { color: colors.accent, fontSize: 13, fontWeight: '700', letterSpacing: 1.2,
                      textTransform: 'uppercase', marginBottom: 12 },
  tableRow:         { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
                      paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: colors.border + '55' },
  tableLabel:       { color: colors.text2, fontSize: 12 },
  tableVal:         { color: colors.text, fontSize: 12, fontWeight: '600' },
  tableSub:         { color: colors.text3, fontSize: 10 },
  badge:            { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 6,
                      borderWidth: 1, marginTop: 4, alignSelf: 'flex-start' },
  badgeText:        { fontSize: 11, fontWeight: '700', letterSpacing: 0.8 },
  scoreRow:         { flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 8 },
  scoreLabel:       { color: colors.text3, fontSize: 10, letterSpacing: 1, marginBottom: 4 },
  scoreBarWrap:     { flex: 1, flexDirection: 'row', alignItems: 'center', gap: 8 },
  scoreBarTrack:    { flex: 1, height: 8, backgroundColor: colors.bg3, borderRadius: 4,
                      overflow: 'hidden', position: 'relative' },
  scoreBarFill:     { height: '100%', borderRadius: 4 },
  scoreBarMid:      { position: 'absolute', left: '50%', top: 0, bottom: 0, width: 1,
                      backgroundColor: colors.text3 },
  scoreNum:         { fontSize: 14, fontWeight: '700', width: 56 },
  summaryText:      { color: colors.text2, fontSize: 11, marginTop: 8, lineHeight: 16 },
  flagRow:          { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 8 },
  subscoreGrid:     { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 10 },
  subscoreItem:     { backgroundColor: colors.bg3, borderRadius: 8, padding: 8, minWidth: 60,
                      alignItems: 'center' },
  subscoreLabel:    { color: colors.text3, fontSize: 10, letterSpacing: 0.5 },
  subscoreVal:      { fontSize: 13, fontWeight: '700', marginTop: 2 },
  fundingHeader:    { flexDirection: 'row', justifyContent: 'space-between',
                      alignItems: 'flex-start', marginBottom: 10 },
  fundingRate:      { color: colors.text, fontSize: 24, fontWeight: '700' },
  fundingPer:       { fontSize: 14, color: colors.text3, fontWeight: '400' },
  fundingAnn:       { color: colors.text3, fontSize: 11, marginTop: 2 },
  interpretText:    { color: colors.text2, fontSize: 11, marginTop: 10, lineHeight: 16,
                      fontStyle: 'italic' },
  liqSectionLabel:  { color: colors.text3, fontSize: 10, letterSpacing: 1,
                      textTransform: 'uppercase', marginTop: 4, marginBottom: 6 },
  liqRow:           { borderLeftWidth: 3, paddingLeft: 8, marginBottom: 6 },
  liqPrice:         { fontSize: 14, fontWeight: '700' },
  liqMeta:          { color: colors.text2, fontSize: 11 },
  liqDesc:          { color: colors.text3, fontSize: 10 },
});
