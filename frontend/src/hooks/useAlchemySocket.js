import { useEffect, useRef } from 'react'
import { useAlchemyStore } from '@/store'
import toast from 'react-hot-toast'

export function useAlchemySocket() {
  const socketRef = useRef(null)
  const reconnectRef = useRef(null)
  const { setConnected, updatePrice, addSignal, setRiskStatus, addNotification } = useAlchemyStore()

  useEffect(() => {
    let ws = null
    let attempts = 0

    function connect() {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const host     = window.location.hostname
      const port     = window.location.port || (protocol === 'wss:' ? '443' : '80')
      const url      = `${protocol}//${host}:${port}/ws`

      ws = new WebSocket(url)
      socketRef.current = ws

      ws.onopen = () => {
        attempts = 0
        setConnected(true)
        ws.send(JSON.stringify({ type: 'subscribe', symbols: ['NIFTY50', 'BTCUSD', 'ETHUSD'] }))
      }

      ws.onclose = () => {
        setConnected(false)
        const delay = Math.min(1000 * 2 ** attempts, 30000)
        attempts++
        reconnectRef.current = setTimeout(connect, delay)
      }

      ws.onerror = () => { setConnected(false) }

      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data)
          // Normalize: data might be nested in msg.data or flat at msg level
          const d = msg.data || msg

          switch (msg.event) {
            case 'price_tick':
            case 'price_update': {
              const sym = d.symbol || msg.symbol
              if (sym) {
                updatePrice(sym, {
                  price: d.price || 0,
                  change_pct: d.change_pct || 0,
                  ts: d.ts || Date.now(),
                })
              }
              break
            }
            case 'signal':
            case 'autonomous_signal': {
              addSignal(d)
              const dir = d.direction || d.signal || d.side || ''
              const sym = d.symbol || d.ticker || ''
              if (dir && sym) {
                const emoji = dir.toUpperCase().includes('BUY') || dir.toUpperCase().includes('LONG') ? '🟢' : '🔴'
                toast(`${emoji} ${dir.toUpperCase()} ${sym}`, { duration: 5000 })
              }
              break
            }
            case 'autonomous_execution': {
              addNotification({ type: 'trade', ...d, ts: new Date().toISOString() })
              const dir = d.direction || d.side || ''
              const sym = d.symbol || ''
              if (dir && sym) {
                toast.success(`Auto-trade: ${dir.toUpperCase()} ${sym}`, { duration: 4000 })
              }
              break
            }
            case 'risk_alert':
              setRiskStatus(msg)
              addNotification({ type: 'risk', ...d, ts: new Date().toISOString() })
              if (msg.emergency_stop || d.emergency_stop) toast.error('Emergency Stop Activated!', { duration: 0 })
              break
            case 'order_filled': {
              addNotification({ type: 'order', ...d, ts: new Date().toISOString() })
              const side = d.side || ''
              const qty = d.quantity || ''
              const sym = d.symbol || ''
              if (sym) toast.success(`Order filled: ${side} ${qty} ${sym}`)
              break
            }
            case 'subscribed':
              break
          }
        } catch { /* ignore malformed messages */ }
      }
    }

    connect()

    return () => {
      clearTimeout(reconnectRef.current)
      if (ws) { ws.onclose = null; ws.close() }
      setConnected(false)
    }
  }, [])
}
