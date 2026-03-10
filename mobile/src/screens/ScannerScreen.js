/**
 * ScannerScreen — scan all contracts and display ranked trading opportunities.
 *
 * Sections:
 *  1. Scan Summary    — total scanned, actionable, duration, market headline
 *  2. Top Opportunities — actionable BUY/SELL cards with suggested allocation
 *  3. Full Ranking    — all contracts colour-coded by signal strength
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, ScrollView, StyleSheet, RefreshControl,
  ActivityIndicator, TouchableOpacity, FlatList,
} from 'react-native';
import { useStore } from '../store/useStore';
import { colors, card } from '../theme';
import api from '../services/api';

const ACTION_COLOR = { BUY: colors.green, SELL: colors.red, HOLD: colors.text3 };
const REGIME_COLOR = { trending: colors.green, ranging: colors.yellow, volatile: colors.red };

function ScoreChip({ score }) {
  const clr = score > 0.15 ? colors.green : score < -0.15 ? colors.red : colors.text3;
  return (
    <View style={[styles.chip, { borderColor: clr + '88', backgroundColor: clr + '18' }]}>
      <Text style={[styles.chipText, { color: clr }]}>
        {score >= 0 ? '+' : ''}{score.toFixed(3)}
      </Text>
    </View>
  );
}

function MiniBar({ value, max = 1.0 }) {
  // value in -1..+1, bar centered at 50%
  const pct    = ((Math.abs(value) / max) * 50);
  const isPos  = value >= 0;
  const clr    = isPos ? colors.green : colors.red;
  return (
    <View style={styles.miniBarTrack}>
      <View style={[styles.miniBarFill, {
        width: `${pct}%`,
        left: isPos ? '50%' : undefined,
        right: !isPos ? '50%' : undefined,
        backgroundColor: clr,
      }]} />
      <View style={styles.miniBarCenter} />
    </View>
  );
}

function OpportunityCard({ item, onPress }) {
  const ac = ACTION_COLOR[item.action] || colors.text2;
  const rc = REGIME_COLOR[item.market_regime] || colors.text2;
  return (
    <TouchableOpacity style={styles.opCard} onPress={() => onPress?.(item)}>
      <View style={styles.opHeader}>
        <View style={styles.opLeft}>
          <Text style={styles.opSymbol}>{item.symbol}</Text>
          <Text style={styles.opPrice}>${item.current_price?.toLocaleString(undefined, { maximumFractionDigits: 4 })}</Text>
        </View>
        <View style={styles.opRight}>
          <View style={[styles.actionBadge, { backgroundColor: ac + '22', borderColor: ac }]}>
            <Text style={[styles.actionText, { color: ac }]}>{item.action}</Text>
          </View>
          <Text style={[styles.regimeBadge, { color: rc }]}>{item.market_regime?.toUpperCase()}</Text>
        </View>
      </View>

      <View style={styles.opScoreRow}>
        <Text style={styles.opScoreLabel}>COMPOSITE</Text>
        <MiniBar value={item.composite_score} />
        <ScoreChip score={item.composite_score} />
      </View>

      <View style={styles.opMetaRow}>
        <View style={styles.opMetaItem}>
          <Text style={styles.opMetaLabel}>ADX</Text>
          <Text style={styles.opMetaVal}>{item.adx?.toFixed(1)}</Text>
        </View>
        <View style={styles.opMetaItem}>
          <Text style={styles.opMetaLabel}>R²</Text>
          <Text style={styles.opMetaVal}>{item.regression_r2?.toFixed(2)}</Text>
        </View>
        <View style={styles.opMetaItem}>
          <Text style={styles.opMetaLabel}>Conf</Text>
          <Text style={styles.opMetaVal}>{(item.confidence * 100).toFixed(0)}%</Text>
        </View>
        <View style={styles.opMetaItem}>
          <Text style={styles.opMetaLabel}>24h</Text>
          <Text style={[styles.opMetaVal, { color: item.change_24h_pct >= 0 ? colors.green : colors.red }]}>
            {item.change_24h_pct >= 0 ? '+' : ''}{item.change_24h_pct?.toFixed(2)}%
          </Text>
        </View>
        <View style={styles.opMetaItem}>
          <Text style={styles.opMetaLabel}>Alloc</Text>
          <Text style={[styles.opMetaVal, { color: colors.accent }]}>
            {item.suggested_size_pct?.toFixed(1)}%
          </Text>
        </View>
      </View>

      <View style={styles.opSubScores}>
        {[
          ['Forecast', item.forecast_score],
          ['Deriv', item.derivatives_score],
          ['Vol', item.volatility_score],
          ['Liquidity', item.volume_score],
        ].map(([lbl, val]) => (
          <View key={lbl} style={styles.opSubItem}>
            <Text style={styles.opSubLabel}>{lbl}</Text>
            <Text style={[styles.opSubVal, {
              color: val > 0 ? colors.green : val < 0 ? colors.red : colors.text3
            }]}>{val >= 0 ? '+' : ''}{val?.toFixed(2)}</Text>
          </View>
        ))}
      </View>

      <Text style={styles.opReasoning}>{item.reasoning}</Text>
    </TouchableOpacity>
  );
}

function RankRow({ item }) {
  const ac  = ACTION_COLOR[item.action] || colors.text3;
  const clr = item.composite_score > 0.15 ? colors.green :
              item.composite_score < -0.15 ? colors.red : colors.text3;
  return (
    <View style={styles.rankRow}>
      <Text style={styles.rankNum}>#{item.rank}</Text>
      <Text style={styles.rankSymbol}>{item.symbol}</Text>
      <MiniBar value={item.composite_score} />
      <Text style={[styles.rankScore, { color: clr }]}>
        {item.composite_score >= 0 ? '+' : ''}{item.composite_score?.toFixed(3)}
      </Text>
      <View style={[styles.rankAction, { borderColor: ac }]}>
        <Text style={[styles.rankActionText, { color: ac }]}>{item.action}</Text>
      </View>
      <Text style={styles.rankConf}>{(item.confidence * 100).toFixed(0)}%</Text>
    </View>
  );
}

export default function ScannerScreen() {
  const { scanResult, setScanResult } = useStore();
  const [loading, setLoading]       = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError]           = useState(null);
  const [showAll, setShowAll]       = useState(false);

  const fetchScan = useCallback(async (isRefresh = false) => {
    if (!isRefresh) setLoading(true);
    setError(null);
    try {
      const result = await api.scanContracts();
      setScanResult(result);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { fetchScan(); }, []);

  const onRefresh = () => { setRefreshing(true); fetchScan(true); };

  if (loading && !scanResult) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color={colors.accent} />
        <Text style={styles.loadingText}>Scanning {'\u2022'} scoring all contracts…</Text>
      </View>
    );
  }

  const sr     = scanResult;
  const ranked = sr?.ranked_contracts || [];
  const top    = sr?.top_opportunities || [];
  const visible = showAll ? ranked : ranked.slice(0, 8);

  return (
    <ScrollView
      style={styles.container}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.accent} />}
    >
      {error ? <Text style={styles.error}>{error}</Text> : null}

      {/* ── Summary ──────────────────────────────────────────────── */}
      {sr && (
        <View style={[card, styles.summaryCard]}>
          <Text style={styles.sectionTitle}>Market Scan</Text>
          <Text style={styles.summaryHeadline}>{sr.market_summary}</Text>
          <View style={styles.summaryStats}>
            <View style={styles.statItem}>
              <Text style={styles.statNum}>{sr.total_scanned}</Text>
              <Text style={styles.statLabel}>Scanned</Text>
            </View>
            <View style={styles.statItem}>
              <Text style={[styles.statNum, { color: colors.accent }]}>{sr.total_actionable}</Text>
              <Text style={styles.statLabel}>Actionable</Text>
            </View>
            <View style={styles.statItem}>
              <Text style={styles.statNum}>{top.length}</Text>
              <Text style={styles.statLabel}>Top Picks</Text>
            </View>
            <View style={styles.statItem}>
              <Text style={styles.statNum}>{sr.scan_duration_seconds?.toFixed(1)}s</Text>
              <Text style={styles.statLabel}>Scan Time</Text>
            </View>
          </View>
        </View>
      )}

      {/* ── Top Opportunities ────────────────────────────────────── */}
      {top.length > 0 && (
        <View style={card}>
          <Text style={styles.sectionTitle}>Top Opportunities</Text>
          {top.map((item) => (
            <OpportunityCard key={item.symbol} item={item} />
          ))}
        </View>
      )}

      {/* ── Full Ranking ─────────────────────────────────────────── */}
      {ranked.length > 0 && (
        <View style={card}>
          <Text style={styles.sectionTitle}>All Contracts Ranked</Text>
          <View style={styles.rankHeader}>
            <Text style={[styles.rankNum, styles.rankHdr]}>#</Text>
            <Text style={[styles.rankSymbol, styles.rankHdr]}>Symbol</Text>
            <Text style={[{ flex: 1 }, styles.rankHdr]}>Score</Text>
            <Text style={[styles.rankScore, styles.rankHdr]}>Val</Text>
            <Text style={[styles.rankAction, styles.rankHdr]}>Sig</Text>
            <Text style={[styles.rankConf, styles.rankHdr]}>Conf</Text>
          </View>
          {visible.map((item) => <RankRow key={item.symbol} item={item} />)}
          {ranked.length > 8 && (
            <TouchableOpacity
              style={styles.showMoreBtn}
              onPress={() => setShowAll(v => !v)}
            >
              <Text style={styles.showMoreText}>
                {showAll ? 'Show less' : `Show all ${ranked.length} contracts`}
              </Text>
            </TouchableOpacity>
          )}
        </View>
      )}

      {!sr && !loading && (
        <Text style={styles.emptyText}>Pull down to scan all contracts.</Text>
      )}
      <View style={{ height: 32 }} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container:      { flex: 1, backgroundColor: colors.bg, padding: 12 },
  center:         { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: colors.bg },
  loadingText:    { color: colors.text2, marginTop: 12, fontSize: 13 },
  error:          { color: colors.red, padding: 12, textAlign: 'center' },
  emptyText:      { color: colors.text3, textAlign: 'center', marginTop: 40, fontSize: 13 },
  sectionTitle:   { color: colors.accent, fontSize: 13, fontWeight: '700', letterSpacing: 1.2,
                    textTransform: 'uppercase', marginBottom: 10 },
  summaryCard:    {},
  summaryHeadline:{ color: colors.text2, fontSize: 12, marginBottom: 12, lineHeight: 17 },
  summaryStats:   { flexDirection: 'row', justifyContent: 'space-around' },
  statItem:       { alignItems: 'center' },
  statNum:        { color: colors.text, fontSize: 20, fontWeight: '700' },
  statLabel:      { color: colors.text3, fontSize: 10, marginTop: 2 },
  // Opportunity card
  opCard:         { backgroundColor: colors.bg3, borderRadius: 10, padding: 12,
                    marginBottom: 10, borderWidth: 1, borderColor: colors.border },
  opHeader:       { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 8 },
  opLeft:         {},
  opRight:        { alignItems: 'flex-end' },
  opSymbol:       { color: colors.text, fontSize: 16, fontWeight: '700' },
  opPrice:        { color: colors.text3, fontSize: 11, marginTop: 2 },
  actionBadge:    { paddingHorizontal: 10, paddingVertical: 3, borderRadius: 6,
                    borderWidth: 1, marginBottom: 4 },
  actionText:     { fontSize: 12, fontWeight: '700', letterSpacing: 0.8 },
  regimeBadge:    { fontSize: 10, fontWeight: '600', letterSpacing: 0.5 },
  opScoreRow:     { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 },
  opScoreLabel:   { color: colors.text3, fontSize: 10, width: 64 },
  chip:           { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 5, borderWidth: 1 },
  chipText:       { fontSize: 12, fontWeight: '700' },
  opMetaRow:      { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 8 },
  opMetaItem:     { alignItems: 'center' },
  opMetaLabel:    { color: colors.text3, fontSize: 9, letterSpacing: 0.5 },
  opMetaVal:      { color: colors.text, fontSize: 13, fontWeight: '600', marginTop: 2 },
  opSubScores:    { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 6 },
  opSubItem:      { alignItems: 'center' },
  opSubLabel:     { color: colors.text3, fontSize: 9 },
  opSubVal:       { fontSize: 11, fontWeight: '600', marginTop: 2 },
  opReasoning:    { color: colors.text3, fontSize: 10, marginTop: 4, lineHeight: 14 },
  // Mini bar
  miniBarTrack:   { flex: 1, height: 6, backgroundColor: colors.bg, borderRadius: 3,
                    overflow: 'hidden', position: 'relative' },
  miniBarFill:    { position: 'absolute', height: '100%', borderRadius: 3 },
  miniBarCenter:  { position: 'absolute', left: '50%', top: 0, bottom: 0, width: 1,
                    backgroundColor: colors.text3 },
  // Rank table
  rankHeader:     { flexDirection: 'row', alignItems: 'center', paddingBottom: 6,
                    borderBottomWidth: 1, borderBottomColor: colors.border, marginBottom: 4 },
  rankHdr:        { color: colors.text3, fontSize: 10, letterSpacing: 0.5 },
  rankRow:        { flexDirection: 'row', alignItems: 'center', paddingVertical: 7,
                    borderBottomWidth: 1, borderBottomColor: colors.border + '44' },
  rankNum:        { color: colors.text3, fontSize: 11, width: 28 },
  rankSymbol:     { color: colors.text, fontSize: 12, fontWeight: '600', width: 80 },
  rankScore:      { fontSize: 12, fontWeight: '700', width: 56, textAlign: 'right' },
  rankAction:     { paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, borderWidth: 1,
                    marginLeft: 6 },
  rankActionText: { fontSize: 10, fontWeight: '700' },
  rankConf:       { color: colors.text3, fontSize: 11, width: 36, textAlign: 'right' },
  showMoreBtn:    { alignItems: 'center', paddingVertical: 12, marginTop: 4 },
  showMoreText:   { color: colors.accent, fontSize: 12, fontWeight: '600' },
});
