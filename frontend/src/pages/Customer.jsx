import { Link } from 'react-router-dom'
import {
  Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { HeartHandshake, Lightbulb, Play, Sparkles, Wrench } from 'lucide-react'
import { useApp } from '../context'
import { useChartColors } from '../components/chartTheme'
import { Badge, Card, ChartCard, EmptyState, KpiCard, SectionTitle } from '../components/ui'

function tone(score) {
  if (score > 0.25) return 'positive'
  if (score < -0.2) return 'negative'
  return 'neutral'
}

export default function Customer() {
  const { run } = useApp()
  const colors = useChartColors()
  if (!run) {
    return <div><SectionTitle eyebrow="Voice of customer" title="Customer insights" /><EmptyState icon={Sparkles} title="No aspect results yet" description="Run an analysis to extract product quality, pricing, delivery and support opinions." action={<Link to="/analyze" className="btn btn-primary"><Play size={16} /> Analyze content</Link>} /></div>
  }

  const chartData = (run.aspects.aspects || []).map((a) => ({
    name: a.aspect.replace(' ', '\n'),
    positive: a.positive_rate * 100,
    negative: a.negative_rate * 100,
    mentions: a.mentions,
  }))

  return (
    <div className="space-y-6">
      <SectionTitle eyebrow="Aspect-based sentiment" title="Customer review intelligence" description="Opinions are linked to specific aspects — for example, praising quality while criticising delivery." />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <KpiCard label="Aspects detected" value={run.aspects.aspects.length} hint="from detected clauses" icon={Sparkles} />
        <KpiCard label="Most appreciated" value={run.aspects.most_appreciated?.[0]?.aspect || '—'} hint={`${Math.round((run.aspects.most_appreciated?.[0]?.positive_rate || 0) * 100)}% positive`} tone="positive" />
        <KpiCard label="Top complaint" value={run.aspects.top_complaints?.[0]?.aspect || '—'} hint={`${run.aspects.top_complaints?.[0]?.negative || 0} negative mentions`} tone="negative" />
        <KpiCard label="Suggestions found" value={run.aspects.suggestions.length} hint="improvement requests" tone="warning" />
      </div>

      <ChartCard title="Aspect sentiment" subtitle="Positive and negative share of mentions per aspect">
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={chartData} margin={{ left: -12 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="name" tickLine={false} axisLine={false} interval={0} height={50} fontSize={10} />
            <YAxis unit="%" tickLine={false} axisLine={false} />
            <Tooltip />
            <Bar dataKey="positive" name="Positive %" stackId="a" fill={colors.positive} />
            <Bar dataKey="negative" name="Negative %" stackId="a" fill={colors.negative} radius={[5, 5, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="p-5">
          <div className="flex items-center gap-2"><HeartHandshake size={17} className="text-[var(--positive)]" /><h3 className="text-sm font-bold">Most appreciated</h3></div>
          <div className="mt-4 space-y-3">
            {run.aspects.most_appreciated.map((a) => (
              <div key={a.aspect} className="card-soft p-3">
                <div className="flex items-center justify-between"><p className="text-xs font-bold">{a.aspect}</p><Badge tone="positive">{Math.round(a.positive_rate * 100)}%</Badge></div>
                <p className="muted mt-1 text-[10px]">{a.mentions} mentions · avg score {a.average_score}</p>
              </div>
            ))}
            {!run.aspects.most_appreciated.length && <p className="muted text-xs">Not enough mentions to rank.</p>}
          </div>
        </Card>

        <Card className="p-5">
          <div className="flex items-center gap-2"><Wrench size={17} className="text-[var(--negative)]" /><h3 className="text-sm font-bold">Frequent complaints</h3></div>
          <div className="mt-4 space-y-3">
            {run.aspects.top_complaints.map((a) => (
              <div key={a.aspect} className="card-soft p-3">
                <div className="flex items-center justify-between"><p className="text-xs font-bold">{a.aspect}</p><Badge tone="negative">{a.negative} negative</Badge></div>
                <p className="muted mt-1 text-[10px]">{Math.round(a.negative_rate * 100)}% negative share</p>
              </div>
            ))}
            {!run.aspects.top_complaints.length && <p className="muted text-xs">No repeated complaints detected.</p>}
          </div>
        </Card>

        <Card className="p-5">
          <div className="flex items-center gap-2"><Lightbulb size={17} className="text-[var(--warning)]" /><h3 className="text-sm font-bold">Customer suggestions</h3></div>
          <div className="mt-4 max-h-[280px] space-y-2 overflow-auto">
            {run.aspects.suggestions.slice(0, 12).map((s, i) => (
              <div key={i} className="card-soft p-2.5">
                <Badge tone="primary">{s.aspect}</Badge>
                <p className="mt-1.5 text-[11px] leading-relaxed">{s.text}</p>
              </div>
            ))}
            {!run.aspects.suggestions.length && <p className="muted text-xs">No suggestion language detected.</p>}
          </div>
        </Card>
      </div>

      <Card className="p-5">
        <h3 className="text-sm font-bold">Aspect detail & example evidence</h3>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[760px] text-left text-xs">
            <thead className="muted"><tr className="border-b"><th className="py-2">Aspect</th><th>Mentions</th><th>Sentiment</th><th>Avg score</th><th>Example</th></tr></thead>
            <tbody>
              {run.aspects.aspects.map((a) => (
                <tr key={a.aspect} className="border-b align-top">
                  <td className="py-3 font-bold">{a.aspect}</td>
                  <td className="py-3">{a.mentions}</td>
                  <td className="py-3"><Badge tone={tone(a.average_score)}>{a.dominant_sentiment}</Badge></td>
                  <td className="py-3">{a.average_score}</td>
                  <td className="py-3 muted">{a.examples?.[0]?.text || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}
