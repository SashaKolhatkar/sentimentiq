import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import { Loading, Toasts } from './components/ui'
import { useApp } from './context'
import { getToken } from './api'
import Login from './pages/Login'
import Overview from './pages/Overview'
import Analyze from './pages/Analyze'
import Sentiment from './pages/Sentiment'
import Emotion from './pages/Emotion'
import Spam from './pages/Spam'
import Bot from './pages/Bot'
import Customer from './pages/Customer'
import Trending from './pages/Trending'
import Reports from './pages/Reports'
import Settings from './pages/Settings'

function Gate({ children }) {
  const { config } = useApp()
  if (!config) return <div className="p-10"><Loading label="Loading SentimentIQ…" /></div>
  if (config.auth_enabled && !getToken()) return <Login />
  return children
}

export default function App() {
  return (
    <>
      <Gate>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Overview />} />
            <Route path="analyze" element={<Analyze />} />
            <Route path="sentiment" element={<Sentiment />} />
            <Route path="emotion" element={<Emotion />} />
            <Route path="spam" element={<Spam />} />
            <Route path="bot" element={<Bot />} />
            <Route path="customer" element={<Customer />} />
            <Route path="trending" element={<Trending />} />
            <Route path="reports" element={<Reports />} />
            <Route path="settings" element={<Settings />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </Gate>
      <Toasts />
    </>
  )
}
