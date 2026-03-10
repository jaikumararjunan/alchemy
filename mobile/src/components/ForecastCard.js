/**
 * ForecastCard — compact market forecast widget for DashboardScreen.
 * Shows: ADX badge, regime chip, trend direction, forecast bias, breakeven.
 */
import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { colors, card } from '../theme';

const REGIME_COLOR = {
  trending: colors.green,
  ranging:  colors.yellow,
  volatile: colors.red,
};

const BIAS_COLOR = {
  bullish: colors.green,
  bearish: colors.red,
  neutral: colors.text2,
};

const STRENGTH_COLOR = {
  very_strong: colors.green,
  strong:      colors.green,
  moderate:    colors.yellow,
  weak:        colors.text2,
  none:        colors.text3,
};

export default function ForecastCard({ forecast = {} }) {
  const {
    adx = 0,
    trend_direction = 'neutral',
    trend_strength = 'none',
    market_regime = 'ranging',
    regime_confidence = 0,
    forecast_bias = 'neutral',
    forecast_price_3,
    regression_r2 = 0,
    vwap,
    vwap_position = 'at',
    vwap_distance_pct = 0,
    support_levels = [],
    resistance_levels = [],
    breakeven_move_pct = 0,
    forecast_score = 0,
    current_price = 0,
  } = forecast;

  const scoreColor = forecast_score > 0.1 ? colors.green
                   : forecast_score < -0.1 ? colors.red
                   : colors.text2;

  const adxColor = adx >= 40 ? colors.green
                 : adx >= 25 ? colors.yellow
                 : colors.text3;

  return (
    <View style={card}>
      <Text style={styles.title}>Market Forecast</Text>

      {/* Top row: ADX + regime */}
      <View style={styles.row}>
        <View style={styles.metricBox}>
          <Text style={styles.metricLabel}>ADX</Text>
          <Text style={[styles.metricVal, { color: adxColor }]}>{adx.toFixed(1)}</Text>
          <Text style={[styles.chip, { color: STRENGTH_COLOR[trend_strength] }]}>
            {trend_strength.replace('_', ' ').toUpperCase()}
          </Text>
        </View>

        <View style={styles.metricBox}>
          <Text style={styles.metricLabel}>REGIME</Text>
          <Text style={[styles.metricVal, { color: REGIME_COLOR[market_regime] }]}>
            {market_regime.toUpperCase()}
          </Text>
          <Text style={styles.conf}>{(regime_confidence * 100).toFixed(0)}% conf</Text>
        </View>

        <View style={styles.metricBox}>
          <Text style={styles.metricLabel}>FORECAST</Text>
          <Text style={[styles.metricVal, { color: BIAS_COLOR[forecast_bias] }]}>
            {forecast_bias.toUpperCase()}
          </Text>
          <Text style={styles.conf}>R²={regression_r2.toFixed(2)}</Text>
        </View>

        <View style={styles.metricBox}>
          <Text style={styles.metricLabel}>SCORE</Text>
          <Text style={[styles.metricVal, { color: scoreColor }]}>
            {forecast_score >= 0 ? '+' : ''}{forecast_score.toFixed(3)}
          </Text>
          <Text style={styles.conf}>{trend_direction.toUpperCase()}</Text>
        </View>
      </View>

      {/* Price targets row */}
      {forecast_price_3 && current_price > 0 && (
        <View style={[styles.row, { marginTop: 8 }]}>
          <View style={styles.levelItem}>
            <Text style={styles.metricLabel}>3-BAR TARGET</Text>
            <Text style={[styles.levelVal, { color: BIAS_COLOR[forecast_bias] }]}>
              ${forecast_price_3.toLocaleString('en', { maximumFractionDigits: 0 })}
            </Text>
          </View>
          {vwap && (
            <View style={styles.levelItem}>
              <Text style={styles.metricLabel}>VWAP</Text>
              <Text style={[styles.levelVal, {
                color: vwap_position === 'above' ? colors.green
                     : vwap_position === 'below' ? colors.red
                     : colors.text2,
              }]}>
                ${vwap.toLocaleString('en', { maximumFractionDigits: 0 })}
                {'  '}<Text style={styles.conf}>{vwap_position.toUpperCase()}</Text>
              </Text>
            </View>
          )}
          <View style={styles.levelItem}>
            <Text style={styles.metricLabel}>BREAK-EVEN</Text>
            <Text style={[styles.levelVal, { color: colors.yellow }]}>
              {breakeven_move_pct.toFixed(2)}%
            </Text>
          </View>
        </View>
      )}

      {/* Support / Resistance */}
      {(resistance_levels.length > 0 || support_levels.length > 0) && (
        <View style={[styles.row, { marginTop: 8 }]}>
          {resistance_levels.slice(0, 2).map((r, i) => (
            <View key={`r${i}`} style={styles.levelItem}>
              <Text style={styles.metricLabel}>R{i + 1}</Text>
              <Text style={[styles.levelVal, { color: colors.red }]}>
                ${r.toLocaleString('en', { maximumFractionDigits: 0 })}
              </Text>
            </View>
          ))}
          {support_levels.slice(0, 2).map((s, i) => (
            <View key={`s${i}`} style={styles.levelItem}>
              <Text style={styles.metricLabel}>S{i + 1}</Text>
              <Text style={[styles.levelVal, { color: colors.green }]}>
                ${s.toLocaleString('en', { maximumFractionDigits: 0 })}
              </Text>
            </View>
          ))}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  title: {
    fontSize: 11, color: colors.text3, textTransform: 'uppercase',
    letterSpacing: 1.5, fontWeight: '600', marginBottom: 12,
  },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: 4 },
  metricBox: { flex: 1, minWidth: 70, alignItems: 'center', padding: 6, backgroundColor: colors.bg3, borderRadius: 8 },
  metricLabel: { fontSize: 9, color: colors.text3, marginBottom: 3, letterSpacing: 0.5 },
  metricVal: { fontSize: 14, fontWeight: '700', color: colors.text },
  chip: { fontSize: 9, fontWeight: '700', marginTop: 2 },
  conf: { fontSize: 9, color: colors.text3, marginTop: 2 },
  levelItem: { flex: 1, minWidth: 70 },
  levelVal: { fontSize: 13, fontWeight: '600', color: colors.text },
});
