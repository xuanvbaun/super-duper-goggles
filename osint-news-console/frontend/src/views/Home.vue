<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { fetchNews, fetchSources, getDailyUrl } from '../api.js'
import MarketSnapshot from '../components/MarketSnapshot.vue'
import { formatDateTime, formatDelay, formatRelativeTime, formatTime } from '../time.js'

const route = useRoute()
const router = useRouter()
const SCROLL_KEY = 'osint_home_scroll'

const articles = ref([])
const loading = ref(true)
const error = ref('')
const page = ref(1)
const total = ref(0)
const pages = ref(0)
const searchQuery = ref('')
const viewMode = ref('today')
const lastUpdatedAt = ref(null)
const sourceStatus = ref([])
const pendingPayload = ref(null)
const newArticlesCount = ref(0)
let refreshTimer = null

const selectedCategory = ref(route.query.category || '')
const categories = ['全部', '综合', '军事', '政治', '财经', '国际', '社会', '科技', '安全', '法律', '文娱', '其他']

const headline = computed(() => articles.value[0] || null)
const mainArticles = computed(() => articles.value.length > 1 ? articles.value.slice(1) : [])
const enabledSources = computed(() => sourceStatus.value.filter(source => source.enabled))
const sourcePreview = computed(() => enabledSources.value
  .slice()
  .sort((a, b) => statusRank(a.last_status) - statusRank(b.last_status))
  .slice(0, 6))
const sourceSummary = computed(() => ({
  fresh: enabledSources.value.filter(source => source.last_status === 'ok').length,
  issues: enabledSources.value.filter(source => ['stale', 'unknown', 'error'].includes(source.last_status)).length,
  pending: enabledSources.value.filter(source => !source.last_status).length,
}))

function statusRank(status) {
  return { error: 0, stale: 1, unknown: 2, null: 3, ok: 4 }[status] ?? 3
}

function sourceStatusLabel(status) {
  return { ok: '新鲜', stale: '延迟', unknown: '未知', error: '异常' }[status] || '等待'
}

function applyNews(payload) {
  articles.value = payload.items
  total.value = payload.total
  pages.value = payload.pages
  pendingPayload.value = null
  newArticlesCount.value = 0
}

async function loadSourceHealth() {
  try {
    const response = await fetchSources()
    sourceStatus.value = response.data
  } catch (e) {
    console.warn('加载来源状态失败:', e)
  }
}

function setCategory(cat) {
  const value = cat === '全部' ? '' : cat
  selectedCategory.value = value
  page.value = 1
  router.replace({ query: value ? { category: value } : {} })
  loadNews()
}

function switchView(mode) {
  viewMode.value = mode
  page.value = 1
  searchQuery.value = ''
  pendingPayload.value = null
  newArticlesCount.value = 0
  loadNews()
}

async function loadNews(options = {}) {
  const silent = options?.silent === true
  if (!silent) loading.value = true
  if (!silent) error.value = ''
  try {
    const params = { page: page.value, size: 20 }
    if (selectedCategory.value) params.category = selectedCategory.value
    if (searchQuery.value) params.search = searchQuery.value
    if (viewMode.value === 'today') params.date = 'today'
    const response = await fetchNews(params)
    if (silent && articles.value.length) {
      const currentIds = new Set(articles.value.map(article => article.id))
      const unseen = response.data.items.filter(article => !currentIds.has(article.id))
      if (unseen.length) {
        pendingPayload.value = response.data
        newArticlesCount.value = unseen.length
      } else {
        applyNews(response.data)
      }
    } else {
      applyNews(response.data)
    }
    lastUpdatedAt.value = new Date()
  } catch (e) {
    console.error('加载新闻失败:', e)
    if (!silent) error.value = e.message || '网络请求失败，请确认后端已启动'
  } finally {
    loading.value = false
  }
}

