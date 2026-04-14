import { useAlchemyStore } from '@/store'
import { Bell, X, Check, Zap, TrendingUp, ShieldAlert, Info } from 'lucide-react'
import clsx from 'clsx'

const ICONS = { trade: TrendingUp, signal: Zap, risk: ShieldAlert, default: Info }
const COLORS = {
  trade: 'text-emerald-400 bg-emerald-500/10',
  signal: 'text-blue-400 bg-blue-500/10',
  risk: 'text-rose-400 bg-rose-500/10',
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
  const markAllRead = useAlchemyStore(s => s.markAllNotificationsRead)
  const clearAll = useAlchemyStore(s => s.clearNotifications)
  const unreadCount = useAlchemyStore(s => s.unreadCount)

  if (!open) return null

  return (
    <>
      <div className="fixed inset-0 z-[70] bg-black/40 backdrop-blur-sm" onClick={onClose} />
      <div className="fixed top-0 right-0 h-full w-full sm:w-96 z-[75]"
        style={{ background: 'var(--surface-1)', animation: 'slideInRight 0.3s cubic-bezier(0.16,1,0.3,1) forwards' }}>
        <style>{`@keyframes slideInRight { from { transform: translateX(100%); } to { transform: translateX(0); } }`}</style>

        <div className="flex items-center justify-between px-5 py-4 border-b" style={{ borderColor: 'var(--border)' }}>
          <div className="flex items-center gap-2">
            <Bell size={18} className="text-blue-400" />
            <h2 className="text-base font-display font-semibold text-white">Notifications</h2>
            {unreadCount > 0 && (
              <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-500 text-white">{unreadCount}</span>
            )}
          </div>
          <div className="flex items-center gap-2">
            {notifications.length > 0 && (
              <button onClick={markAllRead}
                className="text-[11px] text-gray-500 hover:text-blue-400 transition-colors flex items-center gap-1">
                <Check size={12} /> Mark all read
              </button>
            )}
            {notifications.length > 0 && (
              <button onClick={clearAll}
                className="text-[11px] text-gray-500 hover:text-rose-400 transition-colors">
                Clear
              </button>
            )}
            <button onClick={onClose}
              className="p-1.5 rounded-lg hover:bg-white/[0.05] text-gray-500 hover:text-white transition-colors">
              <X size={18} />
            </button>
          </div>
        </div>

        <div className="overflow-y-auto h-[calc(100%-60px)]">
          {notifications.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-gray-600">
              <Bell size={32} className="mb-3 opacity-30" />
              <p className="text-sm font-medium">No notifications yet</p>
              <p className="text-xs mt-1">Trade signals and alerts appear here</p>
            </div>
          ) : (
            <div className="divide-y" style={{ borderColor: 'var(--border)' }}>
              {notifications.slice(0, 50).map((n, i) => {
                const type = n.type || 'default'
                const Icon = ICONS[type] || ICONS.default
                const colorCls = COLORS[type] || COLORS.default

                return (
                  <div key={n.ts || i} className="px-5 py-3.5 transition-colors hover:bg-white/[0.02]">
                    <div className="flex gap-3">
                      <div className={clsx('w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0 mt-0.5',
                        colorCls.split(' ')[1])}>
                        <Icon size={14} className={colorCls.split(' ')[0]} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-gray-300">
                          {n.symbol && <span className="font-semibold">{n.symbol} </span>}
                          {n.direction && <span className={/long|buy/i.test(n.direction) ? 'text-emerald-400' : 'text-rose-400'}>
                            {n.direction.toUpperCase()}
                          </span>}
                          {!n.symbol && !n.direction && (n.message || n.type || 'Event')}
                        </p>
                        {n.confidence != null && (
                          <p className="text-xs text-gray-500 mt-0.5">Confidence: {Math.round((n.confidence || 0) * 100)}%</p>
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

export function NotificationBell({ onClick }) {
  const unreadCount = useAlchemyStore(s => s.unreadCount)

  return (
    <button onClick={onClick} className="relative p-2 rounded-xl hover:bg-white/[0.05] transition-colors group">
      <Bell size={18} className="text-gray-500 group-hover:text-gray-300 transition-colors" />
      {unreadCount > 0 && (
        <span className="absolute -top-0.5 -right-0.5 min-w-[18px] px-1 h-[18px] rounded-full bg-blue-500 text-[9px] font-bold text-white flex items-center justify-center shadow-lg shadow-blue-500/30">
          {unreadCount > 9 ? '9+' : unreadCount}
        </span>
      )}
    </button>
  )
}
