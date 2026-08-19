import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 15000,
})

export function fetchNews(params = {}) {
  return api.get('/news', { params })
}

export function fetchNewsDetail(id) {
  return api.get(`/news/${id}`)
}

export function fetchStats() {
  return api.get('/stats')
}

export function fetchSources() {
  return api.get('/sources')
}

export function fetchHealth() {
  return api.get('/health')
}

// 昨日日报 HTML（浏览器打开后 Ctrl+P 另存 PDF）
export function getDailyUrl() {
  return '/api/daily/yesterday'
}

export default api
