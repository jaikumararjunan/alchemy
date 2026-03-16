/**
 * Tests for the BacktestScreen Optimizer functionality.
 */
import React from 'react';
import { render, fireEvent, act } from '@testing-library/react-native';
import BacktestScreen from '../src/screens/BacktestScreen';

// ── Mock optimizer result ──────────────────────────────────────────────────
const mockOptResult = {
  symbol: 'BTCUSD',
  timeframe: '1h',
  total_combinations: 9,
  valid_combinations: 7,
  sort_metric: 'sharpe_ratio',
  best_params: {
    stop_loss_pct: 2.0,
    take_profit_pct: 4.5,
    leverage: 5,
    position_size_pct: 5.0,
    position_size_usd: 500.0,
  },
  best_metrics: {
    total_return_pct: 22.4,
    annualized_return_pct: 165.3,
    sharpe_ratio: 2.11,
    sortino_ratio: 2.88,
    calmar_ratio: 2.65,
    max_drawdown_pct: 8.45,
    max_drawdown_usd: 845.0,
    avg_drawdown_pct: 1.5,
    recovery_factor: 2.65,
    total_trades: 26,
    winning_trades: 15,
    losing_trades: 11,
    win_rate_pct: 57.69,
    profit_factor: 1.92,
    expectancy_usd: 86.15,
    avg_win_usd: 155.0,
    avg_loss_usd: -105.2,
    avg_win_pct: 31.0,
    avg_loss_pct: -21.0,
    best_trade_usd: 240.0,
    worst_trade_usd: -130.0,
    best_trade_pct: 48.0,
    worst_trade_pct: -26.0,
    max_consecutive_wins: 5,
    max_consecutive_losses: 3,
    total_bars: 500,
    trading_days: 20.8,
    avg_trade_duration_bars: 8.5,
  },
  results: [
    {
      params: { stop_loss_pct: 2.0, take_profit_pct: 4.5, leverage: 5, position_size_pct: 5.0, position_size_usd: 500 },
      total_return_pct: 22.4, sharpe_ratio: 2.11, sortino_ratio: 2.88, calmar_ratio: 2.65,
      max_drawdown_pct: 8.45, win_rate_pct: 57.69, profit_factor: 1.92, total_trades: 26,
    },
    {
      params: { stop_loss_pct: 1.5, take_profit_pct: 3.5, leverage: 5, position_size_pct: 5.0, position_size_usd: 500 },
      total_return_pct: 18.1, sharpe_ratio: 1.75, sortino_ratio: 2.20, calmar_ratio: 1.95,
      max_drawdown_pct: 9.28, win_rate_pct: 53.8, profit_factor: 1.65, total_trades: 31,
    },
    {
      params: { stop_loss_pct: 2.5, take_profit_pct: 6.0, leverage: 5, position_size_pct: 5.0, position_size_usd: 500 },
      total_return_pct: 15.2, sharpe_ratio: 1.42, sortino_ratio: 1.90, calmar_ratio: 1.55,
      max_drawdown_pct: 9.81, win_rate_pct: 51.2, profit_factor: 1.48, total_trades: 20,
    },
  ],
};

// ── Backtest mock result (re-used from BacktestScreen.test.js) ────────────
const mockBtResult = {
  symbol: 'BTCUSD', timeframe: '1h', total_bars: 500,
  initial_balance: 10000, final_balance: 11842.5,
  summary: 'Return: +18.43% | Ann: +134.20% | Sharpe: 1.82 | Sortino: 2.41 | MaxDD: 8.12% | WinRate: 54.2% | PF: 1.68 | Trades: 24',
  trades: [], equity_curve: [10000, 10500, 11000, 11500, 11842.5],
  drawdown_curve: [0, 0.5, 0.2, 0.1, 0],
  metrics: {
    initial_balance: 10000, final_balance: 11842.5,
    total_return_pct: 18.425, annualized_return_pct: 134.2,
    sharpe_ratio: 1.82, sortino_ratio: 2.41, calmar_ratio: 2.27,
    max_drawdown_pct: 8.12, max_drawdown_usd: 812.0, avg_drawdown_pct: 1.3,
    recovery_factor: 2.27, total_trades: 24, winning_trades: 13, losing_trades: 11,
    win_rate_pct: 54.17, profit_factor: 1.68, expectancy_usd: 76.77,
    avg_win_usd: 142.3, avg_loss_usd: -98.6, avg_win_pct: 28.46, avg_loss_pct: -19.72,
    best_trade_usd: 225.0, worst_trade_usd: -118.5, best_trade_pct: 45.0, worst_trade_pct: -23.7,
    max_consecutive_wins: 4, max_consecutive_losses: 3, total_bars: 500,
    trading_days: 20.8, avg_trade_duration_bars: 9.2,
  },
  config_used: {},
};

// ── Mock api ─────────────────────────────────────────────────────────────────
jest.mock('../src/services/api', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn() },
}));

