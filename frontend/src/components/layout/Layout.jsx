import { useState, useEffect, useRef } from 'react'
import { Outlet, NavLink, useLocation } from 'react-router-dom'
import { useAlchemySocket } from '@/hooks/useAlchemySocket'
import { useAlchemyStore } from '@/store'
import { useAuth } from '@/context/AuthContext'
import {
  LayoutDashboard, Briefcase, Zap, Bitcoin, Key, GitBranch,
  ShieldAlert, BarChart3, BookOpen, Settings, Bell, Shield,
  LogOut, Radio, AlertTriangle, Menu, X, ChevronRight,
  TrendingUp, Star, Bot, Wallet,
} from 'lucide-react'
import clsx from 'clsx'

const NAV = [
  { to:'/dashboard',     icon:LayoutDashboard, label:'Dashboard',     group:'main' },
  { to:'/portfolio',     icon:Briefcase,       label:'Portfolio',     group:'main' },
  { to:'/crypto',        icon:Bitcoin,         label:'Crypto',        group:'main' },
  { to:'/signals',       icon:Zap,             label:'AI Signals',    group:'trade' },
  { to:'/paper-trading', icon:Wallet,          label:'Paper Trade',   group:'trade' },
  { to:'/autonomous',    icon:Bot,             label:'Auto Trade',    group:'trade' },
  { to:'/strategy',      icon:BookOpen,        label:'Strategy',      group:'trade' },
  { to:'/analytics',     icon:BarChart3,       label:'Analytics',     group:'trade' },
  { to:'/risk',          icon:ShieldAlert,     label:'Risk',          group:'trade' },
  { to:'/tokens',        icon:Key,             label:'Tokens',        group:'config' },
  { to:'/workflows',     icon:GitBranch,       label:'Workflows',     group:'config' },
  { to:'/notifications', icon:Bell,            label:'Notifications', group:'config' },
  { to:'/settings',      icon:Settings,        label:'Settings',      group:'config' },
  { to:'/subscription',  icon:Star,            label:'Plans',         group:'config' },
]

const ROLE_CLR = {
  super_admin:'text-purple-400', admin:'text-blue-400',
  trader:'text-emerald-400', analyst:'text-amber-400', viewer:'text-gray-400',
}

function NavItem({ to, icon: Icon, label, onClick }) {
  return (
    <NavLink to={to} onClick={onClick}
      className={({ isActive }) => clsx(
        'flex items-center gap-3 px-3 py-2.5 text-sm rounded-xl transition-all duration-150 mx-2 mb-0.5',
        isActive
          ? 'bg-blue-600/20 text-blue-400 font-semibold'
          : 'text-gray-400 hover:text-white hover:bg-gray-800/80 active:scale-95'
      )}>
      <Icon size={16} className="flex-shrink-0"/>
      <span className="truncate">{label}</span>
      <ChevronRight size={12} className="ml-auto opacity-30"/>
    </NavLink>
  )
}

