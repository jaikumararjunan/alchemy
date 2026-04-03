import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/context/AuthContext'
import {
  Bell, BellOff, Plus, Send, Trash2, CheckCircle, XCircle,
  RefreshCw, Eye, EyeOff, Settings, AlertTriangle, Clock,
  ChevronDown, ChevronRight, Info, Zap
} from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'

// ── Provider icons + colors ────────────────────────────────────────────────────
const PROVIDER_META = {
  telegram:  { icon: '✈️', color: '#229ED9', label: 'Telegram',  bg: 'bg-sky-900/30 border-sky-500/30' },
  whatsapp:  { icon: '💬', color: '#25D366', label: 'WhatsApp',  bg: 'bg-green-900/30 border-green-500/30' },
  sms:       { icon: '📱', color: '#6366F1', label: 'SMS',       bg: 'bg-indigo-900/30 border-indigo-500/30' },
  email:     { icon: '📧', color: '#F59E0B', label: 'Email',     bg: 'bg-amber-900/30 border-amber-500/30' },
  slack:     { icon: '💼', color: '#4A154B', label: 'Slack',     bg: 'bg-purple-900/30 border-purple-500/30' },
  discord:   { icon: '🎮', color: '#5865F2', label: 'Discord',   bg: 'bg-indigo-900/30 border-indigo-500/30' },
  webhook:   { icon: '🔗', color: '#10B981', label: 'Webhook',   bg: 'bg-emerald-900/30 border-emerald-500/30' },
  pushover:  { icon: '🔔', color: '#E8792C', label: 'Pushover',  bg: 'bg-orange-900/30 border-orange-500/30' },
}

const SEVERITY_BADGE = {
  info:     'bg-blue-900/40 text-blue-400',
  success:  'bg-emerald-900/40 text-emerald-400',
  warning:  'bg-amber-900/40 text-amber-400',
  critical: 'bg-red-900/40 text-red-400',
}

const STATUS_DOT = {
  sent:      'bg-emerald-400',
  delivered: 'bg-emerald-500',
  failed:    'bg-red-400',
  pending:   'bg-amber-400 animate-pulse',
  queued:    'bg-blue-400 animate-pulse',
  skipped:   'bg-gray-600',
}