jest.mock('@react-navigation/native', () => ({
  useFocusEffect: () => {},
  useNavigation: () => ({ navigate: jest.fn() }),
}));

describe('BacktestScreen Optimizer', () => {
  beforeEach(() => {
    const api = require('../src/services/api').default;
    api.get.mockResolvedValue({});
    api.post.mockImplementation((path) => {
      if (path.includes('/api/backtest/run'))      return Promise.resolve(mockBtResult);
      if (path.includes('/api/backtest/optimize')) return Promise.resolve(mockOptResult);
      return Promise.resolve({});
    });
  });

  test('shows Optimize button', () => {
    const { getByText } = render(<BacktestScreen />);
    expect(getByText('Optimize')).toBeTruthy();
  });

  test('shows optimizer results after clicking Optimize', async () => {
    const { getByText } = render(<BacktestScreen />);
    await act(async () => { fireEvent.press(getByText('Optimize')); });
    await act(async () => {});
    expect(getByText(/Optimizer Results/)).toBeTruthy();
  });

  test('shows valid/total combination count', async () => {
    const { getByText } = render(<BacktestScreen />);
    await act(async () => { fireEvent.press(getByText('Optimize')); });
    await act(async () => {});
    expect(getByText(/7\/9 valid/)).toBeTruthy();
  });

  test('shows Best Params section', async () => {
    const { getByText } = render(<BacktestScreen />);
    await act(async () => { fireEvent.press(getByText('Optimize')); });
    await act(async () => {});
    expect(getByText(/Best Params/)).toBeTruthy();
  });

  test('shows best SL parameter chip', async () => {
    const { getByText } = render(<BacktestScreen />);
    await act(async () => { fireEvent.press(getByText('Optimize')); });
    await act(async () => {});
    expect(getByText('SL 2%')).toBeTruthy();
  });

  test('shows best TP parameter chip', async () => {
    const { getByText } = render(<BacktestScreen />);
    await act(async () => { fireEvent.press(getByText('Optimize')); });
    await act(async () => {});
    expect(getByText('TP 4.5%')).toBeTruthy();
  });

  test('shows best leverage chip', async () => {
    const { getByText } = render(<BacktestScreen />);
    await act(async () => { fireEvent.press(getByText('Optimize')); });
    await act(async () => {});
    expect(getByText('5x')).toBeTruthy();
  });

  test('shows best return stat', async () => {
    const { getByText } = render(<BacktestScreen />);
    await act(async () => { fireEvent.press(getByText('Optimize')); });
    await act(async () => {});
    expect(getByText('+22.40%')).toBeTruthy();
  });

  test('shows best Sharpe stat', async () => {
    const { getAllByText } = render(<BacktestScreen />);
    await act(async () => { fireEvent.press(getAllByText('Optimize')[0]); });
    await act(async () => {});
    expect(getAllByText('2.11').length).toBeGreaterThanOrEqual(1);
  });

  test('shows best max drawdown stat', async () => {
    const { getByText } = render(<BacktestScreen />);
    await act(async () => { fireEvent.press(getByText('Optimize')); });
    await act(async () => {});
    expect(getByText('8.4%')).toBeTruthy();
  });

  test('shows top ranked combo #1', async () => {
    const { getByText } = render(<BacktestScreen />);
    await act(async () => { fireEvent.press(getByText('Optimize')); });
    await act(async () => {});
    expect(getByText('#1')).toBeTruthy();
  });

  test('shows top ranked combo params', async () => {
    const { getByText } = render(<BacktestScreen />);
    await act(async () => { fireEvent.press(getByText('Optimize')); });
    await act(async () => {});
    expect(getByText(/SL 2% · TP 4.5%/)).toBeTruthy();
  });

  test('shows second ranked combo', async () => {
    const { getByText } = render(<BacktestScreen />);
    await act(async () => { fireEvent.press(getByText('Optimize')); });
    await act(async () => {});
    expect(getByText('#2')).toBeTruthy();
  });

  test('shows return in ranked row', async () => {
    const { getByText } = render(<BacktestScreen />);
    await act(async () => { fireEvent.press(getByText('Optimize')); });
    await act(async () => {});
    expect(getByText(/\+22\.40% ret/)).toBeTruthy();
  });

  test('shows sort metric score for best combo', async () => {
    const { getAllByText } = render(<BacktestScreen />);
    await act(async () => { fireEvent.press(getAllByText('Optimize')[0]); });
    await act(async () => {});
    expect(getAllByText('2.110').length).toBeGreaterThanOrEqual(1);
  });

  test('optimizer and backtest can both run independently', async () => {
    const { getByText } = render(<BacktestScreen />);
    await act(async () => { fireEvent.press(getByText('Run Backtest')); });
    await act(async () => {});
    expect(getByText(/Return: \+18\.43%/)).toBeTruthy();
    await act(async () => { fireEvent.press(getByText('Optimize')); });
    await act(async () => {});
    expect(getByText(/Optimizer Results/)).toBeTruthy();
  });
});
