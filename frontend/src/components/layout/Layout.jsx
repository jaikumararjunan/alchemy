import { useState, useEffect, useRef, memo } from 'react'
import { Outlet, NavLink, useLocation } from 'react-router-dom'
import { useAlchemySocket } from '@/hooks/useAlchemySocket'
import { useAlchemyStore } from '@/store'
import { useAuth } from '@/context/AuthContext'
import {
  LayoutDashboard, Briefcase, Zap, Bitcoin, Key, GitBranch,
  ShieldAlert, BarChart3, BookOpen, Settings, Bell, Shield,
  LogOut, AlertTriangle, Menu, X, Star, Bot, Wallet, BellRing,
} from 'lucide-react'
import clsx from 'clsx'
import NotificationPanel, { NotificationBell } from '@/components/NotificationPanel'

const NAV = [
  { section: 'MARKETS', items: [
    { to: '/dashboard',     icon: LayoutDashboard, label: 'Dashboard' },
    { to: '/portfolio',     icon: Briefcase,       label: 'Portfolio' },
    { to: '/crypto',        icon: Bitcoin,         label: 'Crypto' },
    { to: '/watchlist',     icon: Star,            label: 'Watchlist' },
  ]},
  { section: 'TRADING', items: [
    { to: '/paper-trading', icon: Wallet,          label: 'Paper Trade' },
    { to: '/autonomous',    icon: Bot,             label: 'Auto Trade' },
    { to: '/signals',       icon: Zap,             label: 'AI Signals' },
    { to: '/strategy',      icon: BookOpen,        label: 'Strategy' },
  ]},
  { section: 'ANALYSIS', items: [
    { to: '/analytics',     icon: BarChart3,       label: 'Analytics' },
    { to: '/risk',          icon: ShieldAlert,     label: 'Risk' },
    { to: '/alerts',        icon: BellRing,        label: 'Price Alerts' },
  ]},
  { section: 'SETTINGS', items: [
    { to: '/security',      icon: Shield,          label: 'Security' },
    { to: '/tokens',        icon: Key,             label: 'Exchange Keys' },
    { to: '/workflows',     icon: GitBranch,       label: 'Workflows' },
    { to: '/notifications', icon: Bell,            label: 'Notifications' },
    { to: '/settings',      icon: Settings,        label: 'Settings' },
  ]},
]

