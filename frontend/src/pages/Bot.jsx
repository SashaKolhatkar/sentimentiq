import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'
import { Bot as BotIcon, Play } from 'lucide-react'
import { useApp } from '../context'
import { useChartColors } from '../components/chartTheme'
import { Badge, Card, EmptyState, InfoBanner, KpiCard, SectionTitle } from '../components/ui'

const LABEL_TONES = {
  'Likely Human': 'positive',
  'Possibly Automated': 'warning',
  'Strong Automation Indicators': 'negative',
  'Insufficient Data': 'neutral',
}

export default function Bot() {
  const { run } = useApp()
  const colors = useChartColors()
  const accounts = useMemo(() => run?.bots?.accounts || [], [run])
  const chartData = useMemo(() => {
    const counts = run?.summary?.bots?.labels || {}
    return Object.entries(counts).map(([name, value]) => ({ name, value }))
  }, [run])

  if (!run) {
    return <div><SectionTitle eyebrow="Account behaviour" title="Bot detection" /><EmptyState icon={BotIcon} title="No account signals yet" description="Upload data with an author column and timestamps to analyse posting behaviour." action={<Link to="/analyze" className="btn btn-primary"><Play size={16} /> Analyze content</Link>} /></div>
  }

  return (
    <div className="space-y-6">
      <SectionTitle eyebrow="Automation detection" title="AI bot & automated account detection" description="Account-level classification from timing regularity, content repetition, coordination and profile signals." />
      <InfoBanner>
        No account is labelled a bot from a single signal. “Strong Automation Indicators” requires at least three
        independent signals; uncertainty is displayed for every account.
      </InfoBanner>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <KpiCard label="Accounts analysed" value={run.summary.bots.accounts_analysed} hint="unique authors" icon={BotIcon} />
        <KpiCard label="Strong indicators" value={run.summary.bots.labels['Strong Automation Indicators'] || 0} hint="multiple signals agree" tone="negative" />
        <KpiCard label="Possibly automated" value={run.summary.bots.labels['Possibly Automated'] || 0} hint="manual review advised" tone="warning" />
        <KpiCard label="Insufficient data" value={run.summary.bots.labels['Insufficient Data'] || 0} hint="not enough evidence" />
      </div>

      <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
        <Card className="p-5">
          <h3 className="text-sm font-bold">Account classifications</h3>
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie data={chartData} dataKey="value" nameKey="name" outerRadius={82}>
                {chartData.map((_, i) => <Cell key={i} fill={[colors.positive, colors.mixed, colors.negative, colors.neutral][i % 4]} />)}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
          <div className="space-y-1.5">
            {chartData.map((d, i) => <div key={d.name} className="flex items-center justify-between text-xs">
              <span className="flex items-center gap-2"><span className="h-2 w-2 rounded-full" style={{ background: [colors.positive, colors.mixed, colors.negative, colors.neutral][i % 4] }} />{d.name}</span>
              <b>{d.value}</b>
            </div>)}
          </div>
        </Card>

        <Card className="overflow-hidden">
          <div className="border-b p-4">
            <h3 className="text-sm font-bold">Account evidence</h3>
            <p className="muted text-[11px]">Indicators are shown so a human can verify every classification.</p>
          </div>
          <div className="max-h-[460px] overflow-auto">
            <table className="w-full min-w-[680px] text-left text-xs">
              <thead className="sticky top-0" style={{ background: 'var(--surface-2)' }}>
                <tr className="muted"><th className="px-4 py-2">Account</th><th className="px-3 py-2">Posts</th><th className="px-3 py-2">Classification</th><th className="px-3 py-2">Score</th><th className="px-3 py-2">Indicators</th></tr>
              </thead>
              <tbody>
                {accounts.map((a) => (
                  <tr key={a.author} className="border-b align-top">
                    <td className="px-4 py-3 font-semibold">{a.author}</td>
                    <td className="px-3 py-3">{a.posts}</td>
                    <td className="px-3 py-3"><Badge tone={LABEL_TONES[a.label] || 'neutral'}>{a.label}</Badge></td>
                    <td className="px-3 py-3">
                      <span className="font-bold">{a.score}</span>
                      <p className="muted text-[10px]">±{a.uncertainty}</p>
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex flex-wrap gap-1">
                        {a.indicators.length ? a.indicators.map((ind) => <span key={ind.name} className="chip text-[10px]">{ind.name}</span>) : <span className="muted">None detected</span>}
                      </div>
                      <p className="muted mt-1.5 text-[10px]">{a.note}</p>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      <Card className="p-5">
        <h3 className="text-sm font-bold">Signal definitions</h3>
        <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {[
            ['Repeated content', 'Low unique-post ratio across an account.'],
            ['Regular intervals', 'Very low variation in posting gaps over many posts.'],
            ['High frequency', 'Unusually many posts per observed hour.'],
            ['Self-similarity', 'Posts that closely resemble each other in wording.'],
            ['Cross-account coordination', 'Posts that mirror posts from different accounts.'],
            ['Metadata anomalies', 'New accounts, abnormal follower ratios or declared posting rates.'],
          ].map(([title, detail]) => (
            <div key={title} className="card-soft p-3">
              <p className="text-xs font-bold">{title}</p>
              <p className="muted mt-1 text-[11px] leading-relaxed">{detail}</p>
            </div>
          ))}
        </div>
      </Card>
    </div>
  )
}
