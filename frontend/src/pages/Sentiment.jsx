import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Activity, Download, Play } from 'lucide-react'
import { downloadReport } from '../api'
import { useApp } from '../context'
import { useChartColors } from '../components/chartTheme'
import RecordTable from '../components/RecordTable'
import { Badge, Card, ChartCard, EmptyState, KpiCard, SectionTitle } from '../components/ui'

export default function Sentiment() {
  const { run, notify } = useApp()
  const colors = useChartColors()

  const distribution = useMemo(() => {
    const p = run?.summary?.sentiment_percentages || {}
    return ['positive', 'negative', 'neutral', 'mixed'].map((key) => ({
      key, name: key[0].toUpperCase() + key.slice(1), value: p[key] || 0,
    }))
  }, [run])

  const buckets = useMemo(() => (run?.sentiment?.score_buckets || []).map((b) => ({
    range: b.mid.toFixed(2), count: b.count, label: b.range,
  })), [run])

  if (!run) {
    return (
      <div>
        <SectionTitle eyebrow="NLP" title="Sentiment analysis" />
        <EmptyState icon={Activity} title="No sentiment results yet" description="Run an analysis to see per-record classification and confidence." action={<Link to="/analyze" className="btn btn-primary"><Play size={16} /> Analyze content</Link>} />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <SectionTitle
        eyebrow="NLP classification"
        title="Sentiment analysis"
        description="Every item is classified as positive, negative, neutral or mixed, with a calibrated score and confidence."
        action={<div className="flex gap-2">
          <button className="btn btn-secondary" onClick={() => downloadReport(run.id, 'csv').catch((e) => notify(e.message, 'error'))}><Download size={15} /> Export CSV</button>
          <Link to="/analyze" className="btn btn-primary"><Play size={15} /> New analysis</Link>
        </div>}
      />
      {run.is_demo && <p className="text-xs font-bold text-[var(--warning)]">DEMO DATA — these are hand-written examples, not real customer feedback.</p>}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <KpiCard label="Positive" value={`${distribution[0].value}%`} hint={`${run.summary.sentiment_counts.positive || 0} records`} tone="positive" />
        <KpiCard label="Negative" value={`${distribution[1].value}%`} hint={`${run.summary.sentiment_counts.negative || 0} records`} tone="negative" />
        <KpiCard label="Neutral" value={`${distribution[2].value}%`} hint={`${run.summary.sentiment_counts.neutral || 0} records`} />
        <KpiCard label="Mixed" value={`${distribution[3].value}%`} hint={`${run.summary.sentiment_counts.mixed || 0} records`} tone="warning" />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard title="Sentiment distribution" subtitle="Share of all analysed records">
          <ResponsiveContainer width="100%" height={230}>
            <BarChart data={distribution} margin={{ left: -18 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="name" tickLine={false} axisLine={false} />
              <YAxis unit="%" tickLine={false} axisLine={false} />
              <Tooltip />
              <Bar dataKey="value" name="Share %" radius={[6, 6, 0, 0]}>
                {distribution.map((d) => <Cell key={d.key} fill={colors[d.key]} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Sentiment score spread" subtitle="Score = positive probability − negative probability (−1 to +1)">
          <ResponsiveContainer width="100%" height={230}>
            <BarChart data={buckets} margin={{ left: -18 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="range" tickLine={false} axisLine={false} />
              <YAxis allowDecimals={false} tickLine={false} axisLine={false} />
              <Tooltip />
              <Bar dataKey="count" name="Records" fill={colors.primary} radius={[5, 5, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <div>
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-bold">Review explorer</h3>
          <Badge tone="primary">Search · filter · sort · export</Badge>
        </div>
        <RecordTable records={run.records} runId={run.id} summary={run.summary} />
      </div>
    </div>
  )
}
