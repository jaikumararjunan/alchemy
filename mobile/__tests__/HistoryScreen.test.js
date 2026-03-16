/**
 * Tests for HistoryScreen component.
 */
import React from 'react';
import { render, fireEvent, act, waitFor } from '@testing-library/react-native';
import HistoryScreen from '../src/screens/HistoryScreen';

// ── Mock navigation: replace useFocusEffect with a useEffect that fires once ──
jest.mock('@react-navigation/native', () => {
  const React = require('react');
  return {
    useFocusEffect: (cb) => {
      React.useEffect(() => { cb(); }, []);
    },
  };
});

// ── Mock api service ──────────────────────────────────────────────────────────
jest.mock('../src/services/api', () => ({
  __esModule: true,
  default: {
    getHistoryTrades: jest.fn(),
    getHistoryDecisions: jest.fn(),
    getHistoryEquity: jest.fn(),
  },
}));

// ── Shared mock data ──────────────────────────────────────────────────────────
const mockTrades = {
  total: 3,
  trades: [
    {
      symbol: 'BTCUSD', side: 'buy',
      entry_price: 67100, exit_price: 70050,
      pnl_usd: 108.2, pnl_pct: 4.35,
      fee_usd: 16.8, exit_reason: 'tp',
      ts: '2026-01-15T10:30:00Z', dry_run: false,
    },
    {
      symbol: 'ETHUSD', side: 'sell',
      entry_price: 3500, exit_price: 3200,
      pnl_usd: -85.5, pnl_pct: -8.55,
      fee_usd: 12.0, exit_reason: 'sl',
      ts: '2026-01-14T08:00:00Z', dry_run: true,
    },
    {
      symbol: 'SOLUSD', side: 'buy',
      entry_price: 185.5, exit_price: 193.2,
      pnl_usd: 38.5, pnl_pct: 4.15,
      fee_usd: 5.5, exit_reason: 'tp',
      ts: '2026-01-13T14:00:00Z', dry_run: false,
    },
  ],
  stats: {
    total_trades: 3,
    winning_trades: 2,
    losing_trades: 1,
    win_rate_pct: 66.67,
    total_pnl_usd: 61.2,
    total_fees_usd: 34.3,
    best_trade_usd: 108.2,
    worst_trade_usd: -85.5,
    avg_pnl_usd: 20.4,
  },
};

const mockDecisions = {
  total: 4,
  decisions: [
    {
      symbol: 'BTCUSD', action: 'BUY', cycle: 42,
      confidence: 0.78, reasoning: 'Strong uptrend with bullish momentum',
      signal_score: 0.41, adx: 32.5, market_regime: 'trending',
      ts: '2026-01-15T10:00:00Z', dry_run: false,
    },
    {
      symbol: 'ETHUSD', action: 'SELL', cycle: 41,
      confidence: 0.65, reasoning: 'Bearish divergence detected',
      signal_score: -0.38, adx: 28.0, market_regime: 'volatile',
      ts: '2026-01-14T09:00:00Z', dry_run: true,
    },
    {
      symbol: 'BTCUSD', action: 'HOLD', cycle: 40,
      confidence: 0.50, reasoning: null,
      signal_score: 0.05, adx: 18.0, market_regime: 'ranging',
      ts: '2026-01-13T08:00:00Z', dry_run: false,
    },
  ],
  action_counts: { BUY: 1, SELL: 1, HOLD: 1 },
};

const mockEquity = {
  total: 5,
  latest: {
    balance: 10842.5,
    total_equity: 11092.5,
    unrealized_pnl: 250.0,
    open_positions: 2,
    ts: '2026-01-15T10:30:00Z',
  },
  snapshots: [
    { balance: 10842.5, ts: '2026-01-15T10:30:00Z' },
    { balance: 10750.0, ts: '2026-01-15T09:00:00Z' },
    { balance: 10620.0, ts: '2026-01-14T10:00:00Z' },
    { balance: 10500.0, ts: '2026-01-13T10:00:00Z' },
    { balance: 10000.0, ts: '2026-01-12T10:00:00Z' },
  ],
};

// ── Setup ─────────────────────────────────────────────────────────────────────
beforeEach(() => {
  const api = require('../src/services/api').default;
  api.getHistoryTrades.mockResolvedValue(mockTrades);
  api.getHistoryDecisions.mockResolvedValue(mockDecisions);
  api.getHistoryEquity.mockResolvedValue(mockEquity);
});

