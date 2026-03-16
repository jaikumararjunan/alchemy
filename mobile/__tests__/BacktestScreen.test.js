/**
 * Tests for BacktestScreen component.
 */
import React from 'react';
import { render, fireEvent, act, waitFor } from '@testing-library/react-native';
import BacktestScreen from '../src/screens/BacktestScreen';

// ── Shared mock backtest result ───────────────────────────────────────────────
const mockResult = {
  symbol: 'BTCUSD',
  timeframe: '1h',
  total_bars: 500,
  initial_balance: 10000,
  final_balance: 11842.5,
  summary: 'Return: +18.43% | Ann: +134.20% | Sharpe: 1.82 | Sortino: 2.41 | MaxDD: 8.12% | WinRate: 54.2% | PF: 1.68 | Trades: 24',
  trades: [
    {
      symbol: 'BTCUSD', side: 'long', entry_bar: 60, exit_bar: 68,
      entry_price: 67100, exit_price: 70050,
      size_usd: 500, leverage: 5, pnl_usd: 108.2, pnl_pct: 21.64,
      fee_usd: 16.8, exit_reason: 'tp', signal_score: 0.38, duration_bars: 8,
    },
    {
      symbol: 'BTCUSD', side: 'short', entry_bar: 90, exit_bar: 95,
      entry_price: 69800, exit_price: 71200,
      size_usd: 500, leverage: 5, pnl_usd: -118.5, pnl_pct: -23.7,
      fee_usd: 17.5, exit_reason: 'sl', signal_score: -0.31, duration_bars: 5,
    },
  ],
  equity_curve: Array.from({ length: 500 }, (_, i) => 10000 + i * 3.68 + Math.sin(i / 20) * 150),
  drawdown_curve: Array.from({ length: 500 }, (_, i) => Math.max(0, 2.5 * Math.sin(i / 60))),
  metrics: {
    initial_balance: 10000,
    final_balance: 11842.5,
    total_return_pct: 18.425,
    annualized_return_pct: 134.2,
    sharpe_ratio: 1.82,
    sortino_ratio: 2.41,
    calmar_ratio: 2.27,
    max_drawdown_pct: 8.12,
    max_drawdown_usd: 812.0,
    avg_drawdown_pct: 1.3,
    recovery_factor: 2.27,
    total_trades: 24,
    winning_trades: 13,
    losing_trades: 11,
    win_rate_pct: 54.17,
    profit_factor: 1.68,
    expectancy_usd: 76.77,
    avg_win_usd: 142.3,
    avg_loss_usd: -98.6,
    avg_win_pct: 28.46,
    avg_loss_pct: -19.72,
    best_trade_usd: 225.0,
    worst_trade_usd: -118.5,
    best_trade_pct: 45.0,
    worst_trade_pct: -23.7,
    max_consecutive_wins: 4,
    max_consecutive_losses: 3,
    total_bars: 500,
    trading_days: 20.8,
    avg_trade_duration_bars: 9.2,
  },
  config_used: {
    symbol: 'BTCUSD', timeframe: '1h',
    initial_balance: 10000, position_size_usd: 500,
    stop_loss_pct: 2.0, take_profit_pct: 4.5,
    leverage: 5, taker_fee_pct: 0.05,
    slippage_pct: 0.02, warmup_bars: 50, total_candles: 500,
  },
};

const mockDefaults = {
  symbol: 'BTCUSD', timeframe: '1h',
  initial_balance: 10000, position_size_usd: 500,
  stop_loss_pct: 2.0, take_profit_pct: 4.5, leverage: 5,
  warmup_bars: 50, candle_count: 500,
  available_timeframes: ['5m', '15m', '1h', '4h', '1d'],
  available_symbols: ['BTCUSD', 'ETHUSD', 'SOLUSD'],
};

// ── Mock api service ──────────────────────────────────────────────────────────
jest.mock('../src/services/api', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn() },
}));

