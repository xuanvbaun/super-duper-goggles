<script setup>
import { ref, onMounted } from 'vue'
import { fetchStats, fetchSources } from '../api.js'

const stats = ref(null)
const sources = ref([])
const loading = ref(true)

onMounted(async () => {
  try {
    const [sRes, srcRes] = await Promise.all([fetchStats(), fetchSources()])
    stats.value = sRes.data
    sources.value = srcRes.data
  } catch (e) {
    console.error('加载统计失败:', e)
  } finally {
    loading.value = false
  }
})

function dayLabel(dateStr) {
  if (!dateStr) return '—'
  const today = new Date().toISOString().slice(0, 10)
  if (dateStr === today) return '今日'
  const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10)
  if (dateStr === yesterday) return '昨日'
  return dateStr.slice(5) // MM-DD
}
</script>

<template>
  <div class="page">
    <div v-if="loading" class="loading">
      <div class="spinner"></div>
    </div>

    <div v-else-if="!stats" class="empty">
      <p>加载失败</p>
    </div>

    <div v-else>
      <!-- ── 今日 vs 昨日对比 ── -->
      <div class="stats-grid" style="margin-bottom:28px">
        <div class="stat-card">
          <div class="stat-value">{{ stats.today?.total || 0 }}</div>
          <div class="stat-label">今日采集</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ stats.yesterday?.total || 0 }}</div>
          <div class="stat-label">昨日采集</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ stats.total_articles }}</div>
          <div class="stat-label">总计文章</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ stats.ai_processed_count }}</div>
          <div class="stat-label">AI 已处理</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ stats.multi_source_articles || 0 }}</div>
          <div class="stat-label">多来源报道</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ stats.official_confirmed_articles || 0 }}</div>
          <div class="stat-label">含官方来源</div>
        </div>
      </div>

      <!-- ── 近 7 天趋势 ── -->
      <section v-if="stats.daily?.length" style="margin-bottom:28px">
        <h3 style="font-family:var(--sans);font-size:10px;text-transform:uppercase;letter-spacing:2px;color:var(--text-muted);margin-bottom:14px;padding-bottom:8px;border-bottom:2px solid var(--accent)">
          近 7 天收录趋势
        </h3>
        <div style="display:flex;flex-direction:column;gap:8px">
          <div
            v-for="day in stats.daily"
            :key="day.date"
            style="display:flex;align-items:center;gap:12px;padding:8px 0;border-bottom:1px dotted var(--border-light)"
          >
            <!-- 日期标签 -->
            <span style="font-family:var(--sans);font-size:12px;font-weight:700;min-width:48px;color:var(--text-muted)">
              {{ dayLabel(day.date) }}
            </span>
            <!-- 进度条 -->
            <div style="flex:1;height:20px;background:var(--paper-white);border:1px solid var(--border-light);position:relative">
              <div
                :style="{
                  width: stats.today?.total ? Math.min(100, (day.total / stats.today.total) * 100) + '%' : '0%',
                  height: '100%',
                  background: 'var(--accent)',
                  opacity: day.date === new Date().toISOString().slice(0,10) ? 1 : 0.5
                }"
              ></div>
            </div>
            <!-- 数字 -->
            <span style="font-family:var(--serif);font-size:16px;font-weight:700;min-width:36px;text-align:right">
              {{ day.total }}
            </span>
            <span style="font-family:var(--sans);font-size:10px;color:var(--text-subtle);min-width:40px;text-align:right">
              {{ day.ai_processed }} 已处理
            </span>
          </div>
        </div>
      </section>

      <!-- ── 核心统计 ── -->
      <div class="stats-grid" style="margin-bottom:28px">
        <div class="stat-card">
          <div class="stat-value">{{ stats.sources_count }}</div>
          <div class="stat-label">活跃 RSS 源</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ stats.latest_fetch?.slice(11, 19) || '—' }}</div>
          <div class="stat-label">最近采集时间</div>
        </div>
      </div>

      <!-- ── 分类分布 ── -->
      <section style="margin-bottom:28px">
        <h3 style="font-family:var(--sans);font-size:10px;text-transform:uppercase;letter-spacing:2px;color:var(--text-muted);margin-bottom:14px;padding-bottom:8px;border-bottom:2px solid var(--accent)">
          分类分布
        </h3>
        <div style="display:flex;flex-wrap:wrap;gap:8px">
          <span
            v-for="(count, cat) in stats.categories"
            :key="cat"
            style="background:var(--paper-white);border:1px solid var(--border);padding:6px 14px;font-family:var(--sans);font-size:12px"
          >
            {{ cat }} <strong style="color:var(--accent);font-family:var(--serif);font-size:15px">{{ count }}</strong>
          </span>
        </div>
      </section>

      <!-- ── RSS 源状态 ── -->
      <section>
        <h3 style="font-family:var(--sans);font-size:10px;text-transform:uppercase;letter-spacing:2px;color:var(--text-muted);margin-bottom:14px;padding-bottom:8px;border-bottom:2px solid var(--accent)">
          RSS 源状态
        </h3>
        <div style="display:flex;flex-direction:column;gap:8px">
          <div
            v-for="s in sources"
            :key="s.name"
            style="display:flex;justify-content:space-between;align-items:center;background:var(--paper-white);border:1px solid var(--border);padding:12px 16px"
          >
            <div>
              <div style="font-family:var(--serif);font-size:14px;font-weight:600">{{ s.name }}</div>
              <div style="font-family:var(--sans);font-size:11px;color:var(--text-muted)">{{ s.category }} · 可信度 {{ s.credibility }}/5</div>
              <div style="font-family:var(--sans);font-size:10px;color:var(--text-subtle)">{{ s.interval_minutes }}分钟/次<span v-if="s.official"> · 官方来源</span></div>
            </div>
            <div style="text-align:right">
              <div v-if="!s.enabled" style="color:var(--text-subtle);font-family:var(--sans);font-size:11px;text-transform:uppercase;letter-spacing:1px">
                <span class="status-dot" style="background:var(--text-subtle)"></span>
                已禁用
              </div>
              <div v-else>
                <div style="font-family:var(--sans);font-size:11px;text-transform:uppercase;letter-spacing:1px">
                  <span :class="['status-dot', s.last_status === 'ok' ? 'status-ok' : s.last_status === 'error' ? 'status-error' : '']"></span>
                  {{ s.last_status === 'ok' ? '正常' : s.last_status === 'error' ? '失败' : '待首次采集' }}
                </div>
                <div style="font-size:10px;color:var(--text-subtle)" v-if="s.last_fetched_at">
                  {{ s.last_fetched_at?.slice(11, 19) }}
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>