afterEach(() => {
  jest.clearAllMocks();
});

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('HistoryScreen', () => {

  // ── Basic rendering ────────────────────────────────────────────────────────

  test('renders History title', () => {
    const { getByText } = render(<HistoryScreen />);
    expect(getByText('History')).toBeTruthy();
  });

  test('renders three tab buttons', () => {
    const { getByText } = render(<HistoryScreen />);
    expect(getByText('Trades')).toBeTruthy();
    expect(getByText('Decisions')).toBeTruthy();
    expect(getByText('Equity')).toBeTruthy();
  });

  // ── Trades Tab (default) ───────────────────────────────────────────────────

  test('shows Trade Statistics section after load', async () => {
    const { getByText } = render(<HistoryScreen />);
    await waitFor(() => expect(getByText('Trade Statistics')).toBeTruthy());
  });

  test('shows Recent Trades count', async () => {
    const { getByText } = render(<HistoryScreen />);
    await waitFor(() => expect(getByText('Recent Trades (3)')).toBeTruthy());
  });

  test('shows trade symbol BTCUSD', async () => {
    const { getAllByText } = render(<HistoryScreen />);
    await waitFor(() => expect(getAllByText('BTCUSD').length).toBeGreaterThanOrEqual(1));
  });

  test('shows trade side BUY', async () => {
    const { getAllByText } = render(<HistoryScreen />);
    await waitFor(() => expect(getAllByText('BUY').length).toBeGreaterThanOrEqual(1));
  });

  test('shows trade exit reason TP', async () => {
    const { getAllByText } = render(<HistoryScreen />);
    await waitFor(() => expect(getAllByText(/TP/).length).toBeGreaterThanOrEqual(1));
  });

  test('shows PAPER badge for dry-run trade', async () => {
    const { getAllByText } = render(<HistoryScreen />);
    await waitFor(() => expect(getAllByText('PAPER').length).toBeGreaterThanOrEqual(1));
  });

  test('shows win rate stat', async () => {
    const { getByText } = render(<HistoryScreen />);
    await waitFor(() => expect(getByText('66.7%')).toBeTruthy());
  });

  test('shows total PnL stat', async () => {
    const { getByText } = render(<HistoryScreen />);
    await waitFor(() => expect(getByText('$61.20')).toBeTruthy());
  });

  // ── Decisions Tab ──────────────────────────────────────────────────────────

  test('switches to Decisions tab', async () => {
    const { getByText } = render(<HistoryScreen />);
    await waitFor(() => expect(getByText('Trade Statistics')).toBeTruthy());
    fireEvent.press(getByText('Decisions'));
    expect(getByText('Decision Breakdown (4)')).toBeTruthy();
  });

  test('shows Recent Decisions section', async () => {
    const { getByText } = render(<HistoryScreen />);
    await waitFor(() => expect(getByText('Trade Statistics')).toBeTruthy());
    fireEvent.press(getByText('Decisions'));
    expect(getByText('Recent Decisions')).toBeTruthy();
  });

  test('shows decision symbol', async () => {
    const { getByText, getAllByText } = render(<HistoryScreen />);
    await waitFor(() => expect(getByText('Trade Statistics')).toBeTruthy());
    fireEvent.press(getByText('Decisions'));
    expect(getAllByText('BTCUSD').length).toBeGreaterThanOrEqual(1);
  });

  test('shows decision cycle number', async () => {
    const { getByText } = render(<HistoryScreen />);
    await waitFor(() => expect(getByText('Trade Statistics')).toBeTruthy());
    fireEvent.press(getByText('Decisions'));
    expect(getByText('· Cycle 42')).toBeTruthy();
  });

  test('shows decision reasoning', async () => {
    const { getByText } = render(<HistoryScreen />);
    await waitFor(() => expect(getByText('Trade Statistics')).toBeTruthy());
    fireEvent.press(getByText('Decisions'));
    expect(getByText('Strong uptrend with bullish momentum')).toBeTruthy();
  });

  test('shows PAPER badge in Decisions tab', async () => {
    const { getByText, getAllByText } = render(<HistoryScreen />);
    await waitFor(() => expect(getByText('Trade Statistics')).toBeTruthy());
    fireEvent.press(getByText('Decisions'));
    expect(getAllByText('PAPER').length).toBeGreaterThanOrEqual(1);
  });

  test('shows action counts in decision breakdown', async () => {
    const { getByText, getAllByText } = render(<HistoryScreen />);
    await waitFor(() => expect(getByText('Trade Statistics')).toBeTruthy());
    fireEvent.press(getByText('Decisions'));
    // BUY: 1, SELL: 1, HOLD: 1 in mockDecisions.action_counts
    expect(getAllByText('BUY').length).toBeGreaterThanOrEqual(1);
    expect(getAllByText('SELL').length).toBeGreaterThanOrEqual(1);
    expect(getAllByText('HOLD').length).toBeGreaterThanOrEqual(1);
  });

  // ── Equity Tab ─────────────────────────────────────────────────────────────

  test('switches to Equity tab', async () => {
    const { getByText } = render(<HistoryScreen />);
    await waitFor(() => expect(getByText('Trade Statistics')).toBeTruthy());
    fireEvent.press(getByText('Equity'));
    expect(getByText('Equity History (5 snapshots)')).toBeTruthy();
  });

  test('shows latest balance in Equity tab', async () => {
    const { getByText } = render(<HistoryScreen />);
    await waitFor(() => expect(getByText('Trade Statistics')).toBeTruthy());
    fireEvent.press(getByText('Equity'));
    expect(getByText('$10842.50')).toBeTruthy();
  });

  test('shows total equity in Equity tab', async () => {
    const { getByText } = render(<HistoryScreen />);
    await waitFor(() => expect(getByText('Trade Statistics')).toBeTruthy());
    fireEvent.press(getByText('Equity'));
    expect(getByText('$11092.50')).toBeTruthy();
  });

  test('shows unrealized PnL in Equity tab', async () => {
    const { getByText } = render(<HistoryScreen />);
    await waitFor(() => expect(getByText('Trade Statistics')).toBeTruthy());
    fireEvent.press(getByText('Equity'));
    expect(getByText('$250.00')).toBeTruthy();
  });

  test('shows Latest Balance label', async () => {
    const { getByText } = render(<HistoryScreen />);
    await waitFor(() => expect(getByText('Trade Statistics')).toBeTruthy());
    fireEvent.press(getByText('Equity'));
    expect(getByText('Latest Balance')).toBeTruthy();
  });

  // ── Empty states ───────────────────────────────────────────────────────────

  test('shows empty Trades message when api returns null', async () => {
    const api = require('../src/services/api').default;
    api.getHistoryTrades.mockResolvedValue(null);
    const { getByText } = render(<HistoryScreen />);
    await waitFor(() => expect(getByText('No trade history yet.')).toBeTruthy());
  });

  test('shows empty Decisions message when api returns null', async () => {
    const api = require('../src/services/api').default;
    api.getHistoryDecisions.mockResolvedValue(null);
    const { getByText } = render(<HistoryScreen />);
    await waitFor(() => expect(getByText('Trade Statistics')).toBeTruthy());
    fireEvent.press(getByText('Decisions'));
    expect(getByText('No decisions recorded yet.')).toBeTruthy();
  });

  test('shows empty Equity message when api returns null', async () => {
    const api = require('../src/services/api').default;
    api.getHistoryEquity.mockResolvedValue(null);
    const { getByText } = render(<HistoryScreen />);
    await waitFor(() => expect(getByText('Trade Statistics')).toBeTruthy());
    fireEvent.press(getByText('Equity'));
    expect(getByText('No equity history yet.')).toBeTruthy();
  });

  test('shows no-trades message when trades list empty', async () => {
    const api = require('../src/services/api').default;
    api.getHistoryTrades.mockResolvedValue({ total: 0, trades: [], stats: {} });
    const { getByText } = render(<HistoryScreen />);
    await waitFor(() => expect(getByText('No trades recorded yet.')).toBeTruthy());
  });

  test('shows no-decisions message when decisions list empty', async () => {
    const api = require('../src/services/api').default;
    api.getHistoryDecisions.mockResolvedValue({ total: 0, decisions: [], action_counts: {} });
    const { getByText } = render(<HistoryScreen />);
    await waitFor(() => expect(getByText('Trade Statistics')).toBeTruthy());
    fireEvent.press(getByText('Decisions'));
    expect(getByText('No decisions recorded yet.')).toBeTruthy();
  });

  test('shows no-equity-snapshots message when snapshots empty', async () => {
    const api = require('../src/services/api').default;
    api.getHistoryEquity.mockResolvedValue({ total: 0, latest: null, snapshots: [] });
    const { getByText } = render(<HistoryScreen />);
    await waitFor(() => expect(getByText('Trade Statistics')).toBeTruthy());
    fireEvent.press(getByText('Equity'));
    expect(getByText('No equity snapshots yet. Run the bot to record history.')).toBeTruthy();
  });

  // ── Tab switching ──────────────────────────────────────────────────────────

  test('can switch from Decisions back to Trades', async () => {
    const { getByText, getAllByText } = render(<HistoryScreen />);
    await waitFor(() => expect(getByText('Trade Statistics')).toBeTruthy());
    fireEvent.press(getByText('Decisions'));
    expect(getByText('Decision Breakdown (4)')).toBeTruthy();
    fireEvent.press(getAllByText('Trades')[0]);
    expect(getByText('Trade Statistics')).toBeTruthy();
  });

  test('can cycle through all three tabs', async () => {
    const { getByText, getAllByText } = render(<HistoryScreen />);
    await waitFor(() => expect(getByText('Trade Statistics')).toBeTruthy());
    fireEvent.press(getByText('Decisions'));
    expect(getByText('Recent Decisions')).toBeTruthy();
    fireEvent.press(getByText('Equity'));
    expect(getByText(/Equity History/)).toBeTruthy();
    fireEvent.press(getAllByText('Trades')[0]);
    expect(getByText('Trade Statistics')).toBeTruthy();
  });
});
