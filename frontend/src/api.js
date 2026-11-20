const TOKEN_KEY = 'sentimentiq.token'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

async function request(path, options = {}) {
  const headers = { ...(options.headers || {}) }
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  if (options.body && !(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json'
  }

  let response
  try {
    response = await fetch(`/api${path}`, { ...options, headers })
  } catch (error) {
    throw new Error('Cannot reach the SentimentIQ server. Is the backend running?')
  }

  const contentType = response.headers.get('content-type') || ''
  const payload = contentType.includes('json') ? await response.json() : await response.text()

  if (!response.ok) {
    if (response.status === 401 && getToken()) {
      setToken(null)
      window.location.reload()
    }
    const message = typeof payload === 'object' ? payload.detail || 'Request failed' : payload
    throw new Error(typeof message === 'string' ? message : JSON.stringify(message))
  }
  return payload
}

export const api = {
  get: (path) => request(path),
  post: (path, body, options = {}) => request(path, { method: 'POST', body, ...options }),
  del: (path) => request(path, { method: 'DELETE' }),
  upload: (form) => request('/ingest/preview', { method: 'POST', body: form }),
  login: (username, password) =>
    request('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),
  register: (username, email, password) =>
    request('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ username, email, password }),
    }),
  me: () => request('/auth/me'),
  changePassword: (currentPassword, newPassword) =>
    request('/auth/password', {
      method: 'POST',
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    }),
  users: () => request('/users'),
  createUser: (payload) =>
    request('/users', { method: 'POST', body: JSON.stringify(payload) }),
  updateUser: (id, payload) =>
    request(`/users/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  resetUserPassword: (id, newPassword) =>
    request(`/users/${id}/password`, {
      method: 'POST',
      body: JSON.stringify({ new_password: newPassword }),
    }),
  deleteUser: (id) => request(`/users/${id}`, { method: 'DELETE' }),
  config: () => request('/config'),
  health: () => request('/health'),
  models: () => request('/models/status'),
  warmModels: (keys) => request('/models/warm', { method: 'POST', body: JSON.stringify({ keys }) }),
  demo: () => request('/demo/dataset'),
  runs: () => request('/runs'),
  run: (id) => request(`/runs/${id}`),
  runRecords: (id, params = {}) => {
    const query = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== '' && v != null)).toString()
    return request(`/runs/${id}/records${query ? `?${query}` : ''}`)
  },
  job: (id) => request(`/jobs/${id}`),
  analyze: (payload) => request('/analyze', { method: 'POST', body: JSON.stringify(payload) }),
  deleteRun: (id) => request(`/runs/${id}`, { method: 'DELETE' }),
  reportHistory: () => request('/reports/history'),
}

export async function downloadReport(runId, format, params = {}) {
  const token = getToken()
  const headers = token ? { Authorization: `Bearer ${token}` } : {}
  const query = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== '' && v != null)).toString()
  const response = await fetch(`/api/reports/${runId}/${format}${query ? `?${query}` : ''}`, { headers })
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Download failed' }))
    throw new Error(error.detail || 'Download failed')
  }
  const blob = await response.blob()
  const disposition = response.headers.get('content-disposition') || ''
  const filename = disposition.match(/filename="?([^";]+)"?/)?.[1] || `sentimentiq-report.${format}`
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

export async function pollJob(jobId, onProgress, interval = 700) {
  return new Promise((resolve, reject) => {
    let attempts = 0
    const tick = async () => {
      try {
        const job = await api.job(jobId)
        onProgress?.(job)
        if (job.status === 'complete') return resolve(job.result)
        if (job.status === 'failed') return reject(new Error(job.error || 'Analysis failed'))
        if (attempts++ > 600) return reject(new Error('Analysis timed out'))
        setTimeout(tick, interval)
      } catch (error) {
        reject(error)
      }
    }
    tick()
  })
}
