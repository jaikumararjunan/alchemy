/**
 * API Service - connects to Alchemy FastAPI backend
 */

// Change this to your server IP when running on device
const BASE_URL = __DEV__ ? 'http://localhost:8000' : 'http://YOUR_SERVER_IP:8000';
const WS_URL = __DEV__ ? 'ws://localhost:8000/ws' : 'ws://YOUR_SERVER_IP:8000/ws';

class AlchemyAPI {
  constructor() {
    this.baseUrl = BASE_URL;
    this.wsUrl = WS_URL;
    this.ws = null;
    this.listeners = new Map();
    this.reconnectTimer = null;
  }

  async get(path) {
    const res = await fetch(`${this.baseUrl}${path}`);
    if (!res.ok) throw new Error(`API error: ${res.status}`);
    return res.json();
  }

  async post(path, body) {
    const res = await fetch(`${this.baseUrl}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`API error: ${res.status}`);
    return res.json();
  }

  // REST endpoints
  getHealth() { return this.get('/health'); }
  getStatus() { return this.get('/api/status'); }
  getPortfolio() { return this.get('/api/portfolio'); }
  getPositions() { return this.get('/api/positions'); }
  getMarket(symbol = 'BTCUSD') { return this.get(`/api/market/${symbol}`); }
  getEmotion() { return this.get('/api/emotion'); }
  getNews(limit = 20) { return this.get(`/api/news?limit=${limit}`); }
  getDecisions(limit = 20) { return this.get(`/api/decisions?limit=${limit}`); }
  getConfig() { return this.get('/api/config'); }
  getForecast(symbol = 'BTCUSD') { return this.get(`/api/forecast?symbol=${symbol}`); }
  getMlAnalysis(symbol = 'BTCUSD') { return this.get(`/api/ml/analyze?symbol=${symbol}`); }
  getMlStatus() { return this.get('/api/ml/status'); }
  trainModels() { return this.post('/api/ml/train', {}); }
  analyzeSentiment(headlines) { return this.post('/api/ml/sentiment', { headlines }); }

  // Derivatives endpoints
  getDerivativesSignal(symbol = 'BTCUSD')       { return this.get(`/api/derivatives/signal?symbol=${symbol}`); }
  getDerivativesFunding(symbol = 'BTCUSD')      { return this.get(`/api/derivatives/funding?symbol=${symbol}`); }
  getDerivativesBasis(symbol = 'BTCUSD')        { return this.get(`/api/derivatives/basis?symbol=${symbol}`); }
  getDerivativesOI(symbol = 'BTCUSD')           { return this.get(`/api/derivatives/oi?symbol=${symbol}`); }
  getDerivativesLiquidations(symbol = 'BTCUSD') { return this.get(`/api/derivatives/liquidations?symbol=${symbol}`); }
  getDerivativesOptions(symbol = 'BTCUSD')      { return this.get(`/api/derivatives/options?symbol=${symbol}`); }

  // Contract Scanner
  scanContracts(symbols) {
    const q = symbols ? `?symbols=${encodeURIComponent(symbols.join(','))}` : '';
    return this.get(`/api/scanner/scan${q}`);
  }
  getScannerContracts() { return this.get('/api/scanner/contracts'); }
  getScannerTop(n = 5)  { return this.get(`/api/scanner/top?n=${n}`); }

  botControl(action, intervalMinutes) {
    return this.post('/api/bot/control', { action, interval_minutes: intervalMinutes });
  }

  updateConfig(updates) {
    return this.post('/api/config', updates);
  }

  placeTrade(params) {
    return this.post('/api/trade', params);
  }

  // WebSocket
  connectWS(onMessage, onConnect, onDisconnect) {
    if (this.ws) { this.ws.close(); }
    this.ws = new WebSocket(this.wsUrl);

    this.ws.onopen = () => {
      if (this.reconnectTimer) { clearTimeout(this.reconnectTimer); this.reconnectTimer = null; }
      onConnect?.();
    };

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        onMessage?.(data);
      } catch (e) {}
    };

    this.ws.onclose = () => {
      onDisconnect?.();
      this.reconnectTimer = setTimeout(() => this.connectWS(onMessage, onConnect, onDisconnect), 3000);
    };

    this.ws.onerror = () => {};
  }

  disconnectWS() {
    if (this.reconnectTimer) { clearTimeout(this.reconnectTimer); this.reconnectTimer = null; }
    if (this.ws) { this.ws.close(); this.ws = null; }
  }
}

export default new AlchemyAPI();
