import { useState } from 'react'
import { ChartNoAxesCombined, LockKeyhole, UserPlus } from 'lucide-react'
import { api, setToken } from '../api'
import { useApp } from '../context'

export default function Login() {
  const { config } = useApp()
  const [mode, setMode] = useState('login')
  const [username, setUsername] = useState('admin')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const registering = mode === 'register'

  const submit = async (event) => {
    event.preventDefault()
    setBusy(true); setError('')
    try {
      const result = registering
        ? await api.register(username, email, password)
        : await api.login(username, password)
      setToken(result.token)
      window.location.reload()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const switchMode = (next) => {
    setMode(next)
    setError('')
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4" style={{ background: 'var(--bg)' }}>
      <form onSubmit={submit} className="card w-full max-w-md p-7">
        <div className="mb-6 flex items-center gap-3">
          <div className="rounded-xl p-3 text-white" style={{ background: 'var(--primary)' }}>
            <ChartNoAxesCombined size={22} />
          </div>
          <div>
            <h1 className="text-xl font-extrabold">SentimentIQ</h1>
            <p className="muted text-xs">{registering ? 'Create the first admin account' : 'Sign in to your workspace'}</p>
          </div>
        </div>
        {error && <p className="mb-4 rounded-lg px-3 py-2 text-sm" style={{ background: 'color-mix(in srgb, var(--negative) 10%, transparent)', color: 'var(--negative)' }}>{error}</p>}
        <label className="label">Username</label>
        <input className="input mb-4" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
        {registering && (
          <>
            <label className="label">Email (optional)</label>
            <input className="input mb-4" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" placeholder="you@company.com" />
          </>
        )}
        <label className="label">Password</label>
        <input
          className="input"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete={registering ? 'new-password' : 'current-password'}
          placeholder={registering ? 'At least 8 characters' : 'Enter your password'}
        />
        <button className="btn btn-primary mt-6 w-full" disabled={busy || !username || !password}>
          {registering ? <UserPlus size={16} /> : <LockKeyhole size={16} />}
          {busy ? (registering ? 'Creating…' : 'Signing in…') : (registering ? 'Create admin account' : 'Sign in')}
        </button>
        {config?.registration_open && (
          <button
            type="button"
            className="mt-4 w-full text-center text-[11px] font-bold text-primary"
            onClick={() => switchMode(registering ? 'login' : 'register')}
          >
            {registering ? 'Already have an account? Sign in' : 'No accounts yet? Create the first admin'}
          </button>
        )}
        <p className="muted mt-4 text-center text-[11px]">
          Accounts and passwords are managed by an administrator in Settings.
        </p>
      </form>
    </div>
  )
}
