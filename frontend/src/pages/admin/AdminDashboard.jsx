import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/context/AuthContext'
import {
  Users, ShieldAlert, Activity, Search, UserX, UserCheck,
  RefreshCw, Eye, Ban, Unlock, ChevronDown, AlertTriangle,
  BarChart3, Server, Globe
} from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'

const ROLE_BADGE = {
  super_admin: 'bg-purple-900/50 text-purple-400 border border-purple-500/30',
  admin:       'bg-blue-900/50 text-blue-400 border border-blue-500/30',
  trader:      'bg-emerald-900/50 text-emerald-400 border border-emerald-500/30',
  analyst:     'bg-amber-900/50 text-amber-400 border border-amber-500/30',
  viewer:      'bg-gray-800 text-gray-400 border border-gray-700',
}
const STATUS_BADGE = {
  active:   'bg-emerald-900/50 text-emerald-400',
  pending:  'bg-amber-900/50 text-amber-400',
  locked:   'bg-red-900/50 text-red-400',
  banned:   'bg-red-950/80 text-red-300',
  inactive: 'bg-gray-800 text-gray-500',
}

function StatCard({ label, value, sub, icon: Icon, color = 'blue' }) {
  const cols = { blue:'text-blue-400 bg-blue-500/10', red:'text-red-400 bg-red-500/10',
                  green:'text-emerald-400 bg-emerald-500/10', amber:'text-amber-400 bg-amber-500/10' }
  return (
    <div className="card">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs text-gray-400">{label}</p>
          <p className="text-2xl font-bold text-white mt-1">{value}</p>
          {sub && <p className="text-xs text-gray-500 mt-0.5">{sub}</p>}
        </div>
        <div className={clsx('p-2 rounded-lg', cols[color])}><Icon size={18} /></div>
      </div>
    </div>
  )
}

function UserRow({ user, onAction }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <tr className="table-row">
        <td className="py-3 pr-4">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-xs font-bold text-white flex-shrink-0">
              {user.username?.[0]?.toUpperCase()}
            </div>
            <div>
              <div className="text-sm font-medium text-white">{user.username}</div>
              <div className="text-xs text-gray-500">{user.email}</div>
            </div>
          </div>
        </td>
        <td className="py-3 pr-4">
          <span className={clsx('text-xs px-2 py-0.5 rounded-full font-medium', ROLE_BADGE[user.role] || 'bg-gray-800 text-gray-400')}>
            {user.role}
          </span>
        </td>
        <td className="py-3 pr-4">
          <span className={clsx('text-xs px-2 py-0.5 rounded-full', STATUS_BADGE[user.status] || '')}>
            {user.status}
          </span>
        </td>
        <td className="py-3 pr-4 text-xs text-gray-400">
          {user.totp_enabled ? <span className="text-emerald-400">✓ 2FA On</span> : <span className="text-gray-600">2FA Off</span>}
        </td>
        <td className="py-3 pr-4 text-xs text-gray-500">
          {user.last_login_at ? new Date(user.last_login_at).toLocaleDateString('en-IN') : 'Never'}
        </td>
        <td className="py-3">
          <div className="relative">
            <button onClick={() => setOpen(o=>!o)}
              className="text-xs text-gray-400 hover:text-gray-200 flex items-center gap-1">
              Actions <ChevronDown size={11} />
            </button>
            {open && (
              <div className="absolute right-0 top-6 bg-gray-800 border border-gray-700 rounded-lg shadow-xl z-10 min-w-[140px] py-1">
                {user.status === 'locked' && (
                  <button onClick={() => { onAction('unlock', user.id); setOpen(false) }}
                    className="flex items-center gap-2 w-full px-3 py-2 text-xs text-emerald-400 hover:bg-gray-700">
                    <Unlock size={11} /> Unlock
                  </button>
                )}
                {user.status !== 'banned' && (
                  <button onClick={() => { onAction('ban', user.id); setOpen(false) }}
                    className="flex items-center gap-2 w-full px-3 py-2 text-xs text-red-400 hover:bg-gray-700">
                    <Ban size={11} /> Ban User
                  </button>
                )}
                <button onClick={() => { onAction('revoke_sessions', user.id); setOpen(false) }}
                  className="flex items-center gap-2 w-full px-3 py-2 text-xs text-amber-400 hover:bg-gray-700">
                  <RefreshCw size={11} /> Revoke Sessions
                </button>
              </div>
            )}
          </div>
        </td>
      </tr>
    </>
  )
}

