import { Outlet, NavLink } from 'react-router-dom'
import { useAlchemySocket } from '@/hooks/useAlchemySocket'
import { useAlchemyStore } from '@/store'
import { useAuth } from '@/context/AuthContext'
import {
  LayoutDashboard, Briefcase, Zap, Bitcoin, Key, GitBranch,
  ShieldAlert, BarChart3, BookOpen, Settings, Bell, Shield,
  LogOut, Radio, AlertTriangle,
} from 'lucide-react'
import clsx from 'clsx'

const NAV = [
  { to:'/dashboard',     icon:LayoutDashboard, label:'Dashboard'     },
  { to:'/portfolio',     icon:Briefcase,       label:'Portfolio'     },
  { to:'/signals',       icon:Zap,             label:'AI Signals'    },
  { to:'/crypto',        icon:Bitcoin,         label:'Crypto'        },
  { to:'/tokens',        icon:Key,             label:'Tokens'        },
  { to:'/workflows',     icon:GitBranch,       label:'Workflows'     },
  { to:'/risk',          icon:ShieldAlert,     label:'Risk'          },
  { to:'/analytics',     icon:BarChart3,       label:'Analytics'     },
  { to:'/strategy',      icon:BookOpen,        label:'Strategy'      },
  { to:'/settings',      icon:Settings,        label:'Settings'      },
  { to:'/notifications', icon:Bell,            label:'Notifications' },
]

const ROLE_CLR = {
  super_admin:'text-purple-400', admin:'text-blue-400',
  trader:'text-emerald-400', analyst:'text-amber-400', viewer:'text-gray-400',
}

export default function Layout() {
  useAlchemySocket()
  const { connected, emergencyStop, portfolioNAV, portfolioPnL } = useAlchemyStore()
  const { user, logout, isAdmin } = useAuth()

  return (
    <div className="flex h-screen bg-gray-950 overflow-hidden">

      {/* ── Sidebar ────────────────────────────────────────────────────── */}
      <aside className="w-52 flex-shrink-0 bg-gray-900 border-r border-gray-800 flex flex-col overflow-hidden">

        {/* Logo */}
        <div className="h-14 flex items-center px-4 border-b border-gray-800 flex-shrink-0">
          <span className="text-xl mr-2">🔮</span>
          <div>
            <div className="text-sm font-bold text-white tracking-wide leading-tight">ALCHEMY</div>
            <div className="text-[10px] text-gray-500">v0.6 · Secure</div>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 py-3 overflow-y-auto overflow-x-hidden">
          {NAV.map(({ to, icon: Icon, label }) => (
            <NavLink key={to} to={to}
              className={({ isActive }) => clsx(
                'flex items-center gap-3 px-3 py-2 text-sm transition-colors mx-2 rounded-lg mb-0.5 truncate',
                isActive
                  ? 'bg-blue-600/20 text-blue-400 font-medium'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'
              )}>
              <Icon size={15} className="flex-shrink-0"/>
              <span className="truncate">{label}</span>
            </NavLink>
          ))}

          {isAdmin && (
            <div className="mt-2 pt-2 border-t border-gray-800 mx-2">
              <NavLink to="/admin"
                className={({ isActive }) => clsx(
                  'flex items-center gap-3 px-3 py-2 text-sm rounded-lg transition-colors',
                  isActive
                    ? 'bg-purple-600/20 text-purple-400 font-medium'
                    : 'text-purple-400/70 hover:text-purple-300 hover:bg-purple-900/20'
                )}>
                <Shield size={15}/><span>Admin Panel</span>
              </NavLink>
            </div>
          )}
        </nav>

        {/* User footer */}
        <div className="p-3 border-t border-gray-800 flex-shrink-0 space-y-2">
          {user && (
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-xs font-bold text-white flex-shrink-0">
                {user.email?.[0]?.toUpperCase()}
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-xs font-medium text-white truncate leading-tight">{user.email}</div>
                <div className={clsx('text-[10px] capitalize', ROLE_CLR[user.role]||'text-gray-400')}>
                  {user.role?.replace('_',' ')}
                </div>
              </div>
              <button onClick={logout} title="Sign out"
                className="text-gray-600 hover:text-red-400 transition-colors flex-shrink-0 p-1">
                <LogOut size={13}/>
              </button>
            </div>
          )}
          <div className="flex items-center justify-between text-[10px]">
            <span className="text-gray-600">Feed</span>
            <span className={clsx('flex items-center gap-1', connected?'text-emerald-400':'text-gray-600')}>
              <span className={clsx('w-1.5 h-1.5 rounded-full', connected?'bg-emerald-400 animate-pulse':'bg-gray-600')}/>
              {connected?'Live':'Offline'}
            </span>
          </div>
        </div>
      </aside>

      {/* ── Main area ──────────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">

        {/* Topbar */}
        <header className="h-14 bg-gray-900 border-b border-gray-800 flex items-center px-5 flex-shrink-0 gap-4">
          {emergencyStop && (
            <div className="flex items-center gap-1.5 bg-red-900/40 border border-red-500/60 text-red-400 text-xs px-3 py-1 rounded-lg animate-pulse">
              <AlertTriangle size={12}/> Emergency Stop
            </div>
          )}
          <div className="flex items-center gap-5 ml-auto">
            <div className="text-right">
              <div className="text-[10px] text-gray-500">Portfolio NAV</div>
              <div className="text-sm font-semibold text-white">
                {portfolioNAV
                  ? `₹${portfolioNAV.toLocaleString('en-IN',{maximumFractionDigits:0})}`
                  : '₹0'}
              </div>
            </div>
            <div className="text-right">
              <div className="text-[10px] text-gray-500">Day P&L</div>
              <div className={clsx('text-sm font-semibold', portfolioPnL>=0?'text-emerald-400':'text-red-400')}>
                {portfolioPnL>=0?'+':''}{portfolioPnL
                  ? `₹${portfolioPnL.toLocaleString('en-IN',{maximumFractionDigits:0})}`
                  : '₹0'}
              </div>
            </div>
            <div className="text-[10px] text-gray-500 flex items-center gap-1.5">
              <Radio size={10} className="text-blue-400"/>
              {new Date().toLocaleTimeString('en-IN',{hour:'2-digit',minute:'2-digit'})} IST
            </div>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto overflow-x-hidden">
          <div className="p-5 max-w-screen-2xl mx-auto w-full">
            <Outlet/>
          </div>
        </main>
      </div>
    </div>
  )
}
