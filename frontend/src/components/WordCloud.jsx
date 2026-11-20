import { useMemo, useState } from 'react'
import { useChartColors } from './chartTheme'

export default function WordCloud({ words = [] }) {
  const colors = useChartColors()
  const [hovered, setHovered] = useState(null)
  const items = useMemo(() => words.slice(0, 45), [words])

  if (!items.length) {
    return <p className="muted py-10 text-center text-sm">No repeated keywords were found in this dataset.</p>
  }

  return (
    <div className="flex min-h-[240px] flex-wrap items-center justify-center gap-x-4 gap-y-2 py-4">
      {items.map((item, index) => {
        const size = 12 + Math.round((item.weight || 0.4) * 22)
        const color = colors.series[index % colors.series.length]
        return (
          <span
            key={item.text}
            className="cursor-default transition-transform hover:scale-110"
            style={{ fontSize: size, fontWeight: item.weight > 0.7 ? 800 : 600, color, opacity: hovered && hovered !== item.text ? 0.38 : 1 }}
            onMouseEnter={() => setHovered(item.text)}
            onMouseLeave={() => setHovered(null)}
            title={`${item.text}: ${item.value} mentions`}
          >
            {item.text}
          </span>
        )
      })}
    </div>
  )
}
