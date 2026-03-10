import React, { useEffect, useCallback } from 'react';
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity,
  RefreshControl, ActivityIndicator, Dimensions,
} from 'react-native';
import { LineChart } from 'react-native-chart-kit';
import { Ionicons } from '@expo/vector-icons';
import { useStore } from '../store/useStore';
import { colors, card } from '../theme';
import StatCard from '../components/StatCard';
import EmotionMeter from '../components/EmotionMeter';
import api from '../services/api';

const { width } = Dimensions.get('window');

export default function DashboardScreen() {
  const { market, emotion, geo, portfolio, botState, sentimentHistory,
          connected, setConnected, processWSData, setPortfolio, setMarket,
          setEmotion, setGeo } = useStore();
  const [refreshing, setRefreshing] = React.useState(false);

  // Load initial data
  const loadData = useCallback(async () => {
    try {
      const [port, mkt, emo] = await Promise.all([
        api.getPortfolio(),
        api.getMarket(market.symbol || 'BTCUSD'),
        api.getEmotion(),
      ]);
      if (port.stats) setPortfolio(port.stats);
      if (mkt) setMarket(mkt);
      if (emo.emotion) setEmotion(emo.emotion);
      if (emo.geopolitical) setGeo(emo.geopolitical);
    } catch (e) {}
  }, []);

  useEffect(() => {
    loadData();
    api.connectWS(
      processWSData,
      () => setConnected(true),
      () => setConnected(false),
    );
    return () => api.disconnectWS();
  }, []);

  const onRefresh = async () => {
    setRefreshing(true);
    await loadData();
    setRefreshing(false);
  };

  const handleBotControl = async (action) => {
    try { await api.botControl(action, 30); } catch (e) {}
  };

  const price = market.mark_price || 0;
  const change = market.change_24h_pct || 0;
  const priceColor = change >= 0 ? colors.green : colors.red;
  const emoScore = emotion.sentiment_score || 0;

  const chartData = sentimentHistory.length > 2 ? {
    labels: sentimentHistory.slice(-10).map(p => ''),
    datasets: [{ data: sentimentHistory.slice(-10).map(p => p.score), strokeWidth: 2 }],
  } : { labels: [''], datasets: [{ data: [0] }] };

  return (
    <ScrollView
      style={styles.screen}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.accent} />}
    >
      {/* Header Status Bar */}
      <View style={styles.statusBar}>
        <View style={styles.statusLeft}>
          <View style={[styles.dot, { backgroundColor: connected ? colors.green : colors.red }]} />
          <Text style={styles.statusText}>{connected ? 'CONNECTED' : 'OFFLINE'}</Text>
        </View>
        <Text style={[styles.statusText, { color: botState.bot_running ? colors.green : colors.yellow }]}>
          ● {botState.mode?.toUpperCase() || 'MONITORING'}
        </Text>
        <Text style={styles.statusText}>Cycle #{botState.cycle || 0}</Text>
      </View>

      {/* Live Price Card */}
      <View style={[card, styles.priceCard]}>
        <Text style={styles.symbol}>{market.symbol || 'BTCUSD'}</Text>
        <Text style={[styles.price, { color: priceColor }]}>
          ${price.toLocaleString('en', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </Text>
        <View style={styles.priceRow}>
          <View style={[styles.changeBadge, { backgroundColor: change >= 0 ? 'rgba(16,185,129,.15)' : 'rgba(239,68,68,.15)' }]}>
            <Text style={[styles.changeText, { color: priceColor }]}>
              {change >= 0 ? '+' : ''}{change.toFixed(2)}%
            </Text>
          </View>
          <Text style={styles.vol}>Vol: {(market.volume_24h || 0).toLocaleString()}</Text>
        </View>
        <View style={styles.bidAsk}>
          <View>
            <Text style={styles.baLabel}>BID</Text>
            <Text style={[styles.baVal, { color: colors.green }]}>${(market.bid || 0).toLocaleString('en', { maximumFractionDigits: 2 })}</Text>
          </View>
          <View style={{ alignItems: 'flex-end' }}>
            <Text style={styles.baLabel}>ASK</Text>
            <Text style={[styles.baVal, { color: colors.red }]}>${(market.ask || 0).toLocaleString('en', { maximumFractionDigits: 2 })}</Text>
          </View>
        </View>
      </View>

      {/* KPI Row */}
      <View style={styles.row}>
        <StatCard
          label="Portfolio"
          value={`$${(portfolio.equity || 0).toLocaleString('en', { maximumFractionDigits: 0 })}`}
          sub={`${(portfolio.total_pnl_pct || 0) >= 0 ? '+' : ''}${(portfolio.total_pnl_pct || 0).toFixed(2)}% all time`}
          valueColor={colors.accent}
          style={{ marginRight: 8 }}
        />
        <StatCard
          label="Daily P&L"
          value={`${(portfolio.daily_pnl || 0) >= 0 ? '+$' : '-$'}${Math.abs(portfolio.daily_pnl || 0).toFixed(2)}`}
          sub={`${portfolio.open_positions || 0} open positions`}
          valueColor={(portfolio.daily_pnl || 0) >= 0 ? colors.green : colors.red}
        />
      </View>

      <View style={styles.row}>
        <StatCard
          label="Win Rate"
          value={`${(portfolio.win_rate || 0).toFixed(1)}%`}
          sub={`${portfolio.total_trades || 0} total trades`}
          valueColor={(portfolio.win_rate || 0) >= 50 ? colors.green : colors.red}
          style={{ marginRight: 8 }}
        />
        <StatCard
          label="Max Drawdown"
          value={`${(portfolio.max_drawdown_pct || 0).toFixed(2)}%`}
          sub={`PF: ${(portfolio.profit_factor || 0).toFixed(2)}`}
          valueColor={colors.red}
        />
      </View>

      {/* Emotion Intelligence */}
      <View style={card}>
        <Text style={styles.cardTitle}>Claude Emotion Intelligence</Text>
        <EmotionMeter
          score={emoScore}
          emotion={emotion.dominant_emotion || 'neutral'}
          confidence={emotion.confidence || 0}
        />
        <View style={styles.row}>
          <View style={styles.emoTag}>
            <Text style={styles.emoTagLabel}>GEO RISK</Text>
            <Text style={[styles.emoTagVal, { color: { low: colors.green, medium: colors.yellow, high: colors.red, critical: colors.red }[emotion.geopolitical_risk] || colors.text2 }]}>
              {(emotion.geopolitical_risk || 'low').toUpperCase()}
            </Text>
          </View>
          <View style={styles.emoTag}>
            <Text style={styles.emoTagLabel}>BIAS</Text>
            <Text style={[styles.emoTagVal, { color: emoScore > 0 ? colors.green : emoScore < 0 ? colors.red : colors.text2 }]}>
              {(emotion.trading_bias || 'neutral').replace(/_/g, ' ').toUpperCase()}
            </Text>
          </View>
          <View style={styles.emoTag}>
            <Text style={styles.emoTagLabel}>GEO IMPACT</Text>
            <Text style={[styles.emoTagVal, { color: (geo.total_impact || 0) > 0 ? colors.green : colors.red }]}>
              {(geo.total_impact || 0) >= 0 ? '+' : ''}{(geo.total_impact || 0).toFixed(3)}
            </Text>
          </View>
        </View>
        {emotion.reasoning ? (
          <Text style={styles.reasoning}>{emotion.reasoning}</Text>
        ) : null}
      </View>

      {/* Sentiment Mini Chart */}
      {sentimentHistory.length > 3 && (
        <View style={card}>
          <Text style={styles.cardTitle}>Sentiment History</Text>
          <LineChart
            data={chartData}
            width={width - 64}
            height={120}
            chartConfig={{
              backgroundColor: colors.bg2,
              backgroundGradientFrom: colors.bg2,
              backgroundGradientTo: colors.bg2,
              decimalPlaces: 2,
              color: (opacity = 1) => emoScore >= 0 ? `rgba(16,185,129,${opacity})` : `rgba(239,68,68,${opacity})`,
              labelColor: () => colors.text3,
              propsForDots: { r: '3', strokeWidth: '1' },
            }}
            bezier
            withDots={false}
            withInnerLines={false}
            withOuterLines={false}
            style={{ borderRadius: 8 }}
          />
        </View>
      )}

      {/* Bot Controls */}
      <View style={card}>
        <Text style={styles.cardTitle}>Autonomous AI Control</Text>
        <Text style={styles.aiStatus}>{botState.status || 'Waiting...'}</Text>
        {botState.last_action ? (
          <Text style={styles.lastAction}>Last: {botState.last_action}</Text>
        ) : null}
        <View style={styles.btnRow}>
          <TouchableOpacity style={[styles.btn, styles.btnStart]} onPress={() => handleBotControl('start')}>
            <Ionicons name="play" size={14} color="#000" />
            <Text style={styles.btnStartText}>Start</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[styles.btn, styles.btnStop]} onPress={() => handleBotControl('stop')}>
            <Ionicons name="stop" size={14} color="#fff" />
            <Text style={styles.btnStopText}>Stop</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[styles.btn, styles.btnCycle]} onPress={() => handleBotControl('cycle')}>
            <Ionicons name="refresh" size={14} color="#fff" />
            <Text style={styles.btnCycleText}>Run Cycle</Text>
          </TouchableOpacity>
        </View>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  statusBar: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: colors.border },
  statusLeft: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  dot: { width: 7, height: 7, borderRadius: 4 },
  statusText: { fontSize: 10, color: colors.text2, fontWeight: '600', letterSpacing: 0.5 },
  priceCard: { marginHorizontal: 16, marginTop: 12 },
  symbol: { fontSize: 12, color: colors.text3, fontWeight: '600', letterSpacing: 1, marginBottom: 4 },
  price: { fontSize: 36, fontWeight: '700', letterSpacing: -1 },
  priceRow: { flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 6 },
  changeBadge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 },
  changeText: { fontSize: 13, fontWeight: '600' },
  vol: { fontSize: 11, color: colors.text3 },
  bidAsk: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 12, paddingTop: 10, borderTopWidth: 1, borderTopColor: colors.border },
  baLabel: { fontSize: 9, color: colors.text3, marginBottom: 2 },
  baVal: { fontSize: 14, fontWeight: '600' },
  row: { flexDirection: 'row', paddingHorizontal: 16, marginBottom: 12 },
  cardTitle: { fontSize: 11, color: colors.text3, textTransform: 'uppercase', letterSpacing: 1.5, fontWeight: '600', marginBottom: 12 },
  emoTag: { flex: 1, alignItems: 'center' },
  emoTagLabel: { fontSize: 9, color: colors.text3, marginBottom: 3 },
  emoTagVal: { fontSize: 12, fontWeight: '700' },
  reasoning: { fontSize: 11, color: colors.text2, fontStyle: 'italic', lineHeight: 16, marginTop: 10, padding: 8, backgroundColor: colors.bg3, borderRadius: 6 },
  aiStatus: { fontSize: 12, color: colors.text2, lineHeight: 18, marginBottom: 8 },
  lastAction: { fontSize: 11, color: colors.accent, marginBottom: 10, fontWeight: '600' },
  btnRow: { flexDirection: 'row', gap: 8 },
  btn: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 10, borderRadius: 8 },
  btnStart: { backgroundColor: colors.green },
  btnStartText: { color: '#000', fontWeight: '700', fontSize: 13 },
  btnStop: { backgroundColor: colors.red },
  btnStopText: { color: '#fff', fontWeight: '700', fontSize: 13 },
  btnCycle: { backgroundColor: colors.accent2 },
  btnCycleText: { color: '#fff', fontWeight: '700', fontSize: 13 },
});
