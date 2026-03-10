/**
 * MLScreen — Data Science / ML / AI insight panel.
 * Shows: price direction prediction, signal classification,
 *        anomaly detection, headline sentiment analysis, model status.
 */
import React, { useEffect, useState } from 'react';
import {
  View, Text, ScrollView, StyleSheet, RefreshControl,
  ActivityIndicator, TouchableOpacity,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useStore } from '../store/useStore';
import { colors, card } from '../theme';
import api from '../services/api';

// ── Helpers ───────────────────────────────────────────────────────────────────

const DirColor  = { up: colors.green, down: colors.red, flat: colors.text2 };
const SigColor  = { BUY: colors.green, SELL: colors.red, HOLD: colors.text2 };
const RiskColor = { normal: colors.green, elevated: colors.yellow, high: colors.red, critical: '#dc2626' };
const SevColor  = { low: colors.text3, medium: colors.yellow, high: colors.red, critical: '#dc2626' };
const SentColor = { very_positive: colors.green, positive: colors.accent, neutral: colors.text2, negative: colors.red, very_negative: '#dc2626' };

function Row({ label, value, valueColor, sub }) {
  return (
    <View style={s.tableRow}>
      <Text style={s.tableLabel}>{label}</Text>
      <View style={{ alignItems: 'flex-end' }}>
        <Text style={[s.tableVal, valueColor && { color: valueColor }]}>{value}</Text>
        {sub ? <Text style={s.tableSub}>{sub}</Text> : null}
      </View>
    </View>
  );
}

function SectionTitle({ text }) {
  return <Text style={s.sectionTitle}>{text}</Text>;
}

function ProbBar({ label, value, color }) {
  return (
    <View style={s.probRow}>
      <Text style={s.probLabel}>{label}</Text>
      <View style={s.probTrack}>
        <View style={[s.probFill, { width: `${(value * 100).toFixed(0)}%`, backgroundColor: color }]} />
      </View>
      <Text style={[s.probPct, { color }]}>{(value * 100).toFixed(1)}%</Text>
    </View>
  );
}

// ── Screen ────────────────────────────────────────────────────────────────────

