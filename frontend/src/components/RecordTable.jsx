import { useEffect, useMemo, useState } from 'react'
import { ChevronDown, ChevronLeft, ChevronRight, Download, Filter, Search } from 'lucide-react'
import { api, downloadReport } from '../api'
import { Badge, Card } from './ui'

const SENTIMENT_TONES = { positive: 'positive', negative: 'negative', neutral: 'neutral', mixed: 'warning' }
const SPAM_TONES = { 'Likely Genuine': 'positive', 'Potentially Suspicious': 'warning', 'Likely Spam': 'negative' }
const BOT_TONES = { 'Likely Human': 'positive', 'Possibly Automated': 'warning', 'Strong Automation Indicators': 'negative', 'Insufficient Data': 'neutral' }
const PAGE_SIZE = 10

function toneForSentiment(s) { return SENTIMENT_TONES[s] || 'neutral' }
function toneForSpam(s) { return SPAM_TONES[s] || 'neutral' }
function toneForBot(s) { return BOT_TONES[s] || 'neutral' }

export default function RecordTable({ records = [], runId, summary, compact = false }) {
  const [query, setQuery] = useState('')
  const [sentiment, setSentiment] = useState('all')
  const [emotion, setEmotion] = useState('all')
  const [platform, setPlatform] = useState('all')
  const [spam, setSpam] = useState('all')
  const [bot, setBot] = useState('all')
  const [sort, setSort] = useState('newest')
  const [page, setPage] = useState(1)
  const [expanded, setExpanded] = useState(null)
  const [showFilters, setShowFilters] = useState(!compact)
  const [remote, setRemote] = useState({ records: [], total: 0, loading: false, error: '' })
  const [exporting, setExporting] = useState(false)

  const filters = useMemo(() => ({ q: query, sentiment, emotion, platform, spam, bot }),
    [query, sentiment, emotion, platform, spam, bot])

  const platforms = useMemo(() => {
    if (summary?.platform_sentiment?.length) return summary.platform_sentiment.map((p) => p.platform).sort()
    return [...new Set(records.map((r) => r.platform).filter(Boolean))].sort()
  }, [summary, records])

  const emotions = useMemo(() => {
    if (summary?.emotion_distribution?.length) return summary.emotion_distribution.map((e) => e.emotion)
    return [...new Set(records.map((r) => r.emotion).filter(Boolean))].sort()
  }, [summary, records])

  useEffect(() => {
    if (!runId) return undefined
    let cancelled = false
    setRemote((prev) => ({ ...prev, loading: true, error: '' }))
    const timer = setTimeout(() => {
      api.runRecords(runId, {
        ...filters, sort, limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE,
      }).then((data) => {
        if (!cancelled) setRemote({ records: data.records || [], total: data.total || 0, loading: false, error: '' })
      }).catch((err) => {
        if (!cancelled) setRemote({ records: [], total: 0, loading: false, error: err.message })
      })
    }, 250)
    return () => { cancelled = true; clearTimeout(timer) }
  }, [runId, filters, sort, page])

  const localFiltered = useMemo(() => {
    const q = query.toLowerCase().trim()
    let list = records.filter((r) => {
      if (q && !`${r.text} ${r.author || ''} ${r.platform || ''}`.toLowerCase().includes(q)) return false
      if (sentiment !== 'all' && r.sentiment !== sentiment) return false
      if (emotion !== 'all' && r.emotion !== emotion) return false
      if (platform !== 'all' && r.platform !== platform) return false
      if (spam !== 'all' && r.spam_label !== spam) return false
      if (bot !== 'all' && r.automation_label !== bot) return false
      return true
    })
    list = [...list]
    if (sort === 'score') list.sort((a, b) => a.sentiment_score - b.sentiment_score)
    if (sort === 'suspicion') list.sort((a, b) => b.suspicion_score - a.suspicion_score)
    if (sort === 'newest') list.sort((a, b) => String(b.timestamp || '').localeCompare(String(a.timestamp || '')))
    return list
  }, [records, query, sentiment, emotion, platform, spam, bot, sort])

  const total = runId ? remote.total : localFiltered.length
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const currentPage = Math.min(page, pages)
  const visible = runId ? remote.records : localFiltered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)

  const reset = () => {
    setQuery(''); setSentiment('all'); setEmotion('all'); setPlatform('all')
    setSpam('all'); setBot('all'); setPage(1)
  }

  const exportFiltered = async () => {
    setExporting(true)
    try {
      if (runId) {
        await downloadReport(runId, 'csv', { ...filters, sort })
      } else {
        const header = ['id', 'text', 'platform', 'author', 'timestamp', 'sentiment', 'sentiment_score', 'emotion', 'emotion_confidence', 'spam_label', 'suspicion_score', 'automation_label']
        const lines = [header.join(',')]
        for (const r of localFiltered) {
          const values = header.map((key) => `"${String(r[key] ?? '').replace(/"/g, '""')}"`)
          lines.push(values.join(','))
        }
        const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' })
        const url = URL.createObjectURL(blob)
        const link = document.createElement('a')
        link.href = url
        link.download = 'sentimentiq-filtered-records.csv'
        link.click()
        URL.revokeObjectURL(url)
      }
    } finally {
      setExporting(false)
    }
  }

  return (
    <Card className="overflow-hidden">
      <div className="flex flex-wrap items-center gap-2 border-b p-4">
        <div className="relative min-w-[220px] flex-1">
          <Search size={15} className="muted absolute left-3 top-1/2 -translate-y-1/2" />
          <input className="input pl-9" placeholder="Search text, author or platform…" value={query} onChange={(e) => { setQuery(e.target.value); setPage(1) }} />
        </div>
        <button className="btn btn-secondary" onClick={() => setShowFilters((v) => !v)}>
          <Filter size={15} /> Filters
        </button>
        <button className="btn btn-secondary" onClick={exportFiltered} disabled={exporting}><Download size={15} /> {exporting ? 'Exporting…' : 'Export'}</button>
      </div>

      {showFilters && (
        <div className="grid grid-cols-2 gap-3 border-b p-4 md:grid-cols-3 xl:grid-cols-6">
          <select className="input" value={sentiment} onChange={(e) => { setSentiment(e.target.value); setPage(1) }}>
            <option value="all">All sentiments</option>
            {Object.keys(SENTIMENT_TONES).map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <select className="input" value={emotion} onChange={(e) => { setEmotion(e.target.value); setPage(1) }}>
            <option value="all">All emotions</option>
            {emotions.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <select className="input" value={platform} onChange={(e) => { setPlatform(e.target.value); setPage(1) }}>
            <option value="all">All platforms</option>
            {platforms.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <select className="input" value={spam} onChange={(e) => { setSpam(e.target.value); setPage(1) }}>
            <option value="all">All spam states</option>
            <option value="flagged">Flagged only</option>
            {Object.keys(SPAM_TONES).map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <select className="input" value={bot} onChange={(e) => { setBot(e.target.value); setPage(1) }}>
            <option value="all">All automation</option>
            {Object.keys(BOT_TONES).map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <select className="input" value={sort} onChange={(e) => { setSort(e.target.value); setPage(1) }}>
            <option value="newest">Newest first</option>
            <option value="score">Lowest sentiment score</option>
            <option value="suspicion">Highest suspicion</option>
          </select>
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full min-w-[900px] text-left text-sm">
          <thead>
            <tr className="border-b text-[11px] uppercase tracking-wide muted">
              <th className="px-4 py-3 font-bold">Content</th>
              <th className="px-3 py-3 font-bold">Sentiment</th>
              <th className="px-3 py-3 font-bold">Emotion</th>
              <th className="px-3 py-3 font-bold">Spam</th>
              <th className="px-3 py-3 font-bold">Automation</th>
              <th className="px-3 py-3 font-bold">Platform</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((r) => (
              <tr key={r.id} className="border-b last:border-0 align-top hover:bg-[var(--surface-2)]">
                <td className="max-w-[420px] px-4 py-3">
                  <p className="line-clamp-2 text-xs leading-relaxed">{r.text}</p>
                  <div className="mt-1.5 flex flex-wrap items-center gap-2">
                    <span className="muted text-[10px]">{r.timestamp ? new Date(r.timestamp).toLocaleDateString() : 'No date'}</span>
                    <button className="text-[10px] font-bold text-primary" onClick={() => setExpanded(expanded === r.id ? null : r.id)}>
                      {expanded === r.id ? 'Hide details' : 'Why?'}
                    </button>
                  </div>
                  {expanded === r.id && (
                    <div className="mt-2 space-y-1.5 rounded-lg border p-2.5 text-[11px]" style={{ background: 'var(--surface-2)' }}>
                      <p><b>Sentiment score:</b> {r.sentiment_score} · confidence {r.sentiment_confidence}</p>
                      <p><b>Suspicion:</b> {r.suspicion_score} · uncertainty {r.spam_uncertainty}</p>
                      {(r.spam_reasons || []).map((reason, i) => <p key={i} className="muted">• {reason}</p>)}
                      {(r.automation_indicators || []).map((ind, i) => <p key={i} className="muted">• {ind.name}: {ind.detail}</p>)}
                    </div>
                  )}
                </td>
                <td className="px-3 py-3"><Badge tone={toneForSentiment(r.sentiment)} className="capitalize">{r.sentiment}</Badge></td>
                <td className="px-3 py-3">
                  <p className="text-xs font-semibold capitalize">{r.emotion}</p>
                  <p className="muted text-[10px]">{Math.round((r.emotion_confidence || 0) * 100)}% conf.</p>
                </td>
                <td className="px-3 py-3">
                  <Badge tone={toneForSpam(r.spam_label)}>{r.spam_label}</Badge>
                  <p className="muted mt-1 text-[10px]">{r.suspicion_score}</p>
                </td>
                <td className="px-3 py-3">
                  <Badge tone={toneForBot(r.automation_label)}>{r.automation_label}</Badge>
                </td>
                <td className="px-3 py-3"><span className="text-xs capitalize">{r.platform}</span></td>
              </tr>
            ))}
            {!visible.length && (
              <tr>
                <td colSpan={6} className="px-4 py-10 text-center text-sm muted">
                  {remote.error || (remote.loading ? 'Loading records…' : 'No records match these filters.')}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t px-4 py-3">
        <p className="muted text-xs">
          Showing {total ? (currentPage - 1) * PAGE_SIZE + 1 : 0}–{Math.min(currentPage * PAGE_SIZE, total)} of {total.toLocaleString()}
        </p>
        <div className="flex items-center gap-2">
          <button className="btn btn-ghost h-8 px-2" disabled={currentPage <= 1} onClick={() => setPage(currentPage - 1)}><ChevronLeft size={16} /></button>
          <span className="text-xs font-semibold">{currentPage} / {pages}</span>
          <button className="btn btn-ghost h-8 px-2" disabled={currentPage >= pages} onClick={() => setPage(currentPage + 1)}><ChevronRight size={16} /></button>
          <button className="btn btn-ghost h-8 px-2 text-xs" onClick={reset}>Reset</button>
        </div>
      </div>
    </Card>
  )
}
