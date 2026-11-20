import { useCallback, useEffect, useState } from 'react'
import { KeyRound, ShieldCheck, Trash2, UserPlus, Users } from 'lucide-react'
import { api } from '../api'
import { useApp } from '../context'
import { Badge, Card, ErrorBanner, InfoBanner, Loading } from './ui'

const ROLE_TONES = { admin: 'primary', analyst: 'positive', viewer: 'neutral' }
const EMPTY_USER = { username: '', email: '', password: '', role: 'analyst' }

export default function UserManagement() {
  const { config, user, notify } = useApp()
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [adding, setAdding] = useState(false)
  const [newUser, setNewUser] = useState(EMPTY_USER)
  const [passwordForm, setPasswordForm] = useState({ current: '', next: '', confirm: '' })
  const [resetFor, setResetFor] = useState(null)
  const [resetValue, setResetValue] = useState('')

  const isAdmin = user?.role === 'admin'
  const enabled = !!config?.auth_enabled && !!user?.id && user.id !== 'local'

  const load = useCallback(async () => {
    if (!enabled || !isAdmin) return
    setLoading(true)
    try {
      const data = await api.users()
      setUsers(data.users || [])
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [enabled, isAdmin])

  useEffect(() => { load() }, [load])

  const act = async (key, action, success) => {
    setBusy(key); setError('')
    try {
      await action()
      if (success) notify(success, 'success')
      await load()
      return true
    } catch (err) {
      setError(err.message)
      return false
    } finally {
      setBusy('')
    }
  }

  const createUser = async (event) => {
    event.preventDefault()
    const ok = await act('create', () => api.createUser(newUser), `Account ${newUser.username} created`)
    if (ok) { setNewUser(EMPTY_USER); setAdding(false) }
  }

  const changePassword = async (event) => {
    event.preventDefault()
    if (passwordForm.next !== passwordForm.confirm) {
      setError('New passwords do not match')
      return
    }
    const ok = await act(
      'password',
      () => api.changePassword(passwordForm.current, passwordForm.next),
      'Your password has been changed',
    )
    if (ok) setPasswordForm({ current: '', next: '', confirm: '' })
  }

  const resetPassword = async (id) => {
    const ok = await act('reset', () => api.resetUserPassword(id, resetValue), 'Password reset')
    if (ok) { setResetFor(null); setResetValue('') }
  }

  if (!enabled) {
    return (
      <Card className="p-5">
        <div className="flex items-center gap-2"><Users size={17} className="text-primary" /><h3 className="text-sm font-bold">Accounts</h3></div>
        <InfoBanner>
          Multi-user accounts are available when authentication is enabled. Local demo mode uses a single open workspace.
        </InfoBanner>
      </Card>
    )
  }

  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2"><Users size={17} className="text-primary" /><h3 className="text-sm font-bold">Users & access</h3></div>
          <p className="muted mt-1 text-[11px]">Each person has their own password. Roles control what they can change.</p>
        </div>
        <div className="flex items-center gap-2">
          <Badge tone={ROLE_TONES[user.role] || 'neutral'}>Signed in as {user.role}</Badge>
          {isAdmin && (
            <button className="btn btn-primary h-9 px-3 text-xs" onClick={() => setAdding((v) => !v)}>
              <UserPlus size={15} /> {adding ? 'Cancel' : 'Add user'}
            </button>
          )}
        </div>
      </div>

      <ErrorBanner message={error} onDismiss={() => setError('')} />

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <form onSubmit={changePassword} className="card-soft space-y-3 p-4">
          <div className="flex items-center gap-2"><KeyRound size={16} className="text-primary" /><h4 className="text-xs font-bold">Change my password</h4></div>
          <input className="input" type="password" placeholder="Current password" autoComplete="current-password"
            value={passwordForm.current} onChange={(e) => setPasswordForm({ ...passwordForm, current: e.target.value })} />
          <input className="input" type="password" placeholder="New password (8+ characters)" autoComplete="new-password"
            value={passwordForm.next} onChange={(e) => setPasswordForm({ ...passwordForm, next: e.target.value })} />
          <input className="input" type="password" placeholder="Confirm new password" autoComplete="new-password"
            value={passwordForm.confirm} onChange={(e) => setPasswordForm({ ...passwordForm, confirm: e.target.value })} />
          <button className="btn btn-primary w-full" disabled={!!busy || !passwordForm.current || !passwordForm.next}>
            {busy === 'password' ? 'Updating…' : 'Update password'}
          </button>
        </form>

        {isAdmin && adding && (
          <form onSubmit={createUser} className="card-soft space-y-3 p-4">
            <div className="flex items-center gap-2"><ShieldCheck size={16} className="text-primary" /><h4 className="text-xs font-bold">New account</h4></div>
            <input className="input" placeholder="Username (3+ characters)" value={newUser.username}
              onChange={(e) => setNewUser({ ...newUser, username: e.target.value })} />
            <input className="input" type="email" placeholder="Email (optional)" value={newUser.email}
              onChange={(e) => setNewUser({ ...newUser, email: e.target.value })} />
            <input className="input" type="password" placeholder="Temporary password (8+ characters)" value={newUser.password}
              onChange={(e) => setNewUser({ ...newUser, password: e.target.value })} />
            <select className="input" value={newUser.role} onChange={(e) => setNewUser({ ...newUser, role: e.target.value })}>
              <option value="analyst">Analyst — can run analyses</option>
              <option value="viewer">Viewer — read-only access</option>
              <option value="admin">Admin — full access</option>
            </select>
            <button className="btn btn-primary w-full" disabled={!!busy || !newUser.username || !newUser.password}>
              {busy === 'create' ? 'Creating…' : 'Create account'}
            </button>
          </form>
        )}
      </div>

      {isAdmin && (
        <div className="mt-5">
          <h4 className="mb-2 text-xs font-bold">Accounts ({users.length})</h4>
          {loading ? <Loading label="Loading accounts…" /> : (
            <div className="space-y-2">
              {users.map((account) => (
                <div key={account.id} className="card-soft flex flex-wrap items-center gap-3 p-3 text-xs">
                  <div className="min-w-[150px] flex-1">
                    <p className="font-bold">{account.username}</p>
                    <p className="muted mt-0.5">{account.email || 'No email'}</p>
                  </div>
                  <Badge tone={ROLE_TONES[account.role] || 'neutral'}>{account.role}</Badge>
                  {account.disabled && <Badge tone="warning">Disabled</Badge>}
                  <select className="input h-8 w-auto py-0 text-xs" value={account.role}
                    disabled={!!busy || account.id === user.id}
                    onChange={(e) => act('role', () => api.updateUser(account.id, { role: e.target.value }), 'Role updated')}>
                    <option value="admin">admin</option>
                    <option value="analyst">analyst</option>
                    <option value="viewer">viewer</option>
                  </select>
                  <button className="btn btn-secondary h-8 px-3 text-xs" disabled={!!busy || account.id === user.id}
                    onClick={() => act('disable', () => api.updateUser(account.id, { disabled: !account.disabled }), account.disabled ? 'Account enabled' : 'Account disabled')}>
                    {account.disabled ? 'Enable' : 'Disable'}
                  </button>
                  <button className="btn btn-secondary h-8 px-3 text-xs" disabled={!!busy}
                    onClick={() => { setResetFor(resetFor === account.id ? null : account.id); setResetValue('') }}>
                    Reset password
                  </button>
                  <button className="btn btn-secondary h-8 px-3 text-xs" disabled={!!busy || account.id === user.id}
                    onClick={() => {
                      if (window.confirm(`Delete account ${account.username}?`)) {
                        act('delete', () => api.deleteUser(account.id), 'Account deleted')
                      }
                    }}>
                    <Trash2 size={14} />
                  </button>
                  {resetFor === account.id && (
                    <div className="flex w-full items-center gap-2 border-t pt-3" style={{ borderColor: 'var(--border)' }}>
                      <input className="input" type="password" placeholder="New password (8+ characters)" value={resetValue}
                        onChange={(e) => setResetValue(e.target.value)} />
                      <button className="btn btn-primary h-8 px-3 text-xs" disabled={!!busy || resetValue.length < 8}
                        onClick={() => resetPassword(account.id)}>
                        {busy === 'reset' ? 'Saving…' : 'Save'}
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </Card>
  )
}
