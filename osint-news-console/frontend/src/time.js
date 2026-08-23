const SHANGHAI_TZ = 'Asia/Shanghai'

function asDate(value) {
  if (!value) return null
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

export function formatDateTime(value) {
  const date = asDate(value)
  if (!date) return '时间未知'
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: SHANGHAI_TZ,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).format(date)
}

export function formatTime(value) {
  const date = asDate(value)
  if (!date) return '—'
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: SHANGHAI_TZ,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  }).format(date)
}

export function formatDelay(publishedAt, fetchedAt) {
  const published = asDate(publishedAt)
  const fetched = asDate(fetchedAt)
  if (!published || !fetched) return '采集延迟未知'
  const minutes = Math.max(0, Math.round((fetched - published) / 60000))
  if (minutes <= 1) return '采集延迟 ≤1分钟'
  if (minutes < 60) return `采集延迟 ${minutes}分钟`
  const hours = Math.round((minutes / 60) * 10) / 10
  if (hours < 48) return `采集延迟 ${hours}小时`
  return `采集延迟 ${Math.round(hours / 24)}天`
}

export function formatRelativeTime(value) {
  const date = asDate(value)
  if (!date) return '时间未知'
  const minutes = Math.max(0, Math.round((Date.now() - date.getTime()) / 60000))
  if (minutes <= 1) return '刚刚'
  if (minutes < 60) return `${minutes}分钟前`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}小时前`
  const days = Math.round(hours / 24)
  if (days <= 7) return `${days}天前`
  return formatDateTime(value)
}

export function shanghaiDateKey(value = new Date()) {
  const date = asDate(value)
  if (!date) return ''
  const parts = new Intl.DateTimeFormat('en', {
    timeZone: SHANGHAI_TZ,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(date)
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]))
  return `${values.year}-${values.month}-${values.day}`
}
