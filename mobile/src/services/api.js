/**
 * API Service - connects to Alchemy FastAPI backend
 * Includes JWT + TOTP 2FA authentication support.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

// Change this to your server IP when running on device
const BASE_URL = __DEV__ ? 'http://localhost:8000' : 'http://YOUR_SERVER_IP:8000';
const WS_URL = __DEV__ ? 'ws://localhost:8000/ws' : 'ws://YOUR_SERVER_IP:8000/ws';

const TOKEN_KEY = 'alchemy_access_token';

class AlchemyAPI {
  constructor() {
    this.baseUrl = BASE_URL;
    this.wsUrl = WS_URL;
    this.ws = null;
    this.listeners = new Map();
    this.reconnectTimer = null;
    this._token = null;
    this._onUnauthorized = null;  // set by app to redirect to login screen
  }

  // ── Token management ──────────────────────────────────────────────────────

  async loadToken() {
    this._token = await AsyncStorage.getItem(TOKEN_KEY);
    return this._token;
  }

  async saveToken(token) {
    this._token = token;
    await AsyncStorage.setItem(TOKEN_KEY, token);
  }

  async clearToken() {
    this._token = null;
    await AsyncStorage.removeItem(TOKEN_KEY);
  }

  setUnauthorizedHandler(fn) { this._onUnauthorized = fn; }

  _authHeaders() {
    const h = { 'Content-Type': 'application/json' };
    if (this._token) h['Authorization'] = `Bearer ${this._token}`;
    return h;
  }

  async _handleResponse(res) {
    if (res.status === 401) {
      await this.clearToken();
      this._onUnauthorized?.();
      throw new Error('Unauthorized');
    }
    if (!res.ok) throw new Error(`API error: ${res.status}`);
    return res.json();
  }

  // ── Auth endpoints (no token required) ───────────────────────────────────

  async login(username, password) {
    const res = await fetch(`${this.baseUrl}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    if (!res.ok) {
      const d = await res.json();
      throw new Error(d.detail || 'Login failed');
    }
    return res.json();  // { requires_2fa, temp_token }
  }

  async verify2fa(tempToken, code) {
    const res = await fetch(`${this.baseUrl}/api/auth/verify-2fa`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ temp_token: tempToken, code }),
    });
    if (!res.ok) {
      const d = await res.json();
      throw new Error(d.detail || 'Invalid 2FA code');
    }
    const data = await res.json();
    await this.saveToken(data.access_token);
    return data;  // { access_token, token_type, expires_in }
  }

  async logout() {
    await this.clearToken();
    this.disconnectWS();
  }

  // ── Authenticated requests ────────────────────────────────────────────────

  async get(path) {
    const res = await fetch(`${this.baseUrl}${path}`, { headers: this._authHeaders() });
    return this._handleResponse(res);
  }

  async post(path, body) {
    const res = await fetch(`${this.baseUrl}${path}`, {
      method: 'POST',
      headers: this._authHeaders(),
      body: JSON.stringify(body),
    });
    return this._handleResponse(res);
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

  // History (SQLite persistence)
  getHistoryTrades(limit = 50, symbol = null) {
    const q = symbol ? `?limit=${limit}&symbol=${symbol}` : `?limit=${limit}`;
    return this.get(`/api/history/trades${q}`);
  }
  getHistoryDecisions(limit = 50, symbol = null) {
    const q = symbol ? `?limit=${limit}&symbol=${symbol}` : `?limit=${limit}`;
    return this.get(`/api/history/decisions${q}`);
  }
  getHistoryEquity(limit = 200) { return this.get(`/api/history/equity?limit=${limit}`); }

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
    const url = this._token
      ? `${this.wsUrl}?token=${encodeURIComponent(this._token)}`
      : this.wsUrl;
    this.ws = new WebSocket(url);

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
