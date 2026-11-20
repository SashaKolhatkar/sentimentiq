import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api } from './api'

const AppContext = createContext(null)

const THEME_KEY = 'sentimentiq.theme'
const RUN_KEY = 'sentimentiq.activeRun'

export function AppProvider({ children }) {
  const [theme, setThemeState] = useState(() => localStorage.getItem(THEME_KEY) || 'light')
  const [config, setConfig] = useState(null)
  const [run, setRunState] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem(RUN_KEY) || 'null')
    } catch {
      return null
    }
  })
  const [runs, setRuns] = useState([])
  const [toasts, setToasts] = useState([])
  const [bootError, setBootError] = useState('')

  const notify = useCallback((message, type = 'info') => {
    const id = `${Date.now()}-${Math.random().toString(16).slice(2)}`
    setToasts((prev) => [...prev, { id, message, type }])
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 5000)
  }, [])

  const setTheme = useCallback((next) => {
    setThemeState(next)
    localStorage.setItem(THEME_KEY, next)
  }, [])

  const setRun = useCallback((next) => {
    setRunState(next)
    // Runs can contain 100k+ records on the server. Persist only the id and
    // rehydrate the summary through the paginated API when the app reloads.
    if (next) localStorage.setItem(RUN_KEY, JSON.stringify({ id: next.id }))
    else localStorage.removeItem(RUN_KEY)
  }, [])

  const refreshRuns = useCallback(async () => {
    try {
      const data = await api.runs()
      setRuns(data.runs || [])
      return data.runs || []
    } catch (error) {
      notify(error.message, 'error')
      return []
    }
  }, [notify])

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    document.documentElement.classList.toggle('dark', theme === 'dark')
  }, [theme])

  useEffect(() => {
    let storedId = null
    try { storedId = JSON.parse(localStorage.getItem(RUN_KEY) || 'null')?.id } catch { storedId = null }
    if (!storedId) return
    let cancelled = false
    api.run(storedId)
      .then((data) => { if (!cancelled) setRunState(data) })
      .catch(() => { if (!cancelled) { setRunState(null); localStorage.removeItem(RUN_KEY) } })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    let cancelled = false
    Promise.allSettled([api.config(), api.runs()]).then(([cfg, r]) => {
      if (cancelled) return
      if (cfg.status === 'fulfilled') setConfig(cfg.value)
      else setBootError(cfg.reason?.message || 'Configuration could not be loaded')
      if (r.status === 'fulfilled') setRuns(r.value.runs || [])
    })
    return () => { cancelled = true }
  }, [])

  const value = useMemo(
    () => ({
      theme, setTheme, config, run, setRun, runs, setRuns, refreshRuns,
      toasts, notify, bootError,
    }),
    [theme, setTheme, config, run, setRun, runs, refreshRuns, toasts, notify, bootError],
  )

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}

export function useApp() {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error('useApp must be used inside AppProvider')
  return ctx
}
