import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { colors } from '../theme';

export default function EmotionMeter({ score = 0, emotion = 'neutral', confidence = 0 }) {
  const pct = ((score + 1) / 2) * 100;
  const color = score > 0.2 ? colors.green : score < -0.2 ? colors.red : colors.text2;

  return (
    <View style={styles.container}>
      <View style={styles.row}>
        <Text style={[styles.emotion, { color }]}>{emotion.toUpperCase()}</Text>
        <Text style={[styles.score, { color }]}>{score >= 0 ? '+' : ''}{score.toFixed(3)}</Text>
      </View>
      <View style={styles.labelRow}>
        <Text style={styles.label}>BEARISH</Text>
        <Text style={styles.label}>NEUTRAL</Text>
        <Text style={styles.label}>BULLISH</Text>
      </View>
      <View style={styles.barTrack}>
        <View style={[styles.needleWrap, { left: `${Math.min(Math.max(pct, 2), 98)}%` }]}>
          <View style={styles.needle} />
        </View>
      </View>
      <Text style={styles.conf}>Confidence: {(confidence * 100).toFixed(0)}%</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { marginBottom: 8 },
  row: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 6 },
  emotion: { fontSize: 18, fontWeight: '700' },
  score: { fontSize: 16, fontWeight: '700' },
  labelRow: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 3 },
  label: { fontSize: 9, color: colors.text3 },
  barTrack: {
    height: 8, borderRadius: 4, marginBottom: 4,
    backgroundColor: '#1e2d45',
    position: 'relative', overflow: 'visible',
    backgroundImage: 'linear-gradient(to right, #ef4444, #f59e0b, #64748b, #10b981, #00d4ff)',
  },
  needleWrap: { position: 'absolute', top: -4, width: 3, marginLeft: -1.5 },
  needle: { width: 3, height: 16, backgroundColor: '#fff', borderRadius: 2 },
  conf: { fontSize: 10, color: colors.text3 },
});
