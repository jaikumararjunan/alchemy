import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.response.use(
  res => res.data,
  err => { console.error('[API]', err.response?.data || err.message); return Promise.reject(err) }
)

// ── Health ────────────────────────────────────────────────────────────────────
export const getHealth = () => api.get('/health')

// ── Signals (AI Agents) ───────────────────────────────────────────────────────
export const generateSignal = (payload) => api.post('/signal', payload)
export const getSignalHistory = (limit=50) => api.get(`/signals/history?limit=${limit}`)

// ── Portfolio ────────────────────────────────────────────────────────────────
export const getPortfolio    = () => api.get('/portfolio')
export const getPortfolioNAV = () => api.get('/portfolio/nav')
export const getPositions    = () => api.get('/portfolio/positions')
export const getTransactions = (days=30) => api.get(`/portfolio/transactions?days=${days}`)

// ── Risk ─────────────────────────────────────────────────────────────────────
export const getRiskStatus      = () => api.get('/risk/status')
export const triggerEmergencyStop = () => api.post('/risk/emergency-stop')
export const resetEmergencyStop = () => api.delete('/risk/emergency-stop')
export const blockTicker = (ticker) => api.post('/risk/block', { ticker })

// ── Analytics ────────────────────────────────────────────────────────────────
export const getMetrics        = (strategy, start, end) => api.get(`/analytics/metrics?strategy=${strategy}&start=${start}&end=${end}`)
export const getVolatility     = (symbol, market='NSE') => api.get(`/analytics/volatility/${symbol}?market=${market}`)
export const getTearSheet      = (strategy) => api.get(`/analytics/tearsheet/${strategy}`, { responseType: 'blob' })

// ── Crypto — Delta Exchange ───────────────────────────────────────────────────
export const getDeltaProducts      = () => api.get('/crypto/delta/products')
export const getDeltaTicker        = (symbol) => api.get(`/crypto/delta/ticker/${symbol}`)
export const getDeltaOrderbook     = (symbol) => api.get(`/crypto/delta/orderbook/${symbol}`)
export const getDeltaPositions     = () => api.get('/crypto/delta/positions')
export const getDeltaPlaceOrder    = (payload) => api.post('/crypto/delta/order', payload)
export const getDeltaBalance       = () => api.get('/crypto/delta/balance')
export const getDeltaFundingRate   = (symbol) => api.get(`/crypto/delta/funding/${symbol}`)

// ── Crypto — Binance ─────────────────────────────────────────────────────────
export const getBinanceTicker    = (symbol) => api.get(`/crypto/binance/ticker/${symbol}`)
export const getBinanceKlines    = (symbol, interval='1h', limit=100) => api.get(`/crypto/binance/klines/${symbol}?interval=${interval}&limit=${limit}`)
export const getBinanceBalance   = () => api.get('/crypto/binance/balance')
export const getBinancePositions = () => api.get('/crypto/binance/positions')
export const binancePlaceOrder   = (payload) => api.post('/crypto/binance/order', payload)
export const getBinanceFunding   = (symbol) => api.get(`/crypto/binance/funding/${symbol}`)

// ── Strategies ───────────────────────────────────────────────────────────────
export const getStrategies    = () => api.get('/strategies')
export const runBacktest      = (payload) => api.post('/strategies/backtest', payload)
export const deployStrategy   = (name, payload) => api.post(`/strategies/${name}/deploy`, payload)

export default api
