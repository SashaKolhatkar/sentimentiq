import { AlertCircle, CheckCircle2, Info, Loader2, X } from 'lucide-react'
import { useApp } from '../context'

export function Card({ children, className = '' }) {
  return <div className={`card ${className}`}>{children}</div>
}

export function SectionTitle({ eyebrow, title, description, action }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        {eyebrow && <p className="mb-1 text-xs font-bold uppercase tracking-[0.18em] text-primary">{eyebrow}</p>}
        <h2 className="text-xl font-bold tracking-tight sm:text-2xl">{title}</h2>
        {description && <p className="muted mt-1 max-w-2xl text-sm">{description}</p>}
      </div>
      {action}
    </div>
  )
}

const TONES = {
  positive: 'badge-positive',
  negative: 'badge-negative',
  neutral: 'badge-neutral',
  mixed: 'badge-warning',
  primary: 'badge-primary',
  warning: 'badge-warning',
  info: 'badge-primary',
}

export function Badge({ children, tone = 'neutral', className = '' }) {
  return <span className={`chip ${TONES[tone] || TONES.neutral} ${className}`}>{children}</span>
}

export function KpiCard({ label, value, hint, icon: Icon, tone = 'primary', trend }) {
  const toneClass = {
    primary: 'text-primary',
    positive: 'text-[var(--positive)]',
    negative: 'text-[var(--negative)]',
    warning: 'text-[var(--warning)]',
  }[tone] || 'text-primary'
  return (
    <Card className="animate-fade-up p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="muted text-xs font-semibold uppercase tracking-wide">{label}</p>
          <p className="mt-2 text-2xl font-extrabold tracking-tight sm:text-3xl">{value}</p>
          {hint && <p className="muted mt-1 text-xs">{hint}</p>}
        </div>
        {Icon && (
          <div className={`rounded-xl p-2.5 ${toneClass}`} style={{ background: 'var(--surface-2)' }}>
            <Icon size={18} strokeWidth={2.2} />
          </div>
        )}
      </div>
      {trend && <div className="mt-3 text-xs font-semibold">{trend}</div>}
    </Card>
  )
}

export function ChartCard({ title, subtitle, children, action, className = '' }) {
  return (
    <Card className={`p-5 ${className}`}>
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-bold">{title}</h3>
          {subtitle && <p className="muted mt-0.5 text-xs">{subtitle}</p>}
        </div>
        {action}
      </div>
      <div className="min-w-0">{children}</div>
    </Card>
  )
}

export function EmptyState({ icon: Icon, title, description, action }) {
  return (
    <Card className="flex flex-col items-center justify-center px-6 py-16 text-center">
      {Icon && (
        <div className="mb-4 rounded-2xl p-4" style={{ background: 'var(--primary-soft)', color: 'var(--primary)' }}>
          <Icon size={26} />
        </div>
      )}
      <h3 className="text-lg font-bold">{title}</h3>
      {description && <p className="muted mt-2 max-w-md text-sm">{description}</p>}
      {action && <div className="mt-5">{action}</div>}
    </Card>
  )
}

export function Loading({ label = 'Loading…' }) {
  return (
    <div className="flex items-center justify-center gap-2 py-12 text-sm muted">
      <Loader2 className="animate-spin" size={18} /> {label}
    </div>
  )
}

export function ErrorBanner({ message, onDismiss }) {
  if (!message) return null
  return (
    <div className="mb-4 flex items-start gap-3 rounded-xl border px-4 py-3 text-sm"
      style={{ borderColor: 'color-mix(in srgb, var(--negative) 35%, transparent)', background: 'color-mix(in srgb, var(--negative) 8%, transparent)', color: 'var(--negative)' }}>
      <AlertCircle size={18} className="mt-0.5 shrink-0" />
      <span className="flex-1">{message}</span>
      {onDismiss && <button onClick={onDismiss} aria-label="Dismiss"><X size={16} /></button>}
    </div>
  )
}

export function InfoBanner({ children, tone = 'info' }) {
  const Icon = tone === 'warning' ? AlertCircle : tone === 'success' ? CheckCircle2 : Info
  const color = tone === 'warning' ? 'var(--warning)' : tone === 'success' ? 'var(--positive)' : 'var(--primary)'
  return (
    <div className="mb-4 flex items-start gap-3 rounded-xl border px-4 py-3 text-sm"
      style={{ borderColor: `color-mix(in srgb, ${color} 30%, transparent)`, background: `color-mix(in srgb, ${color} 8%, transparent)` }}>
      <Icon size={17} className="mt-0.5 shrink-0" style={{ color }} />
      <div className="flex-1 leading-relaxed">{children}</div>
    </div>
  )
}

export function ProgressPanel({ job }) {
  if (!job) return null
  const complete = job.status === 'complete'
  const failed = job.status === 'failed'
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between text-sm">
        <div className="flex items-center gap-2 font-semibold">
          {!complete && !failed && <Loader2 className="animate-spin text-primary" size={16} />}
          {complete && <CheckCircle2 className="text-[var(--positive)]" size={16} />}
          {failed && <AlertCircle className="text-[var(--negative)]" size={16} />}
          {job.message || 'Working…'}
        </div>
        <span className="muted font-mono text-xs">{job.progress}%</span>
      </div>
      <div className="mt-4 h-2 w-full overflow-hidden rounded-full" style={{ background: 'var(--surface-2)' }}>
        <div className="h-full rounded-full transition-all duration-500" style={{ width: `${job.progress}%`, background: failed ? 'var(--negative)' : 'var(--primary)' }} />
      </div>
      <p className="muted mt-3 text-xs">Models run locally on the server. Larger datasets take longer on CPU.</p>
    </Card>
  )
}

export function Toasts() {
  const { toasts } = useApp()
  return (
    <div className="fixed bottom-5 right-5 z-[100] flex w-[min(92vw,360px)] flex-col gap-2">
      {toasts.map((toast) => {
        const color = toast.type === 'error' ? 'var(--negative)' : toast.type === 'success' ? 'var(--positive)' : 'var(--primary)'
        return (
          <div key={toast.id} className="animate-fade-up rounded-xl border px-4 py-3 text-sm shadow-lg"
            style={{ background: 'var(--surface)', borderColor: `color-mix(in srgb, ${color} 35%, transparent)` }}>
            <div className="flex items-start gap-2">
              <span className="mt-1 h-2 w-2 shrink-0 rounded-full" style={{ background: color }} />
              <span>{toast.message}</span>
            </div>
          </div>
        )
      })}
    </div>
  )
}
