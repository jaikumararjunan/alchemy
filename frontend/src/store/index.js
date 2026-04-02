import { create } from 'zustand'

export const useAlchemyStore = create((set, get) => ({
  // ── Connection ──────────────────────────────────────────────────────────────
  connected:   false,
  env:         'paper',
  setConnected: (v) => set({ connected: v }),

  // ── Live Prices (WebSocket) ─────────────────────────────────────────────────
  livePrices: {},
  updatePrice: (symbol, data) => set(s => ({
    livePrices: { ...s.livePrices, [symbol]: data }
  })),

  // ── Signals ─────────────────────────────────────────────────────────────────
  signals: [],
  addSignal: (sig) => set(s => ({ signals: [sig, ...s.signals].slice(0, 100) })),
  clearSignals: () => set({ signals: [] }),

  // ── Risk ────────────────────────────────────────────────────────────────────
  riskStatus: null,
  emergencyStop: false,
  setRiskStatus: (r) => set({ riskStatus: r, emergencyStop: r?.emergency_stop || false }),

  // ── Crypto Mode ─────────────────────────────────────────────────────────────
  activeBroker: 'paper',          // paper | ib | kite | delta | binance
  setActiveBroker: (b) => set({ activeBroker: b }),

  // ── Portfolio ────────────────────────────────────────────────────────────────
  portfolioNAV:    0,
  portfolioPnL:    0,
  openPositions:   [],
  setPortfolio: (nav, pnl, positions) => set({ portfolioNAV: nav, portfolioPnL: pnl, openPositions: positions }),

  // ── Notifications ─────────────────────────────────────────────────────────
  notifications: [],
  addNotification: (n) => set(s => ({ notifications: [n, ...s.notifications].slice(0, 50) })),
}))
