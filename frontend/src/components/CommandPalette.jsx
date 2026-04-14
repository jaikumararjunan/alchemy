import { useState, useEffect, useRef, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Search, LayoutDashboard, Briefcase, Bitcoin, Star, Zap, Wallet, Bot,
  BookOpen, BarChart3, ShieldAlert, BellRing, Key, GitBranch, Bell,
  Settings, TrendingUp, Moon, Sun, LogOut, Command
} from 'lucide-react'
import clsx from 'clsx'

const COMMANDS = [
  { id: 'dashboard', label: 'Dashboard', path: '/dashboard', icon: LayoutDashboard, group: 'Navigate' },
  { id: 'portfolio', label: 'Portfolio', path: '/portfolio', icon: Briefcase, group: 'Navigate' },
  { id: 'crypto', label: 'Crypto Markets', path: '/crypto', icon: Bitcoin, group: 'Navigate' },
  { id: 'watchlist', label: 'Watchlist', path: '/watchlist', icon: Star, group: 'Navigate' },
  { id: 'paper', label: 'Paper Trading', path: '/paper-trading', icon: Wallet, group: 'Trading' },
  { id: 'auto', label: 'Auto Trading', path: '/autonomous', icon: Bot, group: 'Trading' },
  { id: 'signals', label: 'AI Signals', path: '/signals', icon: Zap, group: 'Trading' },
  { id: 'strategy', label: 'Strategy', path: '/strategy', icon: BookOpen, group: 'Trading' },
  { id: 'analytics', label: 'Analytics', path: '/analytics', icon: BarChart3, group: 'Analysis' },
  { id: 'risk', label: 'Risk Management', path: '/risk', icon: ShieldAlert, group: 'Analysis' },
  { id: 'alerts', label: 'Price Alerts', path: '/alerts', icon: BellRing, group: 'Analysis' },
  { id: 'tokens', label: 'Exchange Keys', path: '/tokens', icon: Key, group: 'Settings' },
  { id: 'settings', label: 'Settings', path: '/settings', icon: Settings, group: 'Settings' },
  { id: 'notifications', label: 'Notifications', path: '/notifications', icon: Bell, group: 'Settings' },
]

export default function CommandPalette() {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState(0)
  const inputRef = useRef(null)
  const navigate = useNavigate()

  // Keyboard shortcut: Cmd+K or Ctrl+K
  useEffect(() => {
    const handler = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setOpen(o => !o)
        setQuery('')
        setSelected(0)
      }
      if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 50)
  }, [open])

  const filtered = useMemo(() => {
    if (!query) return COMMANDS
    const q = query.toLowerCase()
    return COMMANDS.filter(c =>
      c.label.toLowerCase().includes(q) ||
      c.group.toLowerCase().includes(q) ||
      c.id.includes(q)
    )
  }, [query])

  const groups = useMemo(() => {
    const g = {}
    filtered.forEach(c => {
      if (!g[c.group]) g[c.group] = []
      g[c.group].push(c)
    })
    return g
  }, [filtered])

  const handleSelect = (cmd) => {
    setOpen(false)
    setQuery('')
    if (cmd.path) navigate(cmd.path)
    if (cmd.action) cmd.action()
  }

  const handleKeyDown = (e) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setSelected(s => Math.min(s + 1, filtered.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setSelected(s => Math.max(s - 1, 0))
    } else if (e.key === 'Enter' && filtered[selected]) {
      handleSelect(filtered[selected])
    }
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-[90] flex items-start justify-center pt-[15vh]"
      onClick={() => setOpen(false)}>
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />

      <div className="relative w-full max-w-lg mx-4 animate-slide-up"
        onClick={e => e.stopPropagation()}>
        <div className="rounded-2xl overflow-hidden shadow-2xl"
          style={{ background: 'var(--surface-2)', border: '1px solid var(--border)' }}>

          {/* Search input */}
          <div className="flex items-center gap-3 px-5 py-4 border-b" style={{ borderColor: 'var(--border)' }}>
            <Search size={18} className="text-gray-500 flex-shrink-0" />
            <input ref={inputRef} value={query} onChange={e => { setQuery(e.target.value); setSelected(0) }}
              onKeyDown={handleKeyDown}
              placeholder="Search pages, actions..."
              className="flex-1 bg-transparent text-sm text-white placeholder-gray-600 outline-none font-medium" />
            <kbd className="hidden sm:flex items-center gap-0.5 px-2 py-0.5 rounded-md text-[10px] font-mono text-gray-600 bg-white/[0.04] border border-white/[0.06]">
              ESC
            </kbd>
          </div>

          {/* Results */}
          <div className="max-h-[360px] overflow-y-auto py-2">
            {filtered.length === 0 ? (
              <div className="py-10 text-center text-gray-600 text-sm">No results for "{query}"</div>
            ) : (
              Object.entries(groups).map(([group, items]) => (
                <div key={group}>
                  <div className="px-5 py-1.5">
                    <span className="text-[10px] font-bold tracking-[0.12em] text-gray-600 uppercase">{group}</span>
                  </div>
                  {items.map((cmd, i) => {
                    const globalIdx = filtered.indexOf(cmd)
                    return (
                      <button key={cmd.id} onClick={() => handleSelect(cmd)}
                        onMouseEnter={() => setSelected(globalIdx)}
                        className={clsx(
                          'w-full flex items-center gap-3 px-5 py-2.5 text-left transition-colors',
                          globalIdx === selected
                            ? 'bg-blue-500/10 text-blue-400'
                            : 'text-gray-400 hover:bg-white/[0.03]'
                        )}>
                        <cmd.icon size={16} className={globalIdx === selected ? 'text-blue-400' : 'text-gray-600'} />
                        <span className="text-sm font-medium">{cmd.label}</span>
                        {globalIdx === selected && (
                          <span className="ml-auto text-[10px] text-gray-600 font-mono">↵ Enter</span>
                        )}
                      </button>
                    )
                  })}
                </div>
              ))
            )}
          </div>

          {/* Footer */}
          <div className="px-5 py-3 border-t flex items-center gap-4 text-[10px] text-gray-600"
            style={{ borderColor: 'var(--border)' }}>
            <span className="flex items-center gap-1"><kbd className="px-1 py-0.5 rounded bg-white/[0.04] font-mono">↑↓</kbd> Navigate</span>
            <span className="flex items-center gap-1"><kbd className="px-1 py-0.5 rounded bg-white/[0.04] font-mono">↵</kbd> Select</span>
            <span className="flex items-center gap-1"><kbd className="px-1 py-0.5 rounded bg-white/[0.04] font-mono">esc</kbd> Close</span>
          </div>
        </div>
      </div>
    </div>
  )
}

// Trigger button for header/sidebar
export function CommandPaletteTrigger({ onClick }) {
  return (
    <button onClick={onClick}
      className="hidden lg:flex items-center gap-2 px-3 py-1.5 rounded-xl text-xs text-gray-500 bg-white/[0.03] border border-white/[0.06] hover:border-white/[0.1] hover:text-gray-400 transition-all">
      <Search size={13} />
      <span>Search</span>
      <kbd className="ml-2 px-1.5 py-0.5 rounded text-[10px] font-mono bg-white/[0.04] border border-white/[0.06]">⌘K</kbd>
    </button>
  )
}