// ── Dynamic config form renderer ───────────────────────────────────────────────
function ConfigForm({ fields = [], values, onChange }) {
  const [showSecrets, setShowSecrets] = useState({})

  return (
    <div className="space-y-3">
      {fields.map(field => (
        <div key={field.key}>
          <label className="text-xs text-gray-400 mb-1 flex items-center justify-between">
            <span>{field.label}{field.required && <span className="text-red-400 ml-0.5">*</span>}</span>
            {field.help_text && (
              <span className="text-gray-600 text-xs normal-case">{field.help_text.slice(0,60)}</span>
            )}
          </label>
          {field.field_type === 'toggle' ? (
            <label className="flex items-center gap-2 cursor-pointer">
              <div className={clsx('relative w-9 h-5 rounded-full transition-colors',
                values[field.key] ? 'bg-blue-600' : 'bg-gray-700')}
                onClick={() => onChange(field.key, !values[field.key])}>
                <div className={clsx('absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full transition-transform',
                  values[field.key] ? 'translate-x-4' : '')} />
              </div>
              <span className="text-xs text-gray-400">{values[field.key] ? 'Enabled' : 'Disabled'}</span>
            </label>
          ) : field.field_type === 'select' ? (
            <select value={values[field.key] || ''} onChange={e => onChange(field.key, e.target.value)}
              className="input-field text-xs">
              <option value="">Select…</option>
              {field.key === 'backend' && ['twilio','msg91','aws_sns'].map(v=><option key={v}>{v}</option>)}
              {field.key === 'parse_mode' && ['MarkdownV2','HTML'].map(v=><option key={v}>{v}</option>)}
              {field.key === 'provider' && ['twilio','meta'].map(v=><option key={v}>{v}</option>)}
            </select>
          ) : (
            <div className="relative">
              <input
                type={field.secret && !showSecrets[field.key] ? 'password' : 'text'}
                value={values[field.key] || ''}
                onChange={e => onChange(field.key, e.target.value)}
                placeholder={field.placeholder}
                className="input-field text-xs pr-8 font-mono"
              />
              {field.secret && (
                <button type="button"
                  onClick={() => setShowSecrets(s => ({...s, [field.key]: !s[field.key]}))}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500">
                  {showSecrets[field.key] ? <EyeOff size={12}/> : <Eye size={12}/>}
                </button>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

// ── Add Channel Dialog ─────────────────────────────────────────────────────────
function AddChannelModal({ providers, onClose, onAdd }) {
  const [step,     setStep]    = useState('pick')  // pick | configure
  const [provider, setProvider] = useState(null)
  const [name,     setName]    = useState('')
  const [config,   setConfig]  = useState({})
  const [showInstructions, setShowInstructions] = useState(false)

  const updateConfig = (k, v) => setConfig(c => ({...c, [k]: v}))

  const handleAdd = () => {
    if (!name.trim()) return toast.error('Enter a channel name')
    onAdd({ name, provider: provider.type, config })
    onClose()
  }

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 rounded-2xl border border-gray-700 w-full max-w-lg shadow-2xl">
        <div className="flex items-center justify-between p-5 border-b border-gray-800">
          <h3 className="font-semibold text-white">Add Notification Channel</h3>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300 text-xl">✕</button>
        </div>

        <div className="p-5">
          {step === 'pick' && (
            <div className="space-y-3">
              <p className="text-sm text-gray-400">Choose a notification provider:</p>
              <div className="grid grid-cols-2 gap-2">
                {providers.map(p => {
                  const meta = PROVIDER_META[p.type] || {}
                  return (
                    <button key={p.type} onClick={() => { setProvider(p); setStep('configure') }}
                      className={clsx('flex items-center gap-3 p-3 rounded-xl border text-left hover:border-blue-500/50 transition-all', meta.bg || 'bg-gray-800 border-gray-700')}>
                      <span className="text-2xl">{meta.icon || '📣'}</span>
                      <div>
                        <div className="text-sm font-medium text-white">{p.name}</div>
                        <div className="text-xs text-gray-500">{p.config_fields?.filter(f=>f.required).length} required fields</div>
                      </div>
                    </button>
                  )
                })}
              </div>
              {/* "Add New Provider" hint */}
              <div className="mt-3 bg-gray-800/50 rounded-lg p-3 text-xs text-gray-500 border border-gray-700/50">
                <span className="text-blue-400 font-medium">+ Add a new provider:</span> Create
                {' '}<code className="text-gray-300">alchemy/notifications/providers/yourname.py</code>
                {' '}extending <code className="text-gray-300">BaseNotificationProvider</code> and register in the registry. Done.
              </div>
            </div>
          )}

          {step === 'configure' && provider && (
            <div className="space-y-4">
              <div className="flex items-center gap-2">
                <button onClick={() => setStep('pick')} className="text-gray-500 hover:text-gray-300 text-sm">←</button>
                <span className="text-2xl">{PROVIDER_META[provider.type]?.icon}</span>
                <h4 className="font-medium text-white">{provider.name}</h4>
              </div>

              <div>
                <label className="text-xs text-gray-400 mb-1 block">Channel Name</label>
                <input value={name} onChange={e=>setName(e.target.value)}
                  className="input-field" placeholder={`My ${provider.name}`} />
              </div>

              <ConfigForm fields={provider.config_fields} values={config} onChange={updateConfig} />

              {provider.setup_instructions && (
                <div>
                  <button onClick={() => setShowInstructions(s=>!s)}
                    className="text-xs text-blue-400 flex items-center gap-1">
                    <Info size={11} /> {showInstructions ? 'Hide' : 'Show'} setup instructions
                  </button>
                  {showInstructions && (
                    <div className="mt-2 bg-gray-800 rounded-lg p-3 text-xs text-gray-300 whitespace-pre-line border border-gray-700">
                      {provider.setup_instructions}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        <div className="flex gap-2 p-5 border-t border-gray-800">
          <button onClick={onClose} className="btn-ghost flex-1">Cancel</button>
          {step === 'configure' && (
            <button onClick={handleAdd} disabled={!name.trim()} className="btn-primary flex-1">
              <Plus size={14} className="inline mr-1" /> Add Channel
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Channel Card ───────────────────────────────────────────────────────────────
function ChannelCard({ channel, onTest, onDelete, onToggle }) {
  const meta = PROVIDER_META[channel.provider] || {}
  return (
    <div className={clsx('rounded-xl border p-4 space-y-3 transition-all', meta.bg || 'bg-gray-900 border-gray-800',
      !channel.enabled && 'opacity-60')}>
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <span className="text-2xl">{meta.icon || '📣'}</span>
          <div>
            <div className="font-medium text-white text-sm">{channel.name}</div>
            <div className="text-xs text-gray-500 capitalize">{channel.provider}</div>
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          <span className={clsx('w-2 h-2 rounded-full flex-shrink-0',
            channel.enabled ? 'bg-emerald-400' : 'bg-gray-600')} />
          <span className="text-xs text-gray-500">{channel.enabled ? 'Active' : 'Disabled'}</span>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="bg-gray-900/60 rounded-lg px-2 py-1.5">
          <span className="text-gray-500">Sent: </span>
          <span className="text-emerald-400 font-medium">{channel.total_sent || 0}</span>
        </div>
        <div className="bg-gray-900/60 rounded-lg px-2 py-1.5">
          <span className="text-gray-500">Failed: </span>
          <span className={clsx('font-medium', channel.total_failed > 0 ? 'text-red-400' : 'text-gray-400')}>
            {channel.total_failed || 0}
          </span>
        </div>
      </div>

      {channel.last_error && (
        <div className="text-xs text-red-400 bg-red-900/20 rounded px-2 py-1 truncate">
          ⚠ {channel.last_error}
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-1.5">
        <button onClick={() => onTest(channel.id)} title="Test"
          className="flex-1 py-1.5 text-xs bg-blue-900/30 hover:bg-blue-800/40 text-blue-400 rounded-lg transition-colors flex items-center justify-center gap-1">
          <Send size={11} /> Test
        </button>
        <button onClick={() => onToggle(channel.id, !channel.enabled)}
          className="flex-1 py-1.5 text-xs bg-gray-800 hover:bg-gray-700 text-gray-400 rounded-lg transition-colors flex items-center justify-center gap-1">
          {channel.enabled ? <BellOff size={11}/> : <Bell size={11}/>}
          {channel.enabled ? 'Pause' : 'Enable'}
        </button>
        <button onClick={() => onDelete(channel.id)}
          className="px-3 py-1.5 text-xs bg-red-900/20 hover:bg-red-900/40 text-red-400 rounded-lg transition-colors">
          <Trash2 size={11}/>
        </button>
      </div>
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function NotificationsPage() {
  const { apiClient } = useAuth()
  const qc = useQueryClient()
  const api = apiClient()
  const [showAdd, setShowAdd] = useState(false)
  const [tab, setTab] = useState('channels')  // channels | rules | log | settings

  // Queries
  const { data: providersData } = useQuery({
    queryKey: ['notif-providers'],
    queryFn: () => api.get('/notifications/providers').then(r => r.data),
  })
  const { data: channelsData, isLoading } = useQuery({
    queryKey: ['notif-channels'],
    queryFn: () => api.get('/notifications/channels').then(r => r.data),
    refetchInterval: 15000,
  })
  const { data: logData } = useQuery({
    queryKey: ['notif-log', tab],
    queryFn: () => api.get('/notifications/delivery-log?limit=30').then(r => r.data),
    enabled: tab === 'log',
  })
  const { data: prefData } = useQuery({
    queryKey: ['notif-prefs', tab],
    queryFn: () => api.get('/notifications/preferences').then(r => r.data),
    enabled: tab === 'settings',
  })

  // Mutations
  const addMut = useMutation({
    mutationFn: (data) => api.post('/notifications/channels', data).then(r => r.data),
    onSuccess: () => { toast.success('Channel added!'); qc.invalidateQueries(['notif-channels']) },
    onError: (e) => toast.error(e.response?.data?.detail || 'Failed to add channel'),
  })
  const deleteMut = useMutation({
    mutationFn: (id) => api.delete(`/notifications/channels/${id}`).then(r => r.data),
    onSuccess: () => { toast.success('Channel removed'); qc.invalidateQueries(['notif-channels']) },
  })
  const testMut = useMutation({
    mutationFn: (id) => api.post(`/notifications/channels/${id}/test`).then(r => r.data),
    onSuccess: (d) => {
      if (d.success) toast.success(`✅ Test sent! Message ID: ${d.message_id || 'OK'}`)
      else toast.error(`❌ Test failed: ${d.error}`)
    },
  })
  const updateMut = useMutation({
    mutationFn: ({id, ...data}) => api.put(`/notifications/channels/${id}`, data).then(r => r.data),
    onSuccess: () => qc.invalidateQueries(['notif-channels']),
  })
  const prefMut = useMutation({
    mutationFn: (data) => api.post('/notifications/preferences', data).then(r => r.data),
    onSuccess: () => { toast.success('Preferences saved'); qc.invalidateQueries(['notif-prefs']) },
  })

  const channels  = channelsData?.channels || []
  const providers = providersData?.providers || []
  const prefs     = prefData?.preferences || {}

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white flex items-center gap-2">
            <Bell size={20} className="text-blue-400" /> Notifications
          </h1>
          <p className="text-sm text-gray-400">
            Telegram · WhatsApp · SMS — trading alerts, risk events, order fills
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-xs text-gray-500">
            <span className="text-white font-medium">{channels.filter(c=>c.enabled).length}</span> active channels
          </div>
          <button onClick={() => setShowAdd(true)} className="btn-primary text-xs">
            <Plus size={13} className="inline mr-1" /> Add Channel
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-gray-800 rounded-lg p-1 w-fit">
        {[['channels','Channels'],['rules','Rules'],['log','Delivery Log'],['settings','Settings']].map(([k,l]) => (
          <button key={k} onClick={() => setTab(k)}
            className={clsx('px-4 py-1.5 text-sm font-medium rounded-md transition-colors',
              tab===k ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-gray-200')}>
            {l}
          </button>
        ))}
      </div>

      {/* Channels Tab */}
      {tab === 'channels' && (
        <>
          {isLoading
            ? <div className="text-gray-500 text-center py-12 animate-pulse">Loading channels…</div>
            : channels.length === 0
              ? (
                <div className="text-center py-16 space-y-4">
                  <Bell size={48} className="text-gray-700 mx-auto" />
                  <div>
                    <h3 className="text-gray-400 font-medium">No notification channels yet</h3>
                    <p className="text-gray-600 text-sm mt-1">Add Telegram, WhatsApp, or SMS to receive trading alerts</p>
                  </div>
                  <button onClick={() => setShowAdd(true)} className="btn-primary">
                    <Plus size={14} className="inline mr-1" /> Add Your First Channel
                  </button>
                </div>
              )
              : (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  {channels.map(ch => (
                    <ChannelCard key={ch.id} channel={ch}
                      onTest={id => testMut.mutate(id)}
                      onDelete={id => { if (confirm('Delete this channel?')) deleteMut.mutate(id) }}
                      onToggle={(id, enabled) => updateMut.mutate({ id, enabled })}
                    />
                  ))}
                </div>
              )
          }

          {/* Available providers grid */}
          {providers.length > 0 && (
            <div className="card border-dashed border-gray-700">
              <h3 className="text-sm font-semibold text-gray-300 mb-3 flex items-center gap-2">
                <Zap size={14} className="text-blue-400" />
                Available Providers · <span className="text-gray-500 font-normal">Add new providers by creating a Python file</span>
              </h3>
              <div className="flex flex-wrap gap-2">
                {providers.map(p => {
                  const meta = PROVIDER_META[p.type] || {}
                  return (
                    <button key={p.type} onClick={() => setShowAdd(true)}
                      className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-800 hover:bg-gray-700 rounded-lg text-xs transition-colors border border-gray-700 hover:border-blue-500/40">
                      <span>{meta.icon || '📣'}</span>
                      <span className="text-gray-300">{p.name}</span>
                    </button>
                  )
                })}
              </div>
            </div>
          )}
        </>
      )}

      {/* Rules Tab */}
      {tab === 'rules' && (
        <div className="card">
          <h2 className="section-title">Notification Rules</h2>
          <p className="text-sm text-gray-400 mb-4">Configure which events trigger which channels. Default: all events → all channels.</p>
          <div className="text-center py-8 text-gray-500">
            <Settings size={32} className="mx-auto mb-3 opacity-50" />
            <p className="text-sm">Rule builder coming in v0.6</p>
            <p className="text-xs text-gray-600 mt-1">Currently all events are routed to all enabled channels automatically</p>
          </div>
        </div>
      )}

      {/* Delivery Log Tab */}
      {tab === 'log' && (
        <div className="card">
          <h2 className="section-title">Delivery Log</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-gray-500 border-b border-gray-800">
                  {['Time','Provider','Event','Status','Message ID'].map(h =>
                    <th key={h} className="pb-2 text-left font-medium pr-4">{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {(logData?.records || []).map((r, i) => (
                  <tr key={i} className="table-row">
                    <td className="py-2 pr-4 text-gray-500 whitespace-nowrap">
                      {new Date(r.created_at).toLocaleTimeString('en-IN')}
                    </td>
                    <td className="py-2 pr-4">
                      <span className="flex items-center gap-1">
                        <span>{PROVIDER_META[r.provider]?.icon || '📣'}</span>
                        <span className="text-gray-300 capitalize">{r.provider}</span>
                      </span>
                    </td>
                    <td className="py-2 pr-4 text-gray-400 font-mono">{r.event_id?.slice(0,8)}…</td>
                    <td className="py-2 pr-4">
                      <span className="flex items-center gap-1.5">
                        <span className={clsx('w-2 h-2 rounded-full', STATUS_DOT[r.status] || 'bg-gray-500')} />
                        <span className={r.status==='sent'||r.status==='delivered'?'text-emerald-400':r.status==='failed'?'text-red-400':'text-amber-400'}>
                          {r.status}
                        </span>
                      </span>
                    </td>
                    <td className="py-2 text-gray-600 font-mono">{r.message_id?.slice(0,16) || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {(!logData?.records || logData.records.length === 0) && (
              <div className="text-center py-8 text-gray-500 text-sm">No delivery records yet</div>
            )}
          </div>
        </div>
      )}

      {/* Settings Tab */}
      {tab === 'settings' && prefs && (
        <div className="card max-w-lg space-y-5">
          <h2 className="section-title">Notification Preferences</h2>

          <div className="flex items-center justify-between p-3 bg-gray-800/50 rounded-lg">
            <div>
              <div className="text-sm font-medium text-white">All Notifications</div>
              <div className="text-xs text-gray-500">Master enable/disable for all channels</div>
            </div>
            <label className="relative inline-flex cursor-pointer">
              <input type="checkbox" className="sr-only peer"
                checked={prefs.enabled !== false}
                onChange={e => prefMut.mutate({ enabled: e.target.checked })} />
              <div className="w-9 h-5 bg-gray-700 peer-checked:bg-blue-600 rounded-full
                peer-checked:after:translate-x-4 after:absolute after:top-0.5 after:left-0.5
                after:w-4 after:h-4 after:bg-white after:rounded-full after:transition-transform" />
            </label>
          </div>

          <div>
            <label className="text-xs text-gray-400 mb-1 block">Quiet Hours (no non-critical alerts)</label>
            <div className="flex items-center gap-2">
              <select value={prefs.quiet_hours_start ?? ''} onChange={e => prefMut.mutate({quiet_hours_start: Number(e.target.value)})}
                className="input-field w-24">
                <option value="">Off</option>
                {Array.from({length:24},(_,i)=><option key={i} value={i}>{String(i).padStart(2,'0')}:00</option>)}
              </select>
              <span className="text-gray-500 text-sm">to</span>
              <select value={prefs.quiet_hours_end ?? ''} onChange={e => prefMut.mutate({quiet_hours_end: Number(e.target.value)})}
                className="input-field w-24">
                <option value="">Off</option>
                {Array.from({length:24},(_,i)=><option key={i} value={i}>{String(i).padStart(2,'0')}:00</option>)}
              </select>
              <span className="text-gray-500 text-xs">{prefs.timezone_str}</span>
            </div>
          </div>

          <div>
            <label className="text-xs text-gray-400 mb-1 block">Max notifications per hour</label>
            <input type="number" value={prefs.max_per_hour || 50} min="5" max="200"
              onChange={e => prefMut.mutate({ max_per_hour: Number(e.target.value) })}
              className="input-field w-32" />
          </div>
        </div>
      )}

      {/* Add Channel Modal */}
      {showAdd && (
        <AddChannelModal
          providers={providers}
          onClose={() => setShowAdd(false)}
          onAdd={(data) => addMut.mutate(data)}
        />
      )}
    </div>
  )
}
