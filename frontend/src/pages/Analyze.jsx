import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  CheckCircle2, FileSpreadsheet, FileText, FlaskConical, Globe2, Link2,
  ListChecks, Play, Sparkles, UploadCloud,
} from 'lucide-react'
import { api, pollJob } from '../api'
import { useApp } from '../context'
import { Badge, Card, ErrorBanner, InfoBanner, Loading, ProgressPanel, SectionTitle } from '../components/ui'

const TABS = [
  { id: 'text', label: 'Manual text', icon: FileText },
  { id: 'paste', label: 'Paste comments', icon: ListChecks },
  { id: 'file', label: 'Upload file', icon: FileSpreadsheet },
  { id: 'url', label: 'Public page URL', icon: Globe2 },
  { id: 'demo', label: 'Demo dataset', icon: Sparkles },
]

export default function Analyze() {
  const { config, setRun, notify } = useApp()
  const navigate = useNavigate()
  const fileRef = useRef(null)
  const [tab, setTab] = useState('paste')
  const [text, setText] = useState('')
  const [splitLines, setSplitLines] = useState(true)
  const [platform, setPlatform] = useState('manual')
  const [url, setUrl] = useState('')
  const [files, setFiles] = useState([])
  const [name, setName] = useState('Customer feedback analysis')
  const [period, setPeriod] = useState('daily')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [redact, setRedact] = useState(true)
  const [preview, setPreview] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [job, setJob] = useState(null)

  const doPreview = async (mode = tab) => {
    setError(''); setBusy(true); setPreview(null)
    try {
      if (mode === 'demo') {
        const data = await api.demo()
        setPreview({
          records: data.records,
          preview: data.records.slice(0, 10).map((r) => ({ ...r, text: r.text.slice(0, 300) })),
          warnings: [data.notice],
          source_type: 'demo',
          counts: {
            total: data.count,
            with_timestamps: data.records.filter((r) => r.timestamp).length,
            with_authors: data.records.filter((r) => r.author).length,
            with_metadata: data.records.filter((r) => r.metadata && Object.keys(r.metadata).length).length,
            platforms: [...new Set(data.records.map((r) => r.platform))],
          },
        })
        setName('SentimentIQ demo dataset')
        return
      }
      const form = new FormData()
      form.append('text', mode === 'text' || mode === 'paste' ? text : '')
      form.append('split_lines', String(mode === 'paste' ? splitLines : mode === 'text' ? false : true))
      form.append('platform', platform)
      form.append('url', mode === 'url' ? url : '')
      for (const file of files) form.append('files', file)
      const result = await api.upload(form)
      if (!result.count) {
        setError('No usable records were found. Check the input and try again.')
        return
      }
      setPreview(result)
      if (result.source_type === 'file' && files[0]) setName(files[0].name.replace(/\.[^.]+$/, ''))
      if (result.source_type === 'url') setName(new URL(url).hostname)
      if (result.warnings?.length) notify(`${result.warnings.length} ingestion note(s) — review the preview.`, 'info')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const start = async () => {
    if (!preview?.count) return
    setError(''); setBusy(true); setJob(null)
    try {
      const result = await api.analyze({
        name: name || 'Untitled analysis',
        ...(preview.dataset_id
          ? { dataset_id: preview.dataset_id }
          : { records: preview.records || [] }),
        options: { period, start: startDate || null, end: endDate || null, redact_pii: redact },
      })
      const finalResult = await pollJob(result.job_id, setJob)
      setRun(finalResult)
      notify('Analysis complete. Dashboard updated.', 'success')
      navigate('/')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const loadDemo = async () => {
    setTab('demo')
    await doPreview('demo')
  }

  return (
    <div className="space-y-6">
      <SectionTitle
        eyebrow="Data input"
        title="Analyze content"
        description="Paste reviews, upload a dataset, or read a robots-respecting public page. Preview before you analyse."
      />

      <div className="grid gap-5 xl:grid-cols-[1.15fr_0.85fr]">
        <Card className="p-5">
          <div className="flex flex-wrap gap-2">
            {TABS.map((item) => (
              <button key={item.id} onClick={() => { setTab(item.id); setPreview(null); setError('') }}
                className={`btn ${tab === item.id ? 'btn-primary' : 'btn-secondary'}`}>
                <item.icon size={15} /> {item.label}
              </button>
            ))}
          </div>

          <div className="mt-6 space-y-4">
            <div>
              <label className="label">Analysis name</label>
              <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Q4 product reviews" />
            </div>

            {(tab === 'text' || tab === 'paste') && (
              <>
                <div>
                  <label className="label">{tab === 'paste' ? 'Comments or reviews (one per line)' : 'Text to analyse'}</label>
                  <textarea className="input min-h-[210px] resize-y font-mono text-xs leading-relaxed" value={text}
                    onChange={(e) => setText(e.target.value)}
                    placeholder={'Product quality is excellent, but delivery was very slow.\nCustomer support replied quickly and fixed the issue.\nThe app keeps crashing after the update.'} />
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  {tab === 'paste' && (
                    <label className="flex items-center gap-2 text-xs">
                      <input type="checkbox" checked={splitLines} onChange={(e) => setSplitLines(e.target.checked)} /> Treat each line as one record
                    </label>
                  )}
                  <div>
                    <label className="label">Platform label</label>
                    <select className="input" value={platform} onChange={(e) => setPlatform(e.target.value)}>
                      {['manual', 'Instagram', 'Facebook', 'X', 'YouTube', 'Reddit', 'Google Reviews', 'e-commerce'].map((p) => <option key={p}>{p}</option>)}
                    </select>
                  </div>
                </div>
              </>
            )}

            {tab === 'file' && (
              <div>
                <label className="label">CSV, Excel or TXT file</label>
                <div onClick={() => fileRef.current?.click()}
                  className="flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-12 text-center hover:bg-[var(--surface-2)]">
                  <UploadCloud size={28} className="text-primary" />
                  <p className="mt-3 text-sm font-bold">Drop files here or click to browse</p>
                  <p className="muted mt-1 text-xs">Max {config?.max_file_size_mb || 200} MB · up to {(config?.max_records || 250000).toLocaleString()} staged rows · analyse up to {(config?.analyze_limit || 100000).toLocaleString()} per run</p>
                  <input ref={fileRef} type="file" multiple accept=".csv,.xlsx,.xls,.txt" className="hidden"
                    onChange={(e) => { setFiles(Array.from(e.target.files || [])); setPreview(null) }} />
                </div>
                {files.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {files.map((f) => <Badge key={f.name} tone="primary"><FileSpreadsheet size={12} /> {f.name}</Badge>)}
                  </div>
                )}
                <p className="muted mt-3 text-[11px] leading-relaxed">
                  Recognised columns: text/content/review/comment, platform, author, timestamp/date, plus optional
                  likes, followers, following, account_age_days, posts_per_day and verified for spam and bot signals.
                </p>
              </div>
            )}

            {tab === 'url' && (
              <div>
                <label className="label">Public review page URL</label>
                <div className="relative">
                  <Link2 size={15} className="muted absolute left-3 top-1/2 -translate-y-1/2" />
                  <input className="input pl-9" value={url} onChange={(e) => setUrl(e.target.value)}
                    placeholder="https://www.reddit.com/r/.../comments/..." />
                </div>
                <p className="muted mt-2 text-[11px] leading-relaxed">
                  Allowed domains: {(config?.allowed_domains || []).join(', ')}. robots.txt is checked,
                  authenticated content and API bypassing are never attempted.
                </p>
              </div>
            )}

            {tab === 'demo' && (
              <InfoBanner>
                The demo dataset is hand-written and clearly marked <b>DEMO</b> everywhere. Use it to explore the product;
                upload your own data for real customer intelligence.
              </InfoBanner>
            )}

            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label className="label">Trend period</label>
                <select className="input" value={period} onChange={(e) => setPeriod(e.target.value)}>
                  <option value="daily">Daily</option>
                  <option value="weekly">Weekly</option>
                  <option value="monthly">Monthly</option>
                </select>
              </div>
              <label className="flex items-end gap-2 pb-2 text-xs">
                <input type="checkbox" checked={redact} onChange={(e) => setRedact(e.target.checked)} />
                Redact emails, phones and card-like numbers before analysis
              </label>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label className="label">Custom start (optional)</label>
                <input className="input" type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
              </div>
              <div>
                <label className="label">Custom end (optional)</label>
                <input className="input" type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
              </div>
            </div>

            <ErrorBanner message={error} onDismiss={() => setError('')} />

            <div className="flex flex-wrap gap-2">
              <button className="btn btn-secondary" onClick={() => doPreview()} disabled={busy || (tab !== 'demo' && !text.trim() && !files.length && !url.trim())}>
                <ListChecks size={16} /> {busy ? 'Working…' : 'Preview data'}
              </button>
              <button className="btn btn-primary" onClick={start} disabled={busy || !preview?.count}>
                <Play size={16} /> Analyze {preview?.count ? `${preview.count.toLocaleString()} records` : ''}
              </button>
              {tab !== 'demo' && <button className="btn btn-ghost" onClick={loadDemo}>Try demo dataset</button>}
            </div>
          </div>
        </Card>

        <div className="space-y-4">
          {job && <ProgressPanel job={job} />}

          {preview ? (
            <Card className="overflow-hidden">
              <div className="flex items-center justify-between border-b p-4">
                <div>
                  <h3 className="text-sm font-bold">Data preview</h3>
                  <p className="muted text-[11px]">{preview.counts.total} records ready · {preview.counts.with_timestamps} dated · {preview.counts.platforms?.join(', ') || 'unknown platform'}</p>
                </div>
                <Badge tone={preview.source_type === 'demo' ? 'warning' : 'positive'}>
                  {preview.source_type === 'demo' ? 'DEMO' : 'READY'}
                </Badge>
              </div>
              {preview.warnings?.length > 0 && (
                <div className="border-b p-3">
                  {preview.warnings.map((w, i) => <p key={i} className="text-[11px] muted">• {w}</p>)}
                </div>
              )}
              <div className="max-h-[420px] overflow-auto">
                <table className="w-full text-left text-xs">
                  <thead className="sticky top-0" style={{ background: 'var(--surface-2)' }}>
                    <tr className="muted"><th className="px-3 py-2">#</th><th className="px-3 py-2">Text</th><th className="px-3 py-2">Platform</th></tr>
                  </thead>
                  <tbody>
                    {preview.preview.map((row, i) => (
                      <tr key={i} className="border-b align-top">
                        <td className="px-3 py-2 muted">{i + 1}</td>
                        <td className="px-3 py-2">{row.text}</td>
                        <td className="px-3 py-2 muted">{row.platform}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          ) : (
            <Card className="flex flex-col items-center justify-center px-6 py-16 text-center">
              <FlaskConical size={26} className="text-primary" />
              <h3 className="mt-3 text-sm font-bold">Preview before you analyse</h3>
              <p className="muted mt-1 max-w-sm text-xs">Check that columns, line breaks and platforms were detected correctly before sending data to the models.</p>
            </Card>
          )}

          <Card className="p-5">
            <h3 className="text-sm font-bold">What happens on analyze</h3>
            <ol className="muted mt-3 space-y-2 text-xs">
              {[
                'Sentiment classification with a Twitter-RoBERTa model, plus mixed-clause detection.',
                'GoEmotions model mapped to ten business-facing emotions.',
                'Duplicate, burst, promotional and metadata signals with NLI evidence for suspicion.',
                'Account-level automation indicators and aspect-based sentiment.',
                'Keywords, topic clusters, time-series alerts and generated recommendations.',
              ].map((step, i) => <li key={i} className="flex gap-2"><CheckCircle2 size={14} className="mt-0.5 shrink-0 text-primary" /> {step}</li>)}
            </ol>
          </Card>
        </div>
      </div>
    </div>
  )
}
