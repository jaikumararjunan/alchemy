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
      // Use native WebSocket — same host, path /ws
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const host     = window.location.hostname
      const port     = window.location.port || (protocol === 'wss:' ? '443' : '80')
      const url      = `${protocol}//${host}:${port}/ws`

      ws = new WebSocket(url)
      socketRef.current = ws

      ws.onopen = () => {
        attempts = 0
        setConnected(true)
        // Subscribe to all symbols
        ws.send(JSON.stringify({ type: 'subscribe', symbols: ['NIFTY50', 'BTCUSD', 'ETHUSD'] }))
      }

      ws.onclose = () => {
        setConnected(false)
        // Reconnect with backoff (max 30s)
        const delay = Math.min(1000 * 2 ** attempts, 30000)
        attempts++
        reconnectRef.current = setTimeout(connect, delay)
      }

      ws.onerror = () => {
        // onclose will fire after onerror — reconnect handled there
        setConnected(false)
      }

      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data)
          switch (msg.event) {
            case 'price_tick':
              updatePrice(msg.symbol, msg)
              break
            case 'signal':
              addSignal(msg)
              const color = msg.signal === 'BUY' ? '🟢' : msg.signal === 'SELL' ? '🔴' : '🟡'
              toast(`${color} ${msg.signal} ${msg.ticker}`, { duration: 5000 })
              break
            case 'risk_alert':
              setRiskStatus(msg)
              addNotification({ type: 'risk', ...msg, ts: new Date().toISOString() })
              if (msg.emergency_stop) toast.error('Emergency Stop Activated!', { duration: 0 })
              break
            case 'order_filled':
              addNotification({ type: 'order', ...msg, ts: new Date().toISOString() })
              toast.success(`Order filled: ${msg.side} ${msg.quantity} ${msg.symbol}`)
              break
            case 'subscribed':
              // Subscription confirmed — no action needed
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
