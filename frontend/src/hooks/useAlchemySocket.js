import { useEffect, useRef } from 'react'
import { io } from 'socket.io-client'
import { useAlchemyStore } from '@/store'
import toast from 'react-hot-toast'

export function useAlchemySocket() {
  const socketRef = useRef(null)
  const { setConnected, updatePrice, addSignal, setRiskStatus, addNotification } = useAlchemyStore()

  useEffect(() => {
    const socket = io('/', { path: '/ws/socket.io', transports: ['websocket'] })
    socketRef.current = socket

    socket.on('connect',    () => { setConnected(true);  toast.success('Live feed connected') })
    socket.on('disconnect', () => { setConnected(false); toast.error('Live feed disconnected') })

    // Live price ticks
    socket.on('price_tick', ({ symbol, ...data }) => updatePrice(symbol, data))

    // New AI signal
    socket.on('signal', (sig) => {
      addSignal(sig)
      const color = sig.signal === 'BUY' ? '🟢' : sig.signal === 'SELL' ? '🔴' : '🟡'
      toast(`${color} ${sig.signal} ${sig.ticker} @ ${(sig.position_pct * 100).toFixed(1)}%`, { duration: 5000 })
    })

    // Risk alerts
    socket.on('risk_alert', (data) => {
      setRiskStatus(data)
      addNotification({ type: 'risk', ...data, ts: new Date().toISOString() })
      if (data.emergency_stop) toast.error('⚠️ Emergency Stop Activated!', { duration: 0 })
    })

    // Order confirmations
    socket.on('order_filled', (order) => {
      addNotification({ type: 'order', ...order, ts: new Date().toISOString() })
      toast.success(`✅ Order filled: ${order.side} ${order.quantity} ${order.symbol}`)
    })

    return () => socket.disconnect()
  }, [])

  return socketRef
}
