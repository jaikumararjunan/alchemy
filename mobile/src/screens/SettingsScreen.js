import React, { useEffect, useState } from 'react';
import { View, Text, ScrollView, StyleSheet, Switch, TouchableOpacity, TextInput, Alert } from 'react-native';
import { colors, card } from '../theme';
import { useStore } from '../store/useStore';
import api from '../services/api';

export default function SettingsScreen() {
  const { config, setConfig } = useStore();
  const [local, setLocal] = useState({ ...config });
  const [status, setStatus] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.getConfig().then(cfg => { setLocal(cfg); setConfig(cfg); }).catch(() => {});
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      const updated = await api.updateConfig(local);
      setConfig(updated);
      setStatus('Saved!');
      setTimeout(() => setStatus(null), 2000);
    } catch (e) {
      setStatus('Error saving');
    }
    setSaving(false);
  };

  const toggleDryRun = async (val) => {
    const next = { ...local, dry_run: val };
    setLocal(next);
    try { await api.updateConfig({ dry_run: val }); } catch (e) {}
  };

  const symbols = ['BTCUSD', 'ETHUSD', 'SOLUSD', 'BNBUSD', 'ADAUSD', 'DOTUSD'];

  return (
    <ScrollView style={styles.screen}>
      {/* Trading Mode */}
      <View style={[card, { marginHorizontal: 16, marginTop: 16 }]}>
        <Text style={styles.cardTitle}>Trading Mode</Text>
        <View style={styles.settingRow}>
          <View>
            <Text style={styles.settingLabel}>Paper Trading (Dry Run)</Text>
            <Text style={styles.settingDesc}>No real orders placed</Text>
          </View>
          <Switch
            value={local.dry_run}
            onValueChange={toggleDryRun}
            trackColor={{ false: colors.red + '44', true: colors.green + '44' }}
            thumbColor={local.dry_run ? colors.green : colors.red}
          />
        </View>
        {!local.dry_run && (
          <View style={styles.warnBox}>
            <Text style={styles.warnText}>⚠️ LIVE TRADING ENABLED - Real money at risk!</Text>
          </View>
        )}
      </View>

      {/* Symbol Selection */}
      <View style={[card, { marginHorizontal: 16 }]}>
        <Text style={styles.cardTitle}>Trading Symbol</Text>
        <View style={styles.symbolGrid}>
          {symbols.map(sym => (
            <TouchableOpacity
              key={sym}
              style={[styles.symbolBtn, local.symbol === sym && styles.symbolBtnActive]}
              onPress={() => setLocal(p => ({ ...p, symbol: sym }))}
            >
              <Text style={[styles.symbolText, local.symbol === sym && styles.symbolTextActive]}>{sym}</Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>

      {/* Risk Settings */}
      <View style={[card, { marginHorizontal: 16 }]}>
        <Text style={styles.cardTitle}>Risk Management</Text>
        {[
          { label: 'Position Size (USD)', key: 'position_size_usd', desc: 'Base size per trade' },
          { label: 'Risk Per Trade (%)', key: 'risk_per_trade_pct', desc: 'Max % of balance to risk' },
          { label: 'Stop Loss (%)', key: 'stop_loss_pct', desc: 'Default stop loss distance' },
          { label: 'Take Profit (%)', key: 'take_profit_pct', desc: 'Default take profit distance' },
          { label: 'Leverage (x)', key: 'leverage', desc: 'Trading leverage multiplier' },
          { label: 'Max Positions', key: 'max_positions', desc: 'Max simultaneous positions' },
        ].map(f => (
          <View key={f.key} style={styles.inputRow}>
            <View style={{ flex: 1 }}>
              <Text style={styles.settingLabel}>{f.label}</Text>
              <Text style={styles.settingDesc}>{f.desc}</Text>
            </View>
            <TextInput
              style={styles.input}
              value={String(local[f.key] || '')}
              onChangeText={v => setLocal(p => ({ ...p, [f.key]: parseFloat(v) || 0 }))}
              keyboardType="numeric"
              placeholderTextColor={colors.text3}
            />
          </View>
        ))}
      </View>

      {/* Analysis Settings */}
      <View style={[card, { marginHorizontal: 16 }]}>
        <Text style={styles.cardTitle}>Analysis Settings</Text>
        {[
          { label: 'Analysis Interval (min)', key: 'interval_minutes', desc: 'How often AI runs analysis' },
          { label: 'Bullish Threshold', key: 'bullish_threshold', desc: 'Score to trigger buy signal (0-1)' },
          { label: 'Bearish Threshold', key: 'bearish_threshold', desc: 'Score to trigger sell signal (-1-0)' },
        ].map(f => (
          <View key={f.key} style={styles.inputRow}>
            <View style={{ flex: 1 }}>
              <Text style={styles.settingLabel}>{f.label}</Text>
              <Text style={styles.settingDesc}>{f.desc}</Text>
            </View>
            <TextInput
              style={styles.input}
              value={String(local[f.key] || '')}
              onChangeText={v => setLocal(p => ({ ...p, [f.key]: parseFloat(v) || 0 }))}
              keyboardType="numeric"
              placeholderTextColor={colors.text3}
            />
          </View>
        ))}
      </View>

      {/* Save Button */}
      <View style={{ paddingHorizontal: 16, marginBottom: 32 }}>
        <TouchableOpacity style={[styles.saveBtn, saving && { opacity: 0.6 }]} onPress={save} disabled={saving}>
          <Text style={styles.saveBtnText}>{saving ? 'Saving...' : 'Save Settings'}</Text>
        </TouchableOpacity>
        {status ? <Text style={[styles.statusMsg, { color: status === 'Saved!' ? colors.green : colors.red }]}>{status}</Text> : null}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  cardTitle: { fontSize: 11, color: colors.text3, textTransform: 'uppercase', letterSpacing: 1.5, fontWeight: '600', marginBottom: 12 },
  settingRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 },
  settingLabel: { fontSize: 14, color: colors.text, fontWeight: '500' },
  settingDesc: { fontSize: 11, color: colors.text3, marginTop: 2 },
  warnBox: { backgroundColor: 'rgba(239,68,68,.1)', borderRadius: 8, padding: 10, borderWidth: 1, borderColor: colors.red + '44' },
  warnText: { color: colors.red, fontSize: 12, fontWeight: '600' },
  symbolGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  symbolBtn: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bg3 },
  symbolBtnActive: { borderColor: colors.accent, backgroundColor: 'rgba(0,212,255,.1)' },
  symbolText: { fontSize: 13, color: colors.text2, fontWeight: '600' },
  symbolTextActive: { color: colors.accent },
  inputRow: { flexDirection: 'row', alignItems: 'center', marginBottom: 14 },
  input: { width: 80, backgroundColor: colors.bg3, color: colors.text, borderRadius: 8, borderWidth: 1, borderColor: colors.border, padding: 8, fontSize: 14, textAlign: 'center', fontWeight: '600' },
  saveBtn: { backgroundColor: colors.accent2, borderRadius: 12, padding: 16, alignItems: 'center', marginTop: 8 },
  saveBtnText: { color: '#fff', fontSize: 16, fontWeight: '700' },
  statusMsg: { textAlign: 'center', marginTop: 8, fontSize: 14, fontWeight: '600' },
});
