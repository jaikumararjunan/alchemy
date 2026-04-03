import { Outlet, NavLink } from 'react-router-dom'
import { useAlchemySocket } from '@/hooks/useAlchemySocket'
import { useAlchemyStore } from '@/store'
import { useAuth } from '@/context/AuthContext'
import {
  LayoutDashboard, Briefcase, Zap, Bitcoin, Key, GitBranch,
  ShieldAlert, BarChart3, BookOpen, Settings, Radio, AlertTriangle,
  Shield, LogOut, User
} from 'lucide-react'
import clsx from 'clsx'

const NAV = [
  { to:'/dashboard', icon:LayoutDashboard, label:'Dashboard',  perm: null },
  { to:'/portfolio',  icon:Briefcase,      label:'Portfolio',  perm: null },
  { to:'/signals',    icon:Zap,            label:'AI Signals', perm: null },
  { to:'/crypto',     icon:Bitcoin,        label:'Crypto',     perm: null },
  { to:'/tokens',     icon:Key,            label:'Tokens',     perm: null },
  { to:'/workflows',  icon:GitBranch,      label:'Workflows',  perm: null },
  { to:'/risk',       icon:ShieldAlert,    label:'Risk',       perm: null },
  { to:'/analytics',  icon:BarChart3,      label:'Analytics',  perm: null },
  { to:'/strategy',   icon:BookOpen,       label:'Strategy',   perm: null },
  { to:'/settings',   icon:Settings,       label:'Settings',   perm: null },
]

const ROLE_COLOR = {
  super_admin:'text-purple-400', admin:'text-blue-400',
  trader:'text-emerald-400', analyst:'text-amber-400', viewer:'text-gray-400'
}

export default function Layout() {
  useAlchemySocket()
  const { connected, emergencyStop, portfolioNAV, portfolioPnL, activeBroker } = useAlchemyStore()
  const { user, logout, isAdmin } = useAuth()

  return (
    <div className="flex h-screen bg-gray-950 overflow-hidden">
      <aside className="w-56 flex-shrink-0 bg-gray-900 border-r border-gray-800 flex flex-col">
        <div className="h-14 flex items-center px-4 border-b border-gray-800">
          <span className="text-2xl mr-2">🔮</span>
          <div>
            <div className="text-sm font-bold text-white tracking-wide">ALCHEMY</div>
            <div className="text-xs text-gray-500">v0.4 · Secure</div>
          </div>
        </div>

        <nav className="flex-1 py-4 overflow-y-auto">
          {NAV.map(({ to, icon:Icon, label }) => (
            <NavLink key={to} to={to}
              className={({ isActive }) => clsx(
                'flex items-center gap-3 px-4 py-2.5 text-sm transition-colors mx-2 rounded-lg mb-0.5',
                isActive ? 'bg-blue-600/20 text-blue-400 font-medium' : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'
              )}>
              <Icon size={16} />{label}
            </NavLink>
          ))}
          {isAdmin && (
            <NavLink to="/admin"
              className={({ isActive }) => clsx(
                'flex items-center gap-3 px-4 py-2.5 text-sm transition-colors mx-2 rounded-lg mb-0.5 border-t border-gray-800 mt-2 pt-3',
                isActive ? 'bg-purple-600/20 text-purple-400 font-medium' : 'text-purple-400/70 hover:text-purple-300 hover:bg-purple-900/20'
              )}>
              <Shield size={16} /> Admin Panel
            </NavLink>
          )}
        </nav>

        {/* User info + logout */}
        <div className="p-3 border-t border-gray-800 space-y-2">
          {user && (
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-xs font-bold text-white flex-shrink-0">
                {user.email?.[0]?.toUpperCase()}
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-xs font-medium text-white truncate">{user.email}</div>
                <div className={clsx('text-xs font-medium', ROLE_COLOR[user.role] || 'text-gray-400')}>
                  {user.role}
                </div>
              </div>
              <button onClick={logout} title="Logout"
                className="text-gray-600 hover:text-red-400 transition-colors flex-shrink-0">
                <LogOut size={14} />
              </button>
            </div>
          )}
          <div className="flex items-center justify-between text-xs">
            <span className="text-gray-500">Feed</span>
            <span className={clsx('flex items-center gap-1', connected ? 'text-emerald-400' : 'text-red-400')}>
              <span className={clsx('w-1.5 h-1.5 rounded-full', connected ? 'bg-emerald-400 animate-pulse' : 'bg-red-400')} />
              {connected ? 'Live' : 'Offline'}
            </span>
          </div>
        </div>
      </aside>

      <div className="flex-1 flex flex-col min-w-0">
        <header className="h-14 bg-gray-900 border-b border-gray-800 flex items-center justify-between px-6 flex-shrink-0">
          {emergencyStop && (
            <div className="flex items-center gap-2 bg-red-900/40 border border-red-500 text-red-400 text-xs px-3 py-1 rounded-lg">
              <AlertTriangle size={14} /> Emergency Stop Active
            </div>
          )}
          <div className="flex items-center gap-6 ml-auto">
            <div className="text-right">
              <div className="text-xs text-gray-500">Portfolio NAV</div>
              <div className="text-sm font-semibold text-white">
                {portfolioNAV.toLocaleString('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:0})}
              </div>
            </div>
            <div className="text-right">
              <div className="text-xs text-gray-500">Day P&L</div>
              <div className={clsx('text-sm font-semibold', portfolioPnL>=0?'text-emerald-400':'text-red-400')}>
                {portfolioPnL>=0?'+':''}{portfolioPnL.toLocaleString('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:0})}
              </div>
            </div>
            <div className="flex items-center gap-1.5 text-xs text-gray-400">
              <Radio size={12} className="text-blue-400" />
              {new Date().toLocaleTimeString('en-IN',{hour:'2-digit',minute:'2-digit'})} IST
            </div>
          </div>
        </header>
        <main className="flex-1 overflow-y-auto p-6"><Outlet /></main>
      </div>
    </div>
  )
}
