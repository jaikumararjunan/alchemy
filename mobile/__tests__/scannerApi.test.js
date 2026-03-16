/**
 * Tests for Contract Scanner API methods.
 */
global.fetch = jest.fn();
import api from '../src/services/api';

describe('Scanner API methods', () => {
  beforeEach(() => jest.clearAllMocks());
  const mockOk  = (data) => fetch.mockResolvedValueOnce({ ok: true,  json: async () => data });
  const mockFail = ()     => fetch.mockResolvedValueOnce({ ok: false, status: 500 });

  test('scanContracts exists as function', () => {
    expect(typeof api.scanContracts).toBe('function');
  });

  test('scanContracts calls /api/scanner/scan without symbols', async () => {
    mockOk({ total_scanned: 10, ranked_contracts: [] });
    await api.scanContracts();
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/api/scanner/scan'));
  });

  test('scanContracts encodes symbol list in URL', async () => {
    mockOk({ total_scanned: 3 });
    await api.scanContracts(['BTCUSD', 'ETHUSD', 'SOLUSD']);
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('symbols=BTCUSD%2CETHUSD%2CSOLUSD')
    );
  });

  test('scanContracts returns parsed result', async () => {
    const mock = {
      total_scanned: 10, total_actionable: 4,
      market_summary: 'Scanned 10 contracts: 3 BUY / 1 SELL.',
      scan_duration_seconds: 2.1,
      ranked_contracts: [{ symbol: 'SOLUSD', rank: 1, composite_score: 0.45, action: 'BUY' }],
      top_opportunities: [{ symbol: 'SOLUSD', action: 'BUY', confidence: 0.72 }],
    };
    mockOk(mock);
    const r = await api.scanContracts();
    expect(r.total_scanned).toBe(10);
    expect(r.top_opportunities[0].symbol).toBe('SOLUSD');
  });

  test('scanContracts throws on HTTP error', async () => {
    mockFail();
    await expect(api.scanContracts()).rejects.toThrow();
  });

  test('getScannerContracts exists as function', () => {
    expect(typeof api.getScannerContracts).toBe('function');
  });

  test('getScannerContracts calls /api/scanner/contracts', async () => {
    mockOk({ watch_list: ['BTCUSD', 'ETHUSD'], total: 2 });
    await api.getScannerContracts();
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/api/scanner/contracts'));
  });

  test('getScannerContracts returns watch list', async () => {
    mockOk({ watch_list: ['BTCUSD', 'ETHUSD', 'SOLUSD'], total: 3, top_contracts_to_trade: 3 });
    const r = await api.getScannerContracts();
    expect(r.total).toBe(3);
    expect(r.watch_list).toContain('BTCUSD');
  });

  test('getScannerTop exists as function', () => {
    expect(typeof api.getScannerTop).toBe('function');
  });

  test('getScannerTop calls /api/scanner/top with n param', async () => {
    mockOk({ top_opportunities: [] });
    await api.getScannerTop(3);
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/api/scanner/top?n=3'));
  });

  test('getScannerTop returns top opportunities', async () => {
    mockOk({
      top_opportunities: [
        { symbol: 'ETHUSD', action: 'BUY', composite_score: 0.52, confidence: 0.75 },
        { symbol: 'SOLUSD', action: 'SELL', composite_score: -0.38, confidence: 0.65 },
      ],
      total_scanned: 10, total_actionable: 5,
    });
    const r = await api.getScannerTop(5);
    expect(r.top_opportunities).toHaveLength(2);
    expect(r.top_opportunities[0].symbol).toBe('ETHUSD');
  });
});
