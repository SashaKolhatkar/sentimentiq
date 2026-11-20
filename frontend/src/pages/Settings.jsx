import { useCallback, useEffect, useState } from 'react'
import { CheckCircle2, Cpu, Database, DownloadCloud, Moon, RefreshCw, ShieldCheck, Sparkles, Sun } from 'lucide-react'
import { api } from '../api'
import { useApp } from '../context'
import { Badge, Card, ErrorBanner, InfoBanner, SectionTitle } from '../components/ui'

const MODEL_LABELS = {
  sentiment: 'Sentiment (Twitter-RoBERTa / TweetEval family)',
  emotion: 'Emotion (GoEmotions RoBERTa)',
  nli: 'Zero-shot evidence (DistilBERT MNLI)',
  embedding: 'Similarity embeddings (MiniLM)',
}

export default function Settings() {
  const { theme, setTheme, config, notify } = useApp()
  const [models, setModels] = useState(null)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try {
      const data = await api.models()
      setModels(data.models)
    } catch (err) { setError(err.message) }
  }, [])

  useEffect(() => { load() }, [load])

  const warm = async (keys) => {
    setBusy(keys?.join(',') || 'all'); setError('')
    try {
      const result = await api.warmModels(keys)
      const failed = Object.entries(result.models || {}).filter(([, v]) => !v.ok)
      if (failed.length) setError(failed.map(([k, v]) => `${k}: ${v.error}`).join('\n'))
      else notify('Models are ready.', 'success')
      setModels(result.status.models)
    } catch (err) {
      setError(err.message)
    } finally { setBusy('') }
  }

  const themes = [
    { id: 'light', label: 'Light', icon: Sun, detail: 'Clean, bright workspace' },
    { id: 'dark', label: 'Dark', icon: Moon, detail: 'Low-light professional view' },
    { id: 'pastel', label: 'Pastel sepia', icon: Sparkles, detail: 'Soft, warm balanced mode' },
  ]

  return (
    <div className="space-y-6">
      <SectionTitle eyebrow="Workspace configuration" title="Settings" description="Manage appearance, local AI models, access and data privacy." />

      <ErrorBanner message={error} onDismiss={() => setError('')} />

      <Card className="p-5">
        <div className="flex items-center justify-between"><div><h3 className="text-sm font-bold">Appearance</h3><p className="muted text-xs">Choose the theme that fits your workspace.</p></div></div>
        <div className="mt-4 grid gap-3 md:grid-cols-3">
          {themes.map((t) => (
            <button key={t.id} onClick={() => setTheme(t.id)}
              className={`flex items-start gap-3 rounded-xl border p-4 text-left transition ${theme === t.id ? 'text-primary' : 'hover:bg-[var(--surface-2)]'}`}
              style={theme === t.id ? { background: 'var(--primary-soft)', borderColor: 'var(--primary)' } : undefined}>
              <t.icon size={19} className="mt-0.5" />
              <div><p className="text-sm font-bold">{t.label}</p><p className="muted text-[11px]">{t.detail}</p></div>
              {theme === t.id && <CheckCircle2 size={16} className="ml-auto" />}
            </button>
          ))}
        </div>
      </Card>

      <Card className="p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div><h3 className="text-sm font-bold">AI models</h3><p className="muted text-xs">Real Hugging Face models are downloaded on demand and cached locally.</p></div>
          <div className="flex gap-2">
            <button className="btn btn-secondary" onClick={load}><RefreshCw size={15} /> Refresh</button>
            <button className="btn btn-primary" onClick={() => warm()} disabled={!!busy}>
              <DownloadCloud size={15} /> {busy ? 'Downloading…' : 'Download all models'}
            </button>
          </div>
        </div>
        <InfoBanner>
          The first download can be several hundred MB. Analysis still runs with a transparent lexicon fallback
          if a model cannot be downloaded, and the UI always shows which engine was used.
        </InfoBanner>
        <div className="mt-4 space-y-3">
          {Object.entries(models || {}).map(([key, info]) => (
            <div key={key} className="card-soft flex flex-wrap items-center justify-between gap-3 p-3">
              <div className="min-w-[220px]">
                <p className="text-xs font-bold">{MODEL_LABELS[key] || key}</p>
                <p className="muted mt-0.5 break-all font-mono text-[10px]">{info.id}</p>
                {info.error && <p className="mt-1 text-[10px]" style={{ color: 'var(--negative)' }}>{info.error}</p>}
              </div>
              <div className="flex items-center gap-2">
                <Badge tone={info.loaded ? 'positive' : info.cached ? 'primary' : 'neutral'}>
                  {info.loaded ? 'Loaded' : info.cached ? 'Cached' : 'Not downloaded'}
                </Badge>
                <button className="btn btn-secondary h-8 px-3 text-xs" onClick={() => warm([key])} disabled={!!busy}>Load</button>
              </div>
            </div>
          ))}
          {!models && <p className="muted py-4 text-center text-xs">Loading model status…</p>}
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="p-5">
          <div className="flex items-center gap-2"><ShieldCheck size={17} className="text-primary" /><h3 className="text-sm font-bold">Security & access</h3></div>
          <div className="mt-3 space-y-2 text-xs">
            <div className="flex items-center justify-between"><span className="muted">Authentication</span><Badge tone={config?.auth_enabled ? 'positive' : 'warning'}>{config?.auth_enabled ? 'Enabled' : 'Disabled (local demo)'}</Badge></div>
            <div className="flex items-center justify-between"><span className="muted">Upload size limit</span><b>{config?.max_file_size_mb || 25} MB</b></div>
            <div className="flex items-center justify-between"><span className="muted">Record limit</span><b>{config?.max_records || 10000}</b></div>
            <div className="flex items-center justify-between"><span className="muted">Allowed URL domains</span><b>{config?.allowed_domains?.length || 0}</b></div>
            <p className="muted pt-2 leading-relaxed">Set SENTIMENTIQ_ADMIN_PASSWORD and SENTIMENTIQ_SECRET_KEY in the backend environment to enable secure sign-in. Uploads are extension-checked and URL fetches block private addresses and respect robots.txt.</p>
          </div>
        </Card>

        <Card className="p-5">
          <div className="flex items-center gap-2"><Database size={17} className="text-primary" /><h3 className="text-sm font-bold">Dataset foundation</h3></div>
          <p className="muted mt-1 text-[11px]">Five carefully chosen public resources inform the model families and signal design.</p>
          <div className="mt-3 space-y-2">
            {(config?.dataset_foundation || []).map((d) => (
              <div key={d.name} className="card-soft flex items-center justify-between p-2.5 text-xs">
                <span className="font-semibold">{d.name}</span><span className="muted">{d.role}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card className="p-5">
        <div className="flex items-center gap-2"><Cpu size={17} className="text-primary" /><h3 className="text-sm font-bold">How results are produced</h3></div>
        <div className="mt-3 grid gap-3 md:grid-cols-3">
          {[
            ['NLP models', 'Sentiment and emotion use transformer classifiers. Zero-shot NLI provides secondary evidence for suspicion and automation.'],
            ['Statistical learning', 'TF-IDF and NMF extract topics; cosine similarity finds duplicates and coordinated content.'],
            ['Transparent rules', 'Mixed sentiment, aspect linkage, alerts and recommendations are derived from model outputs with explicit thresholds.'],
          ].map(([title, detail]) => <div key={title} className="card-soft p-3"><p className="text-xs font-bold">{title}</p><p className="muted mt-1 text-[11px] leading-relaxed">{detail}</p></div>)}
        </div>
      </Card>
    </div>
  )
}
