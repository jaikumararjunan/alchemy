import React, { useEffect, useState } from 'react';
import { View, Text, ScrollView, StyleSheet, RefreshControl } from 'react-native';
import { useStore } from '../store/useStore';
import { colors, card } from '../theme';
import api from '../services/api';

const RiskColors = { low: colors.green, medium: colors.yellow, high: colors.red, critical: '#dc2626' };

export default function IntelligenceScreen() {
  const { emotion, geo, news, decisions, setEmotion, setGeo, setNews, setDecisions } = useStore();
  const [refreshing, setRefreshing] = useState(false);

  const load = async () => {
    try {
      const [emo, n, dec] = await Promise.all([
        api.getEmotion(),
        api.getNews(20),
        api.getDecisions(15),
      ]);
      if (emo.emotion) setEmotion(emo.emotion);
      if (emo.geopolitical) setGeo(emo.geopolitical);
      if (n.articles) setNews(n.articles);
      if (dec.decisions) setDecisions(dec.decisions);
    } catch (e) {}
  };

  useEffect(() => { load(); }, []);
  const onRefresh = async () => { setRefreshing(true); await load(); setRefreshing(false); };

  const emoBreakdown = emotion.emotions_breakdown || emotion.emotions || {};
  const emoEntries = [
    { key: 'fear', color: colors.red },
    { key: 'greed', color: colors.green },
    { key: 'panic', color: '#dc2626' },
    { key: 'optimism', color: colors.accent },
    { key: 'uncertainty', color: colors.yellow },
    { key: 'pessimism', color: '#f87171' },
  ];

  return (
    <ScrollView style={styles.screen} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.accent} />}>

      {/* Emotion Breakdown */}
      <View style={[card, { marginHorizontal: 16, marginTop: 16 }]}>
        <Text style={styles.cardTitle}>Emotion Intelligence Breakdown</Text>
        <View style={styles.scoreRow}>
          <View style={{ flex: 1 }}>
            <Text style={styles.label}>Sentiment Score</Text>
            <Text style={[styles.bigNum, { color: (emotion.sentiment_score || 0) >= 0 ? colors.green : colors.red }]}>
              {(emotion.sentiment_score || 0) >= 0 ? '+' : ''}{(emotion.sentiment_score || 0).toFixed(3)}
            </Text>
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.label}>Crypto Sentiment</Text>
            <Text style={[styles.bigNum, { color: (emotion.crypto_sentiment || 0) >= 0 ? colors.green : colors.red }]}>
              {(emotion.crypto_sentiment || 0) >= 0 ? '+' : ''}{(emotion.crypto_sentiment || 0).toFixed(3)}
            </Text>
          </View>
          <View style={{ flex: 1, alignItems: 'flex-end' }}>
            <Text style={styles.label}>Confidence</Text>
            <Text style={styles.bigNum}>{((emotion.confidence || 0) * 100).toFixed(0)}%</Text>
          </View>
        </View>

        {emoEntries.map(({ key, color }) => (
          <View key={key} style={styles.emoRow}>
            <Text style={styles.emoLabel}>{key.charAt(0).toUpperCase() + key.slice(1)}</Text>
            <View style={styles.emoBarTrack}>
              <View style={[styles.emoBarFill, { width: `${((emoBreakdown[key] || 0) * 100).toFixed(0)}%`, backgroundColor: color }]} />
            </View>
            <Text style={[styles.emoPct, { color }]}>{((emoBreakdown[key] || 0) * 100).toFixed(0)}%</Text>
          </View>
        ))}
      </View>

      {/* Claude AI Reasoning */}
      <View style={[card, { marginHorizontal: 16 }]}>
        <Text style={styles.cardTitle}>Claude AI Reasoning</Text>
        <Text style={styles.reasoning}>{emotion.reasoning || 'Awaiting AI analysis...'}</Text>

        <Text style={[styles.cardTitle, { marginTop: 12 }]}>Key Events</Text>
        {(emotion.key_events || []).length === 0 ? (
          <Text style={styles.dimText}>No key events detected yet</Text>
        ) : (emotion.key_events || []).map((ev, i) => (
          <View key={i} style={styles.eventRow}>
            <View style={styles.eventDot} />
            <Text style={styles.eventText}>{ev}</Text>
          </View>
        ))}
      </View>

      {/* Geopolitical Impact */}
      <View style={[card, { marginHorizontal: 16 }]}>
        <Text style={styles.cardTitle}>Geopolitical Impact Analysis</Text>
        <View style={styles.geoGrid}>
          <View style={styles.geoItem}>
            <Text style={styles.label}>Total Impact</Text>
            <Text style={[styles.bigNum, { color: (geo.total_impact || 0) >= 0 ? colors.green : colors.red }]}>
              {(geo.total_impact || 0) >= 0 ? '+' : ''}{(geo.total_impact || 0).toFixed(3)}
            </Text>
          </View>
          <View style={styles.geoItem}>
            <Text style={styles.label}>Risk Level</Text>
            <Text style={[styles.bigNum, { color: RiskColors[geo.risk_level || 'low'] }]}>
              {(geo.risk_level || 'LOW').toUpperCase()}
            </Text>
          </View>
          <View style={styles.geoItem}>
            <Text style={styles.label}>Events</Text>
            <Text style={styles.bigNum}>{geo.event_count || 0}</Text>
          </View>
        </View>
        <View style={styles.pressureRow}>
          <View style={styles.pressureItem}>
            <Text style={styles.label}>Bullish Pressure</Text>
            <Text style={[styles.pressureVal, { color: colors.green }]}>+{(geo.bullish_pressure || 0).toFixed(3)}</Text>
          </View>
          <View style={styles.pressureItem}>
            <Text style={styles.label}>Bearish Pressure</Text>
            <Text style={[styles.pressureVal, { color: colors.red }]}>-{(geo.bearish_pressure || 0).toFixed(3)}</Text>
          </View>
        </View>
        {(geo.dominant_events || []).map((ev, i) => (
          <View key={i} style={styles.geoEvent}>
            <View style={[styles.impactDot, { backgroundColor: (ev.impact || 0) >= 0 ? colors.green : colors.red }]} />
            <View style={{ flex: 1 }}>
              <Text style={styles.geoEventDesc}>{ev.description || ev.region}</Text>
              <Text style={[styles.geoEventImp, { color: (ev.impact || 0) >= 0 ? colors.green : colors.red }]}>
                Impact: {(ev.impact || 0) >= 0 ? '+' : ''}{(ev.impact || 0).toFixed(2)} | {ev.region}
              </Text>
            </View>
          </View>
        ))}
      </View>

      {/* AI Decision Feed */}
      <View style={[card, { marginHorizontal: 16 }]}>
        <Text style={styles.cardTitle}>AI Decision Feed</Text>
        {decisions.length === 0 ? (
          <Text style={styles.dimText}>No decisions yet...</Text>
        ) : decisions.slice(0, 10).map((d, i) => {
          const isPos = (d.action || '').toLowerCase().includes('buy');
          const isNeg = (d.action || '').toLowerCase().includes('sell');
          const color = isPos ? colors.green : isNeg ? colors.red : colors.text2;
          return (
            <View key={i} style={[styles.decisionItem, { borderLeftColor: color }]}>
              <Text style={styles.decisionTime}>{d.time ? new Date(d.time).toLocaleTimeString() : ''}</Text>
              <Text style={[styles.decisionAction, { color }]}>{d.action || 'Hold'}</Text>
              {d.price ? <Text style={styles.decisionMeta}>@ ${d.price.toLocaleString()} | SL: ${(d.stop_loss || 0).toLocaleString()} | TP: ${(d.take_profit || 0).toLocaleString()}</Text> : null}
              {d.reasoning ? <Text style={styles.decisionReason}>{d.reasoning}</Text> : null}
            </View>
          );
        })}
      </View>

      {/* News Feed */}
      <View style={[card, { marginHorizontal: 16 }]}>
        <Text style={styles.cardTitle}>Geopolitical News Feed</Text>
        {news.slice(0, 15).map((a, i) => {
          const sc = a.score || 0;
          const scColor = sc >= 0.7 ? colors.green : sc >= 0.4 ? colors.yellow : colors.text3;
          return (
            <View key={i} style={styles.newsItem}>
              <View style={styles.newsHeader}>
                <Text style={styles.newsSource}>{a.source || ''}</Text>
                <Text style={[styles.newsScore, { color: scColor }]}>★ {sc.toFixed(2)}</Text>
              </View>
              <Text style={styles.newsTitle}>{a.title || ''}</Text>
              <Text style={styles.newsTime}>{a.published || ''}</Text>
            </View>
          );
        })}
      </View>

      <View style={{ height: 24 }} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  cardTitle: { fontSize: 11, color: colors.text3, textTransform: 'uppercase', letterSpacing: 1.5, fontWeight: '600', marginBottom: 12 },
  scoreRow: { flexDirection: 'row', marginBottom: 16 },
  label: { fontSize: 10, color: colors.text3, marginBottom: 4 },
  bigNum: { fontSize: 20, fontWeight: '700', color: colors.text },
  emoRow: { flexDirection: 'row', alignItems: 'center', marginBottom: 8 },
  emoLabel: { width: 85, fontSize: 12, color: colors.text2 },
  emoBarTrack: { flex: 1, height: 6, backgroundColor: colors.bg3, borderRadius: 3, overflow: 'hidden', marginHorizontal: 8 },
  emoBarFill: { height: '100%', borderRadius: 3 },
  emoPct: { width: 36, fontSize: 11, fontWeight: '600', textAlign: 'right' },
  reasoning: { fontSize: 12, color: colors.text2, fontStyle: 'italic', lineHeight: 18, backgroundColor: colors.bg3, padding: 10, borderRadius: 6 },
  dimText: { fontSize: 12, color: colors.text3 },
  eventRow: { flexDirection: 'row', alignItems: 'flex-start', marginBottom: 6 },
  eventDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: colors.accent, marginTop: 4, marginRight: 8 },
  eventText: { flex: 1, fontSize: 12, color: colors.text2, lineHeight: 17 },
  geoGrid: { flexDirection: 'row', marginBottom: 12 },
  geoItem: { flex: 1 },
  pressureRow: { flexDirection: 'row', marginBottom: 12 },
  pressureItem: { flex: 1 },
  pressureVal: { fontSize: 16, fontWeight: '700' },
  geoEvent: { flexDirection: 'row', alignItems: 'flex-start', gap: 8, marginBottom: 8, padding: 8, backgroundColor: colors.bg3, borderRadius: 6 },
  impactDot: { width: 8, height: 8, borderRadius: 4, marginTop: 3 },
  geoEventDesc: { fontSize: 12, fontWeight: '600', color: colors.text },
  geoEventImp: { fontSize: 10, marginTop: 2 },
  decisionItem: { borderLeftWidth: 3, paddingLeft: 10, marginBottom: 10, paddingVertical: 4 },
  decisionTime: { fontSize: 10, color: colors.text3 },
  decisionAction: { fontSize: 13, fontWeight: '700', marginVertical: 2 },
  decisionMeta: { fontSize: 11, color: colors.text2 },
  decisionReason: { fontSize: 11, color: colors.text2, marginTop: 2, fontStyle: 'italic' },
  newsItem: { marginBottom: 12, paddingBottom: 12, borderBottomWidth: 1, borderBottomColor: colors.border },
  newsHeader: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 3 },
  newsSource: { fontSize: 10, color: colors.text3 },
  newsScore: { fontSize: 10, fontWeight: '600' },
  newsTitle: { fontSize: 13, fontWeight: '500', color: colors.text, lineHeight: 18 },
  newsTime: { fontSize: 10, color: colors.text3, marginTop: 3 },
});
