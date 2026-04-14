import { useQuery } from '@tanstack/react-query'
import { useAuth } from '@/context/AuthContext'
import { Shield, Monitor, MapPin, AlertTriangle, Clock, Eye, Lock, Unlock, Fingerprint, Globe, Trash2 } from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'

function RiskGauge({ score, level }) {
  const colors = { low:'#10B981', medium:'#F59E0B', high:'#F97316', critical:'#EF4444' }
  const color = colors[level] || colors.low
  const pct = Math.min(score, 100)
  const angle = (pct / 100) * 180

  return (
    <div className="flex flex-col items-center">
      <svg width="140" height="80" viewBox="0 0 140 80">
        <path d="M 10 75 A 60 60 0 0 1 130 75" fill="none" stroke="var(--border)" strokeWidth="8" strokeLinecap="round" />
        <path d="M 10 75 A 60 60 0 0 1 130 75" fill="none" stroke={color} strokeWidth="8" strokeLinecap="round"
          strokeDasharray={`${angle * 1.047} 999`} style={{filter:`drop-shadow(0 0 6px ${color}40)`}} />
      </svg>
      <div className="text-2xl font-display font-bold text-white -mt-6">{score}</div>
      <div className="text-xs font-semibold mt-1 uppercase tracking-wider" style={{color}}>{level}</div>
    </div>
  )
}

