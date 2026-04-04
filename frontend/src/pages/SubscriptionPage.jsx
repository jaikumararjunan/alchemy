import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useAuth } from '@/context/AuthContext'
import { Check, X, Zap, Shield, Users, Building2, Star } from 'lucide-react'
import clsx from 'clsx'

const PLANS = [
  {
    id:'free', name:'Free', price:'₹0', period:'/forever',
    color:'from-gray-700 to-gray-800', border:'border-gray-700',
    icon:Star, iconColor:'text-gray-400',
    description:'Get started with basic trading tools',
    features:[
      {t:'1 exchange (paper only)',ok:true},
      {t:'50 candles chart history',ok:true},
      {t:'5 AI trade ideas/day',ok:true},
      {t:'Momentum strategy only',ok:true},
      {t:'Email OTP + 2FA',ok:true},
      {t:'Live trading',ok:false},
      {t:'Telegram alerts',ok:false},
      {t:'Geo intelligence',ok:false},
      {t:'Data export',ok:false},
    ],
    cta:'Current Plan',
  },
  {
    id:'pro', name:'Pro', price:'₹2,999', period:'/month',
    color:'from-blue-700 to-blue-900', border:'border-blue-500',
    icon:Zap, iconColor:'text-blue-400',
    description:'Full power for individual traders',
    badge:'Most Popular',
    features:[
      {t:'2 exchanges (live trading)',ok:true},
      {t:'500 candles chart history',ok:true},
      {t:'50 AI trade ideas/day',ok:true},
      {t:'All 4 strategies',ok:true},
      {t:'Geo-political signals',ok:true},
      {t:'Telegram alerts',ok:true},
      {t:'CSV data export',ok:true},
      {t:'Backtesting engine',ok:true},
      {t:'WhatsApp alerts',ok:false},
      {t:'Multi-user workspace',ok:false},
    ],
    cta:'Upgrade to Pro',
  },
  {
    id:'team', name:'Team', price:'₹9,999', period:'/month',
    color:'from-purple-700 to-purple-900', border:'border-purple-500',
    icon:Users, iconColor:'text-purple-400',
    description:'Built for trading desks and prop firms',
    features:[
      {t:'4 exchanges (all connected)',ok:true},
      {t:'5,000 candles history',ok:true},
      {t:'Unlimited AI ideas',ok:true},
      {t:'ML price prediction',ok:true},
      {t:'All alerts (TG + WA + SMS)',ok:true},
      {t:'10 concurrent users',ok:true},
      {t:'Audit logs',ok:true},
      {t:'Copy trading',ok:true},
      {t:'Read-only API access',ok:true},
      {t:'JSON + CSV export',ok:true},
    ],
    cta:'Upgrade to Team',
  },
  {
    id:'enterprise', name:'Enterprise', price:'Custom', period:'',
    color:'from-amber-700 to-amber-900', border:'border-amber-500',
    icon:Building2, iconColor:'text-amber-400',
    description:'Institutional-grade, white-label ready',
    features:[
      {t:'Unlimited exchanges',ok:true},
      {t:'Full chart history',ok:true},
      {t:'Custom AI models',ok:true},
      {t:'FIX protocol gateway',ok:true},
      {t:'Full REST API (R/W)',ok:true},
      {t:'Webhook integrations',ok:true},
      {t:'White-label branding',ok:true},
      {t:'Compliance module',ok:true},
      {t:'99.99% SLA',ok:true},
      {t:'Dedicated support',ok:true},
    ],
    cta:'Contact Sales',
  },
]

