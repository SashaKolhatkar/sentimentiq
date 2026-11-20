import { useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import {
  Activity, Bot, BrainCircuit, ChartNoAxesCombined, ChevronDown, CircleHelp,
  FileBarChart2, FlaskConical, Hash, LayoutDashboard, LogOut, Menu, Moon, Search,
  Settings, ShieldAlert, Sparkles, Sun, X,
} from 'lucide-react'
import { useApp } from '../context'
import { Badge } from './ui'

const NAV = [
  { to: '/', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/analyze', label: 'Analyze Content', icon: FlaskConical },
  { to: '/sentiment', label: 'Sentiment Analysis', icon: Activity },
  { to: '/emotion', label: 'Emotion Detection', icon: BrainCircuit },
  { to: '/spam', label: 'Spam & Fake Review', icon: ShieldAlert },
  { to: '/bot', label: 'Bot Detection', icon: Bot },
  { to: '/customer', label: 'Customer Insights', icon: Sparkles },
  { to: '/trending', label: 'Trending Topics', icon: Hash },
  { to: '/reports', label: 'Reports', icon: FileBarChart2 },
  { to: '/settings', label: 'Settings', icon: Settings },
]

const THEME_ICONS = { light: Sun, dark: Moon, pastel: Sparkles }

function ThemeSwitcher() {
  const { theme, setTheme } = useApp()
  const [open, setOpen] = useState(false)
  const Icon = THEME_ICONS[theme] || Sun
  return (
    <div className="relative">
      <button className="btn btn-secondary h-9 px-3" onClick={() => setOpen((v) => !v)} title="Change theme">
        <Icon size={16} />
        <span className="hidden capitalize md:inline">{theme}</span>
        <ChevronDown size={14} />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-30" onClick={() => setOpen(false)} />
          <div className="card absolute right-0 z-40 mt-2 w-44 p-1.5">
            {['light', 'dark', 'pastel'].map((option) => {
              const OptionIcon = THEME_ICONS[option]
              return (
                <button
                  key={option}
                  onClick={() => { setTheme(option); setOpen(false) }}
                  className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm capitalize hover:bg-[var(--surface-2)]"
                  style={theme === option ? { background: 'var(--primary-soft)', color: 'var(--primary)' } : undefined}
                >
                  <OptionIcon size={15} /> {option === 'pastel' ? 'Pastel sepia' : option}
                </button>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}

function ActiveRun() {
  const { run } = useApp()
  if (!run) return <Badge tone="neutral">No analysis loaded</Badge>
  return (
    <div className="flex max-w-[240px] items-center gap-2 rounded-xl border px-3 py-1.5">
      <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: run.is_demo ? 'var(--warning)' : 'var(--positive)' }} />
      <span className="truncate text-xs font-semibold">{run.name}</span>
      {run.is_demo && <Badge tone="warning">DEMO</Badge>}
    </div>
  )
}

export default function Layout() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const location = useLocation()
  const { config, user, signOut } = useApp()
  const current = NAV.find((n) => n.end ? location.pathname === '/' : location.pathname.startsWith(n.to))

  return (
    <div className="min-h-screen" style={{ background: 'var(--bg)' }}>
      {/* Sidebar */}
      <aside className={`fixed inset-y-0 left-0 z-50 flex w-[260px] flex-col border-r transition-transform lg:translate-x-0 ${mobileOpen ? 'translate-x-0' : '-translate-x-full'}`}
        style={{ background: 'var(--surface)' }}>
        <div className="flex h-16 items-center justify-between border-b px-5">
          <div className="flex items-center gap-2.5">
            <div className="rounded-xl p-2 text-white" style={{ background: 'var(--primary)' }}>
              <ChartNoAxesCombined size={19} />
            </div>
            <div>
              <p className="text-sm font-extrabold tracking-tight">Sentiment<span className="text-primary">IQ</span></p>
              <p className="muted text-[10px] uppercase tracking-wider">Review intelligence</p>
            </div>
          </div>
          <button className="btn btn-ghost h-8 w-8 p-0 lg:hidden" onClick={() => setMobileOpen(false)}>
            <X size={18} />
          </button>
        </div>

        <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4">
          <p className="muted mb-2 px-3 text-[10px] font-bold uppercase tracking-[0.18em]">Workspace</p>
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              onClick={() => setMobileOpen(false)}
              className={({ isActive }) => `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition ${isActive ? 'text-primary' : 'muted hover:bg-[var(--surface-2)] hover:text-[var(--text)]'}`}
              style={({ isActive }) => isActive ? { background: 'var(--primary-soft)' } : undefined}
            >
              <item.icon size={17} />
              <span className="flex-1">{item.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="border-t p-3">
          <div className="card-soft p-3">
            <div className="flex items-center gap-2 text-xs font-bold">
              <CircleHelp size={14} className="text-primary" />
              Analysis engine
            </div>
            <p className="muted mt-1.5 text-[11px] leading-relaxed">
              Hugging Face models · scikit-learn · {config?.themes?.length || 3} themes
            </p>
            <NavLink to="/settings" className="mt-2 inline-block text-[11px] font-bold text-primary">
              Manage models →
            </NavLink>
          </div>
        </div>
      </aside>

      {mobileOpen && <div className="fixed inset-0 z-40 bg-black/40 lg:hidden" onClick={() => setMobileOpen(false)} />}

      {/* Main */}
      <div className="lg:pl-[260px]">
        <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b px-4 backdrop-blur lg:px-7"
          style={{ background: 'color-mix(in srgb, var(--bg) 86%, transparent)' }}>
          <button className="btn btn-ghost h-9 w-9 p-0 lg:hidden" onClick={() => setMobileOpen(true)}>
            <Menu size={19} />
          </button>
          <div className="hidden sm:block">
            <p className="text-sm font-bold">{current?.label || 'Overview'}</p>
            <p className="muted text-[11px]">Understand what your audience really thinks</p>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <div className="hidden xl:block"><ActiveRun /></div>
            <div className="hidden md:flex items-center gap-2 rounded-xl border px-3 py-2 text-xs muted">
              <Search size={14} /> Quick insights
            </div>
            <ThemeSwitcher />
            {config?.auth_enabled && user && (
              <button className="btn btn-secondary h-9 px-3" onClick={signOut}
                title={`Signed in as ${user.username} (${user.role})`}>
                <LogOut size={15} />
                <span className="hidden md:inline">{user.username}</span>
              </button>
            )}
            <div className="flex h-9 w-9 items-center justify-center rounded-full text-xs font-bold"
              style={{ background: 'var(--primary-soft)', color: 'var(--primary)' }}>
              {(user?.username || 'SI').slice(0, 2).toUpperCase()}
            </div>
          </div>
        </header>

        <main className="mx-auto w-full max-w-[1500px] px-4 py-6 lg:px-7 lg:py-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
