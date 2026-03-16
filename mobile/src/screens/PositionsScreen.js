import React, { useEffect, useState } from 'react';
import { View, Text, ScrollView, StyleSheet, TouchableOpacity, RefreshControl } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useStore } from '../store/useStore';
import { colors, card } from '../theme';
import api from '../services/api';

export default function PositionsScreen() {
  const { portfolio, trades, positions, setPositions, setTrades } = useStore();
  const [refreshing, setRefreshing] = useState(false);

  const load = async () => {
    try {
      const [pos, port] = await Promise.all([api.getPositions(), api.getPortfolio()]);
      if (pos.positions) setPositions(pos.positions);
      if (port.trades) setTrades(port.trades);
    } catch (e) {}
  };

  useEffect(() => { load(); }, []);

  const onRefresh = async () => { setRefreshing(true); await load(); setRefreshing(false); };

  const PnLBadge = ({ value }) => (
    <Text style={{ color: value >= 0 ? colors.green : colors.red, fontWeight: '700', fontSize: 14 }}>
      {value >= 0 ? '+$' : '-$'}{Math.abs(value).toFixed(2)}
    </Text>
  );

  return (
    <ScrollView style={styles.screen} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.accent} />}>
      {/* Portfolio Summary */}
      <View style={[card, { marginHorizontal: 16, marginTop: 16 }]}>
        <Text style={styles.cardTitle}>Portfolio Summary</Text>
        <View style={styles.summaryGrid}>
          {[
            { label: 'Total P&L', value: `${(portfolio.total_pnl || 0) >= 0 ? '+$' : '-$'}${Math.abs(portfolio.total_pnl || 0).toFixed(2)}`, color: (portfolio.total_pnl || 0) >= 0 ? colors.green : colors.red },
            { label: 'Balance', value: `$${(portfolio.balance || 0).toFixed(2)}`, color: colors.text },
            { label: 'Unrealized', value: `${(portfolio.unrealized_pnl || 0) >= 0 ? '+$' : '-$'}${Math.abs(portfolio.unrealized_pnl || 0).toFixed(2)}`, color: (portfolio.unrealized_pnl || 0) >= 0 ? colors.green : colors.red },
            { label: 'Avg Win', value: `$${(portfolio.avg_win || 0).toFixed(2)}`, color: colors.green },
            { label: 'Avg Loss', value: `-$${Math.abs(portfolio.avg_loss || 0).toFixed(2)}`, color: colors.red },
            { label: 'Open Pos', value: String(portfolio.open_positions || 0), color: colors.accent },
          ].map((s, i) => (
            <View key={i} style={styles.summaryItem}>
              <Text style={styles.summaryLabel}>{s.label}</Text>
              <Text style={[styles.summaryVal, { color: s.color }]}>{s.value}</Text>
            </View>
          ))}
        </View>
      </View>

      {/* Open Positions */}
      <View style={{ paddingHorizontal: 16, marginBottom: 8 }}>
        <Text style={styles.sectionTitle}>Open Positions ({positions.length})</Text>
      </View>
      {positions.length === 0 ? (
        <View style={[card, { marginHorizontal: 16, alignItems: 'center', padding: 32 }]}>
          <Ionicons name="analytics-outline" size={32} color={colors.text3} />
          <Text style={[styles.empty, { marginTop: 8 }]}>No open positions</Text>
        </View>
      ) : positions.map((pos, i) => (
        <View key={i} style={[card, { marginHorizontal: 16 }]}>
          <View style={styles.posHeader}>
            <View>
              <Text style={styles.posSymbol}>{pos.symbol}</Text>
              <View style={[styles.sideBadge, { backgroundColor: pos.side === 'long' ? 'rgba(16,185,129,.15)' : 'rgba(239,68,68,.15)' }]}>
                <Text style={[styles.sideText, { color: pos.side === 'long' ? colors.green : colors.red }]}>
                  {pos.side?.toUpperCase()}
                </Text>
              </View>
            </View>
            <PnLBadge value={pos.unrealized_pnl || 0} />
          </View>
          <View style={styles.posDetails}>
            <View style={styles.posDetail}><Text style={styles.pdLabel}>Entry</Text><Text style={styles.pdVal}>${(pos.entry_price || 0).toLocaleString()}</Text></View>
            <View style={styles.posDetail}><Text style={styles.pdLabel}>Size</Text><Text style={styles.pdVal}>{pos.size}</Text></View>
            <View style={styles.posDetail}><Text style={styles.pdLabel}>Leverage</Text><Text style={styles.pdVal}>{pos.leverage}x</Text></View>
            <View style={styles.posDetail}><Text style={styles.pdLabel}>Liq. Price</Text><Text style={[styles.pdVal, { color: colors.red }]}>${(pos.liquidation_price || 0).toLocaleString()}</Text></View>
          </View>
        </View>
      ))}

      {/* Trade History */}
      <View style={{ paddingHorizontal: 16, marginBottom: 8, marginTop: 8 }}>
        <Text style={styles.sectionTitle}>Trade History ({trades.length})</Text>
      </View>
      {trades.length === 0 ? (
        <View style={[card, { marginHorizontal: 16, alignItems: 'center', padding: 24 }]}>
          <Text style={styles.empty}>No trades yet</Text>
        </View>
      ) : trades.slice(0, 20).map((t, i) => {
        const pnl = t.status === 'open' ? t.upnl : t.pnl;
        const pnlColor = pnl >= 0 ? colors.green : colors.red;
        return (
          <View key={i} style={[card, { marginHorizontal: 16 }]}>
            <View style={styles.tradeRow}>
              <View>
                <Text style={styles.tradeId}>{t.id}</Text>
                <View style={{ flexDirection: 'row', gap: 6, marginTop: 3 }}>
                  <View style={[styles.sideBadge, { backgroundColor: t.side === 'buy' ? 'rgba(16,185,129,.15)' : 'rgba(239,68,68,.15)' }]}>
                    <Text style={[styles.sideText, { color: t.side === 'buy' ? colors.green : colors.red }]}>{t.side?.toUpperCase()}</Text>
                  </View>
                  <View style={[styles.sideBadge, { backgroundColor: t.status === 'open' ? 'rgba(0,212,255,.1)' : 'rgba(100,116,139,.1)' }]}>
                    <Text style={[styles.sideText, { color: t.status === 'open' ? colors.accent : colors.text3 }]}>{t.status?.toUpperCase()}</Text>
                  </View>
                </View>
              </View>
              <View style={{ alignItems: 'flex-end' }}>
                <Text style={[styles.tradePnl, { color: pnlColor }]}>{pnl >= 0 ? '+$' : '-$'}{Math.abs(pnl || 0).toFixed(2)}</Text>
                <Text style={styles.tradeConf}>Conf: {((t.confidence || 0) * 100).toFixed(0)}%</Text>
              </View>
            </View>
            <View style={styles.tradeDetails}>
              <Text style={styles.tdText}>Entry: ${(t.entry || 0).toFixed(2)}</Text>
              {t.exit ? <Text style={styles.tdText}>Exit: ${t.exit.toFixed(2)}</Text> : null}
              <Text style={styles.tdText}>SL: ${(t.stop_loss || 0).toFixed(2)}</Text>
              <Text style={styles.tdText}>TP: ${(t.take_profit || 0).toFixed(2)}</Text>
            </View>
            {t.reasoning ? <Text style={styles.tradeReason}>{t.reasoning}</Text> : null}
          </View>
        );
      })}
      <View style={{ height: 24 }} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  cardTitle: { fontSize: 11, color: colors.text3, textTransform: 'uppercase', letterSpacing: 1.5, fontWeight: '600', marginBottom: 12 },
  summaryGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 12 },
  summaryItem: { width: '30%' },
  summaryLabel: { fontSize: 10, color: colors.text3, marginBottom: 3 },
  summaryVal: { fontSize: 15, fontWeight: '700' },
  sectionTitle: { fontSize: 14, fontWeight: '700', color: colors.text, marginBottom: 8 },
  empty: { fontSize: 13, color: colors.text3 },
  posHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 },
  posSymbol: { fontSize: 16, fontWeight: '700', color: colors.text, marginBottom: 4 },
  sideBadge: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 4, alignSelf: 'flex-start' },
  sideText: { fontSize: 10, fontWeight: '700' },
  posDetails: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  posDetail: { width: '22%' },
  pdLabel: { fontSize: 9, color: colors.text3, marginBottom: 2 },
  pdVal: { fontSize: 12, fontWeight: '600', color: colors.text },
  tradeRow: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 8 },
  tradeId: { fontSize: 12, color: colors.text3 },
  tradePnl: { fontSize: 16, fontWeight: '700' },
  tradeConf: { fontSize: 10, color: colors.text3 },
  tradeDetails: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 6 },
  tdText: { fontSize: 11, color: colors.text2 },
  tradeReason: { fontSize: 10, color: colors.text3, fontStyle: 'italic', lineHeight: 15 },
});