function showPendingNews() {
  if (!pendingPayload.value) return
  applyNews(pendingPayload.value)
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

function search() { page.value = 1; loadNews() }
function prevPage() { if (page.value > 1) { page.value--; loadNews() } }
function nextPage() { if (page.value < pages.value) { page.value++; loadNews() } }

function restoreScroll() {
  const saved = sessionStorage.getItem(SCROLL_KEY)
  if (saved) window.scrollTo({ top: parseInt(saved), behavior: 'instant' })
}

function verificationLabel(article) {
  if (article.official_confirmed) return '含官方来源'
  if (article.corroboration_count >= 2) return `${article.corroboration_count} 个来源交叉报道`
  return '单一来源'
}

onMounted(() => {
  if (route.query.category) selectedCategory.value = route.query.category
  loadNews()
  loadSourceHealth()
  refreshTimer = window.setInterval(() => {
    loadNews({ silent: true })
    loadSourceHealth()
  }, 60000)
  setTimeout(restoreScroll, 100)
})

window.addEventListener('popstate', restoreScroll)

onBeforeUnmount(() => {
  sessionStorage.setItem(SCROLL_KEY, String(window.scrollY))
  window.removeEventListener('popstate', restoreScroll)
  if (refreshTimer) window.clearInterval(refreshTimer)
})
</script>

<template>
  <div class="page home-page">
    <div class="home-toolbar">
      <label class="search-box">
        <span aria-hidden="true">⌕</span>
        <input v-model="searchQuery" placeholder="搜索新闻、来源或关键词" @keyup.enter="search" />
        <button type="button" @click="search">搜索</button>
      </label>
      <div class="view-switch" aria-label="新闻时间范围">
        <button :class="{ active: viewMode === 'today' }" @click="switchView('today')">今日新闻</button>
        <button :class="{ active: viewMode === 'all' }" @click="switchView('all')">往期存档</button>
      </div>
    </div>

    <div class="live-status-strip">
      <span><i class="live-dot"></i>自动采集运行中</span>
      <span>新鲜来源 {{ sourceSummary.fresh }}</span>
      <span v-if="!sourceStatus.length">正在读取来源状态</span>
      <router-link v-else-if="sourceSummary.issues" to="/stats" class="status-warning">{{ sourceSummary.issues }} 个来源需注意</router-link>
      <span v-else-if="sourceSummary.pending">{{ sourceSummary.pending }} 个来源等待首次采集</span>
      <router-link v-else to="/stats">来源状态正常</router-link>
      <span v-if="lastUpdatedAt">页面检查 {{ formatTime(lastUpdatedAt) }}</span>
    </div>

    <div class="category-filter" aria-label="新闻分类">
      <button
        v-for="category in categories"
        :key="category"
        :class="{ active: selectedCategory === category || (category === '全部' && !selectedCategory) }"
        @click="setCategory(category)"
      >{{ category }}</button>
    </div>

    <div class="feed-heading">
      <div><p class="eyebrow">Live intelligence feed</p><h1>实时新闻流</h1></div>
      <div class="feed-actions">
        <button class="icon-button" type="button" title="刷新新闻" @click="loadNews">↻</button>
        <a :href="getDailyUrl()" target="_blank" class="outline-button">昨日日报</a>
      </div>
    </div>

    <button v-if="newArticlesCount" class="new-articles-banner" @click="showPendingNews">
      发现 {{ newArticlesCount }} 条新消息，点击更新版面
    </button>

    <MarketSnapshot class="market-snapshot-mobile" />

    <div v-if="loading" class="loading"><div class="spinner"></div><p>新闻正在加载...</p></div>

    <div v-else-if="error" class="empty panel">
      <p class="empty-icon">!</p>
      <strong>新闻加载失败</strong>
      <p>{{ error }}</p>
      <button class="primary-button" @click="loadNews">重新加载</button>
    </div>

    <div v-else-if="!articles.length" class="empty panel">
      <p class="empty-icon">○</p>
      <strong>{{ viewMode === 'today' ? '今日尚无新闻' : '暂无往期新闻' }}</strong>
      <p>{{ viewMode === 'today' ? '采集器正在检查来源，请稍后刷新' : '数据保留 7 天，过期后自动清理' }}</p>
      <button v-if="viewMode === 'today'" class="outline-button" @click="switchView('all')">查看往期存档</button>
    </div>

    <div v-else class="home-content-grid">
      <main class="news-feed-column">
        <router-link v-if="headline" :to="`/news/${headline.id}`" class="news-card headline-card">
          <div class="news-card-accent"></div>
          <div class="card-meta">
            <span class="category-chip">{{ headline.ai_category || headline.source_category }}</span>
            <span>{{ headline.source_name }}</span>
            <span v-if="headline.source_official" class="official-badge">官方来源</span>
            <span :class="headline.verification_status !== 'single_source' ? 'score-high' : ''">{{ verificationLabel(headline) }}</span>
          </div>
          <h2 class="card-title">{{ headline.title }}</h2>
          <p v-if="headline.ai_summary || headline.raw_summary" class="card-summary">{{ headline.ai_summary || headline.raw_summary }}</p>
          <div class="card-footer">
            <div class="card-tags" v-if="headline.ai_tags?.length">
              <span class="tag" v-for="tag in headline.ai_tags.filter(tag => !['Mock', '开发阶段'].includes(tag)).slice(0, 4)" :key="tag">{{ tag }}</span>
            </div>
            <span :title="formatDateTime(headline.published_at)">{{ formatRelativeTime(headline.published_at) }}</span>
            <span>{{ formatDelay(headline.published_at, headline.fetched_at) }}</span>
          </div>
        </router-link>

        <router-link v-for="article in mainArticles" :key="article.id" :to="`/news/${article.id}`" class="news-card">
          <div class="card-meta">
            <span class="category-chip">{{ article.ai_category || article.source_category }}</span>
            <span>{{ article.source_name }}</span>
            <span v-if="article.source_official" class="official-badge">官方来源</span>
            <span :class="article.verification_status !== 'single_source' ? 'score-high' : ''">{{ verificationLabel(article) }}</span>
          </div>
          <h2 class="card-title">{{ article.title }}</h2>
          <p v-if="article.ai_summary || article.raw_summary" class="card-summary">{{ article.ai_summary || article.raw_summary }}</p>
          <div class="card-footer">
            <div class="card-tags" v-if="article.ai_tags?.length">
              <span class="tag" v-for="tag in article.ai_tags.filter(tag => !['Mock', '开发阶段'].includes(tag)).slice(0, 3)" :key="tag">{{ tag }}</span>
            </div>
            <span :title="formatDateTime(article.published_at)">{{ formatRelativeTime(article.published_at) }}</span>
            <span>{{ formatDelay(article.published_at, article.fetched_at) }}</span>
          </div>
        </router-link>

        <div v-if="pages > 1" class="pagination">
          <button @click="prevPage" :disabled="page <= 1">← 前页</button>
          <span>第 {{ page }} 页 · 共 {{ pages }} 页</span>
          <button @click="nextPage" :disabled="page >= pages">后页 →</button>
        </div>
      </main>

      <aside class="home-sidebar">
        <MarketSnapshot />

        <section class="panel side-panel quick-filter-panel">
          <div class="panel-heading-row"><h2>快速筛选</h2><small>{{ total }} 篇</small></div>
          <button v-for="category in ['军事', '政治', '财经', '科技', '安全']" :key="category" @click="setCategory(category)">
            <span>{{ category }}</span><i>›</i>
          </button>
        </section>

        <section class="panel side-panel source-health-panel">
          <div class="panel-heading-row"><h2>来源健康度</h2><router-link to="/stats">查看全部</router-link></div>
          <div v-for="source in sourcePreview" :key="source.name" class="source-health-row">
            <i :class="['status-dot', source.last_status === 'ok' ? 'status-ok' : 'status-error']"></i>
            <span :title="source.name">{{ source.name }}</span>
            <small>{{ sourceStatusLabel(source.last_status) }}</small>
          </div>
          <div class="source-summary-line">正常 {{ sourceSummary.fresh }} · 注意 {{ sourceSummary.issues }}</div>
        </section>
      </aside>
    </div>
  </div>
</template>
