import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Download, FileSpreadsheet, FileText, FileType2, History, Lightbulb, Play, ShieldCheck } from 'lucide-react'
import { api, downloadReport } from '../api'
import { useApp } from '../context'
import { Badge, Card, EmptyState, ErrorBanner, InfoBanner, SectionTitle } from '../components/ui'

const FORMATS = [
  { id: 'pdf', label: 'PDF report', detail: 'Executive summary, charts and recommendations', icon: FileText },
  { id: 'excel', label: 'Excel workbook', detail: 'Summary, records, aspects, topics, trends and insights', icon: FileSpreadsheet },
  { id: 'csv', label: 'CSV dataset', detail: 'All enriched records for spreadheets or BI tools', icon: FileType2 },
]

export default function Reports() {
  const { run, runs, setRun, refreshRuns, notify } = useApp()
  const [selectedRunId, setSelectedRunId] = useState(run?.id || runs[0]?.id || '')
  const [history, setHistory] = useState([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')

  useEffect(() => {
    api.reportHistory().then((d) => setHistory(d.reports || [])).catch(() => {})
  }, [run])

  const active = selectedRunId === run?.id ? run : null

  const loadSelected = async () => {
    if (!selectedRunId) return
    try {
      const data = await api.run(selectedRunId)
      setRun(data)
      notify('Analysis loaded for reporting.', 'success')
    } catch (err) { setError(err.message) }
  }

  const download = async (fmt) => {
    const id = run?.id || selectedRunId
    if (!id) { setError('Select an analysis first.'); return }
    setBusy(fmt); setError('')
    try {
      await downloadReport(id, fmt)
      notify(`${fmt.toUpperCase()} report downloaded.`, 'success')
      const d = await api.reportHistory()
      setHistory(d.reports || [])
    } catch (err) {
      setError(err.message)
    } finally { setBusy('') }
  }

  if (!run && !runs.length) {
    return <div><SectionTitle eyebrow="Export" title="Reports" /><EmptyState icon={FileText} title="Nothing to report yet" description="Complete an analysis and then generate PDF, Excel or CSV reports." action={<Link to="/analyze" className="btn btn-primary"><Play size={16} /> Analyze content</Link>} /></div>
  }

  return (
    <div className="space-y-6">
      <SectionTitle eyebrow="Export & sharing" title="Reports" description="Download a complete analytical report built from the same metrics as the dashboard." />

      <ErrorBanner message={error} onDismiss={() => setError('')} />

      <Card className="p-5">
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-[260px] flex-1">
            <label className="label">Analysis run</label>
            <select className="input" value={selectedRunId} onChange={(e) => setSelectedRunId(e.target.value)}>
              <option value="">Select a run…</option>
              {runs.map((r) => <option key={r.id} value={r.id}>{r.name} · {new Date(r.created_at).toLocaleDateString()} · {r.record_count} records</option>)}
            </select>
          </div>
          <button className="btn btn-secondary" onClick={loadSelected} disabled={!selectedRunId}>Load into dashboard</button>
          <button className="btn btn-ghost" onClick={() => refreshRuns()}>Refresh list</button>
        </div>
        {run && <div className="mt-3 flex flex-wrap items-center gap-2">
          <Badge tone="primary">Active: {run.name}</Badge>
          {run.is_demo && <Badge tone="warning">DEMO DATA</Badge>}
          <span className="muted text-xs">{run.summary.total_records} records · {run.created_at}</span>
        </div>}
      </Card>

      <div className="grid gap-4 md:grid-cols-3">
        {FORMATS.map((fmt) => (
          <Card key={fmt.id} className="p-5">
            <div className="rounded-xl p-3 text-primary" style={{ background: 'var(--primary-soft)' }}><fmt.icon size={22} /></div>
            <h3 className="mt-4 text-sm font-bold">{fmt.label}</h3>
            <p className="muted mt-1 text-xs leading-relaxed">{fmt.detail}</p>
            <button className="btn btn-primary mt-5 w-full" onClick={() => download(fmt.id)} disabled={!!busy || !run}>
              <Download size={15} /> {busy === fmt.id ? 'Generating…' : `Download ${fmt.id.toUpperCase()}`}
            </button>
          </Card>
        ))}
      </div>

      {run && (
        <InfoBanner tone={run.is_demo ? 'warning' : 'success'}>
          {run.is_demo
            ? 'This report is generated from DEMO data. Upload your own dataset for genuine customer intelligence.'
            : `This report uses analysed data: ${run.summary.total_records} records, ${(run.summary.engines || []).join(', ')}.`}
        </InfoBanner>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="p-5">
          <div className="flex items-center gap-2"><Lightbulb size={17} className="text-primary" /><h3 className="text-sm font-bold">Included insights</h3></div>
          <ul className="muted mt-3 space-y-2 text-xs">
            {(active?.insights?.insights || run?.insights?.insights || []).slice(0, 8).map((insight, i) => <li key={i}>• {insight.text}</li>)}
            {!run && <li>Load an analysis to preview insights.</li>}
          </ul>
        </Card>

        <Card className="p-5">
          <div className="flex items-center gap-2"><History size={17} className="text-primary" /><h3 className="text-sm font-bold">Download history</h3></div>
          <div className="mt-3 max-h-[260px] space-y-2 overflow-auto">
            {history.map((report) => (
              <div key={report.id} className="card-soft flex items-center justify-between p-2.5 text-xs">
                <span className="flex items-center gap-2"><ShieldCheck size={14} className="text-primary" /> {report.filename}</span>
                <button className="font-bold text-primary" onClick={() => downloadReport(report.run_id, report.format).catch((e) => notify(e.message, 'error'))}>Re-download</button>
              </div>
            ))}
            {!history.length && <p className="muted text-xs">No reports downloaded yet.</p>}
          </div>
        </Card>
      </div>
    </div>
  )
}
