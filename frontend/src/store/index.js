import { create } from 'zustand'

export const useAlchemyStore = create((set, get) => ({
  // ── Connection ──
  connected: false,
  setConnected: (v) => set({ connected: v }),

  // ── Live Prices ──
  livePrices: {},
  updatePrice: (symbol, data) => set(s => ({
    livePrices: { ...s.livePrices, [symbol]: data }
  })),

  // ── Signals ──
  signals: [],
  addSignal: (sig) => set(s => ({ signals: [sig, ...s.signals].slice(0, 100) })),
  clearSignals: () => set({ signals: [] }),

  // ── Risk ──
  riskStatus: null,
  emergencyStop: false,
  setRiskStatus: (r) => set({ riskStatus: r, emergencyStop: r?.emergency_stop || false }),

  // ── Broker ──
  activeBroker: 'paper',
  setActiveBroker: (b) => set({ activeBroker: b }),

  // ── Portfolio ──
  portfolioNAV: 0,
  portfolioPnL: 0,
  openPositions: [],
  setPortfolio: (nav, pnl, positions) => set({ portfolioNAV: nav, portfolioPnL: pnl, openPositions: positions }),

  // ── Notifications (with proper unread tracking) ──
  notifications: [],
  unreadCount: 0,

  addNotification: (n) => set(s => {
    const updated = [n, ...s.notifications].slice(0, 50)
    return { notifications: updated, unreadCount: s.unreadCount + 1 }
  }),

  markAllNotificationsRead: () => set({ unreadCount: 0 }),

  clearNotifications: () => set({ notifications: [], unreadCount: 0 }),
}))
