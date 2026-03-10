import React, { useState, useCallback } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, TextInput,
  StyleSheet, ActivityIndicator, Alert,
} from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import api from '../services/api';

const TIMEFRAMES = ['5m', '15m', '1h', '4h', '1d'];

export default function BacktestScreen() {
  const [defaults, setDefaults] = useState(null);
  const [form, setForm] = useState({
    symbol: 'BTCUSD',
    timeframe: '1h',
    initial_balance: '10000',
    position_size_usd: '500',
    stop_loss_pct: '2.0',
    take_profit_pct: '4.5',
    leverage: '5',
    candle_count: '500',
  });
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState(null);
  const [tab, setTab] = useState('metrics'); // 'metrics' | 'trades' | 'equity'

  useFocusEffect(
    useCallback(() => {
      api.get('/api/backtest/defaults')
        .then(d => {
          setDefaults(d);
          setForm(f => ({
            ...f,
            symbol: d.symbol || f.symbol,
            position_size_usd: String(d.position_size_usd || f.position_size_usd),
            stop_loss_pct: String(d.stop_loss_pct || f.stop_loss_pct),
            take_profit_pct: String(d.take_profit_pct || f.take_profit_pct),
            leverage: String(d.leverage || f.leverage),
          }));
        })
        .catch(() => {});
    }, [])
  );

  const runBacktest = async () => {
    setRunning(true);
    setResult(null);
    try {
      const body = {
        symbol: form.symbol,
        timeframe: form.timeframe,
        initial_balance: parseFloat(form.initial_balance) || 10000,
        position_size_usd: parseFloat(form.position_size_usd) || 500,
        stop_loss_pct: parseFloat(form.stop_loss_pct) || 2.0,
        take_profit_pct: parseFloat(form.take_profit_pct) || 4.5,
        leverage: parseInt(form.leverage) || 5,
        candle_count: parseInt(form.candle_count) || 500,
      };
      const data = await api.post('/api/backtest/run', body);
      setResult(data);
      setTab('metrics');
    } catch (e) {
      Alert.alert('Backtest Error', e.message);
    } finally {
      setRunning(false);
    }
  };

  const m = result?.metrics;

  return (
    <ScrollView style={styles.container} keyboardShouldPersistTaps="handled">
      <Text style={styles.title}>Backtester</Text>

      {/* ── Config Form ─────────────────────────────────── */}
      <View style={styles.card}>
        <Text style={styles.sectionTitle}>Configuration</Text>

        <Text style={styles.label}>Symbol</Text>
        <TextInput
          style={styles.input}
          value={form.symbol}
          onChangeText={v => setForm(f => ({ ...f, symbol: v.toUpperCase() }))}
          placeholder="BTCUSD"
          autoCapitalize="characters"
        />

        <Text style={styles.label}>Timeframe</Text>
        <View style={styles.row}>
          {TIMEFRAMES.map(tf => (
            <TouchableOpacity
              key={tf}
              style={[styles.tfBtn, form.timeframe === tf && styles.tfBtnActive]}
              onPress={() => setForm(f => ({ ...f, timeframe: tf }))}
            >
              <Text style={[styles.tfBtnText, form.timeframe === tf && styles.tfBtnTextActive]}>
                {tf}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        <View style={styles.row}>
          <View style={styles.halfCol}>
            <Text style={styles.label}>Balance ($)</Text>
            <TextInput
              style={styles.input}
              value={form.initial_balance}
              onChangeText={v => setForm(f => ({ ...f, initial_balance: v }))}
              keyboardType="numeric"
            />
          </View>
          <View style={styles.halfCol}>
            <Text style={styles.label}>Position ($)</Text>
            <TextInput
              style={styles.input}
              value={form.position_size_usd}
              onChangeText={v => setForm(f => ({ ...f, position_size_usd: v }))}
              keyboardType="numeric"
            />
          </View>
        </View>

        <View style={styles.row}>
          <View style={styles.halfCol}>
            <Text style={styles.label}>SL %</Text>
            <TextInput
              style={styles.input}
              value={form.stop_loss_pct}
              onChangeText={v => setForm(f => ({ ...f, stop_loss_pct: v }))}
              keyboardType="numeric"
            />
          </View>
          <View style={styles.halfCol}>
            <Text style={styles.label}>TP %</Text>
            <TextInput
              style={styles.input}
              value={form.take_profit_pct}
              onChangeText={v => setForm(f => ({ ...f, take_profit_pct: v }))}
              keyboardType="numeric"
            />
          </View>
        </View>

        <View style={styles.row}>
          <View style={styles.halfCol}>
            <Text style={styles.label}>Leverage</Text>
            <TextInput
              style={styles.input}
              value={form.leverage}
              onChangeText={v => setForm(f => ({ ...f, leverage: v }))}
              keyboardType="numeric"
            />
          </View>
          <View style={styles.halfCol}>
            <Text style={styles.label}>Candles</Text>
            <TextInput
              style={styles.input}
              value={form.candle_count}
              onChangeText={v => setForm(f => ({ ...f, candle_count: v }))}
              keyboardType="numeric"
            />
          </View>
        </View>

        <TouchableOpacity
          style={[styles.runBtn, running && styles.runBtnDisabled]}
          onPress={runBacktest}
          disabled={running}
        >
          {running
            ? <ActivityIndicator color="#fff" />
            : <Text style={styles.runBtnText}>Run Backtest</Text>
          }
        </TouchableOpacity>
      </View>

      {/* ── Results ─────────────────────────────────────── */}
      {result && (
        <>
          <View style={styles.summaryCard}>
            <Text style={styles.summaryText}>{result.summary}</Text>
          </View>

          {/* Tab bar */}
          <View style={styles.tabBar}>
            {['metrics', 'trades', 'equity'].map(t => (
              <TouchableOpacity
                key={t}
                style={[styles.tabBtn, tab === t && styles.tabBtnActive]}
                onPress={() => setTab(t)}
              >
                <Text style={[styles.tabText, tab === t && styles.tabTextActive]}>
                  {t.charAt(0).toUpperCase() + t.slice(1)}
                </Text>
              </TouchableOpacity>
            ))}
          </View>

          {tab === 'metrics' && m && <MetricsTab m={m} result={result} />}
          {tab === 'trades'  && <TradesTab trades={result.trades} />}
          {tab === 'equity'  && <EquityTab curve={result.equity_curve} initial={result.initial_balance} />}
        </>
      )}
    </ScrollView>
  );
}

/* ── Metrics Tab ─────────────────────────────────────── */
function MetricsTab({ m, result }) {
  const retColor = m.total_return_pct >= 0 ? '#00c853' : '#ff5252';
  return (
    <View style={styles.card}>
      <Text style={styles.sectionTitle}>Performance Metrics</Text>
      <MetaRow label="Symbol" value={result.symbol} />
      <MetaRow label="Candles" value={`${result.total_bars} (${m.trading_days}d)`} />
      <MetaRow label="Trades" value={result.trades.length} />
      <View style={styles.divider} />
      <MetricRow label="Total Return"       value={`${m.total_return_pct > 0 ? '+' : ''}${m.total_return_pct}%`}  color={retColor} />
      <MetricRow label="Ann. Return"        value={`${m.annualized_return_pct > 0 ? '+' : ''}${m.annualized_return_pct}%`} color={retColor} />
      <MetricRow label="Final Balance"      value={`$${m.final_balance.toFixed(2)}`} />
      <View style={styles.divider} />
      <MetricRow label="Sharpe Ratio"       value={m.sharpe_ratio.toFixed(3)}  color={m.sharpe_ratio >= 1 ? '#00c853' : m.sharpe_ratio >= 0 ? '#ffd740' : '#ff5252'} />
      <MetricRow label="Sortino Ratio"      value={m.sortino_ratio.toFixed(3)} color={m.sortino_ratio >= 1 ? '#00c853' : '#ffd740'} />
      <MetricRow label="Calmar Ratio"       value={m.calmar_ratio.toFixed(3)} />
      <View style={styles.divider} />
      <MetricRow label="Max Drawdown"       value={`${m.max_drawdown_pct.toFixed(2)}%`} color="#ff5252" />
      <MetricRow label="Max DD ($)"         value={`$${m.max_drawdown_usd.toFixed(2)}`} color="#ff5252" />
      <MetricRow label="Recovery Factor"    value={m.recovery_factor.toFixed(3)} />
      <View style={styles.divider} />
      <MetricRow label="Win Rate"           value={`${m.win_rate_pct.toFixed(1)}%`} color={m.win_rate_pct >= 50 ? '#00c853' : '#ff5252'} />
      <MetricRow label="Profit Factor"      value={m.profit_factor.toFixed(3)}      color={m.profit_factor >= 1.5 ? '#00c853' : m.profit_factor >= 1 ? '#ffd740' : '#ff5252'} />
      <MetricRow label="Expectancy"         value={`$${m.expectancy_usd.toFixed(4)}`} />
      <MetricRow label="Avg Win"            value={`$${m.avg_win_usd.toFixed(4)}`}  color="#00c853" />
      <MetricRow label="Avg Loss"           value={`$${m.avg_loss_usd.toFixed(4)}`} color="#ff5252" />
      <MetricRow label="Best Trade"         value={`$${m.best_trade_usd.toFixed(4)}`}  color="#00c853" />
      <MetricRow label="Worst Trade"        value={`$${m.worst_trade_usd.toFixed(4)}`} color="#ff5252" />
      <View style={styles.divider} />
      <MetricRow label="Max Consec. Wins"   value={m.max_consecutive_wins} />
      <MetricRow label="Max Consec. Losses" value={m.max_consecutive_losses} />
      <MetricRow label="Avg Duration"       value={`${m.avg_trade_duration_bars} bars`} />
    </View>
  );
}

function MetricRow({ label, value, color }) {
  return (
    <View style={styles.metricRow}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={[styles.metricValue, color ? { color } : {}]}>{value}</Text>
    </View>
  );
}

function MetaRow({ label, value }) {
  return (
    <View style={styles.metricRow}>
      <Text style={[styles.metricLabel, { color: '#aaa' }]}>{label}</Text>
      <Text style={[styles.metricValue, { color: '#ccc' }]}>{value}</Text>
    </View>
  );
}

/* ── Trades Tab ─────────────────────────────────────── */
function TradesTab({ trades }) {
  if (!trades || trades.length === 0) {
    return <View style={styles.card}><Text style={styles.empty}>No trades in backtest period.</Text></View>;
  }
  return (
    <View style={styles.card}>
      <Text style={styles.sectionTitle}>Trade Log ({trades.length})</Text>
      {trades.map((t, i) => (
        <View key={i} style={[styles.tradeRow, t.pnl_usd >= 0 ? styles.tradeWin : styles.tradeLoss]}>
          <View style={styles.tradeLeft}>
            <Text style={styles.tradeSide}>{t.side.toUpperCase()} #{i + 1}</Text>
            <Text style={styles.tradeMeta}>
              @{t.entry_price.toFixed(2)} → {t.exit_price.toFixed(2)}
            </Text>
            <Text style={styles.tradeMeta}>
              {t.exit_reason.toUpperCase()} · {t.duration_bars}b
            </Text>
          </View>
          <View style={styles.tradeRight}>
            <Text style={[styles.tradePnl, { color: t.pnl_usd >= 0 ? '#00c853' : '#ff5252' }]}>
              {t.pnl_usd >= 0 ? '+' : ''}{t.pnl_usd.toFixed(2)}
            </Text>
            <Text style={[styles.tradePct, { color: t.pnl_pct >= 0 ? '#00c853' : '#ff5252' }]}>
              {t.pnl_pct >= 0 ? '+' : ''}{t.pnl_pct.toFixed(2)}%
            </Text>
          </View>
        </View>
      ))}
    </View>
  );
}

/* ── Equity Tab ─────────────────────────────────────── */
function EquityTab({ curve, initial }) {
  if (!curve || curve.length === 0) {
    return <View style={styles.card}><Text style={styles.empty}>No equity data.</Text></View>;
  }

  // Show every Nth point for a quick ASCII sparkline
  const step  = Math.max(1, Math.floor(curve.length / 40));
  const pts   = curve.filter((_, i) => i % step === 0);
  const minV  = Math.min(...pts);
  const maxV  = Math.max(...pts);
  const range = maxV - minV || 1;
  const HEIGHT = 8;

  const rows = Array.from({ length: HEIGHT }, (_, row) => {
    const threshold = maxV - (row / HEIGHT) * range;
    return pts.map(v => (v >= threshold ? '█' : ' ')).join('');
  });

  return (
    <View style={styles.card}>
      <Text style={styles.sectionTitle}>Equity Curve</Text>
      <Text style={styles.chartLabel}>${maxV.toFixed(0)}</Text>
      <View style={styles.chart}>
        {rows.map((r, i) => <Text key={i} style={styles.chartRow}>{r}</Text>)}
      </View>
      <Text style={styles.chartLabel}>${minV.toFixed(0)}</Text>
      <View style={styles.divider} />
      <Text style={styles.equityStat}>Start: ${initial.toFixed(2)}</Text>
      <Text style={styles.equityStat}>End: ${curve[curve.length - 1].toFixed(2)}</Text>
      <Text style={styles.equityStat}>Points: {curve.length}</Text>
    </View>
  );
}

/* ── Styles ─────────────────────────────────────────── */
const styles = StyleSheet.create({
  container:      { flex: 1, backgroundColor: '#0a0a1a', padding: 16 },
  title:          { color: '#e0e0ff', fontSize: 22, fontWeight: 'bold', marginBottom: 16 },
  card:           { backgroundColor: '#131328', borderRadius: 12, padding: 16, marginBottom: 12 },
  sectionTitle:   { color: '#7c7cff', fontSize: 15, fontWeight: '700', marginBottom: 12 },
  label:          { color: '#aaa', fontSize: 12, marginTop: 8, marginBottom: 4 },
  input: {
    backgroundColor: '#1e1e3a', color: '#fff', borderRadius: 8,
    paddingHorizontal: 12, paddingVertical: 8, fontSize: 14,
  },
  row:            { flexDirection: 'row', gap: 8 },
  halfCol:        { flex: 1 },
  tfBtn: {
    flex: 1, paddingVertical: 8, borderRadius: 8,
    backgroundColor: '#1e1e3a', alignItems: 'center',
  },
  tfBtnActive:    { backgroundColor: '#7c7cff' },
  tfBtnText:      { color: '#aaa', fontSize: 12, fontWeight: '600' },
  tfBtnTextActive:{ color: '#fff' },
  runBtn: {
    backgroundColor: '#7c7cff', borderRadius: 10,
    paddingVertical: 14, alignItems: 'center', marginTop: 16,
  },
  runBtnDisabled: { opacity: 0.5 },
  runBtnText:     { color: '#fff', fontSize: 16, fontWeight: '700' },

  summaryCard: {
    backgroundColor: '#1a1a2e', borderRadius: 10, padding: 12, marginBottom: 8,
  },
  summaryText:    { color: '#e0e0ff', fontSize: 11, fontFamily: 'monospace' },

  tabBar:         { flexDirection: 'row', gap: 8, marginBottom: 8 },
  tabBtn: {
    flex: 1, paddingVertical: 10, borderRadius: 8,
    backgroundColor: '#131328', alignItems: 'center',
  },
  tabBtnActive:   { backgroundColor: '#7c7cff' },
  tabText:        { color: '#aaa', fontSize: 13, fontWeight: '600' },
  tabTextActive:  { color: '#fff' },

  metricRow:      { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 5 },
  metricLabel:    { color: '#aaa', fontSize: 13 },
  metricValue:    { color: '#e0e0ff', fontSize: 13, fontWeight: '600' },
  divider:        { height: 1, backgroundColor: '#1e1e3a', marginVertical: 8 },

  tradeRow: {
    flexDirection: 'row', justifyContent: 'space-between',
    padding: 10, borderRadius: 8, marginBottom: 6,
    borderLeftWidth: 3,
  },
  tradeWin:       { backgroundColor: '#0d1f0d', borderLeftColor: '#00c853' },
  tradeLoss:      { backgroundColor: '#1f0d0d', borderLeftColor: '#ff5252' },
  tradeLeft:      { flex: 1 },
  tradeRight:     { alignItems: 'flex-end' },
  tradeSide:      { color: '#e0e0ff', fontSize: 13, fontWeight: '700' },
  tradeMeta:      { color: '#888', fontSize: 11, marginTop: 2 },
  tradePnl:       { fontSize: 14, fontWeight: '700' },
  tradePct:       { fontSize: 11, marginTop: 2 },

  chart:          { backgroundColor: '#0a0a1a', borderRadius: 6, padding: 4, marginVertical: 4 },
  chartRow:       { color: '#7c7cff', fontSize: 9, fontFamily: 'monospace', lineHeight: 10 },
  chartLabel:     { color: '#666', fontSize: 10, textAlign: 'right' },
  equityStat:     { color: '#aaa', fontSize: 13, paddingVertical: 2 },
  empty:          { color: '#666', textAlign: 'center', paddingVertical: 20 },
});
