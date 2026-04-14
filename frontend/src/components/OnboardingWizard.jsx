import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Rocket, TrendingUp, Shield, ChevronRight, Check, Sparkles, Bot, BarChart3 } from 'lucide-react'
import clsx from 'clsx'

const ONBOARDING_KEY = 'alchemy_onboarded'

export function useOnboarding() {
  const [show, setShow] = useState(false)

  useEffect(() => {
    const done = localStorage.getItem(ONBOARDING_KEY)
    if (!done) setShow(true)
  }, [])

  const complete = () => {
    localStorage.setItem(ONBOARDING_KEY, Date.now().toString())
    setShow(false)
  }

  const reset = () => {
    localStorage.removeItem(ONBOARDING_KEY)
    setShow(true)
  }

  return { showOnboarding: show, completeOnboarding: complete, resetOnboarding: reset }
}

const STEPS = [
  {
    id: 'experience',
    title: 'Welcome to Alchemy',
    subtitle: "Let's personalize your experience",
    icon: Sparkles,
    options: [
      { id: 'beginner', label: 'Beginner', desc: 'New to trading', icon: '🌱' },
      { id: 'intermediate', label: 'Intermediate', desc: '1-3 years experience', icon: '📈' },
      { id: 'advanced', label: 'Advanced', desc: 'Professional trader', icon: '🏆' },
    ],
  },
  {
    id: 'interest',
    title: 'What interests you?',
    subtitle: 'Select all that apply',
    icon: TrendingUp,
    multi: true,
    options: [
      { id: 'paper', label: 'Paper Trading', desc: 'Practice with virtual money', icon: '📝' },
      { id: 'auto', label: 'AI Auto Trading', desc: 'Let AI trade for you', icon: '🤖' },
      { id: 'crypto', label: 'Crypto Markets', desc: 'BTC, ETH, SOL and more', icon: '₿' },
      { id: 'analytics', label: 'Analytics & Risk', desc: 'Portfolio analysis tools', icon: '📊' },
    ],
  },
  {
    id: 'ready',
    title: "You're all set!",
    subtitle: 'Start your trading journey',
    icon: Rocket,
    final: true,
    quickActions: [
      { label: 'Place First Paper Trade', path: '/paper-trading', icon: TrendingUp, color: 'from-emerald-500 to-teal-600' },
      { label: 'Start Auto Trading', path: '/autonomous', icon: Bot, color: 'from-blue-500 to-indigo-600' },
      { label: 'Explore Analytics', path: '/analytics', icon: BarChart3, color: 'from-purple-500 to-pink-600' },
    ],
  },
]

export default function OnboardingWizard({ onComplete }) {
  const [step, setStep] = useState(0)
  const [selections, setSelections] = useState({})
  const navigate = useNavigate()
  const current = STEPS[step]

  const toggleSelection = (optionId) => {
    if (current.multi) {
      setSelections(s => ({
        ...s,
        [current.id]: {
          ...(s[current.id] || {}),
          [optionId]: !(s[current.id]?.[optionId]),
        },
      }))
    } else {
      setSelections(s => ({ ...s, [current.id]: optionId }))
    }
  }

  const canContinue = current.final || (current.multi
    ? Object.values(selections[current.id] || {}).some(Boolean)
    : !!selections[current.id])

  const handleNext = () => {
    if (step < STEPS.length - 1) {
      setStep(s => s + 1)
    }
  }

  const handleAction = (path) => {
    localStorage.setItem('alchemy_preferences', JSON.stringify(selections))
    onComplete?.()
    navigate(path)
  }

  const handleSkip = () => {
    onComplete?.()
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4"
      style={{ background: 'rgba(11,17,32,0.95)', backdropFilter: 'blur(20px)' }}>

      <div className="w-full max-w-lg animate-slide-up">
        {/* Progress */}
        <div className="flex gap-2 mb-8 px-4">
          {STEPS.map((_, i) => (
            <div key={i} className="flex-1 h-1 rounded-full overflow-hidden bg-white/[0.06]">
              <div className={clsx('h-full rounded-full transition-all duration-500',
                i <= step ? 'bg-gradient-to-r from-blue-500 to-indigo-500 w-full' : 'w-0')} />
            </div>
          ))}
        </div>

        {/* Card */}
        <div className="rounded-3xl p-8 relative overflow-hidden"
          style={{ background: 'var(--surface-2)', border: '1px solid var(--border)' }}>

          {/* Background glow */}
          <div className="absolute -top-20 -right-20 w-40 h-40 rounded-full opacity-10 blur-[60px]"
            style={{ background: 'radial-gradient(circle, #3B82F6, transparent)' }} />

          {/* Icon */}
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-blue-500/20 to-indigo-500/20 border border-blue-500/20 flex items-center justify-center mb-6">
            <current.icon size={24} className="text-blue-400" />
          </div>

          {/* Title */}
          <h2 className="text-2xl font-display font-bold text-white tracking-tight mb-1">{current.title}</h2>
          <p className="text-sm text-gray-500 mb-8">{current.subtitle}</p>

          {/* Options */}
          {!current.final && (
            <div className="space-y-3 mb-8">
              {current.options.map(opt => {
                const selected = current.multi
                  ? selections[current.id]?.[opt.id]
                  : selections[current.id] === opt.id
                return (
                  <button key={opt.id} onClick={() => toggleSelection(opt.id)}
                    className={clsx(
                      'w-full flex items-center gap-4 p-4 rounded-2xl border transition-all duration-200 text-left',
                      selected
                        ? 'border-blue-500/40 bg-blue-500/10 shadow-sm shadow-blue-500/10'
                        : 'border-white/[0.06] bg-white/[0.02] hover:border-white/[0.1] hover:bg-white/[0.04]'
                    )}>
                    <span className="text-2xl">{opt.icon}</span>
                    <div className="flex-1">
                      <div className={clsx('text-sm font-semibold', selected ? 'text-white' : 'text-gray-300')}>{opt.label}</div>
                      <div className="text-xs text-gray-500 mt-0.5">{opt.desc}</div>
                    </div>
                    {selected && (
                      <div className="w-6 h-6 rounded-full bg-blue-500 flex items-center justify-center">
                        <Check size={14} className="text-white" />
                      </div>
                    )}
                  </button>
                )
              })}
            </div>
          )}

          {/* Final step — quick actions */}
          {current.final && (
            <div className="space-y-3 mb-8">
              {current.quickActions.map(action => (
                <button key={action.path} onClick={() => handleAction(action.path)}
                  className="w-full flex items-center gap-4 p-4 rounded-2xl border border-white/[0.06] bg-white/[0.02] hover:border-white/[0.12] hover:bg-white/[0.04] transition-all duration-200 text-left group">
                  <div className={clsx('w-10 h-10 rounded-xl bg-gradient-to-br flex items-center justify-center shadow-lg', action.color)}>
                    <action.icon size={18} className="text-white" />
                  </div>
                  <span className="text-sm font-semibold text-gray-300 group-hover:text-white transition-colors">{action.label}</span>
                  <ChevronRight size={16} className="ml-auto text-gray-600 group-hover:text-gray-400 transition-colors" />
                </button>
              ))}
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center justify-between">
            <button onClick={handleSkip} className="text-xs text-gray-600 hover:text-gray-400 transition-colors">
              Skip setup
            </button>
            {!current.final && (
              <button onClick={handleNext} disabled={!canContinue}
                className={clsx('btn-primary flex items-center gap-2',
                  !canContinue && 'opacity-40 cursor-not-allowed')}>
                Continue <ChevronRight size={16} />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