export default function AdminDashboard() {
  const { apiClient } = useAuth()
  const qc = useQueryClient()
  const api = apiClient()

  const [search, setSearch]   = useState('')
  const [roleFilter, setRole] = useState('')
  const [tab, setTab]         = useState('users') // users | audit | system

  const { data: stats } = useQuery({
    queryKey: ['admin-stats'],
    queryFn: () => api.get('/admin/stats').then(r => r.data),
    refetchInterval: 30000,
  })

  const { data: usersData, isLoading: usersLoading } = useQuery({
    queryKey: ['admin-users', search, roleFilter],
    queryFn: () => api.get('/admin/users', { params: { search, role: roleFilter } }).then(r => r.data),
    keepPreviousData: true,
  })

  const { data: auditData } = useQuery({
    queryKey: ['admin-audit', tab],
    queryFn: () => api.get('/admin/audit-logs', { params: { limit: 50 } }).then(r => r.data),
    enabled: tab === 'audit',
  })

  const banMut = useMutation({
    mutationFn: (id) => api.post(`/admin/users/${id}/ban`).then(r=>r.data),
    onSuccess: () => { toast.success('User banned'); qc.invalidateQueries(['admin-users']) },
    onError: (e) => toast.error(e.response?.data?.detail || 'Failed'),
  })
  const unlockMut = useMutation({
    mutationFn: (id) => api.post(`/admin/users/${id}/unlock`).then(r=>r.data),
    onSuccess: () => { toast.success('User unlocked'); qc.invalidateQueries(['admin-users']) },
  })
  const revokeMut = useMutation({
    mutationFn: (id) => api.delete(`/admin/users/${id}/sessions`).then(r=>r.data),
    onSuccess: (d) => toast.success(`${d.count} sessions revoked`),
  })

  const handleAction = (action, userId) => {
    if (action === 'ban')            banMut.mutate(userId)
    else if (action === 'unlock')    unlockMut.mutate(userId)
    else if (action === 'revoke_sessions') revokeMut.mutate(userId)
  }

  const RISK_COLOR = (score) =>
    score >= 80 ? 'text-red-400' : score >= 60 ? 'text-amber-400' : score >= 40 ? 'text-yellow-400' : 'text-gray-400'

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white flex items-center gap-2">
            <ShieldAlert size={20} className="text-blue-400" /> Admin Control Panel
          </h1>
          <p className="text-sm text-gray-400">User management · Security audit · System health</p>
        </div>
      </div>

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard label="Total Users"      value={stats.users?.total}   sub={`${stats.users?.active} active`} icon={Users}       color="blue"  />
          <StatCard label="Active Sessions"  value={stats.sessions?.active}                                     icon={Globe}       color="green" />
          <StatCard label="Failed Logins 24h" value={stats.security_24h?.failed_logins}                        icon={ShieldAlert} color="amber" />
          <StatCard label="High Risk Events" value={stats.security_24h?.high_risk_events}                      icon={AlertTriangle} color="red" />
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 bg-gray-800 rounded-lg p-1 w-fit">
        {[['users','Users'],['audit','Audit Log'],['system','System']].map(([k,l]) => (
          <button key={k} onClick={() => setTab(k)}
            className={clsx('px-4 py-1.5 text-sm font-medium rounded-md transition-colors',
              tab===k ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-gray-200')}>
            {l}
          </button>
        ))}
      </div>

      {/* Users Tab */}
      {tab === 'users' && (
        <div className="card">
          <div className="flex items-center gap-3 mb-4">
            <div className="relative flex-1">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
              <input value={search} onChange={e=>setSearch(e.target.value)}
                className="input-field pl-8" placeholder="Search by email, username…" />
            </div>
            <select value={roleFilter} onChange={e=>setRole(e.target.value)} className="input-field w-36">
              <option value="">All Roles</option>
              {['super_admin','admin','trader','analyst','viewer'].map(r=><option key={r}>{r}</option>)}
            </select>
          </div>

          {usersLoading
            ? <div className="text-gray-500 text-center py-8 animate-pulse">Loading users…</div>
            : <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead><tr className="text-gray-500 border-b border-gray-800">
                    {['User','Role','Status','2FA','Last Login','Actions'].map(h=>
                      <th key={h} className="pb-2 text-left font-medium pr-4">{h}</th>)}
                  </tr></thead>
                  <tbody>
                    {(usersData?.users || []).map(u =>
                      <UserRow key={u.id} user={u} onAction={handleAction} />)}
                  </tbody>
                </table>
                <div className="text-xs text-gray-600 mt-3">
                  {usersData?.total} total users · Page {usersData?.page} of {usersData?.pages}
                </div>
              </div>
          }
        </div>
      )}

      {/* Audit Log Tab */}
      {tab === 'audit' && (
        <div className="card">
          <h2 className="section-title">Security Audit Log</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead><tr className="text-gray-500 border-b border-gray-800">
                {['Time','Action','Status','IP Address','Risk','Detail'].map(h=>
                  <th key={h} className="pb-2 text-left font-medium pr-4">{h}</th>)}
              </tr></thead>
              <tbody>
                {(auditData?.logs || []).map((l,i) => (
                  <tr key={i} className="table-row">
                    <td className="py-2 pr-4 text-gray-500 whitespace-nowrap">
                      {new Date(l.timestamp).toLocaleString('en-IN',{hour:'2-digit',minute:'2-digit',second:'2-digit'})}
                    </td>
                    <td className="py-2 pr-4 font-mono text-blue-300">{l.action}</td>
                    <td className="py-2 pr-4">
                      <span className={l.status==='success'?'text-emerald-400':l.status==='failure'?'text-red-400':'text-amber-400'}>
                        {l.status}
                      </span>
                    </td>
                    <td className="py-2 pr-4 text-gray-400 font-mono">{l.ip_address || '—'}</td>
                    <td className={clsx('py-2 pr-4 font-bold', RISK_COLOR(l.risk_score))}>
                      {l.risk_score > 0 ? l.risk_score : '—'}
                    </td>
                    <td className="py-2 text-gray-600 truncate max-w-xs">{l.detail || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* System Tab */}
      {tab === 'system' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="card">
            <h2 className="section-title flex items-center gap-2"><Server size={16} /> Broker Connections</h2>
            <div className="space-y-2">
              {Object.entries(stats?.broker_connections || {}).map(([ex, info]) => (
                <div key={ex} className="flex items-center justify-between p-2 bg-gray-800/50 rounded-lg">
                  <span className="text-sm font-medium text-white capitalize">{ex}</span>
                  <span className={clsx('text-xs font-medium',
                    info.status==='active'?'text-emerald-400':'text-gray-500')}>
                    {info.status || 'not configured'}
                  </span>
                </div>
              ))}
            </div>
          </div>
          <div className="card">
            <h2 className="section-title flex items-center gap-2"><Activity size={16} /> Quick Actions</h2>
            <div className="space-y-2">
              {[
                ['Force refresh all tokens', () => api.post('/tokens/validate-all')],
                ['Export audit log (CSV)', () => toast('Coming soon')],
                ['Send test notification', () => toast.success('Test notification sent')],
              ].map(([label, action]) => (
                <button key={label} onClick={action}
                  className="w-full text-left px-3 py-2 text-sm text-gray-300 bg-gray-800/50 hover:bg-gray-700 rounded-lg transition-colors">
                  {label}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
