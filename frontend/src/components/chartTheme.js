import { useApp } from '../context'

const PALETTES = {
  light: {
    positive: '#16a34a', negative: '#dc2626', neutral: '#64748b', mixed: '#f59e0b',
    primary: '#4f46e5', accent: '#06b6d4', grid: '#e2e8f0', text: '#475569',
    series: ['#4f46e5', '#06b6d4', '#f59e0b', '#ec4899', '#8b5cf6', '#16a34a', '#64748b'],
  },
  dark: {
    positive: '#4ade80', negative: '#fb7185', neutral: '#94a3b8', mixed: '#fbbf24',
    primary: '#818cf8', accent: '#22d3ee', grid: '#2a3853', text: '#94a3b8',
    series: ['#818cf8', '#22d3ee', '#fbbf24', '#f472b6', '#a78bfa', '#4ade80', '#94a3b8'],
  },
  pastel: {
    positive: '#6f9467', negative: '#b9685b', neutral: '#8a7a66', mixed: '#c8913f',
    primary: '#a86b4e', accent: '#7d9c86', grid: '#ddccb2', text: '#8a7a66',
    series: ['#a86b4e', '#7d9c86', '#c8913f', '#b9868a', '#9c8aae', '#6f9467', '#8a7a66'],
  },
}

export function useChartColors() {
  const { theme } = useApp()
  return PALETTES[theme] || PALETTES.light
}

export const EMOTION_COLORS = ['#6366f1', '#06b6d4', '#f59e0b', '#ec4899', '#8b5cf6', '#10b981', '#f97316', '#3b82f6', '#a855f7', '#64748b']

export function sentimentColor(key, colors) {
  return colors[key] || colors.primary
}