export default function Layout() {
  useAlchemySocket()
  const { connected, emergencyStop, portfolioNAV, portfolioPnL, setPortfolio } = useAlchemyStore()
  const { user, logout, isAdmin, apiClient } = useAuth()
  const location  = useLocation()
  const [open, setOpen] = useState(false)
  const overlayRef = useRef(null)

  // Fetch portfolio for header display
  useEffect(() => {
    const api = apiClient()
    const fetchPortfolio = async () => {
      try {
        const { data } = await api.get('/paper/portfolio')
        if (data) {
          setPortfolio(
            data.portfolio_value || 0,
            (data.unrealized_pnl || 0) + (data.realized_pnl || 0),
            data.open_positions || 0,
          )
        }
      } catch {}
    }
    fetchPortfolio()
    const interval = setInterval(fetchPortfolio, 15000)
    return () => clearInterval(interval)
  }, [])

  // Close nav on route change
  useEffect(() => { setOpen(false) }, [location.pathname])

  const groups = {
    main:   { label:'Markets',       items: NAV.filter(n=>n.group==='main') },
    trade:  { label:'Trading',       items: NAV.filter(n=>n.group==='trade') },
    config: { label:'Configuration', items: NAV.filter(n=>n.group==='config') },
  }

  const Sidebar = ({ mobile }) => (
    <aside className={clsx(
      'flex flex-col bg-gray-900 border-r border-gray-800',
      mobile ? 'h-full w-72' : 'w-52 h-full'
    )}>
      {/* Logo */}
      <div className="h-14 flex items-center justify-between px-4 border-b border-gray-800 flex-shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-xl">🔮</span>
          <div>
            <div className="text-sm font-black text-white tracking-wider leading-tight">ALCHEMY</div>
            <div className="text-[10px] text-gray-500">v0.6 · AI Trading</div>
          </div>
        </div>
        {mobile && (
          <button onClick={()=>setOpen(false)} className="p-1.5 rounded-lg text-gray-500 hover:text-white hover:bg-gray-800">
            <X size={16}/>
          </button>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 py-3 overflow-y-auto overflow-x-hidden">
        {Object.entries(groups).map(([key, { label, items }]) => (
          <div key={key} className="mb-2">
            <div className="px-4 py-1 text-[10px] font-bold text-gray-600 uppercase tracking-widest">{label}</div>
            {items.map(item => (
              <NavItem key={item.to} {...item} onClick={()=>mobile&&setOpen(false)}/>
            ))}
          </div>
        ))}
        {isAdmin && (
          <div className="mt-2 pt-2 border-t border-gray-800 mx-2">
            <NavLink to="/admin"
              className={({ isActive }) => clsx(
                'flex items-center gap-3 px-3 py-2.5 text-sm rounded-xl transition-all',
                isActive ? 'bg-purple-600/20 text-purple-400 font-semibold' : 'text-purple-400/70 hover:text-purple-300 hover:bg-purple-900/20'
              )}>
              <Shield size={16}/><span>Admin Panel</span><ChevronRight size={12} className="ml-auto opacity-30"/>
            </NavLink>
          </div>
        )}
      </nav>

      {/* User footer */}
      <div className="p-3 border-t border-gray-800 flex-shrink-0">
        {user && (
          <div className="flex items-center gap-2.5 mb-2">
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-sm font-bold text-white flex-shrink-0">
              {user.email?.[0]?.toUpperCase()}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-xs font-semibold text-white truncate">{user.email}</div>
              <div className="flex items-center gap-1.5">
                <span className={clsx('text-[10px] capitalize', ROLE_CLR[user.role]||'text-gray-400')}>
                  {user.role?.replace('_',' ')}
                </span>
                <span className="text-[10px] text-gray-700">·</span>
                <span className={clsx('text-[10px] capitalize px-1 rounded',
                  user.subscription==='enterprise'?'text-amber-400':'text-blue-400')}>
                  {user.subscription||'free'}
                </span>
              </div>
            </div>
            <button onClick={logout} title="Sign out"
              className="p-1.5 rounded-lg text-gray-600 hover:text-red-400 hover:bg-red-900/20 transition-colors">
              <LogOut size={13}/>
            </button>
          </div>
        )}
        <div className="flex items-center justify-between text-[10px]">
          <span className="text-gray-600">Live Feed</span>
          <span className={clsx('flex items-center gap-1', connected?'text-emerald-400':'text-gray-600')}>
            <span className={clsx('w-1.5 h-1.5 rounded-full', connected?'bg-emerald-400 animate-pulse':'bg-gray-600')}/>
            {connected?'Connected':'Offline'}
          </span>
        </div>
      </div>
    </aside>
  )

  return (
    <div className="flex h-screen bg-gray-950 overflow-hidden">
      {/* Desktop sidebar */}
      <div className="hidden lg:flex flex-shrink-0">
        <Sidebar mobile={false}/>
      </div>

      {/* Mobile slide-in overlay */}
      {open && (
        <div className="fixed inset-0 z-50 flex lg:hidden">
          <div ref={overlayRef} className="absolute inset-0 bg-black/60 backdrop-blur-sm"
               onClick={()=>setOpen(false)}/>
          <div className="relative flex-shrink-0 animate-slide-in z-10">
            <Sidebar mobile={true}/>
          </div>
        </div>
      )}

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">

        {/* Topbar */}
        <header className="h-14 bg-gray-900/95 backdrop-blur-sm border-b border-gray-800 flex items-center px-4 flex-shrink-0 gap-3 sticky top-0 z-40">
          {/* Mobile menu button */}
          <button onClick={()=>setOpen(true)}
            className="lg:hidden p-2 rounded-xl text-gray-400 hover:text-white hover:bg-gray-800 transition-colors flex-shrink-0">
            <Menu size={18}/>
          </button>

          {/* Emergency stop banner */}
          {emergencyStop && (
            <div className="flex items-center gap-1.5 bg-red-900/40 border border-red-500/60 text-red-400 text-xs px-2 py-1 rounded-lg animate-pulse">
              <AlertTriangle size={12}/><span className="hidden sm:inline">Emergency Stop</span>
            </div>
          )}

          {/* Portfolio metrics */}
          <div className="flex items-center gap-4 ml-auto">
            <div className="hidden sm:block text-right">
              <div className="text-[9px] text-gray-600 uppercase tracking-wider">Portfolio</div>
              <div className="text-xs font-bold text-white">
                {portfolioNAV ? `$${portfolioNAV.toLocaleString()}` : '$0'}
              </div>
            </div>
            <div className="text-right">
              <div className="text-[9px] text-gray-600 uppercase tracking-wider">Day P&L</div>
              <div className={clsx('text-xs font-bold', portfolioPnL>=0?'text-emerald-400':'text-red-400')}>
                {portfolioPnL>=0?'+':''}{portfolioPnL ? `$${portfolioPnL.toLocaleString()}` : '$0'}
              </div>
            </div>
            <div className="hidden md:flex items-center gap-1 text-[10px] text-gray-600">
              <Radio size={9} className="text-blue-400"/>
              {new Date().toLocaleTimeString('en-IN',{hour:'2-digit',minute:'2-digit'})} IST
            </div>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto overflow-x-hidden">
          <div className="p-4 md:p-5 max-w-screen-2xl mx-auto w-full">
            <Outlet/>
          </div>
        </main>

        {/* Mobile bottom nav */}
        <nav className="lg:hidden flex-shrink-0 bg-gray-900 border-t border-gray-800 flex items-center px-1 py-1 safe-area-inset-bottom">
          {NAV.filter(n=>n.group==='main').concat(NAV.filter(n=>n.to==='/tokens')).map(item => {
            const Icon = item.icon
            return (
              <NavLink key={item.to} to={item.to}
                className={({ isActive }) => clsx(
                  'flex-1 flex flex-col items-center gap-0.5 py-1.5 px-1 rounded-xl transition-all active:scale-95',
                  isActive ? 'text-blue-400' : 'text-gray-600'
                )}>
                <Icon size={18}/>
                <span className="text-[9px] font-medium">{item.label}</span>
              </NavLink>
            )
          })}
          {/* More button */}
          <button onClick={()=>setOpen(true)}
            className="flex-1 flex flex-col items-center gap-0.5 py-1.5 px-1 rounded-xl text-gray-600 active:scale-95 transition-all">
            <Menu size={18}/>
            <span className="text-[9px] font-medium">More</span>
          </button>
        </nav>
      </div>
    </div>
  )
}