export default function SubscriptionPage() {
  const { user, apiClient } = useAuth()
  const api = apiClient()
  const [billing, setBilling] = useState('monthly')

  const { data: featData } = useQuery({
    queryKey: ['plan-features'],
    queryFn: () => api.get('/auth/plan/features').then(r=>r.data).catch(()=>null),
  })

  const currentPlan = user?.subscription || 'free'

  return (
    <div className="space-y-6">
      <div className="text-center">
        <h1 className="text-2xl font-bold text-white mb-2">Choose Your Plan</h1>
        <p className="text-gray-400 text-sm">Scale your trading with the right tools</p>
      </div>

      {/* Current plan badge */}
      <div className="flex items-center justify-center gap-2 p-3 bg-blue-900/20 border border-blue-500/30 rounded-2xl">
        <Shield size={16} className="text-blue-400"/>
        <span className="text-sm text-blue-300">
          You are on the <span className="font-bold capitalize">{currentPlan}</span> plan
        </span>
      </div>

      {/* Plan cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        {PLANS.map(plan => {
          const Icon    = plan.icon
          const isCurr  = plan.id === currentPlan
          return (
            <div key={plan.id}
              className={clsx('rounded-2xl border-2 overflow-hidden transition-all',
                isCurr ? 'border-emerald-500 shadow-lg shadow-emerald-500/20' : plan.border,
                'hover:scale-[1.01]')}>
              {/* Header */}
              <div className={clsx('bg-gradient-to-br p-5', plan.color)}>
                {plan.badge && (
                  <div className="text-xs font-bold bg-white/20 text-white px-2 py-0.5 rounded-full inline-block mb-2">
                    {plan.badge}
                  </div>
                )}
                {isCurr && (
                  <div className="text-xs font-bold bg-emerald-500/30 text-emerald-300 px-2 py-0.5 rounded-full inline-block mb-2">
                    ✓ Active
                  </div>
                )}
                <div className="flex items-center gap-2 mb-2">
                  <Icon size={20} className={plan.iconColor}/>
                  <span className="text-lg font-bold text-white">{plan.name}</span>
                </div>
                <div className="flex items-baseline gap-1">
                  <span className="text-3xl font-black text-white">{plan.price}</span>
                  {plan.period && <span className="text-sm text-white/70">{plan.period}</span>}
                </div>
                <p className="text-xs text-white/60 mt-1">{plan.description}</p>
              </div>

              {/* Features */}
              <div className="p-4 bg-gray-900 space-y-2.5">
                {plan.features.map((f,i) => (
                  <div key={i} className="flex items-center gap-2">
                    {f.ok
                      ? <Check size={13} className="text-emerald-400 flex-shrink-0"/>
                      : <X    size={13} className="text-gray-700 flex-shrink-0"/>}
                    <span className={clsx('text-xs', f.ok ? 'text-gray-300' : 'text-gray-600')}>
                      {f.t}
                    </span>
                  </div>
                ))}

                <button
                  className={clsx('w-full mt-4 py-2.5 rounded-xl text-xs font-bold transition-all',
                    isCurr
                      ? 'bg-emerald-900/30 text-emerald-400 cursor-default border border-emerald-500/30'
                      : plan.id === 'enterprise'
                        ? 'bg-amber-600 hover:bg-amber-500 text-white'
                        : 'bg-blue-600 hover:bg-blue-500 text-white')}>
                  {isCurr ? '✓ Current Plan' : plan.cta}
                </button>
              </div>
            </div>
          )
        })}
      </div>

      {/* Feature comparison mini */}
      <div className="card">
        <h2 className="section-title mb-4">Quick Feature Comparison</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-gray-800">
                <th className="text-left pb-3 text-gray-400 font-medium">Feature</th>
                {PLANS.map(p => <th key={p.id} className="pb-3 text-center text-gray-300 font-medium capitalize">{p.name}</th>)}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/50">
              {[
                ['Live Trading',     false, true,  true,  true],
                ['Exchanges',        '1',   '2',   '4',   '∞'],
                ['AI Ideas/Day',     '5',   '50',  '∞',   '∞'],
                ['Telegram Alerts',  false, true,  true,  true],
                ['Backtesting',      false, true,  true,  true],
                ['Multi-User',       false, false, true,  true],
                ['API Access',       false, false, 'R',   'R/W'],
                ['SLA',              '-',   '99.5%','99.9%','99.99%'],
              ].map(([feat, ...vals], i) => (
                <tr key={i} className={clsx('hover:bg-gray-800/20', i%2===0?'':'bg-gray-900/30')}>
                  <td className="py-2.5 text-gray-400">{feat}</td>
                  {vals.map((v,j) => (
                    <td key={j} className="py-2.5 text-center">
                      {v === true  ? <span className="text-emerald-400">✓</span>
                      :v === false ? <span className="text-gray-700">—</span>
                      :<span className="text-gray-300 font-medium">{v}</span>}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