export default function MLScreen() {
  const { mlAnalysis, setMlAnalysis, market } = useStore();
  const [refreshing, setRefreshing] = useState(false);
  const [training, setTraining] = useState(false);
  const [loading, setLoading] = useState(!mlAnalysis?.ml_composite_score);

  const load = async () => {
    try {
      const data = await api.getMlAnalysis(market.symbol || 'BTCUSD');
      if (data && !data.error) setMlAnalysis(data);
    } catch (e) {}
  };

  const triggerTrain = async () => {
    setTraining(true);
    try {
      await api.trainModels();
      await load();
    } catch (e) {}
    setTraining(false);
  };

  useEffect(() => {
    load().then(() => setLoading(false));
    const t = setInterval(load, 90_000);
    return () => clearInterval(t);
  }, [market.symbol]);

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  if (loading) {
    return (
      <View style={s.center}>
        <ActivityIndicator color={colors.accent} size="large" />
        <Text style={s.loadText}>Running ML pipeline…</Text>
      </View>
    );
  }

  const ml = mlAnalysis || {};
  const pred = ml.prediction || {};
  const sig  = ml.signal || {};
  const anom = ml.anomaly_report || {};
  const sent = ml.sentiment || {};
  const isT  = ml.is_trained;

  const scoreColor = ml.ml_composite_score > 0.1 ? colors.green
                   : ml.ml_composite_score < -0.1 ? colors.red
                   : colors.text2;

  return (
    <ScrollView style={s.screen} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.accent} />}>

      {/* Header */}
      <View style={[card, { marginHorizontal: 16, marginTop: 16 }]}>
        <SectionTitle text="ML / AI Analysis Engine" />
        <View style={s.headerRow}>
          <View>
            <Text style={s.tinyLabel}>COMPOSITE ML SCORE</Text>
            <Text style={[s.bigNum, { color: scoreColor }]}>
              {(ml.ml_composite_score || 0) >= 0 ? '+' : ''}{(ml.ml_composite_score || 0).toFixed(4)}
            </Text>
          </View>
          <View style={[s.actionBadge, { borderColor: SigColor[ml.ml_action_suggestion] || colors.text2 }]}>
            <Text style={[s.actionText, { color: SigColor[ml.ml_action_suggestion] }]}>
              {ml.ml_action_suggestion || 'HOLD'}
            </Text>
          </View>
        </View>
        <Row label="Model trained" value={isT ? 'YES' : 'NOT YET'} valueColor={isT ? colors.green : colors.yellow} />
        <Row label="Training samples" value={String(ml.trained_samples || 0)} />

        <TouchableOpacity
          style={[s.trainBtn, training && { opacity: 0.5 }]}
          onPress={triggerTrain}
          disabled={training}
        >
          <Ionicons name="refresh" size={14} color={colors.bg} />
          <Text style={s.trainBtnText}>{training ? 'Training…' : 'Retrain Models Now'}</Text>
        </TouchableOpacity>
      </View>

      {/* Price Predictor */}
      <View style={[card, { marginHorizontal: 16 }]}>
        <SectionTitle text="Price Direction Prediction" />
        <View style={s.dirRow}>
          <Text style={[s.dirLabel, { color: DirColor[pred.direction || 'flat'] }]}>
            {(pred.direction || 'FLAT').toUpperCase()}
          </Text>
          <Text style={[s.dirConf, { color: DirColor[pred.direction || 'flat'] }]}>
            {((pred.confidence || 0) * 100).toFixed(0)}% confident
          </Text>
        </View>
        <ProbBar label="UP  ↑" value={pred.prob_up  || 0} color={colors.green} />
        <ProbBar label="FLAT―" value={pred.prob_flat || 0} color={colors.text2} />
        <ProbBar label="DOWN↓" value={pred.prob_down || 0} color={colors.red} />
        <Row label="Model agreement" value={`${((pred.model_agreement || 0) * 100).toFixed(0)}%`} />
        <Row label="Actionable" value={pred.is_actionable ? 'YES' : 'NO'} valueColor={pred.is_actionable ? colors.green : colors.yellow} />
        {pred.note ? <Text style={s.note}>{pred.note}</Text> : null}

        {/* Top features */}
        {pred.top_features && Object.keys(pred.top_features).length > 0 && (
          <View style={{ marginTop: 10 }}>
            <Text style={s.tinyLabel}>TOP PREDICTIVE FEATURES</Text>
            {Object.entries(pred.top_features).slice(0, 6).map(([k, v], i) => (
              <View key={k} style={s.featRow}>
                <Text style={s.featName}>{i + 1}. {k}</Text>
                <View style={s.featBarTrack}>
                  <View style={[s.featBarFill, { width: `${(v * 100 / 0.15).toFixed(0)}%` }]} />
                </View>
                <Text style={s.featVal}>{(v * 100).toFixed(2)}%</Text>
              </View>
            ))}
          </View>
        )}
      </View>

      {/* Signal Classifier */}
      <View style={[card, { marginHorizontal: 16 }]}>
        <SectionTitle text="ML Signal Classifier" />
        <View style={s.dirRow}>
          <Text style={[s.dirLabel, { color: SigColor[sig.signal || 'HOLD'] }]}>
            {sig.signal || 'HOLD'}
          </Text>
          <View style={[s.actionBadge, { borderColor: SigColor[sig.signal] }]}>
            <Text style={[s.actionText, { color: SigColor[sig.signal] }]}>
              {((sig.confidence || 0) * 100).toFixed(0)}% conf
            </Text>
          </View>
        </View>
        <ProbBar label="BUY " value={sig.prob_buy  || 0} color={colors.green} />
        <ProbBar label="HOLD" value={sig.prob_hold || 0} color={colors.text2} />
        <ProbBar label="SELL" value={sig.prob_sell || 0} color={colors.red} />
        <Row label="ML directional score"
          value={`${(sig.ml_score || 0) >= 0 ? '+' : ''}${(sig.ml_score || 0).toFixed(4)}`}
          valueColor={(sig.ml_score || 0) > 0 ? colors.green : (sig.ml_score || 0) < 0 ? colors.red : colors.text2}
        />
        <Row label="Anomaly risk factor" value={`${((sig.anomaly_risk || 0) * 100).toFixed(0)}%`}
          valueColor={(sig.anomaly_risk || 0) > 0.5 ? colors.red : colors.green}
        />
        <Row label="Actionable" value={sig.is_actionable ? 'YES' : 'NO'} valueColor={sig.is_actionable ? colors.green : colors.yellow} />
        {sig.note ? <Text style={s.note}>{sig.note}</Text> : null}
      </View>

      {/* Anomaly Detector */}
      <View style={[card, { marginHorizontal: 16 }]}>
        <SectionTitle text="Anomaly Detection" />
        <View style={s.dirRow}>
          <Text style={[s.dirLabel, { color: RiskColor[anom.overall_risk || 'normal'] }]}>
            {(anom.overall_risk || 'NORMAL').toUpperCase()}
          </Text>
          <Text style={s.dirConf}>
            {anom.anomaly_count || 0} anomal{(anom.anomaly_count || 0) === 1 ? 'y' : 'ies'}
          </Text>
        </View>
        <Row label="Risk score" value={`${((anom.risk_score || 0) * 100).toFixed(1)}%`}
          valueColor={RiskColor[anom.overall_risk || 'normal']}
        />
        <Row label="CUSUM statistic" value={(anom.cusum_stat || 0).toFixed(4)} />
        <Row label="Regime change" value={anom.regime_change_detected ? 'DETECTED' : 'None'}
          valueColor={anom.regime_change_detected ? colors.red : colors.green}
        />
        {(anom.anomalies || []).map((a, i) => (
          <View key={i} style={[s.anomalyCard, { borderLeftColor: SevColor[a.severity] }]}>
            <Text style={[s.anomalyType, { color: SevColor[a.severity] }]}>
              {a.type} [{a.severity?.toUpperCase()}]
            </Text>
            <Text style={s.anomalyDesc}>{a.description}</Text>
            {a.trading_implication ? (
              <Text style={s.anomalyImpl}>→ {a.trading_implication}</Text>
            ) : null}
          </View>
        ))}
        {anom.summary ? <Text style={s.note}>{anom.summary}</Text> : null}
      </View>

      {/* Headline Sentiment */}
      {sent && sent.score !== undefined && (
        <View style={[card, { marginHorizontal: 16 }]}>
          <SectionTitle text="NLP Headline Sentiment" />
          <Row label="Score" value={`${(sent.score || 0) >= 0 ? '+' : ''}${(sent.score || 0).toFixed(4)}`}
            valueColor={(sent.score || 0) > 0.1 ? colors.green : (sent.score || 0) < -0.1 ? colors.red : colors.text2}
          />
          <Row label="Label" value={(sent.label || 'neutral').replace('_', ' ').toUpperCase()}
            valueColor={SentColor[sent.label || 'neutral']}
          />
          <Row label="Confidence" value={`${((sent.confidence || 0) * 100).toFixed(0)}%`} />
          <Row label="Lexicon signal" value={`${(sent.lexicon_score || 0) >= 0 ? '+' : ''}${(sent.lexicon_score || 0).toFixed(4)}`} />
          <Row label="ML signal" value={`${(sent.ml_score || 0) >= 0 ? '+' : ''}${(sent.ml_score || 0).toFixed(4)}`} />
          {(sent.top_keywords || []).length > 0 && (
            <View style={{ marginTop: 8 }}>
              <Text style={s.tinyLabel}>KEY TERMS</Text>
              <Text style={s.keywords}>{(sent.top_keywords || []).join('  ·  ')}</Text>
            </View>
          )}
        </View>
      )}

      <View style={{ height: 32 }} />
    </ScrollView>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: colors.bg },
  loadText: { color: colors.text2, marginTop: 12, fontSize: 13 },
  sectionTitle: { fontSize: 11, color: colors.text3, textTransform: 'uppercase', letterSpacing: 1.5, fontWeight: '600', marginBottom: 10 },
  headerRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 },
  bigNum: { fontSize: 28, fontWeight: '700', color: colors.text },
  tinyLabel: { fontSize: 9, color: colors.text3, letterSpacing: 0.5, marginBottom: 2 },
  actionBadge: { borderWidth: 2, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 6 },
  actionText: { fontSize: 15, fontWeight: '800' },
  tableRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: colors.border },
  tableLabel: { fontSize: 12, color: colors.text2 },
  tableVal: { fontSize: 13, fontWeight: '600', color: colors.text },
  tableSub: { fontSize: 10, color: colors.text3, textAlign: 'right' },
  dirRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 },
  dirLabel: { fontSize: 32, fontWeight: '800' },
  dirConf: { fontSize: 14, color: colors.text2, fontWeight: '600' },
  probRow: { flexDirection: 'row', alignItems: 'center', marginBottom: 6 },
  probLabel: { width: 44, fontSize: 11, color: colors.text2, fontWeight: '600' },
  probTrack: { flex: 1, height: 8, backgroundColor: colors.bg3, borderRadius: 4, overflow: 'hidden', marginHorizontal: 8 },
  probFill: { height: '100%', borderRadius: 4 },
  probPct: { width: 40, fontSize: 11, fontWeight: '700', textAlign: 'right' },
  note: { fontSize: 11, color: colors.text3, fontStyle: 'italic', marginTop: 8, lineHeight: 15 },
  featRow: { flexDirection: 'row', alignItems: 'center', marginTop: 4 },
  featName: { width: 120, fontSize: 11, color: colors.text2 },
  featBarTrack: { flex: 1, height: 5, backgroundColor: colors.bg3, borderRadius: 3, overflow: 'hidden', marginHorizontal: 6 },
  featBarFill: { height: '100%', backgroundColor: colors.accent2, borderRadius: 3 },
  featVal: { width: 40, fontSize: 10, color: colors.text3, textAlign: 'right' },
  anomalyCard: { borderLeftWidth: 3, paddingLeft: 10, marginTop: 8, paddingVertical: 4 },
  anomalyType: { fontSize: 12, fontWeight: '700' },
  anomalyDesc: { fontSize: 11, color: colors.text2, marginTop: 2 },
  anomalyImpl: { fontSize: 10, color: colors.text3, fontStyle: 'italic', marginTop: 2 },
  keywords: { fontSize: 11, color: colors.accent, marginTop: 4 },
  trainBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, marginTop: 12, backgroundColor: colors.accent2, borderRadius: 8, padding: 10 },
  trainBtnText: { color: colors.bg, fontWeight: '700', fontSize: 13 },
});