/* ── Sidebar (memoized — won't re-render on price ticks) ─────────────────── */
const Sidebar = memo(function Sidebar({ user, isAdmin, onLogout, onClose }) {
  const connected = useAlchemyStore(s => s.connected)

  return (
    <div className="flex flex-col h-full w-56 bg-[#0D1526] border-r border-white/[0.06]">
      {/* Logo */}
      <div className="h-14 flex items-center justify-between px-4 flex-shrink-0 border-b border-white/[0.06]">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center">
            <span className="text-white text-xs font-black">A</span>
          </div>
          <div>
            <div className="text-xs font-black text-white tracking-wide">ALCHEMY</div>
            <div className="text-[9px] text-gray-600">AI Trading Platform</div>
          </div>
        </div>
        {onClose && (
          <button onClick={onClose} className="p-1 rounded text-gray-500 hover:text-white">
            <X size={16}/>
          </button>
        )}
      </div>

      {/* Nav — this is the scrollable area */}
      <div className="flex-1 overflow-y-auto py-2" style={{ minHeight: 0 }}>
        {NAV.map(group => (
          <div key={group.section} className="mb-1">
            <div className="px-4 py-1 text-[9px] font-bold text-gray-600 uppercase tracking-[0.15em]">{group.section}</div>
            {group.items.map(item => (
              <SidebarLink key={item.to} to={item.to} icon={item.icon} label={item.label} onNavigate={onClose} />
            ))}
          </div>
        ))}
        {isAdmin && (
          <div className="mx-2 mt-1 pt-1 border-t border-white/[0.06]">
            <SidebarLink to="/admin" icon={Shield} label="Admin" onNavigate={onClose} />
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="px-3 py-2 border-t border-white/[0.06] flex-shrink-0">
        {user && (
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-full bg-blue-600 flex items-center justify-center text-[10px] font-bold text-white">
              {user.email?.[0]?.toUpperCase()}
            </div>
            <div className="flex-1 min-w-0 text-[10px] text-gray-400 truncate">{user.email}</div>
            <button onClick={onLogout} className="p-1 text-gray-600 hover:text-red-400"><LogOut size={12}/></button>
          </div>
        )}
        <div className="flex items-center justify-between text-[9px] mt-1">
          <span className="text-gray-700">Feed</span>
          <span className={connected ? 'text-emerald-400' : 'text-gray-600'}>
            {connected ? '● Connected' : '○ Offline'}
          </span>
        </div>
      </div>
    </div>
  )
})

/* ── Single sidebar link ─────────────────────────────────────────────────── */
function SidebarLink({ to, icon: Icon, label, onNavigate }) {
  return (
    <NavLink
      to={to}
      end={to === '/dashboard'}
      onClick={onNavigate || undefined}
      className={({ isActive }) => clsx(
        'flex items-center gap-2.5 px-3 py-[7px] mx-2 mb-px rounded-lg text-[12.5px] transition-colors',
        isActive
          ? 'bg-blue-500/15 text-blue-400 font-semibold'
          : 'text-gray-500 hover:text-gray-200 hover:bg-white/[0.04]'
      )}
    >
      <Icon size={14} />
      <span>{label}</span>
    </NavLink>
  )
}

/* ── Main Layout ─────────────────────────────────────────────────────────── */
export default function Layout() {
  useAlchemySocket()
  const { connected, emergencyStop, portfolioNAV, portfolioPnL, setPortfolio } = useAlchemyStore()
  const { user, logout, isAdmin, apiClient } = useAuth()
  const location = useLocation()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [notifOpen, setNotifOpen] = useState(false)

  // Fetch portfolio
  useEffect(() => {
    const api = apiClient()
    const fetch = async () => {
      try {
        const { data } = await api.get('/paper/portfolio')
        if (data) setPortfolio(data.portfolio_value || 0, (data.unrealized_pnl || 0) + (data.realized_pnl || 0), data.open_positions || 0)
      } catch {}
    }
    fetch()
    const id = setInterval(fetch, 15000)
    return () => clearInterval(id)
  }, [])

  // Auto-close mobile nav on route change
  useEffect(() => { setMobileOpen(false) }, [location.pathname])

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: 'var(--surface-0)' }}>

      {/* Desktop sidebar — always visible on lg+ */}
      <div className="hidden lg:block flex-shrink-0">
        <Sidebar user={user} isAdmin={isAdmin} onLogout={logout} />
      </div>

      {/* Mobile sidebar overlay */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-black/60" onClick={() => setMobileOpen(false)} />
          <div className="relative z-10 h-full w-64" style={{ animation: 'slideIn .2s ease-out' }}>
            <Sidebar user={user} isAdmin={isAdmin} onLogout={logout} onClose={() => setMobileOpen(false)} />
          </div>
        </div>
      )}
      <style>{`@keyframes slideIn{from{transform:translateX(-100%)}to{transform:translateX(0)}}`}</style>

      {/* Right side: header + content */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">

        {/* Header */}
        <header className="h-14 flex items-center px-4 gap-3 flex-shrink-0 border-b border-white/[0.06]" style={{ background: 'var(--surface-1)' }}>
          <button onClick={() => setMobileOpen(true)} className="lg:hidden p-2 rounded-lg text-gray-400 hover:text-white">
            <Menu size={18}/>
          </button>

          {emergencyStop && (
            <div className="flex items-center gap-1 bg-red-900/40 border border-red-500/50 text-red-400 text-xs px-2 py-1 rounded-lg animate-pulse font-semibold">
              <AlertTriangle size={12}/> Emergency Stop
            </div>
          )}

          <NotificationBell onClick={() => setNotifOpen(true)} />

          <div className="flex items-center gap-4 ml-auto">
            <div className="hidden md:flex items-center gap-1.5">
              <span className={clsx('w-1.5 h-1.5 rounded-full', connected ? 'bg-emerald-400 animate-pulse' : 'bg-gray-600')} />
              <span className="text-[11px] text-gray-500">{connected ? 'Live' : 'Offline'}</span>
            </div>
            <div className="hidden sm:block text-right">
              <div className="text-[10px] text-gray-500 uppercase tracking-wider">Portfolio</div>
              <div className="text-sm font-bold text-white font-mono">{portfolioNAV ? `$${portfolioNAV.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : '—'}</div>
            </div>
            <div className="text-right">
              <div className="text-[10px] text-gray-500 uppercase tracking-wider">P&L</div>
              <div className={clsx('text-sm font-bold font-mono', portfolioPnL >= 0 ? 'text-emerald-400' : 'text-rose-400')}>
                {portfolioPnL >= 0 ? '+' : ''}{portfolioPnL ? `$${Math.abs(portfolioPnL).toLocaleString(undefined, { maximumFractionDigits: 0 })}` : '$0'}
              </div>
            </div>
          </div>
        </header>

        {/* Page content — scrollable */}
        <main className="flex-1 overflow-y-auto" style={{ background: 'var(--surface-0)' }}>
          <div className="p-4 md:p-6 max-w-[1400px] mx-auto w-full">
            <Outlet />
          </div>
        </main>

        {/* Mobile bottom nav */}
        <nav className="lg:hidden flex-shrink-0 flex items-center border-t border-white/[0.06] px-1 py-1" style={{ background: 'var(--surface-1)' }}>
          {NAV[0].items.concat([NAV[1].items[0]]).map(item => {
            const Icon = item.icon
            return (
              <NavLink key={item.to} to={item.to} className={({ isActive }) => clsx(
                'flex-1 flex flex-col items-center gap-0.5 py-1.5 rounded-lg text-[9px]',
                isActive ? 'text-blue-400' : 'text-gray-600'
              )}>
                <Icon size={17}/><span>{item.label}</span>
              </NavLink>
            )
          })}
          <button onClick={() => setMobileOpen(true)} className="flex-1 flex flex-col items-center gap-0.5 py-1.5 text-[9px] text-gray-600">
            <Menu size={17}/><span>More</span>
          </button>
        </nav>
      </div>

      <NotificationPanel open={notifOpen} onClose={() => setNotifOpen(false)} />
    </div>
  )
}
