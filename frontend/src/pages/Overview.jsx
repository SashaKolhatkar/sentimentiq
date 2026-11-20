import { useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import {
  Activity, ArrowRight, Bot, BrainCircuit, CircleAlert, Database, Play,
  ShieldAlert, Sparkles, TrendingUp,
} from 'lucide-react'
import { api } from '../api'
import { useApp } from '../context'
import { useChartColors } from '../components/chartTheme'
import { Badge, Card, ChartCard, EmptyState, InfoBanner, KpiCard, SectionTitle } from '../components/ui'

export default function Overview() {
  const { run, setRun, runs, refreshRuns, notify } = useApp()
  const colors = useChartColors()

  useEffect(() => {
    if (!run && runs.length) {
      api.run(runs[0].id).then(setRun).catch(() => {})
    }
  }, [run, runs, setRun])

  const sentimentData = useMemo(() => {
    const counts = run?.summary?.sentiment_counts || {}
    return ['positive', 'negative', 'neutral', 'mixed']
      .filter((k) => counts[k])
      .map((k) => ({ name: k[0].toUpperCase() + k.slice(1), value: counts[k], key: k }))
  }, [run])

  const trendData = useMemo(() => (run?.trends?.series || []).map((p) => ({
    date: p.date.slice(5),
    positive: Math.round(p.positive_rate * 100),
    negative: Math.round(p.negative_rate * 100),
    satisfaction: Math.round(p.satisfaction * 100),
  })), [run])

  const emotionData = useMemo(() => (run?.summary?.emotion_distribution || []).slice(0, 8).map((e) => ({
    name: e.emotion.slice(0, 9), value: e.count, full: e.emotion,
  })), [run])

  const spamData = useMemo(() => {
    const labels = run?.summary?.spam?.labels || {}
    return [
      { name: 'Likely Genuine', value: labels['Likely Genuine'] || 0, key: 'genuine' },
      { name: 'Potentially Suspicious', value: labels['Potentially Suspicious'] || 0, key: 'suspicious' },
      { name: 'Likely Spam', value: labels['Likely Spam'] || 0, key: 'spam' },
    ].filter((d) => d.value > 0)
  }, [run])

  if (!run) {
    return (
      <div>
        <SectionTitle eyebrow="Workspace" title="Overview dashboard" description="Turn unstructured feedback into decisions." />
        <EmptyState
          icon={Database}
          title="No analysis loaded yet"
          description="Upload a CSV/Excel/TXT file, paste reviews, or try the clearly labelled demo dataset. All results come from real NLP models."
          action={<div className="flex flex-wrap justify-center gap-2"><Link to="/analyze" className="btn btn-primary"><Play size={16} /> Analyze content</Link></div>}
        />
      </div>
    )
  }

  const s = run.summary
  const pct = s.sentiment_percentages

  return (
    <div className="space-y-6">
      <SectionTitle
        eyebrow="Overview dashboard"
        title={`Good analysis. Clear signals.`}
        description={`${run.name} · ${s.total_records} records analysed with ${(s.engines || []).join(', ') || 'local models'}.`}
        action={
          <div className="flex flex-wrap items-center gap-2">
            {run.is_demo && <Badge tone="warning">DEMO DATA — not customer results</Badge>}
            <Link to="/analyze" className="btn btn-primary"><Play size={15} /> New analysis</Link>
          </div>
        }
      />

      {(run.trends?.alerts || []).some((a) => a.severity === 'high') && (
        <InfoBanner tone="warning">
          <b>Active alert:</b> {run.trends.alerts.find((a) => a.severity === 'high').message}
        </InfoBanner>
      )}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <KpiCard label="Posts analysed" value={s.total_records} hint={`${s.date_range?.start || '—'} → ${s.date_range?.end || '—'}`} icon={Database} />
        <KpiCard label="Positive sentiment" value={`${pct.positive}%`} hint={`${s.sentiment_counts.positive || 0} positive items`} icon={TrendingUp} tone="positive" />
        <KpiCard label="Negative sentiment" value={`${pct.negative}%`} hint={`${s.sentiment_counts.negative || 0} negative items`} icon={Activity} tone="negative" />
        <KpiCard label="Avg sentiment score" value={s.average_sentiment_score} hint={`Satisfaction ${s.satisfaction_score}%`} icon={Sparkles} />
        <KpiCard label="Neutral sentiment" value={`${pct.neutral}%`} hint={`${pct.mixed}% mixed`} icon={Activity} tone="warning" />
        <KpiCard label="Suspicious content" value={`${s.spam.suspicious_percentage}%`} hint={`${s.spam.flagged_count} flagged records`} icon={ShieldAlert} tone="negative" />
        <KpiCard label="Automated accounts" value={s.bots.automated_accounts} hint={`of ${s.bots.accounts_analysed} accounts analysed`} icon={Bot} tone="warning" />
        <KpiCard label="Top emotion" value={s.emotion_distribution?.[0]?.emotion || '—'} hint={`${s.emotion_distribution?.[0]?.percentage || 0}% of records`} icon={BrainCircuit} />
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <ChartCard title="Sentiment distribution" subtitle="Four-class classification including mixed">
          <ResponsiveContainer width="100%" height={230}>
            <PieChart>
              <Pie data={sentimentData} dataKey="value" nameKey="name" innerRadius={55} outerRadius={85} paddingAngle={3}>
                {sentimentData.map((entry) => <Cell key={entry.key} fill={colors[entry.key] || colors.primary} />)}
              </Pie>
              <Tooltip />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Sentiment over time" subtitle={run.trends.available ? `${run.trends.period} aggregation` : 'Timeline unavailable'} className="xl:col-span-2">
          {run.trends.available ? (
            <ResponsiveContainer width="100%" height={230}>
              <AreaChart data={trendData} margin={{ left: -20, right: 8 }}>
                <defs>
                  <linearGradient id="posGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={colors.positive} stopOpacity={0.35} />
                    <stop offset="95%" stopColor={colors.positive} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="date" tickLine={false} axisLine={false} />
                <YAxis tickLine={false} axisLine={false} unit="%" />
                <Tooltip />
                <Legend />
                <Area type="monotone" dataKey="positive" name="Positive %" stroke={colors.positive} fill="url(#posGradient)" strokeWidth={2} />
                <Area type="monotone" dataKey="negative" name="Negative %" stroke={colors.negative} fill="transparent" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex h-[230px] items-center justify-center text-center text-sm muted">
              {run.trends.message}
            </div>
          )}
        </ChartCard>

        <ChartCard title="Emotion distribution" subtitle="Top detected emotions">
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={emotionData} margin={{ left: -22, right: 6 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="name" tickLine={false} axisLine={false} angle={-25} textAnchor="end" height={50} />
              <YAxis tickLine={false} axisLine={false} />
              <Tooltip />
              <Bar dataKey="value" name="Records" radius={[5, 5, 0, 0]}>
                {emotionData.map((_, i) => <Cell key={i} fill={colors.series[i % colors.series.length]} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Spam detection" subtitle="Suspicion classification">
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie data={spamData} dataKey="value" nameKey="name" outerRadius={78} paddingAngle={3}>
                <Cell fill={colors.positive} />
                <Cell fill={colors.mixed} />
                <Cell fill={colors.negative} />
              </Pie>
              <Tooltip />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>

        <Card className="p-5">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold">AI insights</h3>
            <Link to="/reports" className="text-xs font-bold text-primary">Full report →</Link>
          </div>
          <div className="mt-4 space-y-3">
            {(run.insights?.insights || []).slice(0, 4).map((insight, i) => (
              <div key={i} className="rounded-xl p-3" style={{ background: 'var(--surface-2)' }}>
                <p className="text-[10px] font-bold uppercase tracking-wide text-primary">{insight.category}</p>
                <p className="mt-1 text-xs leading-relaxed">{insight.text}</p>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="p-5">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold">Recent analyses</h3>
            <button className="text-xs font-bold text-primary" onClick={() => refreshRuns()}>Refresh</button>
          </div>
          <div className="mt-3 space-y-2">
            {runs.slice(0, 6).map((item) => (
              <button key={item.id} onClick={() => api.run(item.id).then(setRun).catch((e) => notify(e.message, 'error'))}
                className="flex w-full items-center gap-3 rounded-xl border p-3 text-left hover:bg-[var(--surface-2)]">
                <Database size={16} className="text-primary" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-bold">{item.name}</p>
                  <p className="muted text-[10px]">{new Date(item.created_at).toLocaleString()} · {item.record_count} records</p>
                </div>
                {item.is_demo && <Badge tone="warning">DEMO</Badge>}
                <ArrowRight size={14} className="muted" />
              </button>
            ))}
            {!runs.length && <p className="muted py-4 text-center text-xs">No saved analyses.</p>}
          </div>
        </Card>

        <Card className="p-5">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold">Alerts & anomalies</h3>
            <CircleAlert size={16} className="muted" />
          </div>
          <div className="mt-3 space-y-2">
            {(run.trends?.alerts || []).map((alert, i) => (
              <div key={i} className="flex items-start gap-3 rounded-xl p-3" style={{ background: 'var(--surface-2)' }}>
                <span className="mt-1 h-2 w-2 shrink-0 rounded-full" style={{ background: alert.severity === 'high' ? colors.negative : colors.mixed }} />
                <div>
                  <p className="text-xs font-semibold">{alert.message}</p>
                  <p className="muted text-[10px]">{alert.date} · {alert.type}</p>
                </div>
              </div>
            ))}
            {!run.trends?.alerts?.length && <p className="muted py-4 text-center text-xs">No unusual spikes or negative shifts detected.</p>}
          </div>
        </Card>
      </div>
    </div>
  )
}
