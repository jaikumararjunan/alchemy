import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { colors } from '../theme';

export default function StatCard({ label, value, sub, valueColor, style }) {
  return (
    <View style={[styles.card, style]}>
      <Text style={styles.label}>{label}</Text>
      <Text style={[styles.value, valueColor && { color: valueColor }]}>{value}</Text>
      {sub ? <Text style={styles.sub}>{sub}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.bg2,
    borderRadius: 12,
    padding: 14,
    borderWidth: 1,
    borderColor: colors.border,
    flex: 1,
  },
  label: { fontSize: 10, color: colors.text3, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 6 },
  value: { fontSize: 22, fontWeight: '700', color: colors.text },
  sub: { fontSize: 11, color: colors.text2, marginTop: 3 },
});
