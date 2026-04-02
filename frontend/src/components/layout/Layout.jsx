import { Outlet, NavLink } from 'react-router-dom'
import { useAlchemySocket } from '@/hooks/useAlchemySocket'
import { useAlchemyStore } from '@/store'
import {
  LayoutDashboard, Briefcase, Zap, Bitcoin, ShieldAlert,
  BarChart3, BookOpen, Settings, Radio, AlertTriangle
} from 'lucide-react'
import clsx from 'clsx'

const NAV = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/portfolio',  icon: Briefcase,      label: 'Portfolio' },
  { to: '/signals',    icon: Zap,            label: 'AI Signals' },
  { to: '/crypto',     icon: Bitcoin,        label: 'Crypto' },
  { to: '/risk',       icon: ShieldAlert,    label: 'Risk' },
  { to: '/analytics',  icon: BarChart3,      label: 'Analytics' },
  { to: '/strategy',   icon: BookOpen,       label: 'Strategy' },
  { to: '/settings',   icon: Settings,       label: 'Settings' },
]

export default function Layout() {
  useAlchemySocket()
  const { connected, emergencyStop, portfolioNAV, portfolioPnL, activeBroker } = useAlchemyStore()

  return (
    <div className="flex h-screen bg-gray-950 overflow-hidden">
      {/* ── Sidebar ────────────────────────────────────────────────────── */}
      <aside className="w-56 flex-shrink-0 bg-gray-900 border-r border-gray-800 flex flex-col">
        {/* Logo */}
        <div className="h-14 flex items-center px-4 border-b border-gray-800">
          <span className="text-2xl mr-2">🔮</span>
          <div>
            <div className="text-sm font-bold text-white tracking-wide">ALCHEMY</div>
            <div className="text-xs text-gray-500">AI Trading Platform</div>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 py-4 overflow-y-auto">
          {NAV.map(({ to, icon: Icon, label }) => (
            <NavLink key={to} to={to}
              className={({ isActive }) => clsx(
                'flex items-center gap-3 px-4 py-2.5 text-sm transition-colors mx-2 rounded-lg mb-0.5',
                isActive
                  ? 'bg-blue-600/20 text-blue-400 font-medium'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'
              )}>
              <Icon size={16} />
              {label}
            </NavLink>
          ))}
        </nav>

        {/* Status */}
        <div className="p-3 border-t border-gray-800 space-y-2">
          <div className="flex items-center justify-between text-xs">
            <span className="text-gray-500">Feed</span>
            <span className={clsx('flex items-center gap-1', connected ? 'text-emerald-400' : 'text-red-400')}>
              <span className={clsx('w-1.5 h-1.5 rounded-full', connected ? 'bg-emerald-400 animate-pulse' : 'bg-red-400')} />
              {connected ? 'Live' : 'Offline'}
            </span>
          </div>
          <div className="flex items-center justify-between text-xs">
            <span className="text-gray-500">Broker</span>
            <span className="text-blue-400 font-medium capitalize">{activeBroker}</span>
          </div>
        </div>
      </aside>

      {/* ── Main ───────────────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Topbar */}
        <header className="h-14 bg-gray-900 border-b border-gray-800 flex items-center justify-between px-6 flex-shrink-0">
          {/* Emergency stop banner */}
          {emergencyStop && (
            <div className="flex items-center gap-2 bg-red-900/40 border border-red-500 text-red-400 text-xs px-3 py-1 rounded-lg">
              <AlertTriangle size={14} />
              Emergency Stop Active — All trading halted
            </div>
          )}

          <div className="flex items-center gap-6 ml-auto">
            <div className="text-right">
              <div className="text-xs text-gray-500">Portfolio NAV</div>
              <div className="text-sm font-semibold text-white">
                {portfolioNAV.toLocaleString('en-IN', { style:'currency', currency:'INR', maximumFractionDigits:0 })}
              </div>
            </div>
            <div className="text-right">
              <div className="text-xs text-gray-500">Day P&L</div>
              <div className={clsx('text-sm font-semibold', portfolioPnL >= 0 ? 'text-emerald-400' : 'text-red-400')}>
                {portfolioPnL >= 0 ? '+' : ''}{portfolioPnL.toLocaleString('en-IN', { style:'currency', currency:'INR', maximumFractionDigits:0 })}
              </div>
            </div>
            <div className="flex items-center gap-1.5 text-xs text-gray-400">
              <Radio size={12} className="text-blue-400" />
              {new Date().toLocaleTimeString('en-IN', { hour:'2-digit', minute:'2-digit' })} IST
            </div>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
