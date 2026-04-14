import { useState, useEffect } from 'react'
import { useAlchemyStore } from '@/store'
import { Bell, X, Check, Zap, TrendingUp, ShieldAlert, AlertTriangle, Info } from 'lucide-react'
import clsx from 'clsx'

const ICONS = {
  trade: TrendingUp,
  signal: Zap,
  risk: ShieldAlert,
  order: TrendingUp,
  default: Info,
}

const COLORS = {
  trade: 'text-emerald-400 bg-emerald-500/10',
  signal: 'text-blue-400 bg-blue-500/10',
  risk: 'text-rose-400 bg-rose-500/10',
  order: 'text-amber-400 bg-amber-500/10',
  default: 'text-gray-400 bg-gray-500/10',
}

function timeAgo(ts) {
  if (!ts) return ''
  const diff = Date.now() - new Date(ts).getTime()
  if (diff < 60000) return 'Just now'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`
  return `${Math.floor(diff / 86400000)}d ago`
}

export default function NotificationPanel({ open, onClose }) {
  const notifications = useAlchemyStore(s => s.notifications || [])
  const [read, setRead] = useState(new Set())

  const unreadCount = notifications.filter(n => !read.has(n.ts)).length

  const markAllRead = () => {
    setRead(new Set(notifications.map(n => n.ts)))
  }

  if (!open) return null

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-[70] bg-black/40 backdrop-blur-sm" onClick={onClose} />

      {/* Panel */}
      <div className="fixed top-0 right-0 h-full w-full sm:w-96 z-[75] animate-slide-in-right"
        style={{ background: 'var(--surface-1)' }}>
        <style>{`
          @keyframes slideInRight { from { transform: translateX(100%); } to { transform: translateX(0); } }
          .animate-slide-in-right { animation: slideInRight 0.3s cubic-bezier(0.16,1,0.3,1) forwards; }
        `}</style>

        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b" style={{ borderColor: 'var(--border)' }}>
          <div className="flex items-center gap-2">
            <Bell size={18} className="text-blue-400" />
            <h2 className="text-base font-display font-semibold text-white">Notifications</h2>
            {unreadCount > 0 && (
              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-500 text-white">{unreadCount}</span>
            )}
          </div>
          <div className="flex items-center gap-2">
            {unreadCount > 0 && (
              <button onClick={markAllRead}
                className="text-[11px] text-gray-500 hover:text-blue-400 transition-colors flex items-center gap-1">
                <Check size={12} /> Mark all read
              </button>
            )}
            <button onClick={onClose}
              className="p-1.5 rounded-lg hover:bg-white/[0.05] text-gray-500 hover:text-white transition-colors">
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Notification list */}
        <div className="overflow-y-auto h-[calc(100%-60px)]">
          {notifications.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-gray-600">
              <Bell size={32} className="mb-3 opacity-30" />
              <p className="text-sm font-medium">No notifications yet</p>
              <p className="text-xs mt-1">Trade signals and alerts will appear here</p>
            </div>
          ) : (
            <div className="divide-y" style={{ borderColor: 'var(--border)' }}>
              {notifications.slice(0, 50).map((n, i) => {
                const type = n.type || 'default'
                const Icon = ICONS[type] || ICONS.default
                const color = COLORS[type] || COLORS.default
                const isRead = read.has(n.ts)

                return (
                  <div key={n.ts || i}
                    className={clsx(
                      'px-5 py-3.5 transition-colors hover:bg-white/[0.02]',
                      !isRead && 'bg-blue-500/[0.03]'
                    )}>
                    <div className="flex gap-3">
                      <div className={clsx('w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0 mt-0.5', color.split(' ')[1])}>
                        <Icon size={14} className={color.split(' ')[0]} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-start justify-between gap-2">
                          <p className={clsx('text-sm font-medium', isRead ? 'text-gray-400' : 'text-gray-200')}>
                            {n.symbol && <span className="font-semibold">{n.symbol} </span>}
                            {n.side && <span className={n.side === 'buy' || n.direction === 'long' ? 'text-emerald-400' : 'text-rose-400'}>
                              {(n.side || n.direction || '').toUpperCase()}
                            </span>}
                            {n.signal && <span className={n.signal === 'BUY' ? 'text-emerald-400' : 'text-rose-400'}>{n.signal}</span>}
                            {!n.symbol && !n.signal && (n.message || type)}
                          </p>
                          {!isRead && <span className="w-2 h-2 rounded-full bg-blue-500 flex-shrink-0 mt-1.5" />}
                        </div>
                        {n.confidence && (
                          <p className="text-xs text-gray-500 mt-0.5">
                            Confidence: {typeof n.confidence === 'number' ? `${(n.confidence * 100).toFixed(0)}%` : n.confidence}
                          </p>
                        )}
                        <p className="text-[11px] text-gray-600 mt-1 font-mono">{timeAgo(n.ts)}</p>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </>
  )
}

// Bell button with unread count badge
export function NotificationBell({ onClick, count = 0 }) {
  return (
    <button onClick={onClick} className="relative p-2 rounded-xl hover:bg-white/[0.05] transition-colors group">
      <Bell size={18} className="text-gray-500 group-hover:text-gray-300 transition-colors" />
      {count > 0 && (
        <span className="absolute -top-0.5 -right-0.5 w-4.5 h-4.5 min-w-[18px] px-1 rounded-full bg-blue-500 text-[9px] font-bold text-white flex items-center justify-center shadow-lg shadow-blue-500/30">
          {count > 9 ? '9+' : count}
        </span>
      )}
    </button>
  )
}
