import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Hash, Play, TrendingUp } from 'lucide-react'
import { useApp } from '../context'
import { useChartColors } from '../components/chartTheme'
import WordCloud from '../components/WordCloud'
import { Badge, Card, ChartCard, EmptyState, KpiCard, SectionTitle } from '../components/ui'

export default function Trending() {
  const { run } = useApp()
  const colors = useChartColors()
  const keywordBars = useMemo(() => (run?.topics?.keywords || []).slice(0, 12).map((k) => ({ word: k.word, count: k.count })), [run])
  const topicTrend = useMemo(() => (run?.trends?.series || []).map((p) => ({
    date: p.date.slice(5), discussion: p.total, satisfaction: Math.round(p.satisfaction * 100),
  })), [run])

  if (!run) {
    return <div><SectionTitle eyebrow="Text mining" title="Trending topics & keywords" /><EmptyState icon={Hash} title="No topic results yet" description="Run an analysis to extract keywords, hashtags, phrases and topic clusters." action={<Link to="/analyze" className="btn btn-primary"><Play size={16} /> Analyze content</Link>} /></div>
  }

  return (
    <div className="space-y-6">
      <SectionTitle eyebrow="Topic intelligence" title="Trending topics & keywords" description="Frequent terms, hashtags, phrases and NMF topic clusters computed with scikit-learn." />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <KpiCard label="Unique terms" value={run.topics.unique_terms} hint="after stop-word removal" icon={Hash} />
        <KpiCard label="Topic clusters" value={run.topics.clusters.length} hint="NMF clustering" />
        <KpiCard label="Hashtags found" value={run.topics.hashtags.length} hint="unique hashtags" />
        <KpiCard label="Emerging terms" value={run.topics.emerging.length} hint="rising in recent records" icon={TrendingUp} tone="warning" />
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.3fr_0.7fr]">
        <ChartCard title="Word cloud" subtitle="Font size reflects mention count">
          <WordCloud words={run.topics.word_cloud} />
        </ChartCard>

        <ChartCard title="Top keywords" subtitle="Most frequent meaningful terms">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={keywordBars} layout="vertical" margin={{ left: 40, right: 12 }}>
              <CartesianGrid strokeDasharray="3 3" horizontal={false} />
              <XAxis type="number" allowDecimals={false} tickLine={false} axisLine={false} />
              <YAxis type="category" dataKey="word" width={70} tickLine={false} axisLine={false} fontSize={10} />
              <Tooltip />
              <Bar dataKey="count" name="Mentions" fill={colors.primary} radius={[0, 5, 5, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="p-5">
          <h3 className="text-sm font-bold">Topic clusters</h3>
          <p className="muted text-[11px]">Higher importance means more discussion and a larger negative share.</p>
          <div className="mt-4 space-y-3">
            {run.topics.clusters.map((c) => (
              <div key={c.id} className="card-soft p-3">
                <div className="flex items-start justify-between gap-3">
                  <div><p className="text-xs font-bold capitalize">{c.label}</p><p className="muted mt-1 text-[10px]">{c.terms.slice(0, 6).join(' · ')}</p></div>
                  <Badge tone={c.negative_share > 0.5 ? 'negative' : 'primary'}>{Math.round(c.share * 100)}%</Badge>
                </div>
                <div className="mt-2 h-1.5 overflow-hidden rounded-full" style={{ background: 'var(--surface)' }}>
                  <div className="h-full rounded-full" style={{ width: `${Math.min(100, c.importance * 100)}%`, background: colors.primary }} />
                </div>
                <p className="muted mt-1.5 text-[10px]">{c.size} records · {Math.round(c.negative_share * 100)}% negative/mixed</p>
              </div>
            ))}
            {!run.topics.clusters.length && <p className="muted text-xs">At least six records with repeated terms are needed for clustering.</p>}
          </div>
        </Card>

        <div className="space-y-4">
          <Card className="p-5">
            <h3 className="text-sm font-bold">Common phrases</h3>
            <div className="mt-3 flex flex-wrap gap-2">
              {[...run.topics.bigrams.slice(0, 10), ...run.topics.trigrams.slice(0, 8)].map((p) => (
                <span key={p.phrase} className="chip">{p.phrase} <b className="text-primary">{p.count}</b></span>
              ))}
              {!run.topics.bigrams.length && !run.topics.trigrams.length && <p className="muted text-xs">No repeated phrases found.</p>}
            </div>
          </Card>
          <Card className="p-5">
            <h3 className="text-sm font-bold">Hashtags</h3>
            <div className="mt-3 flex flex-wrap gap-2">
              {run.topics.hashtags.map((h) => <span key={h.tag} className="chip badge-primary">#{h.tag} <b>{h.count}</b></span>)}
              {!run.topics.hashtags.length && <p className="muted text-xs">No hashtags detected.</p>}
            </div>
          </Card>
          <Card className="p-5">
            <h3 className="text-sm font-bold">Emerging concerns</h3>
            <div className="mt-3 space-y-2">
              {run.topics.emerging.map((e) => (
                <div key={e.word} className="flex items-center justify-between text-xs">
                  <span className="font-semibold">{e.word}</span>
                  <span className="muted">{e.early} → {e.late} mentions · <b style={{ color: colors.positive }}>{e.growth}×</b></span>
                </div>
              ))}
              {!run.topics.emerging.length && <p className="muted text-xs">Need dated records across a longer period.</p>}
            </div>
          </Card>
        </div>
      </div>

      {run.trends.available && (
        <ChartCard title="Discussion volume vs satisfaction" subtitle="Helps explain why a topic matters">
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={topicTrend} margin={{ left: -18 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="date" tickLine={false} axisLine={false} />
              <YAxis yAxisId="left" tickLine={false} axisLine={false} allowDecimals={false} />
              <YAxis yAxisId="right" orientation="right" domain={[0, 100]} tickLine={false} axisLine={false} unit="%" />
              <Tooltip />
              <Line yAxisId="left" type="monotone" dataKey="discussion" name="Posts" stroke={colors.primary} strokeWidth={2} dot={false} />
              <Line yAxisId="right" type="monotone" dataKey="satisfaction" name="Satisfaction %" stroke={colors.positive} strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
      )}
    </div>
  )
}
