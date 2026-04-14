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
      const host = window.location.hostname
      const port = window.location.port || (protocol === 'wss:' ? '443' : '80')
      const url = `${protocol}//${host}:${port}/ws`

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
          const evt = msg.event || ''

          // Extract symbol and direction safely from ANY message shape
          const sym = msg.symbol || msg.ticker || msg.data?.symbol || msg.data?.ticker || ''
          const dir = msg.direction || msg.signal || msg.side || msg.data?.direction || msg.data?.signal || msg.data?.side || ''

          if (evt === 'price_tick' || evt === 'price_update') {
            const price = msg.price || msg.data?.price || 0
            if (sym && price) {
              updatePrice(sym, { price, change_pct: msg.change_pct || msg.data?.change_pct || 0, ts: Date.now() })
            }
          }
          else if (evt === 'signal' || evt === 'autonomous_signal') {
            addSignal(msg.data || msg)
            // Only toast if we have BOTH symbol and direction
            if (sym && dir) {
              const isLong = /buy|long/i.test(dir)
              toast(`${isLong ? '🟢' : '🔴'} ${dir.toUpperCase()} ${sym}`, { duration: 5000 })
            }
          }
          else if (evt === 'autonomous_execution') {
            addNotification({ type: 'trade', ...(msg.data || msg), ts: new Date().toISOString() })
            if (sym && dir) {
              toast.success(`Auto-trade: ${dir.toUpperCase()} ${sym}`, { duration: 4000 })
            }
          }
          else if (evt === 'risk_alert') {
            setRiskStatus(msg)
            addNotification({ type: 'risk', ...(msg.data || msg), ts: new Date().toISOString() })
            if (msg.emergency_stop) toast.error('Emergency Stop Activated!', { duration: 0 })
          }
          else if (evt === 'order_filled') {
            addNotification({ type: 'order', ...(msg.data || msg), ts: new Date().toISOString() })
            if (sym) toast.success(`Order filled: ${dir} ${sym}`)
          }
          // Ignore: 'subscribed', 'autonomous_scan', 'autonomous_scan_complete', etc.
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