// ── Mock navigation ───────────────────────────────────────────────────────────
jest.mock('@react-navigation/native', () => ({
  useFocusEffect: () => {},  // no-op to avoid async state updates outside act
  useNavigation: () => ({ navigate: jest.fn() }),
}));

// ── Tests ─────────────────────────────────────────────────────────────────────
describe('BacktestScreen', () => {
  beforeEach(() => {
    const api = require('../src/services/api').default;
    api.get.mockImplementation((path) => {
      if (path.includes('/api/backtest/defaults')) return Promise.resolve(mockDefaults);
      return Promise.resolve({});
    });
    api.post.mockImplementation((path) => {
      if (path.includes('/api/backtest/run')) return Promise.resolve(mockResult);
      return Promise.resolve({});
    });
  });

  test('renders without crashing', () => {
    const { getByText } = render(<BacktestScreen />);
    expect(getByText('Backtester')).toBeTruthy();
  });

  test('shows Configuration section', () => {
    const { getByText } = render(<BacktestScreen />);
    expect(getByText('Configuration')).toBeTruthy();
  });

  test('shows timeframe selector buttons', () => {
    const { getByText } = render(<BacktestScreen />);
    expect(getByText('5m')).toBeTruthy();
    expect(getByText('15m')).toBeTruthy();
    expect(getByText('1h')).toBeTruthy();
    expect(getByText('4h')).toBeTruthy();
    expect(getByText('1d')).toBeTruthy();
  });

  test('shows SL and TP labels', () => {
    const { getByText } = render(<BacktestScreen />);
    expect(getByText('SL %')).toBeTruthy();
    expect(getByText('TP %')).toBeTruthy();
  });

  test('shows Balance and Position labels', () => {
    const { getByText } = render(<BacktestScreen />);
    expect(getByText('Balance ($)')).toBeTruthy();
    expect(getByText('Position ($)')).toBeTruthy();
  });

  test('shows Leverage and Candles labels', () => {
    const { getByText } = render(<BacktestScreen />);
    expect(getByText('Leverage')).toBeTruthy();
    expect(getByText('Candles')).toBeTruthy();
  });

  test('shows Run Backtest button', () => {
    const { getByText } = render(<BacktestScreen />);
    expect(getByText('Run Backtest')).toBeTruthy();
  });

  test('shows result summary after run', async () => {
    const { getByText } = render(<BacktestScreen />);
    const btn = getByText('Run Backtest');
    await act(async () => { fireEvent.press(btn); });
    await act(async () => {});
    expect(getByText(/Return: \+18\.43%/)).toBeTruthy();
  });

  test('shows Performance Metrics tab after run', async () => {
    const { getByText } = render(<BacktestScreen />);
    await act(async () => { fireEvent.press(getByText('Run Backtest')); });
    await act(async () => {});
    expect(getByText('Performance Metrics')).toBeTruthy();
  });

  test('shows total return metric', async () => {
    const { getByText } = render(<BacktestScreen />);
    await act(async () => { fireEvent.press(getByText('Run Backtest')); });
    await act(async () => {});
    expect(getByText('Total Return')).toBeTruthy();
    expect(getByText('+18.425%')).toBeTruthy();
  });

  test('shows Sharpe ratio metric', async () => {
    const { getByText } = render(<BacktestScreen />);
    await act(async () => { fireEvent.press(getByText('Run Backtest')); });
    await act(async () => {});
    expect(getByText('Sharpe Ratio')).toBeTruthy();
    expect(getByText('1.820')).toBeTruthy();
  });

  test('shows Sortino ratio metric', async () => {
    const { getByText } = render(<BacktestScreen />);
    await act(async () => { fireEvent.press(getByText('Run Backtest')); });
    await act(async () => {});
    expect(getByText('Sortino Ratio')).toBeTruthy();
    expect(getByText('2.410')).toBeTruthy();
  });

  test('shows Max Drawdown metric', async () => {
    const { getByText } = render(<BacktestScreen />);
    await act(async () => { fireEvent.press(getByText('Run Backtest')); });
    await act(async () => {});
    expect(getByText('Max Drawdown')).toBeTruthy();
    expect(getByText('8.12%')).toBeTruthy();
  });

  test('shows Win Rate metric', async () => {
    const { getByText } = render(<BacktestScreen />);
    await act(async () => { fireEvent.press(getByText('Run Backtest')); });
    await act(async () => {});
    expect(getByText('Win Rate')).toBeTruthy();
    expect(getByText('54.2%')).toBeTruthy();
  });

  test('shows Profit Factor metric', async () => {
    const { getByText } = render(<BacktestScreen />);
    await act(async () => { fireEvent.press(getByText('Run Backtest')); });
    await act(async () => {});
    expect(getByText('Profit Factor')).toBeTruthy();
    expect(getByText('1.680')).toBeTruthy();
  });

  test('shows tab bar after result', async () => {
    const { getByText, getAllByText } = render(<BacktestScreen />);
    await act(async () => { fireEvent.press(getByText('Run Backtest')); });
    await act(async () => {});
    expect(getByText('Metrics')).toBeTruthy();
    expect(getAllByText('Trades').length).toBeGreaterThanOrEqual(1);
    expect(getByText('Equity')).toBeTruthy();
  });

  test('switches to Trades tab and shows trade log', async () => {
    const { getByText, getAllByText } = render(<BacktestScreen />);
    await act(async () => { fireEvent.press(getByText('Run Backtest')); });
    await act(async () => {});
    fireEvent.press(getAllByText('Trades')[0]);
    expect(getByText(/Trade Log/)).toBeTruthy();
  });

  test('shows winning trade with TP exit reason', async () => {
    const { getByText, getAllByText } = render(<BacktestScreen />);
    await act(async () => { fireEvent.press(getByText('Run Backtest')); });
    await act(async () => {});
    fireEvent.press(getAllByText('Trades')[0]);
    expect(getAllByText(/TP/).length).toBeGreaterThanOrEqual(1);
  });

  test('shows losing trade with SL exit reason', async () => {
    const { getByText, getAllByText } = render(<BacktestScreen />);
    await act(async () => { fireEvent.press(getByText('Run Backtest')); });
    await act(async () => {});
    fireEvent.press(getAllByText('Trades')[0]);
    expect(getAllByText(/SL/).length).toBeGreaterThanOrEqual(1);
  });

  test('switches to Equity tab and shows equity curve', async () => {
    const { getByText } = render(<BacktestScreen />);
    await act(async () => { fireEvent.press(getByText('Run Backtest')); });
    await act(async () => {});
    fireEvent.press(getByText('Equity'));
    expect(getByText('Equity Curve')).toBeTruthy();
    expect(getByText(/Start: \$10000\.00/)).toBeTruthy();
  });

  test('selects different timeframe when pressed', () => {
    const { getByText } = render(<BacktestScreen />);
    fireEvent.press(getByText('4h'));
    expect(getByText('4h')).toBeTruthy();
  });

  test('shows Calmar ratio metric', async () => {
    const { getByText, getAllByText } = render(<BacktestScreen />);
    await act(async () => { fireEvent.press(getByText('Run Backtest')); });
    await waitFor(() => expect(getByText('Calmar Ratio')).toBeTruthy());
    expect(getAllByText('2.270').length).toBeGreaterThanOrEqual(1);
  });

  test('shows Max Consecutive Wins metric', async () => {
    const { getByText } = render(<BacktestScreen />);
    await act(async () => { fireEvent.press(getByText('Run Backtest')); });
    await act(async () => {});
    expect(getByText('Max Consec. Wins')).toBeTruthy();
    expect(getByText('4')).toBeTruthy();
  });

  test('shows final balance', async () => {
    const { getByText } = render(<BacktestScreen />);
    await act(async () => { fireEvent.press(getByText('Run Backtest')); });
    await act(async () => {});
    expect(getByText('$11842.50')).toBeTruthy();
  });
});