export default function SecurityDashboardPage() {
  const { apiClient } = useAuth()
  const api = apiClient()

  const { data: stats } = useQuery({
    queryKey: ['security-stats'],
    queryFn: () => api.get('/security/stats?days=30').then(r => r.data),
    refetchInterval: 30000,
  })

  const { data: risk } = useQuery({
    queryKey: ['security-risk'],
    queryFn: () => api.get('/security/risk-assessment').then(r => r.data).catch(() => null),
  })

  const { data: devices } = useQuery({
    queryKey: ['security-devices'],
    queryFn: () => api.get('/security/devices').then(r => r.data),
  })

  const { data: locations } = useQuery({
    queryKey: ['security-locations'],
    queryFn: () => api.get('/security/locations').then(r => r.data),
  })

  const { data: history } = useQuery({
    queryKey: ['security-history'],
    queryFn: () => api.get('/security/login-history?limit=10').then(r => r.data),
  })

  const { data: geoRules } = useQuery({
    queryKey: ['security-geo-fence'],
    queryFn: () => api.get('/security/geo-fence').then(r => r.data),
  })

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-display font-bold text-white tracking-tight flex items-center gap-3">
          <Shield size={24} className="text-blue-400" /> Security Dashboard
        </h1>
        <p className="text-sm text-gray-500 mt-1">Account security, device management, and geo-fencing</p>
      </div>

      {/* Top row: Risk + Stats */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 stagger-children">
        {/* Risk Score */}
        <div className="card flex flex-col items-center justify-center py-6">
          <h3 className="text-[11px] font-bold text-gray-500 uppercase tracking-wider mb-4">Current Risk Score</h3>
          <RiskGauge score={risk?.risk_score || 0} level={risk?.risk_level || 'low'} />
          {risk?.risk_factors?.length > 0 && (
            <div className="mt-4 space-y-1 w-full px-2">
              {risk.risk_factors.map((f, i) => (
                <div key={i} className="flex items-center gap-2 text-xs text-gray-500">
                  <AlertTriangle size={11} className="text-amber-500 flex-shrink-0" />
                  <span>{f}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 30-day stats */}
        <div className="card col-span-1 lg:col-span-2">
          <h3 className="text-[11px] font-bold text-gray-500 uppercase tracking-wider mb-4">Last 30 Days</h3>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            {[
              { label: 'Logins', value: stats?.successful_logins || 0, color: 'text-emerald-400' },
              { label: 'Failed', value: stats?.failed_logins || 0, color: stats?.failed_logins > 0 ? 'text-rose-400' : 'text-gray-400' },
              { label: 'Unique IPs', value: stats?.unique_ips || 0, color: 'text-blue-400' },
              { label: 'Devices', value: stats?.unique_devices || 0, color: 'text-amber-400' },
              { label: 'Countries', value: stats?.countries?.length || 0, color: 'text-purple-400' },
              { label: 'High Risk', value: stats?.high_risk_events || 0, color: stats?.high_risk_events > 0 ? 'text-rose-400' : 'text-gray-400' },
              { label: 'Total Events', value: stats?.total_events || 0, color: 'text-gray-300' },
              { label: 'Period', value: '30d', color: 'text-gray-500' },
            ].map(s => (
              <div key={s.label} className="text-center">
                <div className={clsx('text-xl font-display font-bold', s.color)}>{s.value}</div>
                <div className="text-[10px] text-gray-600 font-medium mt-0.5">{s.label}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Devices + Locations */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Known Devices */}
        <div className="card">
          <h3 className="text-[11px] font-bold text-gray-500 uppercase tracking-wider mb-4 flex items-center gap-2">
            <Monitor size={14} /> Known Devices ({devices?.total || 0})
          </h3>
          <div className="space-y-2">
            {(devices?.devices || []).slice(0, 8).map(d => (
              <div key={d.fingerprint} className="flex items-center gap-3 p-2.5 rounded-xl bg-white/[0.02] border border-white/[0.04]">
                <div className={clsx('w-8 h-8 rounded-lg flex items-center justify-center',
                  d.is_trusted ? 'bg-emerald-500/15' : 'bg-gray-500/10')}>
                  <Fingerprint size={14} className={d.is_trusted ? 'text-emerald-400' : 'text-gray-500'} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-gray-300 truncate">{d.browser} / {d.os}</div>
                  <div className="text-[10px] text-gray-600">{d.device_type} · {d.login_count} logins · {d.last_seen?.split('T')[0]}</div>
                </div>
                {d.is_trusted ? (
                  <Lock size={12} className="text-emerald-400 flex-shrink-0" />
                ) : (
                  <Unlock size={12} className="text-gray-600 flex-shrink-0" />
                )}
              </div>
            ))}
            {(!devices?.devices || devices.devices.length === 0) && (
              <div className="text-center py-6 text-gray-600 text-sm">No devices recorded yet</div>
            )}
          </div>
        </div>

        {/* Known Locations */}
        <div className="card">
          <h3 className="text-[11px] font-bold text-gray-500 uppercase tracking-wider mb-4 flex items-center gap-2">
            <MapPin size={14} /> Known Locations
          </h3>
          <div className="space-y-2">
            {(locations?.locations || []).slice(0, 8).map((loc, i) => (
              <div key={i} className="flex items-center gap-3 p-2.5 rounded-xl bg-white/[0.02] border border-white/[0.04]">
                <div className="w-8 h-8 rounded-lg bg-blue-500/10 flex items-center justify-center">
                  <Globe size={14} className="text-blue-400" />
                </div>
                <div className="flex-1">
                  <div className="text-sm font-medium text-gray-300">{loc.city || 'Unknown'}, {loc.country_code}</div>
                  <div className="text-[10px] text-gray-600">{loc.login_count} logins · Last: {loc.last_seen?.split('T')[0]}</div>
                </div>
              </div>
            ))}
            {(!locations?.locations || locations.locations.length === 0) && (
              <div className="text-center py-6 text-gray-600 text-sm">No locations recorded yet</div>
            )}
          </div>
        </div>
      </div>

      {/* Login History */}
      <div className="card">
        <h3 className="text-[11px] font-bold text-gray-500 uppercase tracking-wider mb-4 flex items-center gap-2">
          <Clock size={14} /> Recent Login Activity
        </h3>
        <div className="space-y-1">
          {(history?.history || []).map((e, i) => (
            <div key={i} className="flex items-center gap-3 py-2.5 border-b border-white/[0.03] last:border-0">
              <div className={clsx('w-2 h-2 rounded-full flex-shrink-0',
                e.event_type === 'login_success' ? 'bg-emerald-400' :
                e.event_type === 'login_failed' ? 'bg-rose-400' : 'bg-amber-400')} />
              <div className="flex-1 min-w-0">
                <div className="text-sm text-gray-300">
                  <span className="font-medium">{e.event_type?.replace(/_/g, ' ')}</span>
                  {e.device_data?.browser && (
                    <span className="text-gray-500 ml-2">· {e.device_data.browser} / {e.device_data.os}</span>
                  )}
                </div>
                <div className="text-[10px] text-gray-600 flex items-center gap-3">
                  <span>IP: {e.ip}</span>
                  {e.geo_data?.city && <span>{e.geo_data.city}, {e.geo_data.country_code}</span>}
                  <span className="font-mono">{e.timestamp?.split('T')[0]} {e.timestamp?.split('T')[1]?.slice(0,5)}</span>
                </div>
              </div>
              <div className={clsx('text-[10px] font-bold px-2 py-0.5 rounded-lg',
                e.risk_level === 'low' ? 'bg-emerald-500/10 text-emerald-400' :
                e.risk_level === 'medium' ? 'bg-amber-500/10 text-amber-400' :
                'bg-rose-500/10 text-rose-400'
              )}>
                {e.risk_score}
              </div>
            </div>
          ))}
          {(!history?.history || history.history.length === 0) && (
            <div className="text-center py-8 text-gray-600 text-sm">No login history yet</div>
          )}
        </div>
      </div>

      {/* Geo-Fence Rules */}
      <div className="card">
        <h3 className="text-[11px] font-bold text-gray-500 uppercase tracking-wider mb-4 flex items-center gap-2">
          <Shield size={14} /> Geo-Fence Rules ({geoRules?.rules?.length || 0})
        </h3>
        {(geoRules?.rules || []).length === 0 ? (
          <div className="text-center py-6 text-gray-600 text-sm">
            No geo-fence rules configured. Add rules via API to restrict login by country or IP.
          </div>
        ) : (
          <div className="space-y-2">
            {geoRules.rules.map(r => (
              <div key={r.id} className="flex items-center gap-3 p-2.5 rounded-xl bg-white/[0.02] border border-white/[0.04]">
                <div className={clsx('w-8 h-8 rounded-lg flex items-center justify-center',
                  r.action === 'block' ? 'bg-rose-500/10' : 'bg-emerald-500/10')}>
                  {r.action === 'block'
                    ? <Lock size={14} className="text-rose-400" />
                    : <Unlock size={14} className="text-emerald-400" />}
                </div>
                <div className="flex-1">
                  <div className="text-sm font-medium text-gray-300">{r.action.toUpperCase()} {r.rule_type}: {r.value}</div>
                  <div className="text-[10px] text-gray-600">{r.description || 'No description'}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
