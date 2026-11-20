import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'
import { AlertTriangle, Play, ShieldAlert } from 'lucide-react'
import { useApp } from '../context'
import { useChartColors } from '../components/chartTheme'
import RecordTable from '../components/RecordTable'
import { Card, ChartCard, EmptyState, InfoBanner, KpiCard, SectionTitle } from '../components/ui'

export default function Spam() {
  const { run } = useApp()
  const colors = useChartColors()
  const data = useMemo(() => {
    const labels = run?.summary?.spam?.labels || {}
    return [
      { name: 'Likely Genuine', value: labels['Likely Genuine'] || 0 },
      { name: 'Potentially Suspicious', value: labels['Potentially Suspicious'] || 0 },
      { name: 'Likely Spam', value: labels['Likely Spam'] || 0 },
    ]
  }, [run])

  if (!run) {
    return <div><SectionTitle eyebrow="Trust & safety" title="Spam & fake review detection" /><EmptyState icon={ShieldAlert} title="No suspicion results yet" description="Run an analysis to see duplicate, burst, promotional and account-level evidence." action={<Link to="/analyze" className="btn btn-primary"><Play size={16} /> Analyze content</Link>} /></div>
  }

  const flagged = run.records.filter((r) => r.suspicion_score >= 0.34)

  return (
    <div className="space-y-6">
      <SectionTitle eyebrow="Content integrity" title="Spam & fake review detection" description="Suspicion scoring combines wording, repetition patterns, timing bursts, account metadata and NLI evidence." />
      <InfoBanner tone="warning">
        <b>Uncertainty is shown on purpose.</b> {run.spam.warning} Wording-only cases are capped at “Potentially Suspicious”.
      </InfoBanner>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <KpiCard label="Suspicious content" value={`${run.summary.spam.suspicious_percentage}%`} hint={`${run.summary.spam.flagged_count} flagged records`} icon={ShieldAlert} tone="negative" />
        <KpiCard label="Likely Spam" value={run.summary.spam.labels['Likely Spam'] || 0} hint="behavioural evidence required" tone="negative" />
        <KpiCard label="Potentially Suspicious" value={run.summary.spam.labels['Potentially Suspicious'] || 0} hint="review manually" tone="warning" />
        <KpiCard label="Avg suspicion score" value={run.summary.spam.average_suspicion_score} hint="0 = genuine, 1 = highly suspicious" />
      </div>

      <div className="grid gap-4 lg:grid-cols-[360px_1fr]">
        <ChartCard title="Classification" subtitle="All records by suspicion label">
          <ResponsiveContainer width="100%" height={250}>
            <PieChart>
              <Pie data={data.filter((d) => d.value > 0)} dataKey="value" nameKey="name" innerRadius={60} outerRadius={92} paddingAngle={3}>
                <Cell fill={colors.positive} /><Cell fill={colors.mixed} /><Cell fill={colors.negative} />
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
          <div className="mt-2 space-y-1.5">
            {data.map((d, i) => <div key={d.name} className="flex items-center justify-between text-xs">
              <span className="flex items-center gap-2"><span className="h-2 w-2 rounded-full" style={{ background: [colors.positive, colors.mixed, colors.negative][i] }} />{d.name}</span>
              <b>{d.value}</b>
            </div>)}
          </div>
        </ChartCard>

        <Card className="p-5">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold">Flagged records & explanations</h3>
            <span className="chip badge-warning">{flagged.length} flagged</span>
          </div>
          <div className="mt-4 max-h-[320px] space-y-3 overflow-auto pr-1">
            {flagged.slice(0, 30).map((r) => (
              <div key={r.id} className="rounded-xl border p-3">
                <div className="flex items-start justify-between gap-3">
                  <p className="text-xs leading-relaxed">{r.text}</p>
                  <span className="shrink-0 text-xs font-bold" style={{ color: r.suspicion_score > 0.66 ? colors.negative : colors.mixed }}>{r.suspicion_score}</span>
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {(r.spam_reasons || []).map((reason, i) => <span key={i} className="chip badge-neutral text-[10px]">{reason}</span>)}
                </div>
                <p className="muted mt-2 text-[10px]">Confidence {r.spam_confidence} · uncertainty {r.spam_uncertainty}</p>
              </div>
            ))}
            {!flagged.length && <p className="muted py-8 text-center text-sm">No records crossed the suspicion threshold.</p>}
          </div>
        </Card>
      </div>

      <div>
        <div className="mb-3 flex items-center gap-2">
          <AlertTriangle size={15} className="text-[var(--warning)]" />
          <h3 className="text-sm font-bold">All records with suspicion signals</h3>
        </div>
        <RecordTable records={run.records} runId={run.id} summary={run.summary} compact />
      </div>
    </div>
  )
}
