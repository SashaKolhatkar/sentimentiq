import { useState } from 'react'
import { ChartNoAxesCombined, LockKeyhole } from 'lucide-react'
import { api, setToken } from '../api'

export default function Login() {
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (event) => {
    event.preventDefault()
    setBusy(true); setError('')
    try {
      const result = await api.login(username, password)
      setToken(result.token)
      window.location.reload()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
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
            <p className="muted text-xs">Sign in to your workspace</p>
          </div>
        </div>
        {error && <p className="mb-4 rounded-lg px-3 py-2 text-sm" style={{ background: 'color-mix(in srgb, var(--negative) 10%, transparent)', color: 'var(--negative)' }}>{error}</p>}
        <label className="label">Username</label>
        <input className="input mb-4" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
        <label className="label">Password</label>
        <input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" placeholder="Enter admin password" />
        <button className="btn btn-primary mt-6 w-full" disabled={busy || !password}>
          <LockKeyhole size={16} /> {busy ? 'Signing in…' : 'Sign in'}
        </button>
        <p className="muted mt-4 text-center text-[11px]">
          Password is set with SENTIMENTIQ_ADMIN_PASSWORD in the backend environment.
        </p>
      </form>
    </div>
  )
}
