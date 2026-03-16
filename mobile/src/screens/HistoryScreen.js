import React, { useState, useCallback } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity,
  StyleSheet, ActivityIndicator, RefreshControl,
} from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import api from '../services/api';

export default function HistoryScreen() {
  const [tab, setTab]           = useState('trades');
  const [trades, setTrades]     = useState(null);
  const [decisions, setDecisions] = useState(null);
  const [equity, setEquity]     = useState(null);
  const [loading, setLoading]   = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async (isRefresh = false) => {
    isRefresh ? setRefreshing(true) : setLoading(true);
    try {
      const [t, d, e] = await Promise.all([
        api.getHistoryTrades(50),
        api.getHistoryDecisions(50),
        api.getHistoryEquity(100),
      ]);
      setTrades(t);
      setDecisions(d);
      setEquity(e);
    } catch (_) {
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const onRefresh = () => load(true);

  return (
    <ScrollView
      style={styles.container}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#7c7cff" />}
    >
      <Text style={styles.title}>History</Text>

      {/* ── Tab bar ─────────────────────────────────────── */}
      <View style={styles.tabBar}>
        {['trades', 'decisions', 'equity'].map(t => (
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

      {loading && <ActivityIndicator color="#7c7cff" style={{ marginTop: 40 }} />}

      {!loading && tab === 'trades'    && <TradesTab    data={trades} />}
      {!loading && tab === 'decisions' && <DecisionsTab data={decisions} />}
      {!loading && tab === 'equity'    && <EquityTab    data={equity} />}
    </ScrollView>
  );
}

/* ── Trades Tab ──────────────────────────────────────── */
function TradesTab({ data }) {
  if (!data) return <Empty message="No trade history yet." />;
  const s = data.stats || {};
  const trades = data.trades || [];

  return (
    <>
      {/* Stats summary */}
      <View style={styles.card}>
        <Text style={styles.sectionTitle}>Trade Statistics</Text>
        <View style={styles.statsGrid}>
          <StatBox label="Total Trades"  value={s.total_trades  ?? 0} />
          <StatBox label="Win Rate"      value={`${(s.win_rate_pct ?? 0).toFixed(1)}%`}
                   color={(s.win_rate_pct ?? 0) >= 50 ? '#00c853' : '#ff5252'} />
          <StatBox label="Total PnL"     value={`$${(s.total_pnl_usd ?? 0).toFixed(2)}`}
                   color={(s.total_pnl_usd ?? 0) >= 0 ? '#00c853' : '#ff5252'} />
          <StatBox label="Total Fees"    value={`$${(s.total_fees_usd ?? 0).toFixed(2)}`} color="#ffd740" />
          <StatBox label="Best Trade"    value={`$${(s.best_trade_usd ?? 0).toFixed(2)}`}  color="#00c853" />
          <StatBox label="Worst Trade"   value={`$${(s.worst_trade_usd ?? 0).toFixed(2)}`} color="#ff5252" />
        </View>
      </View>

      {/* Trade list */}
      <View style={styles.card}>
        <Text style={styles.sectionTitle}>
          Recent Trades ({data.total ?? 0})
        </Text>
        {trades.length === 0
          ? <Text style={styles.empty}>No trades recorded yet.</Text>
          : trades.map((t, i) => <TradeRow key={i} trade={t} />)
        }
      </View>
    </>
  );
}

function TradeRow({ trade: t }) {
  const win  = (t.pnl_usd ?? 0) >= 0;
  const side = (t.side || '').toUpperCase();
  return (
    <View style={[styles.tradeRow, win ? styles.tradeWin : styles.tradeLoss]}>
      <View style={{ flex: 1 }}>
        <View style={styles.row}>
          <Text style={styles.tradeSide}>{side}</Text>
          <Text style={styles.tradeSymbol}>{t.symbol}</Text>
          {t.dry_run ? <View style={styles.dryBadge}><Text style={styles.dryText}>PAPER</Text></View> : null}
        </View>
        <Text style={styles.tradeMeta}>
          @{t.entry_price ? t.entry_price.toFixed(2) : '—'}
          {t.exit_price ? ` → ${t.exit_price.toFixed(2)}` : ''}
          {t.exit_reason ? ` · ${t.exit_reason.toUpperCase()}` : ''}
        </Text>
        <Text style={styles.tradeMeta}>{t.ts ? t.ts.slice(0, 16).replace('T', ' ') : ''}</Text>
      </View>
      <View style={styles.tradeRight}>
        {t.pnl_usd != null && (
          <Text style={[styles.tradePnl, { color: win ? '#00c853' : '#ff5252' }]}>
            {win ? '+' : ''}{t.pnl_usd.toFixed(2)}
          </Text>
        )}
        {t.pnl_pct != null && (
          <Text style={[styles.tradePct, { color: win ? '#00c853' : '#ff5252' }]}>
            {win ? '+' : ''}{t.pnl_pct.toFixed(2)}%
          </Text>
        )}
      </View>
    </View>
  );
}

/* ── Decisions Tab ───────────────────────────────────── */
function DecisionsTab({ data }) {
  if (!data) return <Empty message="No decisions recorded yet." />;
  const counts    = data.action_counts || {};
  const decisions = data.decisions || [];
  const total     = data.total ?? 0;

  return (
    <>
      {/* Action breakdown */}
      <View style={styles.card}>
        <Text style={styles.sectionTitle}>Decision Breakdown ({total})</Text>
        <View style={styles.statsGrid}>
          {Object.entries(counts).map(([action, n]) => (
            <StatBox key={action} label={action}
              value={n}
              color={action === 'BUY' ? '#00c853' : action === 'SELL' ? '#ff5252' : '#aaa'}
            />
          ))}
        </View>
      </View>

      {/* Decision list */}
      <View style={styles.card}>
        <Text style={styles.sectionTitle}>Recent Decisions</Text>
        {decisions.length === 0
          ? <Text style={styles.empty}>No decisions recorded yet.</Text>
          : decisions.map((d, i) => <DecisionRow key={i} dec={d} />)
        }
      </View>
    </>
  );
}

function DecisionRow({ dec: d }) {
  const actionColor = d.action === 'BUY' ? '#00c853'
    : d.action === 'SELL' ? '#ff5252' : '#ffd740';
  return (
    <View style={styles.decisionRow}>
      <View style={[styles.actionBadge, { borderColor: actionColor }]}>
        <Text style={[styles.actionText, { color: actionColor }]}>{d.action}</Text>
      </View>
      <View style={{ flex: 1, marginLeft: 8 }}>
        <View style={styles.row}>
          <Text style={styles.decSymbol}>{d.symbol}</Text>
          <Text style={styles.decMeta}> · Cycle {d.cycle}</Text>
          {d.dry_run ? <View style={styles.dryBadge}><Text style={styles.dryText}>PAPER</Text></View> : null}
        </View>
        {d.reasoning
          ? <Text style={styles.decReasoning} numberOfLines={2}>{d.reasoning}</Text>
          : null
        }
        <View style={styles.decStats}>
          {d.confidence  != null && <DecStat label="Conf"    value={`${(d.confidence * 100).toFixed(0)}%`} />}
          {d.signal_score != null && <DecStat label="Signal" value={d.signal_score.toFixed(2)} />}
          {d.adx         != null && <DecStat label="ADX"    value={d.adx.toFixed(1)} />}
          {d.market_regime && <DecStat label="Regime" value={d.market_regime} />}
        </View>
        <Text style={styles.decTs}>{d.ts ? d.ts.slice(0, 16).replace('T', ' ') : ''}</Text>
      </View>
    </View>
  );
}

function DecStat({ label, value }) {
  return (
    <View style={styles.decStatItem}>
      <Text style={styles.decStatLabel}>{label}</Text>
      <Text style={styles.decStatValue}>{value}</Text>
    </View>
  );
}

/* ── Equity Tab ──────────────────────────────────────── */
function EquityTab({ data }) {
  if (!data) return <Empty message="No equity history yet." />;
  const snapshots = data.snapshots || [];
  const latest    = data.latest;

  // ASCII sparkline from snapshots (reversed — oldest first for display)
  const pts    = [...snapshots].reverse().map(s => s.balance);
  const minV   = Math.min(...pts);
  const maxV   = Math.max(...pts);
  const range  = maxV - minV || 1;
  const HEIGHT = 6;
  const WIDTH  = Math.min(pts.length, 50);
  const sampled = pts.filter((_, i) => i % Math.max(1, Math.floor(pts.length / WIDTH)) === 0).slice(0, WIDTH);
  const rows = Array.from({ length: HEIGHT }, (_, row) => {
    const threshold = maxV - (row / HEIGHT) * range;
    return sampled.map(v => (v >= threshold ? '█' : ' ')).join('');
  });

  return (
    <View style={styles.card}>
      <Text style={styles.sectionTitle}>Equity History ({data.total ?? 0} snapshots)</Text>

      {latest && (
        <View style={styles.equityLatest}>
          <EquityStatRow label="Latest Balance"  value={`$${latest.balance.toFixed(2)}`} />
          <EquityStatRow label="Total Equity"    value={`$${latest.total_equity.toFixed(2)}`} />
          <EquityStatRow label="Unrealized PnL"  value={`$${latest.unrealized_pnl.toFixed(2)}`}
                         color={(latest.unrealized_pnl ?? 0) >= 0 ? '#00c853' : '#ff5252'} />
          <EquityStatRow label="Open Positions"  value={latest.open_positions} />
          <EquityStatRow label="Last Updated"
                         value={latest.ts ? latest.ts.slice(0, 16).replace('T', ' ') : '—'} />
        </View>
      )}

      {pts.length >= 2 && (
        <>
          <View style={styles.divider} />
          <Text style={styles.chartMax}>${maxV.toFixed(0)}</Text>
          <View style={styles.chart}>
            {rows.map((r, i) => <Text key={i} style={styles.chartRow}>{r}</Text>)}
          </View>
          <Text style={styles.chartMin}>${minV.toFixed(0)}</Text>
        </>
      )}

      {snapshots.length === 0 && (
        <Text style={styles.empty}>No equity snapshots yet. Run the bot to record history.</Text>
      )}
    </View>
  );
}

function EquityStatRow({ label, value, color }) {
  return (
    <View style={styles.metricRow}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={[styles.metricValue, color ? { color } : {}]}>{value}</Text>
    </View>
  );
}

/* ── Shared ──────────────────────────────────────────── */
function StatBox({ label, value, color }) {
  return (
    <View style={styles.statBox}>
      <Text style={[styles.statValue, color ? { color } : {}]}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

function Empty({ message }) {
  return <View style={styles.card}><Text style={styles.empty}>{message}</Text></View>;
}

/* ── Styles ──────────────────────────────────────────── */
const styles = StyleSheet.create({
  container:       { flex: 1, backgroundColor: '#0a0a1a', padding: 16 },
  title:           { color: '#e0e0ff', fontSize: 22, fontWeight: 'bold', marginBottom: 16 },
  card:            { backgroundColor: '#131328', borderRadius: 12, padding: 16, marginBottom: 12 },
  sectionTitle:    { color: '#7c7cff', fontSize: 15, fontWeight: '700', marginBottom: 12 },
  empty:           { color: '#555', textAlign: 'center', paddingVertical: 20 },
  row:             { flexDirection: 'row', alignItems: 'center', gap: 6 },
  divider:         { height: 1, backgroundColor: '#1e1e3a', marginVertical: 10 },

  tabBar:          { flexDirection: 'row', gap: 8, marginBottom: 12 },
  tabBtn:          { flex: 1, paddingVertical: 10, borderRadius: 8, backgroundColor: '#131328', alignItems: 'center' },
  tabBtnActive:    { backgroundColor: '#7c7cff' },
  tabText:         { color: '#aaa', fontSize: 13, fontWeight: '600' },
  tabTextActive:   { color: '#fff' },

  statsGrid:       { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  statBox:         { backgroundColor: '#1e1e3a', borderRadius: 8, padding: 10, minWidth: '30%', flex: 1, alignItems: 'center' },
  statValue:       { color: '#e0e0ff', fontSize: 16, fontWeight: '700' },
  statLabel:       { color: '#888', fontSize: 10, marginTop: 2 },

  tradeRow:        { flexDirection: 'row', padding: 10, borderRadius: 8, marginBottom: 6, borderLeftWidth: 3 },
  tradeWin:        { backgroundColor: '#0d1f0d', borderLeftColor: '#00c853' },
  tradeLoss:       { backgroundColor: '#1f0d0d', borderLeftColor: '#ff5252' },
  tradeSide:       { color: '#e0e0ff', fontSize: 12, fontWeight: '700' },
  tradeSymbol:     { color: '#7c7cff', fontSize: 12, fontWeight: '700' },
  tradeMeta:       { color: '#888', fontSize: 10, marginTop: 2 },
  tradeRight:      { alignItems: 'flex-end' },
  tradePnl:        { fontSize: 14, fontWeight: '700' },
  tradePct:        { fontSize: 10, marginTop: 2 },

  dryBadge:        { backgroundColor: '#2a2a1a', borderRadius: 4, paddingHorizontal: 4, paddingVertical: 1 },
  dryText:         { color: '#ffd740', fontSize: 9, fontWeight: '700' },

  decisionRow:     { flexDirection: 'row', paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: '#1e1e3a' },
  actionBadge:     { borderWidth: 1.5, borderRadius: 6, paddingHorizontal: 8, paddingVertical: 4, alignSelf: 'flex-start', minWidth: 52, alignItems: 'center' },
  actionText:      { fontSize: 12, fontWeight: '700' },
  decSymbol:       { color: '#e0e0ff', fontSize: 13, fontWeight: '700' },
  decMeta:         { color: '#888', fontSize: 11 },
  decReasoning:    { color: '#aaa', fontSize: 11, marginTop: 3, lineHeight: 16 },
  decStats:        { flexDirection: 'row', gap: 8, marginTop: 4 },
  decStatItem:     { alignItems: 'center' },
  decStatLabel:    { color: '#555', fontSize: 9 },
  decStatValue:    { color: '#e0e0ff', fontSize: 11, fontWeight: '600' },
  decTs:           { color: '#555', fontSize: 9, marginTop: 4 },

  equityLatest:    { marginBottom: 4 },
  metricRow:       { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 5 },
  metricLabel:     { color: '#aaa', fontSize: 13 },
  metricValue:     { color: '#e0e0ff', fontSize: 13, fontWeight: '600' },

  chart:           { backgroundColor: '#0a0a1a', borderRadius: 6, padding: 4, marginVertical: 2 },
  chartRow:        { color: '#7c7cff', fontSize: 8, fontFamily: 'monospace', lineHeight: 9 },
  chartMax:        { color: '#666', fontSize: 9, textAlign: 'right' },
  chartMin:        { color: '#666', fontSize: 9 },
});
