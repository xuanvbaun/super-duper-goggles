const pointCount = 50

function makeSeries(base, drift, amplitude, phase = 0) {
  return Array.from({ length: pointCount }, (_, index) => {
    const progress = index / (pointCount - 1)
    const wave = Math.sin(index * 0.58 + phase) * amplitude
    const micro = Math.sin(index * 1.87 + phase * 0.6) * amplitude * 0.28
    return Number((base + drift * progress + wave + micro).toFixed(2))
  })
}

export const marketMeta = {
  mode: 'demo',
  label: '演示数据 · 非实时',
  updatedAt: '等待接入行情源',
}

export const marketIndexes = [
  {
    code: '000001.SH',
    name: '上证指数',
    value: 3185.26,
    change: 0.42,
    color: '#ff5f57',
    series: makeSeries(3168, 17, 3.8, 0.3),
  },
  {
    code: '399001.SZ',
    name: '深证成指',
    value: 9732.28,
    change: 0.57,
    color: '#ff7a59',
    series: makeSeries(9674, 58, 13, 1.1),
  },
  {
    code: '399006.SZ',
    name: '创业板指',
    value: 1872.64,
    change: -0.26,
    color: '#55c98b',
    series: makeSeries(1880, -7, 4.5, 2.4),
  },
  {
    code: '000300.SH',
    name: '沪深300',
    value: 3692.41,
    change: 0.33,
    color: '#63a8ff',
    series: makeSeries(3678, 14, 3.1, 0.8),
  },
]

export const marketAnomalies = [
  {
    time: '14:32',
    title: '军工板块成交活跃度上升',
    detail: '成交量较近 5 日同时段均值高 38%',
    tone: 'blue',
  },
  {
    time: '14:25',
    title: '半导体指数短时波动扩大',
    detail: '10 分钟区间振幅达到 1.76%',
    tone: 'amber',
  },
  {
    time: '14:17',
    title: '银行板块出现同步拉升',
    detail: '相关指数 8 分钟内变化 0.31%',
    tone: 'green',
  },
]

export const marketBreadth = {
  rising: 3184,
  falling: 1746,
  flat: 154,
}

export const sectors = [
  { name: '国防军工', change: 2.21, turnover: '823.6 亿', trend: [31, 35, 34, 43, 48, 51, 56, 61] },
  { name: '半导体', change: 1.48, turnover: '612.4 亿', trend: [30, 32, 37, 40, 46, 45, 52, 55] },
  { name: '银行', change: 0.96, turnover: '498.1 亿', trend: [35, 33, 36, 39, 38, 42, 45, 47] },
  { name: '新能源', change: 0.72, turnover: '456.7 亿', trend: [38, 36, 39, 43, 41, 44, 46, 48] },
  { name: '医药', change: -0.36, turnover: '389.3 亿', trend: [52, 50, 48, 46, 47, 43, 41, 40] },
]

export const heatmap = [
  { name: '军工', value: 2.21, size: 1.25 },
  { name: 'AI 算力', value: 1.63, size: 1.1 },
  { name: '证券', value: 0.89, size: 0.92 },
  { name: '消费电子', value: 0.54, size: 1.08 },
  { name: '有色金属', value: -0.12, size: 0.88 },
]

export const marketEvents = [
  { index: 13, time: '10:15', source: '国家统计局', title: '发布月度宏观经济数据', related: '消费' },
  { index: 25, time: '11:08', source: '中国人民银行', title: '发布公开市场操作公告', related: '银行、地产' },
  { index: 39, time: '14:17', source: '证监会网站', title: '发布上市公司监管动态', related: '证券' },
]

export const marketTimes = Array.from({ length: pointCount }, (_, index) => {
  const morningPoints = 25
  if (index < morningPoints) {
    const totalMinutes = 9 * 60 + 30 + index * 5
    return `${String(Math.floor(totalMinutes / 60)).padStart(2, '0')}:${String(totalMinutes % 60).padStart(2, '0')}`
  }
  const totalMinutes = 13 * 60 + (index - morningPoints) * 5
  return `${String(Math.floor(totalMinutes / 60)).padStart(2, '0')}:${String(totalMinutes % 60).padStart(2, '0')}`
})

export const volumeSeries = Array.from({ length: pointCount }, (_, index) => {
  const edgeBoost = index < 5 || index > pointCount - 6 ? 48 : 0
  return Math.round(24 + edgeBoost + Math.abs(Math.sin(index * 0.71)) * 48)
})

export function sparklinePoints(values, width = 100, height = 28, padding = 2) {
  const min = Math.min(...values)
  const max = Math.max(...values)
  const range = max - min || 1
  return values.map((value, index) => {
    const x = padding + (index / Math.max(1, values.length - 1)) * (width - padding * 2)
    const y = height - padding - ((value - min) / range) * (height - padding * 2)
    return `${x.toFixed(2)},${y.toFixed(2)}`
  }).join(' ')
}
