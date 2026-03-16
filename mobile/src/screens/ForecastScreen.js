/**
 * ForecastScreen — full market forecast view.
 * Displays ADX, regime, linear regression, VWAP, pivot levels, and fee analysis.
 */
import React, { useEffect, useState } from 'react';
import {
  View, Text, ScrollView, StyleSheet, RefreshControl, ActivityIndicator,
} from 'react-native';
import { useStore } from '../store/useStore';
import { colors, card } from '../theme';
import api from '../services/api';

const REGIME_COLOR  = { trending: colors.green, ranging: colors.yellow, volatile: colors.red };
const BIAS_COLOR    = { bullish: colors.green, bearish: colors.red, neutral: colors.text2 };
const STRENGTH_LBL  = { very_strong: 'VERY STRONG', strong: 'STRONG', moderate: 'MODERATE', weak: 'WEAK', none: 'NONE' };

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

function SectionTitle({ text }) {
  return <Text style={styles.sectionTitle}>{text}</Text>;
}

export default function ForecastScreen() {
  const { forecast, setForecast, market } = useStore();
  const [refreshing, setRefreshing] = useState(false);
  const [loading, setLoading] = useState(!forecast.timestamp);

  const load = async () => {
    try {
      const data = await api.getForecast(market.symbol || 'BTCUSD');
      if (!data.error) setForecast(data);
    } catch (e) {}
  };

  useEffect(() => {
    load().then(() => setLoading(false));
    const interval = setInterval(load, 60_000);
    return () => clearInterval(interval);
  }, [market.symbol]);

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={colors.accent} size="large" />
        <Text style={styles.loadingText}>Running Market Forecaster…</Text>
      </View>
    );
  }

  const fc = forecast;
  const adxColor     = fc.adx >= 40 ? colors.green : fc.adx >= 25 ? colors.yellow : colors.text3;
  const scoreColor   = fc.forecast_score > 0.1 ? colors.green : fc.forecast_score < -0.1 ? colors.red : colors.text2;
  const adxBarWidth  = `${Math.min(fc.adx || 0, 100)}%`;

  return (
    <ScrollView
      style={styles.screen}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.accent} />}
    >
      {/* Header price */}
      <View style={[card, { marginHorizontal: 16, marginTop: 16 }]}>
        <Text style={styles.cardTitle}>
          {fc.symbol || market.symbol || 'BTCUSD'} — Market Intelligence
        </Text>
        <View style={styles.priceRow}>
          <View>
            <Text style={styles.tinyLabel}>CURRENT PRICE</Text>
            <Text style={styles.bigPrice}>
              ${(fc.current_price || 0).toLocaleString('en', { maximumFractionDigits: 2 })}
            </Text>
          </View>
          <View style={{ alignItems: 'flex-end' }}>
            <Text style={styles.tinyLabel}>FORECAST SCORE</Text>
            <Text style={[styles.bigPrice, { color: scoreColor }]}>
              {fc.forecast_score >= 0 ? '+' : ''}{(fc.forecast_score || 0).toFixed(4)}
            </Text>
          </View>
        </View>
        <Text style={styles.ts}>{fc.timestamp ? new Date(fc.timestamp).toLocaleTimeString() : 'N/A'}</Text>
      </View>

      {/* Trend Strength */}
      <View style={[card, { marginHorizontal: 16 }]}>
        <SectionTitle text="Trend Strength (ADX)" />

        <View style={styles.adxRow}>
          <Text style={[styles.adxNum, { color: adxColor }]}>{(fc.adx || 0).toFixed(1)}</Text>
          <Text style={[styles.adxLabel, { color: adxColor }]}>
            {STRENGTH_LBL[fc.trend_strength] || 'NONE'}
          </Text>
        </View>

        {/* ADX progress bar */}
        <View style={styles.barTrack}>
          <View style={[styles.barFill, { width: adxBarWidth, backgroundColor: adxColor }]} />
          {/* Zone markers */}
          <View style={[styles.marker, { left: '25%' }]} />
          <View style={[styles.marker, { left: '40%' }]} />
          <View style={[styles.marker, { left: '60%' }]} />
        </View>
        <View style={styles.barLabels}>
          <Text style={styles.barLabel}>Weak</Text>
          <Text style={styles.barLabel}>Mod</Text>
          <Text style={styles.barLabel}>Strong</Text>
          <Text style={styles.barLabel}>V.Strong</Text>
        </View>

        <View style={[styles.diRow, { marginTop: 12 }]}>
          <View style={styles.diBox}>
            <Text style={styles.tinyLabel}>+DI</Text>
            <Text style={[styles.diVal, { color: colors.green }]}>{(fc.plus_di || 0).toFixed(1)}</Text>
          </View>
          <View style={styles.diBox}>
            <Text style={styles.tinyLabel}>−DI</Text>
            <Text style={[styles.diVal, { color: colors.red }]}>{(fc.minus_di || 0).toFixed(1)}</Text>
          </View>
          <View style={styles.diBox}>
            <Text style={styles.tinyLabel}>DIRECTION</Text>
            <Text style={[styles.diVal, { color: BIAS_COLOR[fc.trend_direction] }]}>
              {(fc.trend_direction || 'NEUTRAL').toUpperCase()}
            </Text>
          </View>
        </View>
      </View>

      {/* Market Regime */}
      <View style={[card, { marginHorizontal: 16 }]}>
        <SectionTitle text="Market Regime" />
        <View style={styles.regimeRow}>
          {['trending', 'ranging', 'volatile'].map(r => (
            <View
              key={r}
              style={[
                styles.regimeChip,
                fc.market_regime === r && { borderColor: REGIME_COLOR[r], backgroundColor: REGIME_COLOR[r] + '22' },
              ]}
            >
              <Text style={[styles.regimeText, fc.market_regime === r && { color: REGIME_COLOR[r] }]}>
                {r.toUpperCase()}
              </Text>
            </View>
          ))}
        </View>
        <Row label="Regime Confidence" value={`${((fc.regime_confidence || 0) * 100).toFixed(0)}%`} />
        <Row label="Strategy hint"
          value={
            fc.market_regime === 'trending' ? 'Trade WITH the trend' :
            fc.market_regime === 'ranging'  ? 'Mean-revert at levels' :
            'Wait for clear breakout'
          }
          valueColor={REGIME_COLOR[fc.market_regime]}
        />
      </View>

      {/* Linear Regression Forecast */}
      <View style={[card, { marginHorizontal: 16 }]}>
        <SectionTitle text="Linear Regression Price Forecast" />
        <Row
          label="Forecast Bias"
          value={(fc.forecast_bias || 'neutral').toUpperCase()}
          valueColor={BIAS_COLOR[fc.forecast_bias]}
        />
        <Row label="R² Quality" value={(fc.regression_r2 || 0).toFixed(4)}
          sub={fc.regression_r2 >= 0.4 ? 'High confidence' : fc.regression_r2 >= 0.2 ? 'Moderate' : 'Low confidence'}
        />
        <Row label="Slope (% per period)" value={`${(fc.forecast_slope_pct || 0) >= 0 ? '+' : ''}${(fc.forecast_slope_pct || 0).toFixed(5)}%`} />
        <View style={styles.forecastPrices}>
          {[
            { label: '+1 Bar', val: fc.forecast_price_1 },
            { label: '+3 Bars', val: fc.forecast_price_3 },
            { label: '+5 Bars', val: fc.forecast_price_5 },
          ].map(({ label, val }) => val && (
            <View key={label} style={styles.fpBox}>
              <Text style={styles.tinyLabel}>{label}</Text>
              <Text style={[styles.fpVal, {
                color: val > (fc.current_price || 0) ? colors.green : colors.red,
              }]}>
                ${val.toLocaleString('en', { maximumFractionDigits: 0 })}
              </Text>
              <Text style={styles.tableSub}>
                {val > (fc.current_price || 0) ? '+' : ''}
                {(fc.current_price ? ((val - fc.current_price) / fc.current_price * 100) : 0).toFixed(2)}%
              </Text>
            </View>
          ))}
        </View>
      </View>

      {/* VWAP */}
      <View style={[card, { marginHorizontal: 16 }]}>
        <SectionTitle text="VWAP Analysis" />
        <Row
          label="VWAP"
          value={fc.vwap ? `$${fc.vwap.toLocaleString('en', { maximumFractionDigits: 2 })}` : 'N/A'}
        />
        <Row
          label="Price vs VWAP"
          value={(fc.vwap_position || 'at').toUpperCase()}
          valueColor={
            fc.vwap_position === 'above' ? colors.green :
            fc.vwap_position === 'below' ? colors.red : colors.text2
          }
          sub="Institutional buy/sell bias"
        />
        <Row
          label="Distance from VWAP"
          value={`${(fc.vwap_distance_pct || 0) >= 0 ? '+' : ''}${(fc.vwap_distance_pct || 0).toFixed(3)}%`}
          valueColor={(fc.vwap_distance_pct || 0) >= 0 ? colors.green : colors.red}
        />
      </View>

      {/* Support / Resistance */}
      <View style={[card, { marginHorizontal: 16 }]}>
        <SectionTitle text="Pivot Point Levels" />
        <Row label="Pivot Point (PP)" value={fc.pivot_point ? `$${fc.pivot_point.toLocaleString('en', { maximumFractionDigits: 0 })}` : 'N/A'} />
        {(fc.resistance_levels || []).map((r, i) => (
          <Row key={`r${i}`}
            label={`Resistance R${i + 1}`}
            value={`$${r.toLocaleString('en', { maximumFractionDigits: 0 })}`}
            valueColor={colors.red}
          />
        ))}
        {(fc.support_levels || []).map((s, i) => (
          <Row key={`s${i}`}
            label={`Support S${i + 1}`}
            value={`$${s.toLocaleString('en', { maximumFractionDigits: 0 })}`}
            valueColor={colors.green}
          />
        ))}
      </View>

      {/* Brokerage Analysis */}
      <View style={[card, { marginHorizontal: 16 }]}>
        <SectionTitle text="Brokerage Cost Analysis" />
        <Row label="Taker Fee (per side)" value={`${(fc.taker_fee_pct || 0).toFixed(3)}%`} />
        <Row label="Leverage" value={`${fc.leverage || 5}×`} />
        <Row
          label="Round-trip fee (of margin)"
          value={`${(fc.round_trip_fee_pct || 0).toFixed(2)}%`}
          valueColor={colors.yellow}
          sub="taker × 2 × leverage"
        />
        <Row
          label="Break-even move needed"
          value={`≥ ${(fc.breakeven_move_pct || 0).toFixed(2)}%`}
          valueColor={colors.yellow}
          sub="Min TP distance to cover fees"
        />
        <View style={styles.warnBox}>
          <Text style={styles.warnText}>
            Net R:R must be ≥ 1.5 after deducting {(fc.round_trip_fee_pct || 0).toFixed(2)}% fee cost
            from both reward and risk.
          </Text>
        </View>
      </View>

      <View style={{ height: 24 }} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: colors.bg },
  loadingText: { color: colors.text2, marginTop: 12, fontSize: 13 },
  cardTitle: { fontSize: 11, color: colors.text3, textTransform: 'uppercase', letterSpacing: 1.5, fontWeight: '600', marginBottom: 12 },
  sectionTitle: { fontSize: 11, color: colors.text3, textTransform: 'uppercase', letterSpacing: 1.5, fontWeight: '600', marginBottom: 10 },
  priceRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' },
  tinyLabel: { fontSize: 9, color: colors.text3, letterSpacing: 0.5, marginBottom: 2 },
  bigPrice: { fontSize: 24, fontWeight: '700', color: colors.text },
  ts: { fontSize: 10, color: colors.text3, marginTop: 8 },
  adxRow: { flexDirection: 'row', alignItems: 'baseline', gap: 10, marginBottom: 10 },
  adxNum: { fontSize: 40, fontWeight: '700' },
  adxLabel: { fontSize: 14, fontWeight: '700' },
  barTrack: { height: 10, backgroundColor: colors.bg3, borderRadius: 5, overflow: 'hidden', marginBottom: 6, position: 'relative' },
  barFill: { height: '100%', borderRadius: 5 },
  marker: { position: 'absolute', top: 0, bottom: 0, width: 1, backgroundColor: colors.border },
  barLabels: { flexDirection: 'row', justifyContent: 'space-between' },
  barLabel: { fontSize: 9, color: colors.text3 },
  diRow: { flexDirection: 'row', gap: 8 },
  diBox: { flex: 1, alignItems: 'center', padding: 8, backgroundColor: colors.bg3, borderRadius: 8 },
  diVal: { fontSize: 18, fontWeight: '700', marginTop: 2 },
  regimeRow: { flexDirection: 'row', gap: 8, marginBottom: 12 },
  regimeChip: { flex: 1, padding: 10, borderRadius: 8, borderWidth: 1, borderColor: colors.border, alignItems: 'center' },
  regimeText: { fontSize: 11, fontWeight: '700', color: colors.text3 },
  tableRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 7, borderBottomWidth: 1, borderBottomColor: colors.border },
  tableLabel: { fontSize: 12, color: colors.text2 },
  tableVal: { fontSize: 13, fontWeight: '600', color: colors.text },
  tableSub: { fontSize: 10, color: colors.text3, textAlign: 'right' },
  forecastPrices: { flexDirection: 'row', gap: 8, marginTop: 10 },
  fpBox: { flex: 1, padding: 10, backgroundColor: colors.bg3, borderRadius: 8, alignItems: 'center' },
  fpVal: { fontSize: 14, fontWeight: '700', marginTop: 3 },
  warnBox: { marginTop: 10, backgroundColor: 'rgba(245,158,11,.08)', borderRadius: 8, padding: 10, borderWidth: 1, borderColor: colors.yellow + '44' },
  warnText: { color: colors.yellow, fontSize: 11, lineHeight: 16 },
});
