import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { BrainCircuit, Play } from 'lucide-react'
import { useApp } from '../context'
import { EMOTION_COLORS, useChartColors } from '../components/chartTheme'
import RecordTable from '../components/RecordTable'
import { Card, ChartCard, EmptyState, KpiCard, SectionTitle } from '../components/ui'

export default function Emotion() {
  const { run } = useApp()
  const colors = useChartColors()
  const data = useMemo(() => (run?.summary?.emotion_distribution || []).map((e) => ({
    name: e.emotion.slice(0, 10), emotion: e.emotion, count: e.count, percentage: e.percentage,
  })), [run])

  if (!run) {
    return <div><SectionTitle eyebrow="Affective computing" title="Emotion detection" /><EmptyState icon={BrainCircuit} title="No emotion results yet" description="Run an analysis to detect emotions and confidence per record." action={<Link to="/analyze" className="btn btn-primary"><Play size={16} /> Analyze content</Link>} /></div>
  }

  const top = data[0]
  const avg = run.emotions.average_confidence

  return (
    <div className="space-y-6">
      <SectionTitle eyebrow="GoEmotions model" title="Emotion detection" description="Ten business-facing emotions detected from each comment, with per-record confidence." />
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <KpiCard label="Top emotion" value={top?.emotion || '—'} hint={`${top?.percentage || 0}% of records`} icon={BrainCircuit} />
        <KpiCard label="Emotions detected" value={data.length} hint="distinct categories" />
        <KpiCard label="Avg confidence" value={avg} hint="model confidence across records" />
        <KpiCard label="Dataset size" value={run.summary.total_records} hint="analysed items" />
      </div>

      <ChartCard title="Emotion distribution" subtitle="Detected dominant emotion per record">
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={data} margin={{ left: -16, right: 10 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="name" tickLine={false} axisLine={false} angle={-18} textAnchor="end" height={55} />
            <YAxis tickLine={false} axisLine={false} allowDecimals={false} />
            <Tooltip />
            <Bar dataKey="count" name="Records" radius={[6, 6, 0, 0]}>
              {data.map((_, i) => <Cell key={i} fill={EMOTION_COLORS[i % EMOTION_COLORS.length]} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {data.slice(0, 10).map((item, i) => (
          <Card key={item.emotion} className="p-4">
            <div className="flex items-center justify-between">
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: EMOTION_COLORS[i % EMOTION_COLORS.length] }} />
              <span className="muted text-[10px]">{item.percentage}%</span>
            </div>
            <p className="mt-2 text-sm font-bold capitalize">{item.emotion}</p>
            <p className="muted text-xs">{item.count} records</p>
            <div className="mt-3 h-1.5 overflow-hidden rounded-full" style={{ background: 'var(--surface-2)' }}>
              <div className="h-full rounded-full" style={{ width: `${item.percentage}%`, background: EMOTION_COLORS[i % EMOTION_COLORS.length] }} />
            </div>
          </Card>
        ))}
      </div>

      <div>
        <h3 className="mb-3 text-sm font-bold">Emotion by record</h3>
        <RecordTable records={run.records} runId={run.id} summary={run.summary} compact />
      </div>
    </div>
  )
}
